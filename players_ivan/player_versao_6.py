"""
versao_6 — versao_1 com duas variáveis comportamentais novas.

Tudo idêntico ao versao_1, exceto:

  1. BLUFF_FOLD_FREQ (default 0.10)
     Em cada situação em que a lógica decidiria FOLD, há uma chance de
     blefar em vez disso — virar a fold em raise pot-sized (ou shove
     quando o stack não permite).

  2. OVERBET_FREQ (default 0.20)
     Em cada situação em que a lógica decidiria RAISE com mão forte
     (premium pré-flop, monster/strong pós-flop), há uma chance de
     aumentar o tamanho do raise em ~60% — overbet para extrair valor
     extra ou aplicar mais pressão.

A defesa contra all-in (`_defend_allin`) não tem hook de blefe porque
nessa situação só existem as ações call/fold — não há como blefar.
"""
from __future__ import annotations

import random
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
    RANK_STRAIGHT,
    RANK_TRINCA,
    RANK_UM_PAR,
    score_cinco_cartas,
    valor_carta,
)


def _best_score(cards: list[Card]) -> int:
    if len(cards) < 5:
        return 0
    return max(score_cinco_cartas(list(c)) for c in combinations(cards, 5))


def _rank_of(score: int) -> int:
    return score // BASE_DESEMPATE


def _has_flush_draw(cards: list[Card]) -> bool:
    counts = Counter(c.suit for c in cards)
    return any(n >= 4 for n in counts.values())


def _has_straight_draw(cards: list[Card]) -> tuple[bool, bool]:
    vals = {valor_carta(c) for c in cards}
    if 14 in vals:
        vals = vals | {1}
    sorted_vals = sorted(vals)

    open_ended = False
    gutshot = False
    for v in sorted_vals:
        run = sum(1 for k in range(4) if (v + k) in vals)
        if run == 4:
            open_ended = True
        present = [k for k in range(5) if (v + k) in vals]
        if len(present) == 4 and 0 in present and 4 in present:
            gutshot = True
    return open_ended, gutshot


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


