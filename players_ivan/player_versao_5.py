"""
versao_5 — bot heads-up estilo pro player com decisões equity-driven.

Em cima da base do versao_2/4 (equity tabular pré-flop + Monte Carlo pós-flop):

Elementos de pro player adicionados:
  - Detecção de draws (flush draw, open-ended straight draw) com cálculo
    de equity por outs (rule of 2 and 4).
  - Semi-bluff proativo com draws fortes (raise / bet com equity de outs).
  - Probe bet / c-bet em posição quando a equity é moderada.
  - Push/fold abaixo de 12 BB pré-flop com range adaptativa por stack.
  - Implied odds: chama draws quando o preço justifica.
  - Range tightening mais leve (0.15 max → 0.08 max). v4 superdobra vs
    apostas grandes; v5 calls de equity vs ranges realistas.
  - Mistura controlada: slow-play 10% com monstros (≥85% equity),
    3-bet light 15% com mãos strong (62-72% equity).
  - Sizing tier-baseado em equity para apostas/raises.

Diferenças vs versao_4:
  - Não totalmente determinístico — mixes controlados de pro player
    (slow-play e 3-bet light) precisam de randomização real.
  - Mais agressão: thresholds de raise menores aproveitam fold equity.
  - Push/fold curto evita ser bleeding pelos blinds.
  - Semi-bluff e probe bet capturam equity que v4 deixava na mesa.
"""
from __future__ import annotations

import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Card, Hand


# ─── Tabela de equity pré-flop (poker_equity_reference.md) ────────────────

PREFLOP_EQUITY: dict[str, float] = {
    "AA": 0.8520, "KK": 0.8240, "QQ": 0.7992, "JJ": 0.7747, "TT": 0.7474,
    "99": 0.7169, "88": 0.6871, "77": 0.6571, "66": 0.6269, "55": 0.5962,
    "44": 0.5627, "33": 0.5292, "22": 0.4992,

    "AKs": 0.6704, "AQs": 0.6613, "AJs": 0.6541, "ATs": 0.6469,
    "A9s": 0.6291, "A8s": 0.6194, "A7s": 0.6091, "A6s": 0.5936,
    "A5s": 0.5949, "A4s": 0.5855, "A3s": 0.5761, "A2s": 0.5661,

    "KQs": 0.6341, "KJs": 0.6261, "KTs": 0.6194, "K9s": 0.6010,
    "K8s": 0.5816, "K7s": 0.5718, "K6s": 0.5620, "K5s": 0.5522,
    "K4s": 0.5423, "K3s": 0.5330, "K2s": 0.5237,

    "QJs": 0.6031, "QTs": 0.5965, "Q9s": 0.5779, "Q8s": 0.5579,
    "Q7s": 0.5378, "Q6s": 0.5291, "Q5s": 0.5191, "Q4s": 0.5097,
    "Q3s": 0.5005, "Q2s": 0.4910,

    "JTs": 0.5751, "J9s": 0.5559, "J8s": 0.5359, "J7s": 0.5155,
    "J6s": 0.4934, "J5s": 0.4845, "J4s": 0.4752, "J3s": 0.4660,
    "J2s": 0.4568,

    "T9s": 0.5383, "T8s": 0.5186, "T7s": 0.4985, "T6s": 0.4784,
    "T5s": 0.4562, "T4s": 0.4474, "T3s": 0.4385, "T2s": 0.4296,

    "98s": 0.5021, "97s": 0.4820, "96s": 0.4616, "95s": 0.4403,
    "94s": 0.4194, "93s": 0.4110, "92s": 0.4018,
    "87s": 0.4651, "86s": 0.4447, "85s": 0.4236, "84s": 0.4030,
    "83s": 0.3834, "82s": 0.3743,
    "76s": 0.4279, "75s": 0.4067, "74s": 0.3865, "73s": 0.3674,
    "72s": 0.3471,
    "65s": 0.3912, "64s": 0.3711, "63s": 0.3510, "62s": 0.3320,
    "54s": 0.3591, "53s": 0.3396, "52s": 0.3216,
    "43s": 0.3092, "42s": 0.2927,
    "32s": 0.2745,

    "AKo": 0.6536, "AQo": 0.6439, "AJo": 0.6360, "ATo": 0.6279,
    "A9o": 0.6086, "A8o": 0.5983, "A7o": 0.5871, "A6o": 0.5706,
    "A5o": 0.5727, "A4o": 0.5627, "A3o": 0.5527, "A2o": 0.5420,

    "KQo": 0.6141, "KJo": 0.6055, "KTo": 0.5984, "K9o": 0.5784,
    "K8o": 0.5574, "K7o": 0.5470, "K6o": 0.5363, "K5o": 0.5258,
    "K4o": 0.5152, "K3o": 0.5051, "K2o": 0.4951,

    "QJo": 0.5805, "QTo": 0.5734, "Q9o": 0.5532, "Q8o": 0.5315,
    "Q7o": 0.5097, "Q6o": 0.5002, "Q5o": 0.4894, "Q4o": 0.4793,
    "Q3o": 0.4693, "Q2o": 0.4591,

    "JTo": 0.5495, "J9o": 0.5286, "J8o": 0.5069, "J7o": 0.4849,
    "J6o": 0.4609, "J5o": 0.4514, "J4o": 0.4415, "J3o": 0.4315,
    "J2o": 0.4216,

    "T9o": 0.5100, "T8o": 0.4883, "T7o": 0.4666, "T6o": 0.4450,
    "T5o": 0.4210, "T4o": 0.4116, "T3o": 0.4020, "T2o": 0.3924,

    "98o": 0.4707, "97o": 0.4489, "96o": 0.4269, "95o": 0.4040,
    "94o": 0.3815, "93o": 0.3724, "92o": 0.3625,
    "87o": 0.4316, "86o": 0.4095, "85o": 0.3866, "84o": 0.3643,
    "83o": 0.3430, "82o": 0.3330,
    "76o": 0.3928, "75o": 0.3699, "74o": 0.3481, "73o": 0.3274,
    "72o": 0.3054,
    "65o": 0.3545, "64o": 0.3327, "63o": 0.3110, "62o": 0.2905,
    "54o": 0.3210, "53o": 0.3000, "52o": 0.2805,
    "43o": 0.2671, "42o": 0.2493,
    "32o": 0.2296,
}


