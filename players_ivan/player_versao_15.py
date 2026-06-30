"""
versao_15 — política aprendida por Reinforcement Learning (PPO) sobre as
features do v14.

Arquitetura (ver pasta ../rl/):
  - O ESTADO é o vetor de features de `build_features()` abaixo: a hand
    strength do avaliador do v14 (hs_total/hs_made/draws) + contexto do
    spot (pot odds, eff_bb, spr, street, posição, agressão) + o modelo de
    oponente (aggro_rate, fold_to_raise, big_rate, early_fold_rate).
  - A AÇÃO é um índice discreto (ver ACTIONS) que `decode_action()` traduz
    para o inteiro que a engine espera (-1 fold / 0 call / N raise-para-N).
  - A POLÍTICA é um MLP pequeno treinado por PPO. Os pesos são exportados
    para `../rl/weights_v15.npz` e carregados aqui num forward 100% numpy
    (sem torch) — inferência em microssegundos, zero risco do timeout 50ms.

Este arquivo é SELF-CONTAINED (a engine carrega cada player isoladamente).
O treino em ../rl/ reimporta `build_features`, `decode_action`,
`legal_mask` e a classe `Versao15` DESTE arquivo, garantindo que as
features vistas no treino são idênticas às do deploy (uma só implementação).

Se `weights_v15.npz` não existir, cai num fallback heurístico sóbrio para
continuar sendo um player válido no torneio.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand

VAL = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


def _cv(c) -> int:
    return VAL[c.value]


# ─── Avaliador de 5 cartas (idêntico ao v14) ──────────────────────────────

def _eval5(cards) -> tuple:
    vals = sorted((_cv(c) for c in cards), reverse=True)
    suits = [c.suit for c in cards]
    vc = Counter(vals)
    counts = sorted(vc.values(), reverse=True)
    is_flush = len(set(suits)) == 1

    uv = sorted(set(vals))
    if 14 in uv:
        uv = [1] + uv
    is_straight = False
    straight_high = 0
    for i in range(len(uv) - 5, -1, -1):
        if uv[i + 4] - uv[i] == 4:
            is_straight = True
            straight_high = uv[i + 4]
            break

    if is_flush and is_straight:
        return (8, straight_high)
    if counts[0] == 4:
        q = max(v for v, n in vc.items() if n == 4)
        k = max(v for v in vals if v != q)
        return (7, q, k)
    if counts[0] == 3 and counts[1] >= 2:
        t = max(v for v, n in vc.items() if n == 3)
        p = max(v for v, n in vc.items() if n >= 2 and v != t)
        return (6, t, p)
    if is_flush:
        return (5,) + tuple(vals)
    if is_straight:
        return (4, straight_high)
    if counts[0] == 3:
        t = max(v for v, n in vc.items() if n == 3)
        ks = [v for v in vals if v != t][:2]
        return (3, t) + tuple(ks)
    if counts[0] == 2 and counts[1] == 2:
        ps = sorted((v for v, n in vc.items() if n == 2), reverse=True)
        k = max(v for v in vals if v not in ps[:2])
        return (2, ps[0], ps[1], k)
    if counts[0] == 2:
        p = max(v for v, n in vc.items() if n == 2)
        ks = [v for v in vals if v != p][:3]
        return (1, p) + tuple(ks)
    return (0,) + tuple(vals)


def _best_hand(cards: list) -> tuple:
    if len(cards) == 5:
        return _eval5(cards)
    return max(_eval5(list(c)) for c in combinations(cards, 5))


def _flush_draw(hole, board) -> bool:
    sc = Counter(c.suit for c in list(hole) + list(board))
    for s, n in sc.items():
        if n == 4 and any(c.suit == s for c in hole):
            return True
    return False


def _straight_draws(cards) -> tuple[bool, bool]:
    vals = {_cv(c) for c in cards}
    if 14 in vals:
        vals = vals | {1}
    oesd = gut = False
    for lo in range(1, 11):
        present = [k for k in range(5) if (lo + k) in vals]
        if len(present) == 4:
            if 0 in present and 4 in present:
                gut = True
            else:
                oesd = True
    return oesd, gut


def _strength(hole, board) -> tuple[float, float, bool, bool]:
    """(hs_total, hs_made, strong_draw, any_draw) — idêntico ao v14."""
    hole = list(hole)
    board = list(board)
    allc = hole + board
    best = _best_hand(allc)
    cat = best[0]

    hv = sorted((_cv(c) for c in hole), reverse=True)
    bv = sorted((_cv(c) for c in board), reverse=True)
    top_b = bv[0]
    bcount = Counter(bv)
    hcount = Counter(hv)
    pocket = hv[0] == hv[1]
    ctc = 5 - len(board)

    hs = 0.30
    if cat == 8:
        hs = 0.99
    elif cat == 7:
        q = best[1]
        hs = 0.90 if bcount.get(q, 0) == 4 else 0.985
    elif cat == 6:
        t, p = best[1], best[2]
        board_made = bcount.get(t, 0) >= 3 and bcount.get(p, 0) >= 2
        hs = 0.62 if board_made else 0.965
    elif cat == 5:
        sc = Counter(c.suit for c in allc)
        fsuit = max(sc, key=sc.get)
        mine = [_cv(c) for c in hole if c.suit == fsuit]
        if not mine:
            hs = 0.55
        else:
            hi = max(mine)
            hs = {14: 0.95, 13: 0.91, 12: 0.87, 11: 0.82, 10: 0.78}.get(hi, 0.72)
            if sum(1 for c in board if c.suit == fsuit) >= 4:
                hs -= 0.07
    elif cat == 4:
        hs = 0.90
        if len(board) == 5 and _eval5(board)[0] == 4 and _eval5(board) >= best:
            hs = 0.55
        else:
            buv = sorted(set(bv))
            if 14 in buv:
                buv = [1] + buv
            for i in range(len(buv) - 4, -1, -1):
                if buv[i + 3] - buv[i] <= 4:
                    hs = 0.82
                    break
    elif cat == 3:
        t = best[1]
        if pocket and hv[0] == t:
            hs = 0.93
        elif bcount.get(t, 0) == 2:
            kick = max((v for v in hv if v != t), default=0)
            hs = 0.80 + (0.05 if kick >= 12 else 0.0)
        else:
            hs = min(0.62, 0.38 + 0.022 * (hv[0] - 7))
    elif cat == 2:
        p1, p2 = best[1], best[2]
        live = [p for p in (p1, p2) if hcount.get(p, 0) >= 1 and bcount.get(p, 0) <= 1]
        if len(live) == 2:
            hs = 0.86 + (0.03 if p1 >= top_b else 0.0)
        elif len(live) == 1:
            p = live[0]
            if pocket and p == hv[0]:
                hs = 0.70 if p > top_b else 0.58
            elif p == top_b:
                kick = max((v for v in hv if v != p), default=0)
                hs = 0.70 + (0.04 if kick >= 13 else 0.0)
            else:
                hs = 0.58
        else:
            hs = min(0.55, 0.32 + 0.020 * (hv[0] - 7))
    elif cat == 1:
        p = best[1]
        if bcount.get(p, 0) >= 2:
            hs = min(0.46, 0.28 + 0.018 * (hv[0] - 7) + 0.008 * (hv[1] - 7))
        elif pocket:
            if p > top_b:
                hs = 0.72 + 0.004 * max(0, p - 10)
            else:
                above = sum(1 for v in set(bv) if v > p)
                hs = 0.60 if above == 1 else (0.52 if above == 2 else 0.46)
        else:
            kick = max((v for v in hv if v != p), default=0)
            if p == top_b:
                hs = 0.60 + (0.08 if kick >= 13 else 0.05 if kick >= 11 else 0.02 if kick >= 9 else 0.0)
            else:
                above = sum(1 for v in set(bv) if v > p)
                hs = 0.54 if above == 1 else 0.47
    else:
        hs = 0.16 + 0.022 * (hv[0] - 7) + 0.010 * (hv[1] - 7)

    if 1 <= cat <= 2:
        bs = Counter(c.suit for c in board)
        if bs:
            ms, mn = bs.most_common(1)[0]
            if mn >= 3 and not any(c.suit == ms for c in hole):
                hs -= 0.05
            if mn >= 4 and not any(c.suit == ms for c in hole):
                hs -= 0.08

    hs_made = max(0.05, min(0.99, hs))

    fdraw = _flush_draw(hole, board) if ctc > 0 and cat < 5 else False
    oesd, gut = _straight_draws(allc) if ctc > 0 and cat < 4 else (False, False)
    overcards = (not pocket) and hv[1] > top_b and cat == 0

    bonus = 0.0
    if cat <= 1:
        if fdraw:
            bonus += 0.16 if ctc == 2 else 0.09
        if oesd:
            bonus += 0.12 if ctc == 2 else 0.07
        elif gut:
            bonus += 0.05 if ctc == 2 else 0.03
        if overcards:
            bonus += 0.05 if ctc == 2 else 0.02
        bonus = min(bonus, 0.26)
    elif cat == 2 and fdraw:
        bonus = 0.04

    hs_total = min(0.97, hs_made + bonus)
    strong_draw = fdraw or oesd
    any_draw = strong_draw or gut
    return hs_total, hs_made, strong_draw, any_draw


# ═══ Espaço de ações ══════════════════════════════════════════════════════
# Índice discreto → tradução para o inteiro da engine em decode_action().
ACTION_FOLD = 0
ACTION_CALL = 1
ACTION_RAISE_HALF = 2
ACTION_RAISE_POT = 3
ACTION_RAISE_2POT = 4
ACTION_ALLIN = 5
N_ACTIONS = 6

_RAISE_FRAC = {ACTION_RAISE_HALF: 0.5, ACTION_RAISE_POT: 1.0, ACTION_RAISE_2POT: 2.0}

FEATURE_DIM = 23


def legal_mask(gv: GameView, matched: int, first_action: bool) -> np.ndarray:
    """Máscara booleana (N_ACTIONS,) de ações válidas no spot."""
    m = np.zeros(N_ACTIONS, dtype=bool)
    to_call = gv.to_call
    # CALL/CHECK e ALLIN sempre disponíveis.
    m[ACTION_CALL] = True
    m[ACTION_ALLIN] = gv.my_chips > 0
    # FOLD só faz sentido se há algo a pagar (senão é check).
    m[ACTION_FOLD] = to_call > 0
    # Raises só se temos stack acima do call.
    can_raise = gv.my_chips > to_call
    m[ACTION_RAISE_HALF] = can_raise
    m[ACTION_RAISE_POT] = can_raise
    m[ACTION_RAISE_2POT] = can_raise
    if not m.any():
        m[ACTION_CALL] = True
    return m


def decode_action(gv: GameView, idx: int, matched: int) -> tuple[int, int, bool]:
    """Traduz índice → (ação_engine, novo_matched, foi_raise).

    ação_engine: -1 fold / 0 call|check / N>0 raise-para-total-N nesta rodada.
    """
    if idx == ACTION_FOLD and gv.to_call > 0:
        return -1, matched, False
    if idx == ACTION_CALL or idx == ACTION_FOLD:
        return 0, gv.current_bet, False

    invested = gv.current_bet - gv.to_call
    max_total = invested + gv.my_chips
    if idx == ACTION_ALLIN:
        target = max_total
    else:
        frac = _RAISE_FRAC[idx]
        target = gv.current_bet + int(frac * max(1, gv.pot))
        target = min(target, max_total)
    if target <= gv.current_bet:
        # Raise degenerou em call (sem stack pra subir): vira call.
        return 0, gv.current_bet, False
    return target, target, True


# ═══ Modelo de oponente (trackers; mesma lógica do v14) ════════════════════

class _OppModel:
    """Estado persistente da partida: replica os trackers do v14 para que as
    features sejam idênticas entre treino e deploy."""

    def __init__(self) -> None:
        self.hands = 0
        self.opp_faced_raise = 0
        self.opp_fold_raise = 0
        self.opp_raises = 0
        self.opp_big_raises = 0
        self.opp_early_folds = 0

        self.last_dealer = None
        self.am_sb = False
        self.first_done = False
        self.matched = 0
        self.pending_raise = None        # (was_river, was_allin)
        self.opp_raised_hand = False
        self.we_folded_hand = False
        self.saw_allin_hand = False
        self.last_street_seen = 3
        self.we_raised_hand = False
        self.total_chips = 0             # total de fichas em jogo (constante)

    def update(self, gv: GameView) -> None:
        new_hand = self.last_dealer is None or gv.dealer_position != self.last_dealer
        if self.total_chips == 0:
            self.total_chips = gv.my_chips + sum(o.chips for o in gv.opponents) + gv.pot
        if new_hand:
            if self.pending_raise is not None:
                was_river, was_allin = self.pending_raise
                if not was_river and not was_allin:
                    self.opp_faced_raise += 1
                    self.opp_fold_raise += 1
                self.pending_raise = None
            if (self.hands > 0 and not self.we_folded_hand
                    and not self.saw_allin_hand and self.last_street_seen < 5):
                self.opp_early_folds += 1
            self.hands += 1
            self.first_done = False
            self.we_raised_hand = False
            self.opp_raised_hand = False
            self.we_folded_hand = False
            self.saw_allin_hand = False
            self.matched = gv.big_blind
            self.am_sb = gv.pot <= gv.small_blind + gv.big_blind
            self.last_dealer = gv.dealer_position
        else:
            if self.pending_raise is not None:
                self.opp_faced_raise += 1
                self.pending_raise = None

        self.last_street_seen = len(gv.board)
        if gv.to_call >= gv.my_chips or (gv.opponents and gv.opponents[0].chips == 0):
            self.saw_allin_hand = True

        if gv.current_bet > self.matched:
            self.opp_raises += 1
            self.opp_raised_hand = True
            inc = gv.current_bet - self.matched
            pot_before = max(1, gv.pot - gv.to_call)
            if gv.to_call >= gv.my_chips or inc >= 0.9 * pot_before:
                self.opp_big_raises += 1

    def fold_to_raise(self) -> float:
        return (self.opp_fold_raise + 1.6) / (self.opp_faced_raise + 4.0)

    def aggro_rate(self) -> float:
        return self.opp_raises / max(6.0, self.hands)

    def big_rate(self) -> float:
        return self.opp_big_raises / max(8.0, self.hands)

    def early_fold_rate(self) -> float:
        return self.opp_early_folds / max(1.0, self.hands)


def build_features(gv: GameView, om: _OppModel, first_action: bool) -> np.ndarray:
    """Vetor de estado (FEATURE_DIM,) — único ponto de verdade treino/deploy."""
    bb = max(1, gv.big_blind)
    pot = max(1, gv.pot)
    to_call = gv.to_call
    opp = gv.opponents[0]
    street = len(gv.board)

    hs_total, hs_made, strong_draw, any_draw = _strength(gv.my_hand, gv.board)
    pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0
    eff = min(gv.my_chips, opp.chips + to_call)
    eff_bb = eff / bb
    spr = gv.my_chips / pot
    is_aggro = 1.0 if (gv.current_bet > om.matched and not (
        first_action and gv.current_bet <= bb)) else 0.0
    total = max(1, om.total_chips)

    f = np.empty(FEATURE_DIM, dtype=np.float32)
    f[0] = hs_total
    f[1] = hs_made
    f[2] = 1.0 if strong_draw else 0.0
    f[3] = 1.0 if any_draw else 0.0
    f[4] = pot_odds
    f[5] = min(1.0, to_call / pot)
    f[6] = min(1.0, to_call / max(1, gv.my_chips))
    f[7] = min(eff_bb, 150.0) / 150.0
    f[8] = min(pot / bb, 50.0) / 50.0
    f[9] = min(spr, 20.0) / 20.0
    f[10] = 1.0 if street == 3 else 0.0
    f[11] = 1.0 if street == 4 else 0.0
    f[12] = 1.0 if street == 5 else 0.0
    f[13] = is_aggro
    f[14] = 1.0 if om.am_sb else 0.0
    f[15] = gv.my_chips / total
    f[16] = 1.0 if first_action else 0.0
    f[17] = min(om.aggro_rate(), 1.5) / 1.5
    f[18] = om.fold_to_raise()
    f[19] = min(om.big_rate(), 1.0)
    f[20] = min(om.early_fold_rate(), 1.0)
    f[21] = min(gv.current_bet / bb, 40.0) / 40.0
    f[22] = min(om.hands, 250.0) / 250.0
    return f


# ═══ Política numpy (carregada de weights_v15.npz) ════════════════════════

# Pesos: por padrão os de produção; sobrescrevível por env var (avaliar
# experimentos sem trocar o arquivo de produção).
_WEIGHTS_PATH = Path(os.environ.get(
    "V15_WEIGHTS",
    str(Path(__file__).resolve().parents[1] / "rl" / "weights_v15.npz")))


class _NumpyPolicy:
    """Forward de um MLP (tanh) → logits da política. 100% numpy."""

    def __init__(self, layers: list[tuple[np.ndarray, np.ndarray]]):
        self.layers = layers   # [(W, b), ...] última camada = logits

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return None
        data = np.load(path)
        n = int(data["n_layers"])
        layers = [(data[f"w{i}"].astype(np.float32),
                   data[f"b{i}"].astype(np.float32)) for i in range(n)]
        return cls(layers)

    def logits(self, x: np.ndarray) -> np.ndarray:
        for i, (w, b) in enumerate(self.layers):
            x = x @ w + b
            if i < len(self.layers) - 1:
                x = np.tanh(x)
        return x


# ═══ Player ════════════════════════════════════════════════════════════════

class Versao15(Player):

    SAFE = True

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self._om = _OppModel()
        self._policy = _NumpyPolicy.load(_WEIGHTS_PATH)

    # Ponto de extensão: o treino subclassa e sobrescreve isto para deixar o
    # PPO escolher a ação (mantendo features/máscara idênticas).
    def _choose_idx(self, feat: np.ndarray, mask: np.ndarray, gv: GameView) -> int:
        if self._policy is not None:
            logits = self._policy.logits(feat)
            logits = np.where(mask, logits, -1e9)
            return int(np.argmax(logits))
        return self._fallback_idx(feat, mask, gv)

    @staticmethod
    def _fallback_idx(feat: np.ndarray, mask: np.ndarray, gv: GameView) -> int:
        """Heurística sóbria usada só se não houver pesos treinados."""
        hs_total = float(feat[0])
        hs_made = float(feat[1])
        pot_odds = float(feat[4])
        eff_bb = float(feat[7]) * 150.0
        idx = ACTION_CALL
        if eff_bb <= 9.0 and hs_total >= 0.54 and mask[ACTION_ALLIN]:
            idx = ACTION_ALLIN
        elif hs_made >= 0.72 and mask[ACTION_RAISE_POT]:
            idx = ACTION_RAISE_POT
        elif hs_total > pot_odds + 0.05:
            idx = ACTION_CALL
        elif mask[ACTION_FOLD]:
            idx = ACTION_FOLD
        if not mask[idx]:
            idx = ACTION_CALL
        return idx

    def decision(self, gv: GameView) -> int:
        try:
            return self._decide(gv)
        except Exception:
            if not self.SAFE:
                raise
            return 0

    def _decide(self, gv: GameView) -> int:
        self._om.update(gv)
        first_action = not self._om.first_done
        self._om.first_done = True

        feat = build_features(gv, self._om, first_action)
        mask = legal_mask(gv, self._om.matched, first_action)
        idx = self._choose_idx(feat, mask, gv)
        if not mask[idx]:
            idx = ACTION_CALL

        action, new_matched, _ = decode_action(gv, idx, self._om.matched)
        self._om.matched = new_matched
        if action == -1:
            self._om.we_folded_hand = True
        elif action > 0:
            self._om.we_raised_hand = True
            self._om.pending_raise = (len(gv.board) == 5, action - gv.current_bet >= gv.opponents[0].chips)
        return action


def create_player() -> Player:
    return Versao15("versao_15", Hand(), 0)
