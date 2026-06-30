"""
train.py — Treino PPO do v15, na CUDA, com retomada à prova de interrupção.

Garantias pedidas:
  * RODA NA GPU: usa CUDA por padrão; aborta com instrução clara se não houver
    (ou rode com --device cpu para forçar CPU).
  * INTERROMPER NÃO ARRUÍNA O PROGRESSO:
      - checkpoint a cada --save-every updates;
      - escrita ATÔMICA (tmp + os.replace) → um kill no meio nunca corrompe;
      - Ctrl+C / SIGTERM capturados: termina o update corrente, salva e sai;
      - retoma sozinho do último checkpoint (modelo, optimizer, contadores e
        estados de RNG de torch/numpy/python) — basta rodar de novo.
  * Exporta weights_v15.npz a cada checkpoint → o player_versao_15 já joga
    com a política mais recente, sem depender de torch.

Uso:
    py rl/train.py                       # começa ou retoma
    py rl/train.py --updates 5000
    py rl/train.py --device cpu          # sem GPU
    py rl/train.py --fresh               # ignora checkpoint e recomeça
"""
from __future__ import annotations

import argparse
import os
import random
import signal
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RL = ROOT / "rl"
sys.path.insert(0, str(RL))

try:
    import torch
    import torch.nn as nn
except ImportError:
    print(
        "\n[ERRO] PyTorch não está instalado.\n"
        "Para treinar na CUDA da sua RTX 3050, instale a build com CUDA:\n\n"
        "    py -m pip install torch --index-url https://download.pytorch.org/whl/cu121\n\n"
        "(ou veja https://pytorch.org/get-started/locally/). Depois rode de novo.\n"
    )
    sys.exit(1)

from env import VecEnv, FEATURE_DIM, N_ACTIONS                     # noqa: E402
from model import ActorCritic                                      # noqa: E402

CKPT_DIR = RL / "checkpoints"
LATEST = CKPT_DIR / "latest.pt"
BEST = CKPT_DIR / "best.pt"
WEIGHTS_NPZ = RL / "weights_v15.npz"
LOG_TXT = RL / "treino.log"            # ÚNICO log: o plotter lê este arquivo.


class _Tee:
    """Duplica o stdout para o terminal E para o treino.log (append).
    Assim existe sempre UM só arquivo de log, rodando em foreground ou
    background, e que cresce entre retomadas."""

    def __init__(self, path):
        self._term = sys.stdout
        self._f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, s):
        self._term.write(s)
        self._f.write(s)

    def flush(self):
        self._term.flush()
        self._f.flush()

# Oponentes disponíveis (chave → arquivo). Escolha o pool com --opps.
OPP_MAP = {
    "v14": str(ROOT / "players" / "player_versao_14.py"),
    "v13": str(ROOT / "players" / "player_versao_13.py"),
    "v12": str(ROOT / "players" / "player_versao_12.py"),
    "v11": str(ROOT / "players" / "player_versao_11.py"),
    "v8":  str(ROOT / "players" / "player_versao_8.py"),
    "v1":  str(ROOT / "players" / "player_no_name.py"),
}
DEFAULT_OPPS = "v14,v13,v8,v1"

# Mapeia o nome do sistema de recompensa → (dense_scale, win, loss).
#   chip      = denso (Δfichas) + terminal ±1   (sistema original)
#   win_loss  = SÓ vitória/derrota da partida (esparso)
REWARD_MODES = {
    "chip":     (1.0, 1.0, -1.0),
    "win_loss": (0.0, 1.0, -1.0),
}

# Caminho do PNG de evolução (ajustado por run em main()).
PNG_OUT = RL / "evolucao.png"


# ─── Checkpoint atômico ───────────────────────────────────────────────────

def atomic_save(obj, path: Path) -> None:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)            # rename atômico no mesmo volume