# ─── Avaliador de 7 cartas ────────────────────────────────────────────────

_RANK_INT = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
             "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
_SUIT_INT = {"s": 0, "h": 1, "d": 2, "c": 3}

_FULL_DECK: tuple[tuple[int, int], ...] = tuple(
    (r, s) for r in range(2, 15) for s in range(4)
)


def _card_tuple(card: Card) -> tuple[int, int]:
    return (_RANK_INT[card.value], _SUIT_INT[card.suit])


def _eval7(cards: list[tuple[int, int]]) -> tuple:
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]

    rcount = Counter(ranks)
    scount = Counter(suits)

    flush_suit = None
    for s, n in scount.items():
        if n >= 5:
            flush_suit = s
            break

    unique_ranks = sorted(set(ranks), reverse=True)
    seq_pool = unique_ranks + ([1] if 14 in unique_ranks else [])
    straight_high = 0
    for i in range(len(seq_pool) - 4):
        if seq_pool[i] - seq_pool[i + 4] == 4:
            straight_high = seq_pool[i]
            break

    if flush_suit is not None and straight_high:
        flush_set = {c[0] for c in cards if c[1] == flush_suit}
        flush_seq = sorted(flush_set, reverse=True)
        if 14 in flush_set:
            flush_seq.append(1)
        for i in range(len(flush_seq) - 4):
            if flush_seq[i] - flush_seq[i + 4] == 4:
                return (8, flush_seq[i])

    counts_sorted = sorted(rcount.items(), key=lambda x: (-x[1], -x[0]))
    top_count = counts_sorted[0][1]
    second_count = counts_sorted[1][1] if len(counts_sorted) > 1 else 0

    if top_count == 4:
        quad = counts_sorted[0][0]
        kicker = max(r for r in ranks if r != quad)
        return (7, quad, kicker)

    if top_count == 3 and second_count >= 2:
        return (6, counts_sorted[0][0], counts_sorted[1][0])

    if flush_suit is not None:
        flush_ranks = sorted(
            [c[0] for c in cards if c[1] == flush_suit], reverse=True
        )[:5]
        return (5, *flush_ranks)

    if straight_high:
        return (4, straight_high)

    if top_count == 3:
        trip = counts_sorted[0][0]
        kickers = sorted([r for r in ranks if r != trip], reverse=True)[:2]
        return (3, trip, *kickers)

    if top_count == 2 and second_count == 2:
        p1 = counts_sorted[0][0]
        p2 = counts_sorted[1][0]
        kicker = max(r for r in ranks if r != p1 and r != p2)
        return (2, p1, p2, kicker)

    if top_count == 2:
        pair = counts_sorted[0][0]
        kickers = sorted([r for r in ranks if r != pair], reverse=True)[:3]
        return (1, pair, *kickers)

    return (0, *sorted(ranks, reverse=True)[:5])


