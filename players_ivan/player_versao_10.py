"""
versao_10 — evolução cirúrgica da v8.

Em testes preliminares descobrimos que polarizar sizing (block / standard /
overbet) e jitter agressivo vaza valor contra v8 (que é equity-based). Mas
contra Pinguim_Rei (heurístico) o jitter + river-catch amplo ajuda muito.

Estratégia: manter v10 ~= v8 onde v8 é forte (value betting, range
narrowing, push/fold) e adicionar APENAS mudanças cirúrgicas que ajudam
contra adversários adaptativos/heurísticos sem regredir vs v8:

  1. Position detection robusta via `current_bet - to_call` (lock por mão).
     Substitui `dealer_position == 0` em spots ambíguos.

  2. River bluff catcher calibrado contra blefe-block (≤0.40 pot) em board
     sem draws completos. Especificamente anti-Pinguim_Rei (que blefa river
     com 15-35% HS em 30% de freq).

  3. Slowplay condicionado à textura: 18% em board seco, 8% em board drawy.
     Em vez do 12% indiscriminado do v8.

  4. Sizing jitter ±8% (pequeno) — anti-leitura de bots adaptativos sem
     comprometer EV.

Tudo o resto é v8 fiel.
"""
from __future__ import annotations

import random
import sys
import time
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
    RANK_FLUSH,
    RANK_STRAIGHT,
    RANK_TRINCA,
    RANK_UM_PAR,
    score_cinco_cartas,
    valor_carta,
)


_VALUES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
_SUITS = ["s", "h", "d", "c"]
_FULL_DECK: list[Card] = [Card(v, s) for v in _VALUES for s in _SUITS]


def _card_key(c: Card) -> str:
    return c.value + c.suit


def _best_score(cards: list[Card]) -> int:
    if len(cards) < 5:
        return 0
    if len(cards) == 5:
        return score_cinco_cartas(cards)
    best = 0
    for combo in combinations(cards, 5):
        s = score_cinco_cartas(list(combo))
        if s > best:
            best = s
    return best


def _rank_of(score: int) -> int:
    return score // BASE_DESEMPATE


def _has_flush_draw(cards: list[Card]) -> bool:
    counts = Counter(c.suit for c in cards)
    return any(n >= 4 for n in counts.values())


def _has_straight_draw(cards: list[Card]) -> tuple[bool, bool]:
    vals = {valor_carta(c) for c in cards}
    if 14 in vals:
        vals = vals | {1}
    open_ended = False
    gutshot = False
    for v in sorted(vals):
        run = sum(1 for k in range(4) if (v + k) in vals)
        if run == 4:
            open_ended = True
        present = [k for k in range(5) if (v + k) in vals]
        if len(present) == 4 and 0 in present and 4 in present:
            gutshot = True
    return open_ended, gutshot


def _board_is_drawy(board: list[Card]) -> bool:
    if len(board) < 3:
        return False
    if _has_flush_draw(board):
        return True
    oesd, _ = _has_straight_draw(board)
    return oesd


def _board_is_dry(board: list[Card]) -> bool:
    if len(board) < 3:
        return False
    if _has_flush_draw(board):
        return False
    oesd, gut = _has_straight_draw(board)
    return not (oesd or gut)


def _board_has_completed_draws(board: list[Card]) -> bool:
    """Flush ou straight já completáveis com 2 cartas próprias."""
    if len(board) < 3:
        return False
    counts = Counter(c.suit for c in board)
    if any(n >= 3 for n in counts.values()):
        return True
    vals = sorted({valor_carta(c) for c in board})
    if 14 in vals:
        vals = [1] + vals
    for v in vals:
        present = [k for k in range(5) if (v + k) in vals]
        if len(present) >= 3:
            return True
    return False


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


def _strength_for_top_pct(pct: float) -> float:
    table = [
        (0.05, 0.66), (0.10, 0.62), (0.15, 0.58), (0.20, 0.54),
        (0.25, 0.51), (0.30, 0.48), (0.35, 0.46), (0.40, 0.43),
        (0.50, 0.40), (0.60, 0.37), (0.75, 0.33), (1.00, 0.20),
    ]
    for p, thr in table:
        if pct <= p:
            return thr
    return 0.20


def _nash_sb_push_strength(stack_bb: float) -> float:
    if stack_bb <= 4:
        return 0.32
    if stack_bb <= 7:
        return 0.36
    if stack_bb <= 10:
        return 0.40
    if stack_bb <= 13:
        return 0.44
    return 0.48


