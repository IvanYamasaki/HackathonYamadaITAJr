"""
Ponto de entrada do Torneio de Poker — ITA Jr | Treinamento POO
================================================================

Execute da raiz do projeto:

    python run_tournament.py                   # 1000 partidas (padrão)
    python run_tournament.py --games 200       # N partidas
    python run_tournament.py --per-game 4      # máximo 4 bots por partida
    python run_tournament.py --verbose         # imprime cada ação (lento)

Para adicionar seu bot ao torneio:
    1. Copie players/player_template.py  →  players/player_SEU_NOME.py
    2. Implemente o método decision()
    3. Execute este script
"""
import sys
import argparse
from pathlib import Path

# Adiciona src/ ao path para importar a engine
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from tournament.tournament import Tournament


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Torneio de Poker com bots da pasta players/"
    )
    parser.add_argument(
        "--games", type=int, default=1000,
        help="Número de partidas a jogar (padrão: 1000)"
    )
    parser.add_argument(
        "--per-game", type=int, default=None,
        dest="per_game",
        help="Máximo de bots por partida (padrão: todos)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Imprime cada ação de jogo (muito lento para muitas partidas)"
    )
    args = parser.parse_args()

    players_dir = ROOT / "players"
    if not players_dir.exists():
        print(f"Pasta '{players_dir}' não encontrada.")
        print("Crie a pasta players/ e adicione seus bots lá.")
        sys.exit(1)

    print(f"\nTorneio de Poker — ITA Jr")
    print(f"Bots: {players_dir}")
    print(f"Partidas: {args.games}")
    if args.per_game:
        print(f"Bots por partida: {args.per_game}")
    print()

    t = Tournament(
        players_dir=players_dir,
        num_games=args.games,
        players_per_game=args.per_game,
        verbose=args.verbose,
    )

    t.run()
    t.print_leaderboard()


if __name__ == "__main__":
    main()