def _preflop_key(c_a: Card, c_b: Card) -> str:
    rank_chars = "23456789TJQKA"
    a = "T" if c_a.value == "10" else c_a.value
    b = "T" if c_b.value == "10" else c_b.value
    if rank_chars.index(a) < rank_chars.index(b):
        a, b = b, a
    if a == b:
        return a + b
    suffix = "s" if c_a.suit == c_b.suit else "o"
    return a + b + suffix


# ─── Bot ──────────────────────────────────────────────────────────────────

class Versao5(Player):

    MC_BUDGET_MS = 30.0
    MIN_SAMPLES = 80

    # Push/fold preflop quando stack <= SHORT_STACK_BB
    SHORT_STACK_BB = 12
    PUSH_BASE_THRESHOLD = 0.40   # base do threshold de shove
    PUSH_PER_BB = 0.015          # quanto wider por BB que falta até 12

    # Tiers de bet (to_call == 0)
    BET_NUTS_EQ = 0.78
    BET_VALUE_EQ = 0.62
    BET_THIN_EQ = 0.46
    PROBE_BET_EQ = 0.36          # em posição

    # Tiers de raise (enfrentando aposta)
    RAISE_NUTS_EQ = 0.72
    RAISE_VALUE_EQ = 0.58
    RAISE_NUTS_BUFFER = 0.20
    RAISE_VALUE_BUFFER = 0.18

    # Calls
    CALL_BUFFER = 0.02
    CHEAP_CALL_BB = 3
    CHEAP_CALL_GAP = 0.04

    # Mistura controlada
    SLOWPLAY_EQ = 0.85
    SLOWPLAY_FREQ = 0.10
    LIGHT_3BET_LOW = 0.62
    LIGHT_3BET_HIGH = 0.72
    LIGHT_3BET_FREQ = 0.15

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._rng = random.Random()

    def decision(self, gv: GameView) -> int:
        if len(gv.board) == 0:
            equity = self._preflop_equity(gv.my_hand)
        else:
            equity = self._monte_carlo_equity(gv.my_hand, gv.board)

        # Push/fold pré-flop em stack curto
        stack_bb = gv.my_chips / max(1, gv.big_blind)
        if len(gv.board) == 0 and stack_bb <= self.SHORT_STACK_BB:
            return self._push_fold(gv, equity)

        flush_dr, oesd = (False, False)
        if gv.board:
            flush_dr, oesd = self._detect_draws(gv)

        return self._action(gv, equity, flush_dr, oesd)

    # ─── Equity ──────────────────────────────────────────────────────────

    def _preflop_equity(self, hand: tuple[Card, ...]) -> float:
        return PREFLOP_EQUITY.get(_preflop_key(hand[0], hand[1]), 0.5)

    def _monte_carlo_equity(
        self,
        hand: tuple[Card, ...],
        board: tuple[Card, ...],
    ) -> float:
        my_cards = [_card_tuple(c) for c in hand]
        board_cards = [_card_tuple(c) for c in board]
        used = set(my_cards) | set(board_cards)
        remaining = [c for c in _FULL_DECK if c not in used]
        cards_needed = 2 + (5 - len(board_cards))

        deadline = time.perf_counter() + self.MC_BUDGET_MS / 1000.0
        sample = self._rng.sample
        wins = ties = total = 0

        while True:
            drawn = sample(remaining, cards_needed)
            opp_hand = drawn[:2]
            full_board = board_cards + drawn[2:]

            my_score = _eval7(my_cards + full_board)
            opp_score = _eval7(opp_hand + full_board)

            if my_score > opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            total += 1

            if total >= self.MIN_SAMPLES and time.perf_counter() >= deadline:
                break

        return (wins + ties * 0.5) / total

    # ─── Detecção de draws ────────────────────────────────────────────────

    def _detect_draws(self, gv: GameView) -> tuple[bool, bool]:
        """Retorna (flush_draw, open_ended_straight_draw)."""
        all_cards = list(gv.my_hand) + list(gv.board)

        # Flush draw: 4 do mesmo naipe (e ainda não é flush feito)
        suits = Counter(c.suit for c in all_cards)
        has_flush = any(n >= 5 for n in suits.values())
        flush_dr = (not has_flush) and any(n == 4 for n in suits.values())

        # Open-ended: 4 valores consecutivos. Não detecta se já há straight feito.
        ranks_set = {_RANK_INT[c.value] for c in all_cards}
        if 14 in ranks_set:
            ranks_set = ranks_set | {1}
        sorted_ranks = sorted(ranks_set)

        has_straight = False
        for i in range(len(sorted_ranks) - 4):
            if sorted_ranks[i + 4] - sorted_ranks[i] == 4:
                has_straight = True
                break

        oesd = False
        if not has_straight:
            for i in range(len(sorted_ranks) - 3):
                if sorted_ranks[i + 3] - sorted_ranks[i] == 3:
                    oesd = True
                    break

        return flush_dr, oesd

    # ─── Push/fold pré-flop ───────────────────────────────────────────────

    def _push_fold(self, gv: GameView, equity: float) -> int:
        bb = gv.big_blind
        stack_bb = gv.my_chips / max(1, bb)
        threshold = (
            self.PUSH_BASE_THRESHOLD
            - max(0.0, self.SHORT_STACK_BB - stack_bb) * self.PUSH_PER_BB
        )

        # Defesa contra all-in que cobre nosso stack
        if gv.to_call >= gv.my_chips:
            adj = max(0.0, equity - 0.08)
            pot_odds = gv.to_call / (gv.pot + gv.to_call)
            return 0 if adj >= pot_odds else -1

        if equity >= threshold:
            invested = gv.current_bet - gv.to_call
            return invested + gv.my_chips

        if gv.to_call == 0:
            return 0  # nunca fold no BB sem custo
        return -1

    # ─── Decisão principal ────────────────────────────────────────────────

    def _action(
        self,
        gv: GameView,
        equity: float,
        flush_dr: bool,
        oesd: bool,
    ) -> int:
        bb = gv.big_blind
        pot = gv.pot
        to_call = gv.to_call
        my_chips = gv.my_chips
        in_position = (gv.dealer_position != 0)
        has_draw = flush_dr or oesd
        cards_to_come = 5 - len(gv.board)

        # All-in forçado (oponente cobre nosso stack)
        if to_call >= my_chips:
            adj = max(0.0, equity - 0.08)
            pot_odds = to_call / (pot + to_call)
            return 0 if adj >= pot_odds else -1

        adj = self._adjust_for_range(equity, gv)

        # Sem aposta para igualar
        if to_call == 0:
            # Slow-play ocasional com monstros
            if adj >= self.SLOWPLAY_EQ and self._rng.random() < self.SLOWPLAY_FREQ:
                return 0

            if adj >= self.BET_NUTS_EQ:
                return self._raise_to(gv, self._sizing(gv, 0.80))
            if adj >= self.BET_VALUE_EQ:
                return self._raise_to(gv, self._sizing(gv, 0.60))
            if adj >= self.BET_THIN_EQ:
                return self._raise_to(gv, self._sizing(gv, 0.45))

            # Semi-bluff com draw forte
            if has_draw and cards_to_come > 0:
                return self._raise_to(gv, self._sizing(gv, 0.55))

            # Probe bet em posição
            if in_position and adj >= self.PROBE_BET_EQ:
                return self._raise_to(gv, self._sizing(gv, 0.35))

            return 0

        # Enfrentando aposta
        pot_odds = to_call / (pot + to_call)

        # 3-bet light com mãos strong (mistura controlada)
        if (
            self.LIGHT_3BET_LOW <= adj < self.LIGHT_3BET_HIGH
            and self._rng.random() < self.LIGHT_3BET_FREQ
        ):
            return self._raise_to(gv, self._sizing(gv, 0.55))

        # Value raise
        if (
            adj >= self.RAISE_NUTS_EQ
            and adj >= pot_odds + self.RAISE_NUTS_BUFFER
        ):
            return self._raise_to(gv, self._sizing(gv, 0.80))
        if (
            adj >= self.RAISE_VALUE_EQ
            and adj >= pot_odds + self.RAISE_VALUE_BUFFER
        ):
            return self._raise_to(gv, self._sizing(gv, 0.55))

        # Semi-bluff raise com draw forte e barato
        if (
            has_draw
            and cards_to_come > 0
            and in_position
            and to_call <= 4 * bb
        ):
            return self._raise_to(gv, self._sizing(gv, 0.60))

        # Call por equity
        if adj >= pot_odds + self.CALL_BUFFER:
            return 0

        # Call por draw (implied odds: usa equity de outs)
        if has_draw and cards_to_come > 0:
            if flush_dr and oesd:
                outs = 15
            elif flush_dr:
                outs = 9
            elif oesd:
                outs = 8
            else:
                outs = 4  # gutshot (não detectado, mas fica como fallback)
            draw_eq = outs * (4 if cards_to_come == 2 else 2) / 100
            # Implied odds: aceita pequena lacuna de pot odds para draws
            if draw_eq >= pot_odds - 0.05:
                return 0

        # Call barato (pot odds quase fechando)
        if (
            adj >= pot_odds - self.CHEAP_CALL_GAP
            and to_call <= self.CHEAP_CALL_BB * bb
        ):
            return 0

        return -1

    def _adjust_for_range(
        self,
        equity: float,
        gv: GameView,
        all_in: bool = False,
    ) -> float:
        """
        Tightening mais leve que v4: v4 dobrava demais vs apostas grandes.
        """
        bb = gv.big_blind
        if gv.current_bet <= bb and not all_in:
            return equity

        if all_in:
            tighten = 0.08
        else:
            ratio = gv.current_bet / bb
            if ratio >= 8:
                tighten = 0.08
            elif ratio >= 5:
                tighten = 0.05
            elif ratio >= 3:
                tighten = 0.03
            else:
                tighten = 0.01

        return max(0.0, min(1.0, equity - tighten))

    # ─── Sizing e raise ───────────────────────────────────────────────────

    def _sizing(self, gv: GameView, fraction: float) -> int:
        invested = gv.current_bet - gv.to_call
        bet_amount = max(gv.big_blind, int(gv.pot * fraction))
        return invested + gv.to_call + bet_amount

    def _raise_to(self, gv: GameView, target_total: int) -> int:
        invested = gv.current_bet - gv.to_call
        max_total = invested + gv.my_chips
        return min(target_total, max_total)


def create_player() -> Player:
    return Versao5("versao_5", Hand(), 0)
