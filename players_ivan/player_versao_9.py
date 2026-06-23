"""
versao_9 — variante extrema da versao_1.

Estratégia:
  - Se a mão é forte, vai de all-in.
  - Caso contrário, dá fold (ou check, se for grátis).

Definição de "mão forte":
  - Pré-flop: força >= 0.62 (pares altos, AK, AQs, KQs etc. — equivale ao
    tier "premium" usado pela versao_1 para abrir 3x BB).
  - Pós-flop: dois pares ou melhor (RANK_DOIS_PARES+), ou top pair top
    kicker (tier "strong" da versao_1).
"""
from __future__ import annotations

import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Card, Hand
from cards.sequences import (
    BASE_DESEMPATE,
    RANK_DOIS_PARES,
    RANK_UM_PAR,
    score_cinco_cartas,
    valor_carta,
)


_STRONG_PREFLOP_THRESHOLD = 0.62


def _best_score(cards: list[Card]) -> int:
    if len(cards) < 5:
        return 0
    return max(score_cinco_cartas(list(c)) for c in combinations(cards, 5))


def _rank_of(score: int) -> int:
    return score // BASE_DESEMPATE


def _preflop_strength(hand: tuple[Card, ...]) -> float:
    c1, c2 = hand[0], hand[1]
    v1, v2 = valor_carta(c1), valor_carta(c2)
    hi, lo = max(v1, v2), min(v1, v2)
    suited = c1.suit == c2.suit
    pair = v1 == v2
    gap = hi - lo - 1

    if pair:
        return 0.45 + (v1 - 2) * 0.033

    base = 0.28
    base += (hi - 2) * 0.013
    base += (lo - 2) * 0.008
    if suited:
        base += 0.045
    if gap == 0:
        base += 0.030
    elif gap == 1:
        base += 0.015
    elif gap >= 4:
        base -= 0.025
    if hi == 14:
        base += 0.015
    return max(0.20, min(0.78, base))


class Versao9(Player):

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)

    def decision(self, gv: GameView) -> int:
        if self._has_strong_hand(gv):
            return self._shove(gv)
        if gv.to_call == 0:
            return 0
        return -1

    def _has_strong_hand(self, gv: GameView) -> bool:
        if len(gv.board) == 0:
            return _preflop_strength(gv.my_hand) >= _STRONG_PREFLOP_THRESHOLD

        all_cards = list(gv.my_hand) + list(gv.board)
        score = _best_score(all_cards)
        rank = _rank_of(score)

        if rank >= RANK_DOIS_PARES:
            return True
        if rank == RANK_UM_PAR and self._is_top_pair_top_kicker(gv):
            return True
        return False

    def _is_top_pair_top_kicker(self, gv: GameView) -> bool:
        my_vals = [valor_carta(c) for c in gv.my_hand]
        board_vals = [valor_carta(c) for c in gv.board]
        all_vals = my_vals + board_vals
        counts = Counter(all_vals)
        pair_value = max((v for v, n in counts.items() if n >= 2), default=0)
        if pair_value == 0:
            return False

        top_board = max(board_vals) if board_vals else 0

        if my_vals.count(pair_value) == 2:
            return pair_value > top_board

        if pair_value == top_board and pair_value in my_vals:
            kicker = max((v for v in my_vals if v != pair_value), default=0)
            return kicker >= 12
        return False

    def _shove(self, gv: GameView) -> int:
        invested = gv.current_bet - gv.to_call
        return invested + gv.my_chips


def create_player() -> Player:
    return Versao9("versao_9", Hand(), 0)
