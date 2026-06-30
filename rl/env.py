"""
env.py — Ambiente de RL heads-up sobre a ENGINE REAL do torneio.

Por que não reimplementar a mesa? Porque os quirks da engine (o "pedágio":
current_bet não reseta entre streets, flop antes da 1ª aposta) são o coração
do jogo. Reimplementar arriscaria divergir. Em vez disso, rodamos a `Game`
de verdade numa thread e invertemos o controle: o nosso player (_RLProxy,
subclasse de Versao15) bloqueia em `decision()` esperando a ação que o
treinador escolher, devolvendo enquanto isso (features, máscara, fichas).

VecEnv roda N dessas threads em paralelo lógico e entrega ao PPO uma
interface vetorizada com auto-reset:

    obs, mask = venv.reset()
    obs, mask, reward, done = venv.step(action_idx)   # arrays (N, ...)

Recompensa (FÁCIL e telescópica — ver REWARD_*):
    r_t = (Δ fichas próprias) / (fichas totais em jogo)
    + bônus terminal (+ganhou / -perdeu a PARTIDA inteira)
A soma dos r_t ao longo da partida = ganho de fichas normalizado + bônus,
então o sinal denso "aponta" exatamente para vencer a partida.
"""
from __future__ import annotations

import importlib.util
import queue
import random
import sys
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "players"))

from game.game import Game                                   # noqa: E402
from game.game_view import GameView                          # noqa: E402
from cards.cards import Hand                                 # noqa: E402
from players.player import Player                            # noqa: E402

# Importa o player v15 (fonte única de features/ações).
_spec = importlib.util.spec_from_file_location(
    "player_versao_15", ROOT / "players" / "player_versao_15.py")
_v15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v15)

Versao15 = _v15.Versao15
build_features = _v15.build_features
legal_mask = _v15.legal_mask
decode_action = _v15.decode_action
FEATURE_DIM = _v15.FEATURE_DIM
N_ACTIONS = _v15.N_ACTIONS

# Recompensa (fácil): denso = ganho de fichas normalizado; terminal = ±bônus.
REWARD_TERMINAL_WIN = 1.0
REWARD_TERMINAL_LOSS = -1.0
REWARD_DENSE_SCALE = 1.0


# ─── Pacotes trocados thread-do-jogo ↔ treinador ──────────────────────────

class _StepPkt:
    __slots__ = ("feat", "mask", "my_chips")

    def __init__(self, feat, mask, my_chips):
        self.feat = feat
        self.mask = mask
        self.my_chips = my_chips


class _TermPkt:
    __slots__ = ("final_my", "won")

    def __init__(self, final_my, won):
        self.final_my = final_my
        self.won = won


class _Stop(BaseException):
    """Sinaliza shutdown. BaseException p/ NÃO ser capturada pelo
    `except Exception` da engine — propaga até a thread encerrar limpa."""
    pass


class _RLProxy(Versao15):
    """Player cuja decisão é delegada ao treinador via filas.

    INVARIANTE CRÍTICA: toda chamada a decision() faz exatamente 1 put no
    obs_q e 1 get no act_q — senão o VecEnv trava. Por isso não usamos o
    try/except SAFE da base e protegemos a montagem de features localmente.
    """

    def __init__(self, name, obs_q: queue.Queue, act_q: queue.Queue):
        # Evita o carregamento de pesos do disco a cada partida (Versao15
        # faria isso). Só precisamos dos trackers.
        Player.__init__(self, name, Hand(), 0)
        self._om = _v15._OppModel()
        self._policy = None
        self._obs_q = obs_q
        self._act_q = act_q

    def decision(self, gv: GameView) -> int:  # bypassa o SAFE da base
        return self._decide(gv)

    def _decide(self, gv: GameView) -> int:
        try:
            self._om.update(gv)
            first_action = not self._om.first_done
            self._om.first_done = True
            feat = build_features(gv, self._om, first_action)
            mask = legal_mask(gv, self._om.matched, first_action)
        except Exception:
            # Garante o put+get mesmo em erro (sem travar o VecEnv).
            feat = np.zeros(FEATURE_DIM, dtype=np.float32)
            mask = np.zeros(N_ACTIONS, dtype=bool)
            mask[_v15.ACTION_CALL] = True
            self._obs_q.put(_StepPkt(feat, mask, gv.my_chips))
            idx = self._act_q.get()
            if idx is None:
                raise _Stop()
            return 0

        self._obs_q.put(_StepPkt(feat, mask, gv.my_chips))
        idx = self._act_q.get()
        if idx is None:
            raise _Stop()
        if not mask[idx]:
            idx = _v15.ACTION_CALL

        action, new_matched, _ = decode_action(gv, idx, self._om.matched)
        self._om.matched = new_matched
        if action == -1:
            self._om.we_folded_hand = True
        elif action > 0:
            self._om.we_raised_hand = True
            self._om.pending_raise = (
                len(gv.board) == 5,
                action - gv.current_bet >= gv.opponents[0].chips)
        return action


