"""
avaliar.py — Mede a força REAL do versao_15 (greedy, como joga no torneio).

Joga N partidas do versao_15 (usando os pesos atuais de weights_v15.npz, em
modo argmax — sem exploração) contra um oponente, alternando posição, e
reporta o win-rate com intervalo de confiança de 95%.

Diferente da WR do treino (que explora), isto é exatamente como o bot joga
de verdade. Rode enquanto treina (ou depois) para saber se já está bom.

Uso:
    py rl/avaliar.py                       # vs v14, 1000 partidas
    py rl/avaliar.py --opp v13 --games 2000
    py rl/avaliar.py --opp all --games 600 # contra cada bot do pool
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

V15 = str(ROOT / "players" / "player_versao_15.py")
OPP = {
    "v14": str(ROOT / "players" / "player_versao_14.py"),
    "v13": str(ROOT / "players" / "player_versao_13.py"),
    "v12": str(ROOT / "players" / "player_versao_12.py"),
    "v11": str(ROOT / "players" / "player_versao_11.py"),
    "v8":  str(ROOT / "players" / "player_versao_8.py"),
    "v1":  str(ROOT / "players" / "player_no_name.py"),
}


def _load(p):
    spec = importlib.util.spec_from_file_location(Path(p).stem.replace(" ", "_"), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_chunk(args):
    opp_path, n_games, start_idx, seed = args
    import random
    random.seed(seed)
    from game.game import Game

    fa = _load(V15).create_player
    fb = _load(opp_path).create_player
    name_a = fa().name
    wins = losses = 0
    for g in range(start_idx, start_idx + n_games):
        players = [fa(), fb()] if g % 2 == 0 else [fb(), fa()]
        game = Game(players)
        game.verbose = False
        game.decision_timeout_s = None
        winner = game.play_game()
        if winner is None:
            continue
        if winner.name == name_a:
            wins += 1
        else:
            losses += 1
    return wins, losses


def eval_vs(opp_key, games, workers):
    opp_path = OPP[opp_key]
    chunk = max(1, games // workers)
    tasks, idx = [], 0
    s0 = int(time.time() * 1000) % 999983
    while idx < games:
        sz = min(chunk, games - idx)
        tasks.append((opp_path, sz, idx, s0 + idx * 7919))
        idx += sz
    t0 = time.perf_counter()
    wins = losses = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for w, l in pool.map(run_chunk, tasks):
            wins += w
            losses += l
    n = wins + losses or 1
    wr = wins / n
    margin = 1.96 * math.sqrt(wr * (1 - wr) / n)
    dt = time.perf_counter() - t0
    return wr, margin, wins, losses, dt


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--opp", type=str, default="v14")
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--weights", type=str, default=None,
                    help="caminho p/ pesos alternativos (ex.: rl/runs/<exp>/weights.npz)")
    args = ap.parse_args()

    # Define os pesos ANTES de criar o pool → herdado pelos workers (spawn).
    if args.weights:
        os.environ["V15_WEIGHTS"] = str(Path(args.weights).resolve())
        print(f"[pesos] avaliando com {os.environ['V15_WEIGHTS']}")

    weights_now = Path(os.environ.get("V15_WEIGHTS",
                       str(ROOT / "rl" / "weights_v15.npz")))
    if not weights_now.exists():
        print(f"[aviso] {weights_now} não existe — o v15 jogará com o "
              "fallback heurístico (fraco).")

    keys = list(OPP) if args.opp == "all" else [args.opp]
    print(f"versao_15 (greedy) — {args.games} partidas por oponente\n")
    for k in keys:
        wr, margin, w, l, dt = eval_vs(k, args.games, args.workers)
        verdict = "VENCENDO" if wr - margin > 0.5 else ("perdendo" if wr + margin < 0.5 else "empate ~50%")
        print(f"  vs {k:<4}  {w}-{l:<5}  WR {wr:6.1%} [±{margin:.1%}]  → {verdict}  ({dt:.0f}s)")


if __name__ == "__main__":
    main()
