"""
versao_16 — gêmeo do versao_15, mas com a política treinada sob o sistema de
recompensa ESPARSO (só vitória/derrota da partida).

Mesma rede/features/forward do v15 — muda só QUAL conjunto de pesos é carregado:
os do run esparso (rl/runs/v16_sparse/), exportados para rl/weights_v16.npz.
v15 e v16 são treinos INDEPENDENTES, do zero, no MESMO pool (v14,v13,v8,v1),
diferindo APENAS no reward (chip/denso × win_loss/esparso). Assim dá pra colocar
os dois na mesma mesa e comparar qual sistema de recompensa produz o bot mais
forte, com todo o resto constante.

Se os pesos do experimento ainda não existirem, cai no fallback do v15.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "player_versao_15", _HERE / "player_versao_15.py")
_v15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v15)

# Pesos do v16 (reward esparso). Caminho ESTÁVEL de deploy, exportado pelo run
# rl/runs/v16_sparse/ via --weights-out. Sobrescrevível por env var.
_EXP_WEIGHTS = Path(os.environ.get(
    "V16_WEIGHTS",
    str(_HERE.parent / "rl" / "weights_v16.npz")))


class Versao16(_v15.Versao15):
    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        # Troca a política do v15 pelos pesos do experimento esparso.
        pol = _v15._NumpyPolicy.load(_EXP_WEIGHTS)
        if pol is not None:
            self._policy = pol


def create_player():
    return Versao16("versao_16", _v15.Hand(), 0)
