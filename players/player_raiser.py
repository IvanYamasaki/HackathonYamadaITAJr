"""
Bot de Exemplo: RaiserPlayer — Sempre Tenta Aumentar
=====================================================

Estratégia: sempre que possível, aumenta a aposta em 1 big blind.
Se não tiver fichas suficientes para aumentar, acompanha a aposta.

Demonstra como usar as informações do GameView para tomar decisões mais
sofisticadas do que simplesmente foldar ou chamar.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class RaiserPlayer(Player):
    """
    Estratégia agressiva: aumenta sempre que as fichas permitem.

    POLIMORFISMO: usa game_view para tomar uma decisão informada,
    ao contrário do CallerPlayer que ignora completamente o estado do jogo.
    """

    def decision(self, game_view: GameView) -> int:
        # Sem aposta atual e com fichas para aumentar: raise de 1 big blind
        if game_view.to_call == 0 and self.chips > game_view.big_blind:
            return game_view.current_bet + game_view.big_blind

        # Com aposta a pagar mas fichas suficientes para raise: aumenta
        if self.chips > game_view.to_call + game_view.big_blind:
            return game_view.current_bet + game_view.big_blind

        # Sem fichas para aumentar: acompanha (ou all-in se necessário)
        return 0


def create_player(name: str = "raiser") -> Player:
    return RaiserPlayer(name, Hand(), 0)
