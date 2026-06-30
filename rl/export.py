"""
export.py — Converte um checkpoint do PyTorch em weights_v15.npz (numpy puro).

O treino já exporta a cada checkpoint, mas isto serve para gerar os pesos a
partir de um checkpoint específico (ex.: best.pt) sob demanda.

Uso:
    py rl/export.py                 # usa checkpoints/latest.pt
    py rl/export.py --ckpt checkpoints/best.pt
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
RL = ROOT / "rl"
sys.path.insert(0, str(RL))

from model import ActorCritic                                      # noqa: E402

WEIGHTS_NPZ = RL / "weights_v15.npz"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", type=str,
                    default=str(RL / "runs" / "v15_chip" / "checkpoints" / "latest.pt"))
    ap.add_argument("--out", type=str, default=str(WEIGHTS_NPZ))
    args = ap.parse_args()

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    cfg = ck["cfg"]
    model = ActorCritic(cfg["feat_dim"], cfg["n_actions"], cfg["hidden"])
    model.load_state_dict(ck["model"])
    model.eval()

    out = Path(args.out)
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "wb") as f:
        np.savez(f, **model.export_numpy())
    os.replace(tmp, out)
    print(f"[export] {args.ckpt} (update {ck.get('update')}, "
          f"best WR {ck.get('best_wr', float('nan')):.1%}) → {out}")


if __name__ == "__main__":
    main()
