"""
versao_4 — bot heads-up 100% determinístico, decisão pura por equity vs pot odds.

Diferenças em relação ao versao_2:
  - Zero `random.random()` para escolher entre ações: nenhuma slow-play
    aleatória, nenhum blefe, nenhuma 3-bet "light" probabilística.
  - Monte Carlo pós-flop usa RNG seedado pelo estado do jogo (mão + board
    + pot + apostas + stacks). Mesmo estado → mesmas amostras → mesma
    equity → mesma decisão. Reprodutibilidade total.
  - Tabela de tiers determinística para sizing: equity → fração do pote.

Regra de decisão:
  1. Calcula equity (lookup pré-flop, MC pós-flop).
  2. Ajusta para range provável do oponente (tighten conforme aposta dele).
  3. Compara equity ajustada com pot odds:
       - equity ≥ threshold_value → raise/bet com tamanho proporcional.
       - equity ≥ pot_odds + buffer → call.
       - equity < pot_odds → fold (exceto BB grátis).
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


# ─── Tabela de equity vs mão aleatória (poker_equity_reference.md) ────────

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

class Versao4(Player):

    MC_BUDGET_MS = 30.0
    MIN_SAMPLES = 80   # mais alto que versao_2 (a determinismo precisa de baixa variância)

    # Limiares determinísticos para sizing quando livre (to_call == 0)
    BET_NUTS_EQUITY = 0.80   # → aposta 80% pot
    BET_VALUE_EQUITY = 0.65  # → aposta 60% pot
    BET_THIN_EQUITY = 0.52   # → aposta 40% pot (value thin)
    # Abaixo de BET_THIN_EQUITY → check (sem blefe)

    # Limiares para raise quando enfrentando aposta
    RAISE_NUTS_EQUITY = 0.75       # equity absoluta para raise grande
    RAISE_VALUE_EQUITY = 0.62      # equity absoluta para raise médio
    RAISE_NUTS_BUFFER = 0.25       # margem mínima sobre pot odds
    RAISE_VALUE_BUFFER = 0.20

    # Limiar para call simples (equity > pot_odds + CALL_BUFFER)
    CALL_BUFFER = 0.02
    # Call "implied odds" quando preço é muito barato
    CHEAP_CALL_BB = 3              # to_call <= N * bb
    CHEAP_CALL_GAP = 0.03          # tolera equity até pot_odds - GAP

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._rng = random.Random()

    def decision(self, gv: GameView) -> int:
        # Seed determinístico a partir do estado público completo
        self._rng.seed(self._state_seed(gv))

        if len(gv.board) == 0:
            equity = self._preflop_equity(gv.my_hand)
        else:
            equity = self._monte_carlo_equity(gv.my_hand, gv.board)

        return self._action_from_equity(gv, equity)

    # ─── Seed determinístico ─────────────────────────────────────────────

    def _state_seed(self, gv: GameView) -> int:
        """
        Estado de jogo → seed. Mesmo estado produz mesma sequência de amostras
        e portanto mesma equity estimada e mesma decisão.
        """
        parts: list = []
        for c in gv.my_hand:
            parts.append(c.value)
            parts.append(c.suit)
        for c in gv.board:
            parts.append(c.value)
            parts.append(c.suit)
        parts.extend((gv.pot, gv.current_bet, gv.to_call,
                      gv.my_chips, gv.dealer_position,
                      gv.small_blind, gv.big_blind))
        for op in gv.opponents:
            parts.append(op.chips)
            parts.append(op.current_bet_in_round)
            parts.append(op.is_active)
        return hash(tuple(parts))

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

    # ─── Decisão determinística ───────────────────────────────────────────

    def _action_from_equity(self, gv: GameView, equity: float) -> int:
        bb = gv.big_blind
        pot = gv.pot
        to_call = gv.to_call
        my_chips = gv.my_chips

        # Caso 1: oponente cobre nosso stack — só call ou fold
        if to_call >= my_chips:
            pot_odds = to_call / (pot + to_call)
            adj = self._adjust_for_range(equity, gv, all_in=True)
            return 0 if adj >= pot_odds else -1

        adj = self._adjust_for_range(equity, gv)

        # Caso 2: pode dar check de graça
        if to_call == 0:
            if adj >= self.BET_NUTS_EQUITY:
                return self._raise_to(gv, self._sizing(gv, 0.80))
            if adj >= self.BET_VALUE_EQUITY:
                return self._raise_to(gv, self._sizing(gv, 0.60))
            if adj >= self.BET_THIN_EQUITY:
                return self._raise_to(gv, self._sizing(gv, 0.40))
            return 0  # check (sem blefe)

        # Caso 3: enfrentando aposta — pot odds decide
        pot_odds = to_call / (pot + to_call)

        # Raise para valor (precisa de equity absoluta E margem sobre pot odds)
        if (
            adj >= self.RAISE_NUTS_EQUITY
            and adj >= pot_odds + self.RAISE_NUTS_BUFFER
        ):
            return self._raise_to(gv, self._sizing(gv, 0.80))
        if (
            adj >= self.RAISE_VALUE_EQUITY
            and adj >= pot_odds + self.RAISE_VALUE_BUFFER
        ):
            return self._raise_to(gv, self._sizing(gv, 0.55))

        # Call por equity
        if adj >= pot_odds + self.CALL_BUFFER:
            return 0

        # Call por implied odds barato (equity quase fechando)
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
        Equity da tabela é vs mão aleatória. Quando o oponente aposta forte,
        o range dele é mais tight que random — equity real cai.
        """
        bb = gv.big_blind
        if gv.current_bet <= bb and not all_in:
            return equity

        if all_in:
            tighten = 0.15
        else:
            ratio = gv.current_bet / bb
            if ratio >= 8:
                tighten = 0.12
            elif ratio >= 5:
                tighten = 0.08
            elif ratio >= 3:
                tighten = 0.05
            else:
                tighten = 0.02

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
    return Versao4("versao_4", Hand(), 0)