def _load_factory(path: str):
    spec = importlib.util.spec_from_file_location(
        Path(path).stem.replace(" ", "_"), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.create_player


class _GameThread(threading.Thread):
    """Roda partidas em loop infinito, alternando posição e oponente."""

    def __init__(self, env_id, obs_q, act_q, opp_paths, seed):
        super().__init__(daemon=True)
        self.env_id = env_id
        self.obs_q = obs_q
        self.act_q = act_q
        self.opp_factories = [_load_factory(p) for p in opp_paths]
        self.proxy_name = "versao_15"
        self.rng = random.Random(seed)
        self._stop = False

    def stop(self):
        self._stop = True
        try:
            self.act_q.put_nowait(None)   # desbloqueia decision() pendente
        except Exception:
            pass

    def run(self):
        game_i = 0
        while not self._stop:
            proxy = _RLProxy(self.proxy_name, self.obs_q, self.act_q)
            opp = self.rng.choice(self.opp_factories)()
            players = [proxy, opp] if game_i % 2 == 0 else [opp, proxy]
            game_i += 1
            game = Game(players)
            game.verbose = False
            game.decision_timeout_s = None    # nossa decisão bloqueia nas filas
            try:
                winner = game.play_game()
            except _Stop:
                return
            except Exception:
                winner = None
            won = winner is not None and winner.name == self.proxy_name
            self.obs_q.put(_TermPkt(proxy.chips, won))


class VecEnv:
    """N partidas heads-up em paralelo (auto-reset). Interface PPO-friendly."""

    def __init__(self, num_envs: int, opp_paths: list[str], seed: int = 0,
                 dense_scale: float = REWARD_DENSE_SCALE,
                 reward_win: float = REWARD_TERMINAL_WIN,
                 reward_loss: float = REWARD_TERMINAL_LOSS):
        self.n = num_envs
        # Recompensa configurável (permite trocar de sistema sem mexer no resto).
        self._dense = dense_scale       # peso do denso (0 = só vitória/esparso)
        self._rwin = reward_win
        self._rloss = reward_loss
        self._obs_qs = [queue.Queue() for _ in range(num_envs)]
        self._act_qs = [queue.Queue() for _ in range(num_envs)]
        self._threads = [
            _GameThread(i, self._obs_qs[i], self._act_qs[i], opp_paths,
                        seed + i * 100003)
            for i in range(num_envs)
        ]
        self._prev_chips = [0.0] * num_envs
        self._total = [10000.0] * num_envs
        self._started = False

    # ── interface ───────────────────────────────────────────────────────
    def reset(self):
        if not self._started:
            for t in self._threads:
                t.start()
            self._started = True
        obs = np.zeros((self.n, FEATURE_DIM), dtype=np.float32)
        mask = np.zeros((self.n, N_ACTIONS), dtype=bool)
        for i in range(self.n):
            pkt = self._next_step(i)
            obs[i] = pkt.feat
            mask[i] = pkt.mask
            self._prev_chips[i] = pkt.my_chips
            self._total[i] = self._thread_total(i)
        return obs, mask

    def step(self, actions):
        for i in range(self.n):
            self._act_qs[i].put(int(actions[i]))

        obs = np.zeros((self.n, FEATURE_DIM), dtype=np.float32)
        mask = np.zeros((self.n, N_ACTIONS), dtype=bool)
        rew = np.zeros(self.n, dtype=np.float32)
        done = np.zeros(self.n, dtype=np.float32)
        wins = np.full(self.n, -1.0, dtype=np.float32)   # -1 = sem terminal

        for i in range(self.n):
            total = max(1.0, self._total[i])
            reward = 0.0
            terminal = False
            won = False
            while True:
                pkt = self._get(i)
                if isinstance(pkt, _TermPkt):
                    reward += self._dense * (pkt.final_my - self._prev_chips[i]) / total
                    terminal = True
                    won = pkt.won
                    continue   # próximo pacote é o 1º step da nova partida
                # _StepPkt
                if terminal:
                    # obs de reset da nova partida; não creditamos o delta.
                    reward += self._rwin if won else self._rloss
                    self._prev_chips[i] = pkt.my_chips
                    self._total[i] = self._thread_total(i)
                else:
                    reward += self._dense * (pkt.my_chips - self._prev_chips[i]) / total
                    self._prev_chips[i] = pkt.my_chips
                obs[i] = pkt.feat
                mask[i] = pkt.mask
                break
            rew[i] = reward
            done[i] = 1.0 if terminal else 0.0
            if terminal:
                wins[i] = 1.0 if won else 0.0
        return obs, mask, rew, done, wins

    def close(self):
        for t in self._threads:
            t.stop()

    # ── helpers ─────────────────────────────────────────────────────────
    def _get(self, i):
        """Get com timeout: se a thread morreu, falha alto em vez de travar."""
        try:
            return self._obs_qs[i].get(timeout=60.0)
        except queue.Empty:
            alive = self._threads[i].is_alive()
            raise RuntimeError(
                f"env {i} sem resposta em 60s (thread viva={alive}). "
                f"Provável exceção na thread de jogo — ver traceback acima.")

    def _next_step(self, i) -> _StepPkt:
        while True:
            pkt = self._get(i)
            if isinstance(pkt, _StepPkt):
                return pkt
            # ignora terminais residuais

    def _thread_total(self, i) -> float:
        # total de fichas em jogo é constante (= 2 * 500 * bb_inicial = 10000).
        return 10000.0