def _nash_bb_call_strength(stack_bb: float) -> float:
    if stack_bb <= 4:
        return 0.36
    if stack_bb <= 7:
        return 0.42
    if stack_bb <= 10:
        return 0.46
    if stack_bb <= 13:
        return 0.50
    return 0.54


class Versao10(Player):

    SAFETY_BUDGET_MS = 38.0
    MC_BUDGET_MS = 22.0
    MIN_MC_SAMPLES = 8

    BLUFF_FREQ_BASE = 0.08
    OVERBET_FREQ_BASE = 0.15

    # Sizings v8 (mantidos como base estável).
    SIZINGS = (0.50, 0.75, 1.10, 1.60)

    # Jitter pequeno (anti-leitura sem regredir EV).
    SIZING_JITTER = 0.08

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._rng = random.Random()

        self._opp_hands_seen = 0
        self._opp_vpip_hands = 0
        self._opp_pfr_hands = 0
        self._opp_postflop_bets = 0
        self._opp_postflop_calls = 0

        self._last_dealer = None
        self._last_board_len = 0
        self._last_pot = 0
        self._this_hand_opp_vpip = False
        self._this_hand_opp_raised_pf = False
        self._this_hand_opp_max_bet = 0
        self._this_hand_my_last_bet = 0

        # Position lock (M1).
        self._am_bb = False
        self._am_sb = False
        self._position_locked = False

    def decision(self, gv: GameView) -> int:
        try:
            t0 = time.perf_counter()
            deadline = t0 + self.SAFETY_BUDGET_MS / 1000.0

            self._update_opp_model(gv)
            self._detect_position(gv)

            if gv.to_call >= gv.my_chips:
                return self._defend_allin(gv, deadline)

            stack_bb = gv.my_chips / max(1, gv.big_blind)

            if stack_bb <= 12 and len(gv.board) == 0:
                return self._push_fold_preflop(gv, stack_bb)

            if len(gv.board) == 0:
                return self._preflop(gv)

            return self._postflop(gv, deadline)
        except Exception:
            return 0

    # ─── Position detection (M1) ──────────────────────────────────────────

    def _detect_position(self, gv: GameView) -> None:
        if self._last_pot > 0 and gv.pot < self._last_pot:
            self._position_locked = False

        if not self._position_locked and gv.pot <= gv.big_blind * 4:
            my_invested = gv.current_bet - gv.to_call
            if my_invested == gv.big_blind:
                self._am_bb = True
                self._am_sb = False
            elif my_invested == gv.small_blind:
                self._am_bb = False
                self._am_sb = True
            else:
                self._am_bb = (gv.dealer_position == 0)
                self._am_sb = not self._am_bb
            self._position_locked = True

    # ─── Opp modeling (igual v8) ──────────────────────────────────────────

    def _update_opp_model(self, gv: GameView) -> None:
        opp = gv.opponents[0] if gv.opponents else None
        if opp is None:
            return

        new_hand = False
        if self._last_dealer is None:
            new_hand = True
        elif gv.dealer_position != self._last_dealer:
            new_hand = True
        elif len(gv.board) == 0 and self._last_board_len > 0:
            new_hand = True
        elif len(gv.board) == 0 and gv.pot <= (gv.small_blind + gv.big_blind + 2):
            if self._last_pot > gv.pot:
                new_hand = True

        if new_hand:
            if self._opp_hands_seen > 0 or self._this_hand_opp_vpip:
                if self._this_hand_opp_vpip:
                    self._opp_vpip_hands += 1
                if self._this_hand_opp_raised_pf:
                    self._opp_pfr_hands += 1
            self._opp_hands_seen += 1
            self._this_hand_opp_vpip = False
            self._this_hand_opp_raised_pf = False
            self._this_hand_opp_max_bet = 0
            self._this_hand_my_last_bet = 0

        opp_bet = opp.current_bet_in_round
        if opp_bet > gv.big_blind:
            self._this_hand_opp_vpip = True
            if len(gv.board) == 0 and opp_bet > self._this_hand_opp_max_bet:
                self._this_hand_opp_raised_pf = True
        elif opp_bet >= gv.big_blind and len(gv.board) == 0:
            self._this_hand_opp_vpip = True

        if len(gv.board) > 0:
            if opp_bet > self._this_hand_opp_max_bet:
                self._opp_postflop_bets += 1
            elif opp_bet > 0 and opp_bet == gv.current_bet:
                self._opp_postflop_calls += 1

        if opp_bet > self._this_hand_opp_max_bet:
            self._this_hand_opp_max_bet = opp_bet

        self._last_dealer = gv.dealer_position
        self._last_board_len = len(gv.board)
        self._last_pot = gv.pot

    def _opp_vpip(self) -> float:
        if self._opp_hands_seen < 5:
            return 0.50
        return self._opp_vpip_hands / max(1, self._opp_hands_seen)

    def _opp_pfr(self) -> float:
        if self._opp_hands_seen < 5:
            return 0.25
        return self._opp_pfr_hands / max(1, self._opp_hands_seen)

    def _opp_af(self) -> float:
        total = self._opp_postflop_bets + self._opp_postflop_calls
        if total < 5:
            return 0.50
        return self._opp_postflop_bets / total

    # ─── Range estimation (igual v8) ──────────────────────────────────────

    def _estimate_opp_pf_range_pct(self, gv: GameView) -> float:
        vpip = self._opp_vpip()
        pfr = self._opp_pfr()

        bb = gv.big_blind
        opp_bet_round = gv.opponents[0].current_bet_in_round if gv.opponents else 0
        opp_raised = opp_bet_round > bb

        if not opp_raised:
            return min(0.90, max(0.30, vpip))

        raise_ratio = opp_bet_round / bb
        if raise_ratio >= 8:
            return min(pfr * 0.5, 0.10)
        if raise_ratio >= 4:
            return min(pfr * 0.7, 0.18)
        return min(max(pfr, 0.20), 0.40)

    def _estimate_opp_postflop_range_pct(self, gv: GameView) -> float:
        opp = gv.opponents[0]
        pot = max(1, gv.pot)
        opp_invested_this_round = opp.current_bet_in_round

        pf_range = self._estimate_opp_pf_range_pct(gv)

        if opp_invested_this_round > 0:
            bet_to_pot = opp_invested_this_round / pot
            if bet_to_pot >= 1.0:
                return pf_range * 0.40
            if bet_to_pot >= 0.6:
                return pf_range * 0.55
            return pf_range * 0.75

        return min(1.0, pf_range * 1.1)

    # ─── MC equity (igual v8) ─────────────────────────────────────────────

    def _sample_opp_hand(
        self, deck_remaining: list[Card], min_strength: float
    ) -> tuple[Card, Card] | None:
        n = len(deck_remaining)
        if n < 2:
            return None
        for _ in range(12):
            i = self._rng.randrange(n)
            j = self._rng.randrange(n)
            if i == j:
                continue
            a, b = deck_remaining[i], deck_remaining[j]
            if _preflop_strength((a, b)) >= min_strength:
                return (a, b)
        i = self._rng.randrange(n)
        j = self._rng.randrange(n)
        while j == i:
            j = self._rng.randrange(n)
        return (deck_remaining[i], deck_remaining[j])

    def _mc_equity(
        self, gv: GameView, deadline: float, range_pct: float
    ) -> tuple[float, int]:
        mc_deadline = min(deadline, time.perf_counter() + self.MC_BUDGET_MS / 1000.0)
        my_hand = list(gv.my_hand)
        board = list(gv.board)

        known_keys = {_card_key(c) for c in my_hand} | {_card_key(c) for c in board}
        deck_remaining = [c for c in _FULL_DECK if _card_key(c) not in known_keys]

        min_strength = _strength_for_top_pct(range_pct)
        cards_to_come = 5 - len(board)

        wins = 0
        ties = 0
        n = 0

        my_score_fixed = None
        if cards_to_come == 0:
            my_score_fixed = _best_score(my_hand + board)

        while time.perf_counter() < mc_deadline:
            opp_hand = self._sample_opp_hand(deck_remaining, min_strength)
            if opp_hand is None:
                break

            opp_keys = {_card_key(opp_hand[0]), _card_key(opp_hand[1])}
            available_for_runout = [
                c for c in deck_remaining if _card_key(c) not in opp_keys
            ]
            if len(available_for_runout) < cards_to_come:
                break

            if cards_to_come == 0:
                runout: list[Card] = []
            else:
                indices = self._rng.sample(
                    range(len(available_for_runout)), cards_to_come
                )
                runout = [available_for_runout[i] for i in indices]

            full_board = board + runout
            if my_score_fixed is not None:
                my_score = my_score_fixed
            else:
                my_score = _best_score(my_hand + full_board)
            opp_score = _best_score(list(opp_hand) + full_board)

            if my_score > opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            n += 1

            if n >= 100:
                break

        if n == 0:
            return (0.5, 0)
        equity = (wins + 0.5 * ties) / n
        return (equity, n)

    # ─── Pré-flop (igual v8 + position lock) ──────────────────────────────

    def _preflop(self, gv: GameView) -> int:
        strength = _preflop_strength(gv.my_hand)
        bb = gv.big_blind
        i_am_bb = self._am_bb  # M1

        unopened = gv.current_bet <= bb
        opp_vpip = self._opp_vpip()
        opp_pfr = self._opp_pfr()

        if unopened:
            open_mult = 3.0 if opp_pfr < 0.20 else 2.5

            if strength >= 0.62:
                target = self._maybe_overbet(gv, int(open_mult * bb))
                return self._raise_to_jit(gv, target)
            if strength >= 0.50:
                return self._raise_to_jit(gv, int(2.5 * bb))
            if strength >= 0.40:
                if opp_vpip > 0.55:
                    return self._raise_to_jit(gv, int(2.5 * bb))
                return 0
            if i_am_bb:
                return 0
            if strength <= 0.30:
                return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE)
            return 0

        raise_size_bb = gv.current_bet / bb
        pot_odds = gv.to_call / (gv.pot + gv.to_call)

        threebet_thr = 0.72 if opp_pfr < 0.25 else 0.66
        call_thr = 0.48 if opp_pfr < 0.25 else 0.43

        if strength >= threebet_thr:
            target = self._maybe_overbet(gv, int(gv.current_bet * 3))
            return self._raise_to_jit(gv, target)
        if strength >= 0.58:
            if self._rng.random() < 0.22:
                return self._raise_to_jit(gv, int(gv.current_bet * 3))
            return 0
        if strength >= call_thr and raise_size_bb <= 5:
            return 0
        if strength >= 0.40 and pot_odds < 0.18:
            return 0
        if i_am_bb and pot_odds < 0.30 and strength >= 0.36:
            return 0
        return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE)

    # ─── Pós-flop (v8 + slowplay condicional + river catcher) ────────────

    def _postflop(self, gv: GameView, deadline: float) -> int:
        all_cards = list(gv.my_hand) + list(gv.board)
        score = _best_score(all_cards)
        rank = _rank_of(score)
        cards_to_come = 5 - len(gv.board)

        flush_dr = _has_flush_draw(all_cards) if cards_to_come > 0 else False
        oesd, gut = (
            _has_straight_draw(all_cards) if cards_to_come > 0 else (False, False)
        )
        strong_draw = flush_dr or oesd
        any_draw = strong_draw or gut

        board = list(gv.board)
        board_drawy = _board_is_drawy(board)
        board_dry = _board_is_dry(board)

        to_call = gv.to_call
        pot = max(1, gv.pot)
        bb = gv.big_blind
        is_river = (cards_to_come == 0)

        range_pct = self._estimate_opp_postflop_range_pct(gv)
        equity, n_samples = self._mc_equity(gv, deadline, range_pct)

        if n_samples < self.MIN_MC_SAMPLES:
            return self._postflop_heuristic(
                gv, rank, strong_draw, any_draw, flush_dr, oesd, cards_to_come
            )

        implied_bonus = 0.05 if (strong_draw and cards_to_come > 0) else 0.0
        adjusted_equity = min(0.99, equity + implied_bonus)

        pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0

        is_monster = rank >= RANK_STRAIGHT or adjusted_equity >= 0.85
        is_strong = (rank in (RANK_TRINCA, RANK_DOIS_PARES)) or adjusted_equity >= 0.70
        is_medium = (rank == RANK_UM_PAR and self._pair_tier(gv) != "weak") or adjusted_equity >= 0.50

        # ─── Monster ─────────────────────────────────────────────────────
        if is_monster:
            # Slowplay condicional: mais em board seco, menos em drawy.
            slowplay_freq = 0.18 if board_dry else 0.08
            if to_call == 0:
                if self._rng.random() < slowplay_freq:
                    return 0
                target = self._sizing(gv, 0.75)
                target = self._maybe_overbet(gv, target)
                return self._raise_to_jit(gv, target)
            if self._rng.random() < 0.18:
                return 0
            raise_target = max(self._sizing(gv, 0.75), int(gv.current_bet * 2.6))
            raise_target = self._maybe_overbet(gv, raise_target)
            return self._raise_to_jit(gv, raise_target)

        # ─── Strong ──────────────────────────────────────────────────────
        if is_strong:
            if to_call == 0:
                if self._rng.random() < 0.82:
                    target = self._sizing(gv, 0.65)
                    return self._raise_to_jit(gv, target)
                return 0
            bet_to_pot = gv.current_bet / pot
            if bet_to_pot >= 1.2:
                if adjusted_equity >= 0.60:
                    return 0
                if adjusted_equity >= 0.45 and pot_odds < 0.35:
                    return 0
                return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE * 0.5)
            if self._rng.random() < 0.30 and adjusted_equity >= 0.65:
                rt = self._maybe_overbet(gv, int(gv.current_bet * 2.4))
                return self._raise_to_jit(gv, rt)
            return 0

        # ─── Medium ──────────────────────────────────────────────────────
        if is_medium:
            if to_call == 0:
                if self._rng.random() < 0.40:
                    return self._raise_to_jit(gv, self._sizing(gv, 0.45))
                return 0

            # ── River bluff catcher anti-Pinguim_Rei ─────────────────
            # Pinguim_Rei blefa river com bet pequeno (~0.3 pot) em 15-35% HS.
            # Em river + bet pequeno + sem draws completos → catch wider.
            if is_river:
                bet_to_pot_now = gv.current_bet / pot
                if bet_to_pot_now <= 0.40 and not _board_has_completed_draws(board):
                    if adjusted_equity > pot_odds - 0.10:
                        return 0

            if adjusted_equity > pot_odds + 0.05:
                return 0
            if self._opp_af() > 0.65 and adjusted_equity > pot_odds - 0.05:
                return 0
            if to_call <= 3 * bb and adjusted_equity > pot_odds - 0.05:
                return 0
            return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE * 0.5)

        # ─── Draws ───────────────────────────────────────────────────────
        if strong_draw and cards_to_come > 0:
            outs = 9 if flush_dr else (8 if oesd else 4)
            draw_equity = min(0.50, outs * (4 if cards_to_come == 2 else 2) / 100)
            if to_call == 0:
                if self._rng.random() < 0.55:
                    return self._raise_to_jit(gv, self._sizing(gv, 0.55))
                return 0
            if draw_equity > pot_odds:
                return 0
            return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE)

        if any_draw and cards_to_come > 0 and to_call == 0:
            if self._rng.random() < 0.18:
                return self._raise_to_jit(gv, self._sizing(gv, 0.45))
            return 0

        # ─── Air ─────────────────────────────────────────────────────────
        if to_call == 0:
            cbet_freq = 0.15
            if len(gv.board) == 3:
                cbet_freq = 0.35
            if self._opp_af() < 0.35:
                cbet_freq *= 0.6
            if self._rng.random() < cbet_freq:
                return self._raise_to_jit(gv, self._sizing(gv, 0.55))
            return 0
        return self._fold_or_bluff(gv, bluff_freq=self.BLUFF_FREQ_BASE * 0.6)

    def _postflop_heuristic(
        self,
        gv: GameView,
        rank: int,
        strong_draw: bool,
        any_draw: bool,
        flush_dr: bool,
        oesd: bool,
        cards_to_come: int,
    ) -> int:
        if rank >= RANK_STRAIGHT:
            tier = "monster"
        elif rank in (RANK_TRINCA, RANK_DOIS_PARES):
            tier = "strong"
        elif rank == RANK_UM_PAR:
            tier = self._pair_tier(gv)
        else:
            tier = "weak"

        to_call = gv.to_call
        pot = max(1, gv.pot)

        if tier == "monster":
            target = self._sizing(gv, 0.75)
            if to_call == 0:
                return self._raise_to_jit(gv, self._maybe_overbet(gv, target))
            if self._rng.random() < 0.15:
                return 0
            rt = self._maybe_overbet(gv, max(target, int(gv.current_bet * 2.5)))
            return self._raise_to_jit(gv, rt)

        if tier == "strong":
            target = self._sizing(gv, 0.6)
            if to_call == 0:
                if self._rng.random() < 0.82:
                    return self._raise_to_jit(gv, self._maybe_overbet(gv, target))
                return 0
            if gv.current_bet >= pot * 0.9 and self._rng.random() < 0.30:
                return self._fold_or_bluff(gv, self.BLUFF_FREQ_BASE * 0.5)
            return 0

        if tier == "medium":
            if to_call == 0:
                if self._rng.random() < 0.4:
                    return self._raise_to_jit(gv, self._sizing(gv, 0.4))
                return 0
            pot_odds = to_call / (pot + to_call)
            if pot_odds < 0.25 and to_call <= 4 * gv.big_blind:
                return 0
            return self._fold_or_bluff(gv, self.BLUFF_FREQ_BASE * 0.5)

        if strong_draw and cards_to_come > 0:
            outs = 9 if flush_dr else (8 if oesd else 4)
            equity = outs * (4 if cards_to_come == 2 else 2) / 100
            if to_call == 0:
                if self._rng.random() < 0.5:
                    return self._raise_to_jit(gv, self._sizing(gv, 0.5))
                return 0
            pot_odds = to_call / (pot + to_call)
            if equity > pot_odds:
                return 0
            return self._fold_or_bluff(gv, self.BLUFF_FREQ_BASE)

        if to_call == 0:
            if self._rng.random() < 0.10:
                return self._raise_to_jit(gv, self._sizing(gv, 0.5))
            return 0
        return self._fold_or_bluff(gv, self.BLUFF_FREQ_BASE * 0.6)

    # ─── Hooks ────────────────────────────────────────────────────────────

    def _fold_or_bluff(self, gv: GameView, bluff_freq: float) -> int:
        if self._rng.random() >= bluff_freq:
            return -1
        if gv.to_call == 0:
            return self._raise_to_jit(gv, self._sizing(gv, 0.65))
        target = int(gv.current_bet * 2.7)
        return self._raise_to_jit(gv, target)

    def _maybe_overbet(self, gv: GameView, normal_target: int) -> int:
        if self._rng.random() >= self.OVERBET_FREQ_BASE:
            return normal_target
        invested = gv.current_bet - gv.to_call
        delta = normal_target - invested
        bigger = invested + int(delta * 1.7)
        return bigger

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
        return min(target_total, max_total)

    def _raise_to_jit(self, gv: GameView, target_total: int) -> int:
        """Aplica jitter ±SIZING_JITTER ao tamanho da aposta antes do cap."""
        invested = gv.current_bet - gv.to_call
        bet_size = target_total - invested - gv.to_call
        if bet_size <= 0:
            return self._raise_to(gv, target_total)
        jitter = 1.0 + (self._rng.random() * 2 - 1) * self.SIZING_JITTER
        new_bet_size = max(gv.big_blind, int(bet_size * jitter))
        new_target = invested + gv.to_call + new_bet_size
        return self._raise_to(gv, new_target)

    def _push_fold_preflop(self, gv: GameView, stack_bb: float) -> int:
        strength = _preflop_strength(gv.my_hand)
        i_am_bb = self._am_bb
        bb = gv.big_blind

        if not i_am_bb:
            thr = _nash_sb_push_strength(stack_bb)
            if strength >= thr:
                return self._shove(gv)
            if self._opp_af() < 0.30 and strength >= 0.36 and stack_bb >= 8:
                return 0
            return -1

        if gv.to_call == 0:
            return 0
        thr_call = _nash_bb_call_strength(stack_bb)
        pot_odds = gv.to_call / (gv.pot + gv.to_call)
        if pot_odds < 0.40:
            thr_call -= 0.04
        if strength >= thr_call:
            return 0
        if strength >= 0.42 and pot_odds <= 0.25:
            return 0
        return self._fold_or_bluff(gv, self.BLUFF_FREQ_BASE * 0.5)

    def _shove(self, gv: GameView) -> int:
        invested = gv.current_bet - gv.to_call
        return invested + gv.my_chips

    def _defend_allin(self, gv: GameView, deadline: float) -> int:
        pot_odds = gv.to_call / (gv.pot + gv.to_call)

        if len(gv.board) == 0:
            strength = _preflop_strength(gv.my_hand)
            min_strength = 0.55 - (0.30 - min(pot_odds, 0.30)) * 0.5
            return 0 if strength >= min_strength else -1

        range_pct = self._estimate_opp_postflop_range_pct(gv)
        equity, n_samples = self._mc_equity(gv, deadline, range_pct)
        if n_samples >= self.MIN_MC_SAMPLES:
            margin = 0.02
            return 0 if equity > pot_odds + margin else -1

        score = _best_score(list(gv.my_hand) + list(gv.board))
        rank = _rank_of(score)
        if rank >= RANK_DOIS_PARES:
            return 0
        if rank == RANK_UM_PAR and pot_odds <= 0.40:
            return 0
        return -1


def create_player() -> Player:
    return Versao10("versao_10", Hand(), 0)