def export_weights(model: ActorCritic) -> None:
    # np.savez força sufixo .npz no nome → escrevemos via handle p/ controlar
    # o caminho exato do arquivo temporário e fazer replace atômico.
    tmp = WEIGHTS_NPZ.with_name(WEIGHTS_NPZ.name + ".tmp")
    with open(tmp, "wb") as f:
        np.savez(f, **model.export_numpy())
    os.replace(tmp, WEIGHTS_NPZ)


def save_checkpoint(path, model, opt, cfg, update, gstep, best_wr):
    atomic_save({
        "model": model.state_dict(),
        "opt": opt.state_dict(),
        "cfg": cfg,
        "update": update,
        "global_step": gstep,
        "best_wr": best_wr,
        "rng_torch": torch.get_rng_state(),
        "rng_cuda": (torch.cuda.get_rng_state_all()
                     if torch.cuda.is_available() else None),
        "rng_numpy": np.random.get_state(),
        "rng_python": random.getstate(),
    }, path)


# ─── GAE ──────────────────────────────────────────────────────────────────

def compute_gae(rewards, values, dones, last_values, gamma, lam):
    T, N = rewards.shape
    adv = np.zeros((T, N), dtype=np.float32)
    lastgae = np.zeros(N, dtype=np.float32)
    for t in reversed(range(T)):
        nonterminal = 1.0 - dones[t]
        nextval = last_values if t == T - 1 else values[t + 1]
        delta = rewards[t] + gamma * nextval * nonterminal - values[t]
        lastgae = delta + gamma * lam * nonterminal * lastgae
        adv[t] = lastgae
    returns = adv + values
    return adv, returns


# ─── Treino ────────────────────────────────────────────────────────────────