class Versao6(Player):

    # Novos parâmetros vs versao_1
    BLUFF_FOLD_FREQ = 0.05        # chance de blefar quando lógica diz fold
    OVERBET_FREQ = 0.20           # chance de overbet com mão forte
    OVERBET_MULTIPLIER = 1.6      # quanto maior é o overbet (1.0 = igual ao normal)
    BLUFF_BET_FRACTION = 0.75     # tamanho do blefe quando to_call == 0 (fração pot)
    BLUFF_RAISE_FACTOR = 2.5      # raise múltiplo quando blefando vs aposta

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._rng = random.Random()

    # ─── Decisão principal ────────────────────────────────────────────────

    def decision(self, gv: GameView) -> int:
        if gv.to_call >= gv.my_chips:
            return self._defend_allin(gv)

        stack_bb = gv.my_chips / max(1, gv.big_blind)
        if stack_bb <= 15 and len(gv.board) == 0:
            return self._push_fold_preflop(gv, stack_bb)

        if len(gv.board) == 0:
            return self._preflop(gv)
        return self._postflop(gv)

    # ─── Pré-flop ─────────────────────────────────────────────────────────

    def _preflop(self, gv: GameView) -> int:
        strength = _preflop_strength(gv.my_hand)
        bb = gv.big_blind
        i_am_bb = (gv.dealer_position == 0)

        unopened = gv.current_bet <= bb

        if unopened:
            if strength >= 0.62:
                # Premium open: 3x BB normal, com chance de overbet
                target = self._maybe_overbet(gv, 3 * bb)
                return self._raise_to(gv, target)
            if strength >= 0.50:
                return self._raise_to(gv, int(2.5 * bb))
            if strength >= 0.40:
                return 0
            if i_am_bb:
                return 0
            # SB com lixo: chance de blefar antes de foldar
            if strength <= 0.30:
                return self._fold_or_bluff(gv)
            return 0

        # Enfrentando raise
        raise_size_bb = gv.current_bet / bb
        pot_odds = gv.to_call / (gv.pot + gv.to_call)

        if strength >= 0.72:
            # Premium 3-bet: 3x normal, com chance de overbet
            target = self._maybe_overbet(gv, int(gv.current_bet * 3))
            return self._raise_to(gv, target)
        if strength >= 0.58:
            if self._rng.random() < 0.20:
                return self._raise_to(gv, int(gv.current_bet * 3))
            return 0
        if strength >= 0.45 and raise_size_bb <= 4:
            return 0
        if strength >= 0.40 and pot_odds < 0.18:
            return 0
        return self._fold_or_bluff(gv)

    # ─── Pós-flop ─────────────────────────────────────────────────────────

    def _postflop(self, gv: GameView) -> int:
        all_cards = list(gv.my_hand) + list(gv.board)
        score = _best_score(all_cards)
        rank = _rank_of(score)

        if rank >= RANK_STRAIGHT:
            tier = "monster"
        elif rank in (RANK_TRINCA, RANK_DOIS_PARES):
            tier = "strong"
        elif rank == RANK_UM_PAR:
            tier = self._pair_tier(gv)
        else:
            tier = "weak"

        cards_to_come = 5 - len(gv.board)
        flush_dr = _has_flush_draw(all_cards) if cards_to_come > 0 else False
        oesd, gut = (_has_straight_draw(all_cards) if cards_to_come > 0 else (False, False))
        strong_draw = flush_dr or oesd

        to_call = gv.to_call
        pot = gv.pot

        if tier == "monster":
            target = self._sizing(gv, 0.75)
            if to_call == 0:
                # Monster value bet: chance de overbet
                target = self._maybe_overbet(gv, target)
                return self._raise_to(gv, target)
            if self._rng.random() < 0.15:
                return 0
            # Monster raise vs aposta: chance de overbet
            raise_target = max(target, int(gv.current_bet * 2.5))
            raise_target = self._maybe_overbet(gv, raise_target)
            return self._raise_to(gv, raise_target)

        if tier == "strong":
            target = self._sizing(gv, 0.6)
            if to_call == 0:
                if self._rng.random() < 0.85:
                    # Strong value bet: chance de overbet
                    target = self._maybe_overbet(gv, target)
                    return self._raise_to(gv, target)
                return 0
            if gv.current_bet >= pot * 0.9:
                if self._rng.random() < 0.7:
                    return 0
                return self._fold_or_bluff(gv)
            if self._rng.random() < 0.25:
                # Strong raise vs aposta: chance de overbet
                rt = self._maybe_overbet(gv, int(gv.current_bet * 2.5))
                return self._raise_to(gv, rt)
            return 0

        if tier == "medium":
            if to_call == 0:
                if self._rng.random() < 0.4:
                    return self._raise_to(gv, self._sizing(gv, 0.4))
                return 0
            pot_odds = to_call / (pot + to_call)
            if pot_odds < 0.25 and to_call <= 4 * gv.big_blind:
                return 0
            return self._fold_or_bluff(gv)

        # tier == "weak"
        if strong_draw and cards_to_come > 0:
            outs = 9 if flush_dr else (8 if oesd else 4)
            multiplier = 4 if cards_to_come == 2 else 2
            equity = outs * multiplier / 100
            if to_call == 0:
                if self._rng.random() < 0.5:
                    return self._raise_to(gv, self._sizing(gv, 0.5))
                return 0
            pot_odds = to_call / (pot + to_call)
            if equity > pot_odds:
                return 0
            return self._fold_or_bluff(gv)

        if to_call == 0:
            if self._rng.random() < 0.10:
                return self._raise_to(gv, self._sizing(gv, 0.5))
            return 0
        return self._fold_or_bluff(gv)

    # ─── Novos hooks: blefe e overbet ────────────────────────────────────

    def _fold_or_bluff(self, gv: GameView) -> int:
        """Em situações de fold, sorteia se vira blefe."""
        if self._rng.random() >= self.BLUFF_FOLD_FREQ:
            return -1
        # Bluff: aposta pot-sized se to_call == 0, senão raise grande
        if gv.to_call == 0:
            return self._raise_to(gv, self._sizing(gv, self.BLUFF_BET_FRACTION))
        # Se to_call cobre quase todo o stack, o blefe vira shove
        target = int(gv.current_bet * self.BLUFF_RAISE_FACTOR)
        return self._raise_to(gv, target)

    def _maybe_overbet(self, gv: GameView, normal_target: int) -> int:
        """Com mão forte, sorteia se eleva o tamanho do raise."""
        if self._rng.random() >= self.OVERBET_FREQ:
            return normal_target
        # Escala o "delta" (raise acima da minha contribuição atual)
        invested = gv.current_bet - gv.to_call
        delta = normal_target - invested
        bigger = invested + int(delta * self.OVERBET_MULTIPLIER)
        return bigger

    # ─── Helpers (idênticos ao versao_1) ──────────────────────────────────

    def _pair_tier(self, gv: GameView) -> str:
        my_vals = [valor_carta(c) for c in gv.my_hand]
        board_vals = [valor_carta(c) for c in gv.board]
        all_vals = my_vals + board_vals
        counts = Counter(all_vals)
        pair_value = max((v for v, n in counts.items() if n >= 2), default=0)
        if pair_value == 0:
            return "weak"

        top_board = max(board_vals) if board_vals else 0

        if my_vals.count(pair_value) == 2:
            return "strong" if pair_value > top_board else "medium"

        if pair_value == top_board and pair_value in my_vals:
            kicker = max((v for v in my_vals if v != pair_value), default=0)
            return "strong" if kicker >= 12 else "medium"

        if pair_value >= 10 and pair_value in my_vals:
            return "medium"
        return "weak"

    def _sizing(self, gv: GameView, fraction: float) -> int:
        invested = gv.current_bet - gv.to_call
        bet_amount = max(gv.big_blind, int(gv.pot * fraction))
        return invested + gv.to_call + bet_amount

    def _raise_to(self, gv: GameView, target_total: int) -> int:
        invested = gv.current_bet - gv.to_call
        max_total = invested + gv.my_chips
        target = min(target_total, max_total)
        if target <= gv.current_bet:
            return target
        return target

    def _push_fold_preflop(self, gv: GameView, stack_bb: float) -> int:
        strength = _preflop_strength(gv.my_hand)
        threshold = 0.40 + max(0.0, (15 - stack_bb)) * 0.005
        if strength >= threshold:
            return self._shove(gv)
        if gv.to_call == 0:
            return 0
        pot_odds = gv.to_call / (gv.pot + gv.to_call)
        if strength >= 0.42 and pot_odds <= 0.30:
            return 0
        # Em vez de fold direto: hook de blefe (vira shove)
        return self._fold_or_bluff(gv)

    def _shove(self, gv: GameView) -> int:
        invested = gv.current_bet - gv.to_call
        return invested + gv.my_chips

    def _defend_allin(self, gv: GameView) -> int:
        # Defesa de all-in só permite call/fold — não tem como blefar
        pot_odds = gv.to_call / (gv.pot + gv.to_call)
        if len(gv.board) == 0:
            strength = _preflop_strength(gv.my_hand)
            min_strength = 0.55 - (0.30 - min(pot_odds, 0.30)) * 0.5
            return 0 if strength >= min_strength else -1

        score = _best_score(list(gv.my_hand) + list(gv.board))
        rank = _rank_of(score)
        if rank >= RANK_DOIS_PARES:
            return 0
        if rank == RANK_UM_PAR and pot_odds <= 0.40:
            return 0
        return -1


def create_player() -> Player:
    return Versao6("versao_6", Hand(), 0)
