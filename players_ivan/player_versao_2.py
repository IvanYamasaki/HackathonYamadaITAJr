"""
versao_2 — bot heads-up que calcula equity e decide por pot odds.

Pré-flop:
  Lookup direto na tabela de 169 mãos (poker_equity_reference.md):
  equity exata de cada mão inicial vs mão aleatória em HU.

Pós-flop:
  Monte Carlo com avaliador próprio de 7 cartas (sem itertools.combinations).
  Cerca de 200-500 amostras dentro de ~30ms, erro padrão ~2-3%.

Decisão:
  - Calcula equity, ajusta para range provável do oponente (quanto maior
    a aposta dele, mais tight assumimos o range).
  - Aposta/raise dimensionado pela equity (alta → 75% pot, média → 50%).
  - Call quando equity > pot_odds + buffer; fold caso contrário.
  - Nunca fold quando to_call == 0 (BB grátis).
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


# ─── Tabela de equity vs mão aleatória ────────────────────────────────────
# Valores da seção 2 de poker_equity_reference.md (HU, all-in até showdown).

PREFLOP_EQUITY: dict[str, float] = {
    # Pares
    "AA": 0.8520, "KK": 0.8240, "QQ": 0.7992, "JJ": 0.7747, "TT": 0.7474,
    "99": 0.7169, "88": 0.6871, "77": 0.6571, "66": 0.6269, "55": 0.5962,
    "44": 0.5627, "33": 0.5292, "22": 0.4992,

    # Suited - Ases
    "AKs": 0.6704, "AQs": 0.6613, "AJs": 0.6541, "ATs": 0.6469,
    "A9s": 0.6291, "A8s": 0.6194, "A7s": 0.6091, "A6s": 0.5936,
    "A5s": 0.5949, "A4s": 0.5855, "A3s": 0.5761, "A2s": 0.5661,

    # Suited - Reis
    "KQs": 0.6341, "KJs": 0.6261, "KTs": 0.6194, "K9s": 0.6010,
    "K8s": 0.5816, "K7s": 0.5718, "K6s": 0.5620, "K5s": 0.5522,
    "K4s": 0.5423, "K3s": 0.5330, "K2s": 0.5237,

    # Suited - Damas
    "QJs": 0.6031, "QTs": 0.5965, "Q9s": 0.5779, "Q8s": 0.5579,
    "Q7s": 0.5378, "Q6s": 0.5291, "Q5s": 0.5191, "Q4s": 0.5097,
    "Q3s": 0.5005, "Q2s": 0.4910,

    # Suited - Valetes
    "JTs": 0.5751, "J9s": 0.5559, "J8s": 0.5359, "J7s": 0.5155,
    "J6s": 0.4934, "J5s": 0.4845, "J4s": 0.4752, "J3s": 0.4660,
    "J2s": 0.4568,

    # Suited - Dezenas
    "T9s": 0.5383, "T8s": 0.5186, "T7s": 0.4985, "T6s": 0.4784,
    "T5s": 0.4562, "T4s": 0.4474, "T3s": 0.4385, "T2s": 0.4296,

    # Suited - médias e baixas
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

    # Offsuit - Ases
    "AKo": 0.6536, "AQo": 0.6439, "AJo": 0.6360, "ATo": 0.6279,
    "A9o": 0.6086, "A8o": 0.5983, "A7o": 0.5871, "A6o": 0.5706,
    "A5o": 0.5727, "A4o": 0.5627, "A3o": 0.5527, "A2o": 0.5420,

    # Offsuit - Reis
    "KQo": 0.6141, "KJo": 0.6055, "KTo": 0.5984, "K9o": 0.5784,
    "K8o": 0.5574, "K7o": 0.5470, "K6o": 0.5363, "K5o": 0.5258,
    "K4o": 0.5152, "K3o": 0.5051, "K2o": 0.4951,

    # Offsuit - Damas
    "QJo": 0.5805, "QTo": 0.5734, "Q9o": 0.5532, "Q8o": 0.5315,
    "Q7o": 0.5097, "Q6o": 0.5002, "Q5o": 0.4894, "Q4o": 0.4793,
    "Q3o": 0.4693, "Q2o": 0.4591,

    # Offsuit - Valetes
    "JTo": 0.5495, "J9o": 0.5286, "J8o": 0.5069, "J7o": 0.4849,
    "J6o": 0.4609, "J5o": 0.4514, "J4o": 0.4415, "J3o": 0.4315,
    "J2o": 0.4216,

    # Offsuit - Dezenas
    "T9o": 0.5100, "T8o": 0.4883, "T7o": 0.4666, "T6o": 0.4450,
    "T5o": 0.4210, "T4o": 0.4116, "T3o": 0.4020, "T2o": 0.3924,

    # Offsuit - médias e baixas
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


# ─── Avaliador rápido de 7 cartas (sem combinations) ──────────────────────

_RANK_INT = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
             "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
_SUIT_INT = {"s": 0, "h": 1, "d": 2, "c": 3}

_FULL_DECK: tuple[tuple[int, int], ...] = tuple(
    (r, s) for r in range(2, 15) for s in range(4)
)


def _card_tuple(card: Card) -> tuple[int, int]:
    return (_RANK_INT[card.value], _SUIT_INT[card.suit])


def _eval7(cards: list[tuple[int, int]]) -> tuple:
    """
    Avalia 7 cartas direto (sem enumerar C(7,5)).
    Retorna tupla (rank_class, *kickers) — tuplas comparam lexicograficamente.
    rank_class: 8 straight-flush, 7 quadra, 6 full, 5 flush, 4 straight,
                3 trinca, 2 dois-pares, 1 par, 0 carta-alta.
    """
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]

    rcount = Counter(ranks)
    scount = Counter(suits)

    flush_suit = None
    for s, n in scount.items():
        if n >= 5:
            flush_suit = s
            break

    # Sequência (com wheel A-2-3-4-5)
    unique_ranks = sorted(set(ranks), reverse=True)
    seq_pool = unique_ranks + ([1] if 14 in unique_ranks else [])
    straight_high = 0
    for i in range(len(seq_pool) - 4):
        if seq_pool[i] - seq_pool[i + 4] == 4:
            straight_high = seq_pool[i]
            break

    # Straight flush
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

    # Quadra
    if top_count == 4:
        quad = counts_sorted[0][0]
        kicker = max(r for r in ranks if r != quad)
        return (7, quad, kicker)

    # Full house
    if top_count == 3 and second_count >= 2:
        return (6, counts_sorted[0][0], counts_sorted[1][0])

    # Flush
    if flush_suit is not None:
        flush_ranks = sorted(
            [c[0] for c in cards if c[1] == flush_suit], reverse=True
        )[:5]
        return (5, *flush_ranks)

    # Sequência
    if straight_high:
        return (4, straight_high)

    # Trinca
    if top_count == 3:
        trip = counts_sorted[0][0]
        kickers = sorted([r for r in ranks if r != trip], reverse=True)[:2]
        return (3, trip, *kickers)

    # Dois pares
    if top_count == 2 and second_count == 2:
        p1 = counts_sorted[0][0]
        p2 = counts_sorted[1][0]
        kicker = max(r for r in ranks if r != p1 and r != p2)
        return (2, p1, p2, kicker)

    # Um par
    if top_count == 2:
        pair = counts_sorted[0][0]
        kickers = sorted([r for r in ranks if r != pair], reverse=True)[:3]
        return (1, pair, *kickers)

    # Carta alta
    return (0, *sorted(ranks, reverse=True)[:5])


def _preflop_key(c_a: Card, c_b: Card) -> str:
    """Converte par de Card no formato 'AKs', 'TT', '72o', etc."""
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

class Versao2(Player):

    MC_BUDGET_MS = 20.0  # tempo máximo gasto em Monte Carlo
    MIN_SAMPLES = 20     # nunca decidir com menos amostras que isso

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._rng = random.Random()

    def decision(self, gv: GameView) -> int:
        if len(gv.board) == 0:
            equity = self._preflop_equity(gv.my_hand)
        else:
            equity = self._monte_carlo_equity(gv.my_hand, gv.board)
        return self._action_from_equity(gv, equity)

    # ─── Cálculo de equity ────────────────────────────────────────────────

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

    # ─── Decisão a partir de equity ───────────────────────────────────────

    def _action_from_equity(self, gv: GameView, equity: float) -> int:
        bb = gv.big_blind
        pot = gv.pot
        to_call = gv.to_call
        my_chips = gv.my_chips

        # Caso 1: oponente já cobre nosso stack
        if to_call >= my_chips:
            pot_odds = to_call / (pot + to_call)
            adj = self._adjust_for_range(equity, gv, all_in=True)
            return 0 if adj >= pot_odds else -1

        adj = self._adjust_for_range(equity, gv)

        # Caso 2: pode dar check de graça
        if to_call == 0:
            return self._free_action(gv, adj)

        # Caso 3: enfrentando aposta — decide por pot odds
        pot_odds = to_call / (pot + to_call)

        # Equity muito acima do preço: raise para valor
        if adj > pot_odds + 0.30 and adj > 0.65:
            return self._raise_to(gv, self._sizing(gv, 0.75))

        # Equity confortavelmente acima: principalmente call, raise às vezes
        if adj > pot_odds + 0.15:
            if adj > 0.58 and self._rng.random() < 0.35:
                return self._raise_to(gv, self._sizing(gv, 0.6))
            return 0

        # Equity um pouco acima: call de valor
        if adj > pot_odds + 0.02:
            return 0

        # Equity próxima e preço baixo: call para fechar pot odds
        if adj > pot_odds - 0.04 and to_call <= 3 * bb:
            return 0

        # Bluff-raise raro contra apostas pequenas
        if (
            adj < 0.25
            and to_call <= 4 * bb
            and self._rng.random() < 0.05
        ):
            return self._raise_to(gv, self._sizing(gv, 0.7))

        return -1

    def _free_action(self, gv: GameView, equity: float) -> int:
        """Sem to_call: escolhe entre check, bet de valor e bluff esporádico."""
        if equity > 0.78:
            return self._raise_to(gv, self._sizing(gv, 0.8))
        if equity > 0.60:
            return self._raise_to(gv, self._sizing(gv, 0.6))
        if equity > 0.48:
            if self._rng.random() < 0.55:
                return self._raise_to(gv, self._sizing(gv, 0.45))
            return 0
        if equity > 0.35:
            if self._rng.random() < 0.20:
                return self._raise_to(gv, self._sizing(gv, 0.5))
            return 0
        # Mãos fracas: bluff esporádico
        if self._rng.random() < 0.08:
            return self._raise_to(gv, self._sizing(gv, 0.5))
        return 0

    def _adjust_for_range(
        self,
        equity: float,
        gv: GameView,
        all_in: bool = False,
    ) -> float:
        """
        Equity da tabela é vs mão aleatória. Quando o oponente aposta forte,
        seu range é mais tight que random — equity real cai.
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
        """Total da rodada para apostar `fraction` do pote atual."""
        invested = gv.current_bet - gv.to_call
        bet_amount = max(gv.big_blind, int(gv.pot * fraction))
        return invested + gv.to_call + bet_amount

    def _raise_to(self, gv: GameView, target_total: int) -> int:
        """Limita o target ao stack disponível."""
        invested = gv.current_bet - gv.to_call
        max_total = invested + gv.my_chips
        return min(target_total, max_total)


def create_player() -> Player:
    return Versao2("versao_2", Hand(), 0)
