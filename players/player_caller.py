"""
Bot de Exemplo: CallerPlayer — Sempre Check/Call
=================================================

Estratégia: nunca fold, nunca raise. Sempre acompanha a aposta ou dá check.

Útil como baseline: qualquer bot que vença o Caller com frequência está
fazendo alguma coisa certa.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class CallerPlayer(Player):
    """
    HERANÇA: CallerPlayer(Player) — herda toda a estrutura de Player.
    POLIMORFISMO: implementa decision() com a estratégia mais simples possível.
    """

    def decision(self, game_view: GameView) -> int:
        # Sempre check/call — ignora todas as informações do jogo
        return 0


def create_player(name: str = "caller") -> Player:
    return CallerPlayer(name, Hand(), 0)
