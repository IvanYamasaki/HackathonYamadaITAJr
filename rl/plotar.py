"""
plotar.py — Gráfico da evolução do treino lendo o ÚNICO arquivo treino.log.

Lê rl/treino.log (que o train.py alimenta a cada update, em qualquer execução)
e gera rl/evolucao.png com vários painéis: win-rate, melhor WR, entropia,
recompensa média e perdas (policy/value). Quebra a linha em buracos do
histórico para não enganar.

Uso:
    py rl/plotar.py
    py rl/plotar.py --x step        # eixo X em passos em vez de update
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RL = Path(__file__).resolve().parent
LOG_TXT = RL / "treino.log"
OUT = RL / "evolucao.png"

# Formato novo: "upd 90 | 7.5min | step 184320 | WR 49.3% (melhor 48.6%, 2400
#   partidas) | r +0.0041 | pi +0.01 v 0.17 ent 1.44 | 230 st/s"
_NEW = re.compile(
    r"upd\s+(\d+)\s+\|\s+[\d.]+min\s+\|\s+step\s+(\d+)\s+\|\s+WR\s+([\d.]+)%\s+"
    r"\(melhor\s+([\d.]+)%[^)]*\)\s+\|\s+r\s+([+-][\d.]+)\s+\|\s+"
    r"(?:pi\s+([+-][\d.]+)\s+v\s+([\d.]+)\s+)?ent\s+([\d.]+)")
# Formato antigo: "upd 83 | step 169984 | WR(últ 500) 48.2% | r +0.0028 |
#   pi +0.046 v 0.174 ent 1.454 | 246 st/s"
_OLD = re.compile(
    r"upd\s+(\d+)\s+\|\s+step\s+(\d+)\s+\|\s+WR\(\S+\s+\d+\)\s+([\d.]+)%\s+\|\s+"
    r"r\s+([+-][\d.]+)\s+\|\s+pi\s+([+-][\d.]+)\s+v\s+([\d.]+)\s+ent\s+([\d.]+)")


def parse_log(path: Path) -> dict:
    keys = ["update", "step", "wr", "best_wr", "reward", "pi_loss", "v_loss", "entropy"]
    d = {k: [] for k in keys}
    best = 0.0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _NEW.search(line)
        if m:
            upd, step, wr, bwr, r, pi, v, ent = m.groups()
            wr = float(wr) / 100.0
            best = max(best, float(bwr) / 100.0, wr)
            d["update"].append(float(upd)); d["step"].append(float(step))
            d["wr"].append(wr); d["best_wr"].append(best)
            d["reward"].append(float(r))
            d["pi_loss"].append(float(pi) if pi is not None else np.nan)
            d["v_loss"].append(float(v) if v is not None else np.nan)
            d["entropy"].append(float(ent))
            continue
        m = _OLD.search(line)
        if m:
            upd, step, wr, r, pi, v, ent = m.groups()
            wr = float(wr) / 100.0
            best = max(best, wr)
            d["update"].append(float(upd)); d["step"].append(float(step))
            d["wr"].append(wr); d["best_wr"].append(best)
            d["reward"].append(float(r))
            d["pi_loss"].append(float(pi)); d["v_loss"].append(float(v))
            d["entropy"].append(float(ent))
    # ordena por update (caso o log tenha trechos fora de ordem)
    if d["update"]:
        order = np.argsort(d["update"], kind="stable")
        for k in keys:
            d[k] = np.array(d[k], dtype=float)[order]
    return d


def break_gaps(x, y, max_gap):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 2:
        return x, y
    nx, ny = [x[0]], [y[0]]
    for i in range(1, len(x)):
        if x[i] - x[i - 1] > max_gap:
            nx.append(np.nan); ny.append(np.nan)
        nx.append(x[i]); ny.append(y[i])
    return np.array(nx), np.array(ny)


def plot_log(log=LOG_TXT, out=OUT, x="update", label=None):
    """Gera o PNG a partir do treino.log. Retorna (ok, mensagem).
    Reutilizável: o train.py chama isto ao encerrar para atualizar o gráfico.
    `label` identifica o run no título (ex.: "v16_sparse (reward=win_loss)").
    Se None, deriva do nome da pasta do log."""
    path = Path(log)
    if label is None:
        parent = path.resolve().parent.name
        label = parent if parent not in ("rl", "") else "principal"
    if not path.exists():
        return False, f"{path} não existe"
    d = parse_log(path)
    n = len(d["update"])
    if n == 0:
        return False, f"nenhuma linha de update reconhecida em {path}"
    xv = d["update"] if x == "update" else d["step"]
    xlabel = "update" if x == "update" else "passos (decisões)"
    gap = 5 if x == "update" else 5 * 50000

    panels = [
        ("wr",      "Win-rate (treino, c/ exploração)", True,  0.5),
        ("best_wr", "Melhor WR (best.pt)",              True,  0.5),
        ("entropy", "Entropia da política",             False, None),
        ("reward",  "Recompensa média / decisão",       False, 0.0),
        ("pi_loss", "Perda da política (PPO)",          False, 0.0),
        ("v_loss",  "Perda do crítico (value)",         False, None),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(13, 9))
    axes = axes.ravel()
    for ax, (key, title, pct, hline) in zip(axes, panels):
        gx, gy = break_gaps(xv, d[key], gap)
        ax.plot(gx, gy, lw=1.3, color="#1f77b4")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.grid(alpha=0.3)
        if pct:
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        if hline is not None:
            ax.axhline(hline, color="red", ls="--", lw=0.9, alpha=0.6)

    fig.suptitle(
        f"Evolução do treino — {label} (PPO)   |   "
        f"update {int(d['update'][-1])}, WR {d['wr'][-1]:.1%}, "
        f"melhor {d['best_wr'][-1]:.1%}, entropia {d['entropy'][-1]:.2f}",
        fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(str(out), dpi=110)
    plt.close(fig)
    return True, f"{n} updates lidos de {path.name} → {out}"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", choices=["update", "step"], default="update")
    ap.add_argument("--log", default=str(LOG_TXT))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--label", default=None, help="rótulo do run no título")
    args = ap.parse_args()

    ok, msg = plot_log(args.log, args.out, args.x, args.label)
    print(("[ok] " if ok else "[erro] ") + msg)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
