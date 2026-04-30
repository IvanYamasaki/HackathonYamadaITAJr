import sys
from pathlib import Path

# Permite rodar `python3 tests/test_game_run.py` a partir da raiz
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from game.game import Game, find_players  # noqa: E402


def main() -> None:
    players = find_players()
    if len(players) < 2:
        raise RuntimeError("Precisa de pelo menos 2 players em players/player*.py")

    g = Game(players)
    g.verbose = True
    g.blind_increase_every = 999999  # deixa estável pro teste

    winner = g.play_game()
    print("\n=== FIM ===")
    print("Vencedor:", winner)
    print("Chips:", [(p.name, p.chips) for p in g.players])


if __name__ == "__main__":
    main()