def main():
    try:                       # console Windows (cp1252) não encoda → etc.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--updates", type=int, default=100000)
    ap.add_argument("--num-envs", type=int, default=16)
    ap.add_argument("--horizon", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--minibatches", type=int, default=4)
    ap.add_argument("--gamma", type=float, default=0.999)
    ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--ent-coef", type=float, default=0.01)
    ap.add_argument("--vf-coef", type=float, default=0.5)
    ap.add_argument("--max-grad-norm", type=float, default=0.5)
    ap.add_argument("--hidden", type=str, default="128,128")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--save-every", type=int, default=20)
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--fresh", action="store_true")
    # ── Experimentos: pasta isolada, recompensa, pool e warm-start ──
    ap.add_argument("--run-name", type=str, default="",
                    help="nome do experimento → rl/runs/<nome>/ (isola ckpt/log/pesos)")
    ap.add_argument("--reward", type=str, default="chip",
                    choices=list(REWARD_MODES),
                    help="sistema de recompensa: chip (denso) ou win_loss (esparso)")
    ap.add_argument("--opps", type=str, default=DEFAULT_OPPS,
                    help="pool de oponentes, ex.: v14,v1")
    ap.add_argument("--warm-start", type=str, default="",
                    help="checkpoint p/ iniciar os PESOS (fine-tune sob nova recompensa)")
    ap.add_argument("--weights-out", type=str, default="",
                    help="caminho ESTÁVEL do .npz de deploy (ex.: rl/weights_v16.npz). "
                         "Desacopla os pesos do torneio da pasta do run.")
    # ── Comparação automática ao encerrar (igual ao gráfico de evolução) ──
    ap.add_argument("--compare-on-exit", action="store_true",
                    help="ao parar, roda comparacao.py (v15 produção × este run)")
    ap.add_argument("--compare-opps", type=str, default="v14,v1,v13,v8",
                    help="oponentes da comparação automática")
    ap.add_argument("--compare-games", type=int, default=500,
                    help="partidas/oponente na comparação automática")
    args = ap.parse_args()

    # ── Paths por experimento (não mexe no run principal se --run-name vazio) ─
    global CKPT_DIR, LATEST, BEST, WEIGHTS_NPZ, LOG_TXT, PNG_OUT
    if args.run_name:
        rundir = RL / "runs" / args.run_name
        (rundir / "checkpoints").mkdir(parents=True, exist_ok=True)
        CKPT_DIR = rundir / "checkpoints"
        LATEST = CKPT_DIR / "latest.pt"
        BEST = CKPT_DIR / "best.pt"
        WEIGHTS_NPZ = rundir / "weights.npz"
        LOG_TXT = rundir / "treino.log"
        PNG_OUT = rundir / "evolucao.png"
    # Caminho ESTÁVEL de deploy (sobrescreve o destino do .npz exportado).
    # Mantém o run isolado em runs/<nome>/ mas os pesos do torneio num lugar fixo.
    if args.weights_out:
        WEIGHTS_NPZ = Path(args.weights_out)
    sys.stdout = _Tee(LOG_TXT)   # tudo que for printado vai também pro log do run
    print(f"[run] {args.run_name or 'principal'} | reward={args.reward} | "
          f"opps={args.opps} | dir={LOG_TXT.parent}")

    # ── Recompensa e pool ────────────────────────────────────────────────
    dense_scale, r_win, r_loss = REWARD_MODES[args.reward]
    opp_keys = [k.strip() for k in args.opps.split(",") if k.strip()]
    bad = [k for k in opp_keys if k not in OPP_MAP]
    if bad:
        print(f"[ERRO] oponentes desconhecidos: {bad}. Opções: {list(OPP_MAP)}")
        sys.exit(1)
    opp_pool = [OPP_MAP[k] for k in opp_keys]

    # ── Device / CUDA ────────────────────────────────────────────────────
    if args.device == "cuda" and not torch.cuda.is_available():
        print(
            "\n[ERRO] CUDA não disponível para o PyTorch instalado.\n"
            "Provavelmente você tem a build CPU. Para usar a RTX 3050:\n\n"
            "    py -m pip uninstall -y torch\n"
            "    py -m pip install torch --index-url https://download.pytorch.org/whl/cu121\n\n"
            "Ou rode na CPU: py rl/train.py --device cpu\n"
        )
        sys.exit(1)
    device = torch.device(args.device)
    if device.type == "cuda":
        print(f"[device] CUDA: {torch.cuda.get_device_name(0)}")
    else:
        print("[device] CPU")

    hidden = tuple(int(x) for x in args.hidden.split(","))
    cfg = {"feat_dim": FEATURE_DIM, "n_actions": N_ACTIONS, "hidden": hidden,
           "reward": args.reward, "opps": args.opps}

    model = ActorCritic(FEATURE_DIM, N_ACTIONS, hidden).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, eps=1e-5)

    start_update = 0
    global_step = 0
    best_wr = -1.0

    # ── Retomada ─────────────────────────────────────────────────────────
    if LATEST.exists() and not args.fresh:
        print(f"[resume] carregando {LATEST}")
        ck = torch.load(LATEST, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        start_update = ck["update"]
        global_step = ck["global_step"]
        best_wr = ck.get("best_wr", -1.0)
        try:
            torch.set_rng_state(ck["rng_torch"].cpu())
            if ck.get("rng_cuda") is not None and torch.cuda.is_available():
                torch.cuda.set_rng_state_all([s.cpu() for s in ck["rng_cuda"]])
            np.random.set_state(ck["rng_numpy"])
            random.setstate(ck["rng_python"])
        except Exception as e:
            print(f"[resume] aviso ao restaurar RNG: {e}")
        print(f"[resume] retomando do update {start_update} (step {global_step})")
    else:
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        if args.warm_start:
            # Fine-tune: pega só os PESOS de outro checkpoint (optimizer e
            # contadores começam zerados, pois a recompensa mudou).
            wpath = Path(args.warm_start)
            ck = torch.load(wpath, map_location=device, weights_only=False)
            model.load_state_dict(ck["model"])
            print(f"[warm-start] pesos carregados de {wpath} "
                  f"(update orig {ck.get('update')}) — optimizer/contadores zerados")
        else:
            print("[init] treino novo (pesos aleatórios)")

    # ── Parada limpa ─────────────────────────────────────────────────────
    stop = {"flag": False}

    def _handler(signum, frame):
        if stop["flag"]:
            print("\n[stop] segunda interrupção — abortando sem salvar.")
            sys.exit(1)
        stop["flag"] = True
        print("\n[stop] interrupção recebida — terminando o update e salvando…")

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, AttributeError):
        pass

    # ── Env ──────────────────────────────────────────────────────────────
    N = args.num_envs
    T = args.horizon
    env = VecEnv(N, opp_pool, seed=args.seed + start_update,
                 dense_scale=dense_scale, reward_win=r_win, reward_loss=r_loss)
    obs, mask = env.reset()

    win_hist = []         # janela de resultados de partidas (1/0)
    t_start = time.perf_counter()
    step_start = global_step   # p/ st/s honesto após resume

    def to_t(x, dtype=torch.float32):
        return torch.as_tensor(x, dtype=dtype, device=device)

    try:
        for update in range(start_update, args.updates):
            # Buffers do rollout.
            b_obs = np.zeros((T, N, FEATURE_DIM), dtype=np.float32)
            b_mask = np.zeros((T, N, N_ACTIONS), dtype=bool)
            b_act = np.zeros((T, N), dtype=np.int64)
            b_logp = np.zeros((T, N), dtype=np.float32)
            b_val = np.zeros((T, N), dtype=np.float32)
            b_rew = np.zeros((T, N), dtype=np.float32)
            b_done = np.zeros((T, N), dtype=np.float32)

            # ── Coleta ───────────────────────────────────────────────────
            for t in range(T):
                ot = to_t(obs)
                mt = to_t(mask, dtype=torch.bool)
                a, logp, val = model.act(ot, mt)
                a_np = a.cpu().numpy()

                nobs, nmask, rew, done, wins = env.step(a_np)

                b_obs[t] = obs
                b_mask[t] = mask
                b_act[t] = a_np
                b_logp[t] = logp.cpu().numpy()
                b_val[t] = val.cpu().numpy()
                b_rew[t] = rew
                b_done[t] = done

                for w in wins:
                    if w >= 0.0:
                        win_hist.append(w)
                obs, mask = nobs, nmask
            global_step += T * N

            # ── Vantagens (GAE) ──────────────────────────────────────────
            with torch.no_grad():
                _, last_val = model.forward(to_t(obs))
                last_val = last_val.cpu().numpy()
            adv, ret = compute_gae(b_rew, b_val, b_done, last_val,
                                   args.gamma, args.lam)

            # Flatten.
            f_obs = to_t(b_obs.reshape(-1, FEATURE_DIM))
            f_mask = to_t(b_mask.reshape(-1, N_ACTIONS), dtype=torch.bool)
            f_act = to_t(b_act.reshape(-1), dtype=torch.int64)
            f_logp = to_t(b_logp.reshape(-1))
            f_adv = to_t(adv.reshape(-1))
            f_ret = to_t(ret.reshape(-1))
            f_adv = (f_adv - f_adv.mean()) / (f_adv.std() + 1e-8)

            # ── Update PPO ───────────────────────────────────────────────
            B = T * N
            mb = B // args.minibatches
            idx = np.arange(B)
            last_stats = {}
            for _ in range(args.epochs):
                np.random.shuffle(idx)
                for s in range(0, B, mb):
                    j = idx[s:s + mb]
                    jt = torch.as_tensor(j, device=device)
                    new_logp, ent, val = model.evaluate(
                        f_obs[jt], f_mask[jt], f_act[jt])
                    ratio = torch.exp(new_logp - f_logp[jt])
                    a_mb = f_adv[jt]
                    l1 = ratio * a_mb
                    l2 = torch.clamp(ratio, 1 - args.clip, 1 + args.clip) * a_mb
                    pi_loss = -torch.min(l1, l2).mean()
                    v_loss = 0.5 * (val - f_ret[jt]).pow(2).mean()
                    ent_loss = ent.mean()
                    loss = pi_loss + args.vf_coef * v_loss - args.ent_coef * ent_loss

                    opt.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
                    opt.step()
                    last_stats = {"pi": pi_loss.item(), "v": v_loss.item(),
                                  "ent": ent_loss.item()}

            # ── Log ──────────────────────────────────────────────────────
            recent = win_hist[-500:]
            wr = (sum(recent) / len(recent)) if recent else float("nan")
            elapsed = time.perf_counter() - t_start
            sps = (global_step - step_start) / max(1e-6, elapsed)
            mins = elapsed / 60.0
            games = len(win_hist)
            print(f"upd {update+1:>6} | {mins:5.1f}min | step {global_step:>9} | "
                  f"WR {wr:5.1%} (melhor {max(best_wr,0):4.1%}, {games} partidas) | "
                  f"r {b_rew.mean():+.4f} | pi {last_stats.get('pi',0):+.4f} "
                  f"v {last_stats.get('v',0):.4f} ent {last_stats.get('ent',0):.3f} "
                  f"| {sps:,.0f} st/s", flush=True)

            # ── Checkpoint ───────────────────────────────────────────────
            need_save = ((update + 1) % args.save_every == 0) or stop["flag"]
            if recent and len(recent) >= 100 and wr > best_wr:
                best_wr = wr
                save_checkpoint(BEST, model, opt, cfg, update + 1,
                                global_step, best_wr)
            if need_save:
                save_checkpoint(LATEST, model, opt, cfg, update + 1,
                                global_step, best_wr)
                export_weights(model)
                print(f"  [ckpt] salvo update {update+1} "
                      f"(best WR {best_wr:.1%}) → {LATEST.name}, {WEIGHTS_NPZ.name}",
                      flush=True)

            if stop["flag"]:
                break

    finally:
        # Salva sempre ao sair (inclusive em exceção), de forma atômica.
        save_checkpoint(LATEST, model, opt, cfg,
                        update + 1 if 'update' in dir() else start_update,
                        global_step, best_wr)
        export_weights(model)
        env.close()
        print(f"[exit] checkpoint final salvo em {LATEST}")
        # Atualiza o gráfico de evolução ao encerrar (cancelar/fim/erro).
        try:
            sys.stdout.flush()                 # garante o treino.log no disco
            from plotar import plot_log
            label = f"{args.run_name or 'principal'} (reward={args.reward})"
            ok, msg = plot_log(log=LOG_TXT, out=PNG_OUT, label=label)
            print(f"[plot] {'evolucao.png atualizado — ' + msg if ok else 'falha: ' + msg}")
        except Exception as e:
            print(f"[plot] não foi possível atualizar o gráfico: {e!r}")

        # Comparação automática v15(produção) × este run, ao encerrar.
        if getattr(args, "compare_on_exit", False):
            try:
                import subprocess
                out_png = LOG_TXT.parent / "comparacao.png"
                print(f"[compare] rodando comparação ({args.compare_games} "
                      f"partidas/oponente, opps={args.compare_opps})…", flush=True)
                subprocess.run(
                    [sys.executable, str(RL / "comparacao.py"),
                     "--exp", str(WEIGHTS_NPZ),
                     "--opps", args.compare_opps,
                     "--games", str(args.compare_games),
                     "--out", str(out_png)],
                    check=False)
                print(f"[compare] imagem → {out_png}", flush=True)
            except Exception as e:
                print(f"[compare] não foi possível comparar: {e!r}")


if __name__ == "__main__":
    main()
