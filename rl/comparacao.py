"""
comparacao.py — Compara dois sistemas de recompensa, greedy, vs cada bot.

Mede o win-rate REAL (greedy) de dois conjuntos de pesos contra cada oponente
e gera rl/comparacao.png (barras agrupadas: produção vs experimento) + tabela.

  v15 = rl/weights_v15.npz   (reward "chip", denso)    → run rl/runs/v15_chip/
  v16 = rl/weights_v16.npz   (reward "win_loss", esparso) → run rl/runs/v16_sparse/

Ambos treinados do zero, MESMO pool (v14,v13,v8,v1), diferindo só no reward.

Uso:
    py rl/comparacao.py --games 1000
    py rl/comparacao.py --opps v14,v1,v13,v8 --games 800
    py rl/comparacao.py --exp rl/runs/<outro>/weights.npz
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RL = ROOT / "rl"
sys.path.insert(0, str(RL))
sys.path.insert(0, str(ROOT / "src"))

import avaliar   # reusa eval_vs / OPP / run_chunk

PROD_DEFAULT = RL / "weights_v15.npz"
EXP_DEFAULT = RL / "weights_v16.npz"
OUT = RL / "comparacao.png"


def eval_set(weights_path, opps, games, workers):
    """Avalia um conjunto de pesos vs cada oponente. weights_path=None → produção."""
    if weights_path:
        os.environ["V15_WEIGHTS"] = str(Path(weights_path).resolve())
    else:
        os.environ.pop("V15_WEIGHTS", None)
    out = {}
    for k in opps:
        wr, margin, w, l, dt = avaliar.eval_vs(k, games, workers)
        out[k] = (wr, margin)
        print(f"    vs {k:<4} WR {wr:6.1%} [±{margin:.1%}]")
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--opps", type=str, default="v14,v1,v13,v8,v12,v11")
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--prod", type=str, default=str(PROD_DEFAULT))
    ap.add_argument("--exp", type=str, default=str(EXP_DEFAULT))
    ap.add_argument("--out", type=str, default=str(OUT))
    args = ap.parse_args()

    opps = [k.strip() for k in args.opps.split(",") if k.strip() in avaliar.OPP]

    if not Path(args.exp).exists():
        print(f"[erro] pesos do experimento não existem: {args.exp}\n"
              f"      rode o experimento antes (treinar_sparse.bat).")
        sys.exit(1)

    print(f"PRODUÇÃO (reward chip) = {args.prod}")
    prod = eval_set(None if Path(args.prod) == PROD_DEFAULT else args.prod,
                    opps, args.games, args.workers)
    print(f"EXPERIMENTO (reward win_loss) = {args.exp}")
    exp = eval_set(args.exp, opps, args.games, args.workers)

    # ── Gráfico de barras agrupadas ──────────────────────────────────────
    x = np.arange(len(opps))
    w = 0.38
    pv = [prod[k][0] for k in opps]; pe = [prod[k][1] for k in opps]
    ev = [exp[k][0] for k in opps];  ee = [exp[k][1] for k in opps]

    fig, ax = plt.subplots(figsize=(max(8, 1.6 * len(opps)), 6))
    b1 = ax.bar(x - w/2, pv, w, yerr=pe, capsize=3, label="v15 — reward chip (denso)", color="#1f77b4")
    b2 = ax.bar(x + w/2, ev, w, yerr=ee, capsize=3, label="v16 — reward win_loss (esparso)", color="#ff7f0e")
    ax.axhline(0.5, color="red", ls="--", lw=1, alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels([f"vs {k}" for k in opps])
    ax.set_ylabel("Win-rate (greedy)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylim(0, 1)
    ax.set_title(f"Comparação de sistemas de recompensa — {args.games} partidas/oponente\n"
                 "(barras acima de 50% = vencendo; ambos do zero, mesmo pool v14,v13,v8,v1)",
                 fontsize=11)
    ax.legend()
    for bars, vals in ((b1, pv), (b2, ev)):
        for rect, v in zip(bars, vals):
            ax.text(rect.get_x() + rect.get_width()/2, v + 0.02, f"{v:.0%}",
                    ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out, dpi=110)
    plt.close(fig)

    print("\n=== Resumo (Δ = win_loss − chip) ===")
    treinados = {"v14", "v13", "v8", "v1"}   # pool comum dos dois treinos
    for k in opps:
        d = exp[k][0] - prod[k][0]
        tag = "treinado" if k in treinados else "HELD-OUT"
        print(f"  vs {k:<4} chip {prod[k][0]:5.1%} | win_loss {exp[k][0]:5.1%} | "
              f"Δ {d:+5.1%}  ({tag})")
    print(f"\n[ok] imagem → {args.out}")


if __name__ == "__main__":
    main()
