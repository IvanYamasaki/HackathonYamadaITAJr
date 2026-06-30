"""Smoke test do pipeline RL (roda na CPU, rápido)."""
import sys, time, importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "rl"))

# 1) player_versao_15 carrega e joga (fallback heurístico, sem pesos)
from game.game import Game
spec = importlib.util.spec_from_file_location("p15", ROOT/"players"/"player_versao_15.py")
p15 = importlib.util.module_from_spec(spec); spec.loader.exec_module(p15)
spec2 = importlib.util.spec_from_file_location("p14", ROOT/"players"/"player_versao_14.py")
p14 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(p14)

print("[1] v15(fallback) vs v14 — 20 partidas")
w = 0
for g in range(20):
    players = [p15.create_player(), p14.create_player()] if g % 2 == 0 else [p14.create_player(), p15.create_player()]
    game = Game(players); game.verbose = False; game.decision_timeout_s = None
    win = game.play_game()
    if win and win.name == "versao_15": w += 1
print(f"    v15 venceu {w}/20 (só sanity — fallback é fraco)")

# 2) env vetorizado com ações aleatórias
from env import VecEnv, FEATURE_DIM, N_ACTIONS
OPP = [str(ROOT/"players"/"player_versao_14.py"), str(ROOT/"players"/"player_versao_8.py")]
print(f"[2] VecEnv: FEATURE_DIM={FEATURE_DIM} N_ACTIONS={N_ACTIONS}")
env = VecEnv(4, OPP, seed=1)
obs, mask = env.reset()
assert obs.shape == (4, FEATURE_DIM), obs.shape
assert mask.shape == (4, N_ACTIONS), mask.shape
rng = np.random.default_rng(0)
t0 = time.perf_counter(); steps = 200; ndone = 0
for _ in range(steps):
    acts = []
    for i in range(4):
        legal = np.where(mask[i])[0]
        acts.append(int(rng.choice(legal)))
    obs, mask, rew, done, wins = env.step(np.array(acts))
    ndone += int(done.sum())
dt = time.perf_counter() - t0
env.close()
print(f"    {steps} steps x4 envs em {dt:.1f}s = {steps*4/dt:,.0f} decisões/s; "
      f"{ndone} partidas terminadas; reward médio {rew.mean():+.4f}")
print("[OK] smoke test passou")
