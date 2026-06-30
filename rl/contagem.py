"""contagem.py — partidas vencidas/perdidas (não só win-rate) de v15 e v16."""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rl"))
sys.path.insert(0, str(ROOT / "src"))
import avaliar

RL = ROOT / "rl"
GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 500
OPPS = ["v14", "v13", "v8", "v1"]


def run_set(weights, opps, games, workers=10):
    if weights:
        os.environ["V15_WEIGHTS"] = str(Path(weights).resolve())
    else:
        os.environ.pop("V15_WEIGHTS", None)
    res = {}
    for k in opps:
        wr, margin, w, l, dt = avaliar.eval_vs(k, games, workers)
        res[k] = (w, l, wr, margin)
    return res


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"GAMES por oponente = {GAMES}\n")
    v15 = run_set(None, OPPS, GAMES)
    v16 = run_set(str(RL / "weights_v16.npz"), OPPS, GAMES)

    print(f"{'opp':<5}|{'v15 venceu':>20} |{'v16 venceu':>20}")
    print("-" * 50)
    for k in OPPS:
        w5, l5, wr5, m5 = v15[k]
        w6, l6, wr6, m6 = v16[k]
        d5 = GAMES - (w5 + l5)
        d6 = GAMES - (w6 + l6)
        print(f"{k:<5}| {w5:3d}/{GAMES} (perdeu {l5}, empate {d5}) | "
              f"{w6:3d}/{GAMES} (perdeu {l6}, empate {d6})")
    print()
    # totais somando os 4 oponentes
    tw5 = sum(v15[k][0] for k in OPPS); tl5 = sum(v15[k][1] for k in OPPS)
    tw6 = sum(v16[k][0] for k in OPPS); tl6 = sum(v16[k][1] for k in OPPS)
    tot = GAMES * len(OPPS)
    print(f"TOTAL (4 oponentes, {tot} partidas):")
    print(f"  v15: {tw5}/{tot} vencidas  ({tw5/tot:.1%})")
    print(f"  v16: {tw6}/{tot} vencidas  ({tw6/tot:.1%})")


if __name__ == "__main__":
    main()
