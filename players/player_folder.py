"""
Bot de Exemplo: FolderPlayer — Sempre Fold
==========================================

Estratégia: desiste de toda mão imediatamente.

Útil para testar que o jogo encerra rapidamente quando só um jogador fica.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class FolderPlayer(Player):
    """
    POLIMORFISMO: mesma interface de Player, comportamento completamente oposto
    ao CallerPlayer — demonstra como polimorfismo permite variação de estratégia.
    """

    def decision(self, game_view: GameView) -> int:
        # Sempre fold — perde os blinds obrigatórios e nada mais
        return -1


def create_player(name: str = "folder") -> Player:
    return FolderPlayer(name, Hand(), 0)
