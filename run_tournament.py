"""
Ponto de entrada do Torneio de Poker — ITA Jr | Yamada Poker Clube
===================================================================

Execute da raiz do projeto:

    # Modo clássico (múltiplos bots por partida, bom para debug)
    python run_tournament.py                          # 1000 partidas
    python run_tournament.py --games 200
    python run_tournament.py --per-game 4             # máximo 4 bots por partida
    python run_tournament.py --verbose

    # Heads-up round-robin simples (todos vs todos, uma fase)
    python run_tournament.py --heads-up
    python run_tournament.py --heads-up --games-per-matchup 500

    # Torneio oficial em duas fases:
    python run_tournament.py --phase1                              # Fase 1 — todos os bots
    python run_tournament.py --phase2 --bots "bot_a,bot_b,bot_c"  # Fase 2 — bots selecionados

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

from tournament.tournament import Tournament, HeadsUpTournament


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Torneio de Poker com bots da pasta players/"
    )
    parser.add_argument(
        "--games", type=int, default=1000,
        help="Número de partidas a jogar no modo clássico (padrão: 1000)"
    )
    parser.add_argument(
        "--per-game", type=int, default=None,
        dest="per_game",
        help="Máximo de bots por partida no modo clássico (padrão: todos)"
    )
    parser.add_argument(
        "--heads-up", action="store_true",
        dest="heads_up",
        help="Modo round-robin 1v1: todos os pares se enfrentam"
    )
    parser.add_argument(
        "--phase1", action="store_true",
        dest="phase1",
        help="Fase 1 do torneio oficial: round-robin com todos os bots, imprime quem avança"
    )
    parser.add_argument(
        "--phase2", action="store_true",
        dest="phase2",
        help="Fase 2 do torneio oficial: round-robin apenas com os bots listados em --bots"
    )
    parser.add_argument(
        "--bots", type=str, default=None,
        help="Lista de bots para a Fase 2, separados por vírgula (ex: 'player_ana,player_joao')"
    )
    parser.add_argument(
        "--games-per-matchup", type=int, default=2000,
        dest="games_per_matchup",
        help="Partidas por confronto nos modos heads-up/phase (padrão: 2000)"
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

    if args.phase1:
        print(f"\nTorneio de Poker — ITA Jr × Yamada  [FASE 1]")
        print(f"Bots: {players_dir}")
        print(f"Partidas por confronto: {args.games_per_matchup}")
        print()

        t = HeadsUpTournament(
            players_dir=players_dir,
            games_per_matchup=args.games_per_matchup,
            verbose=args.verbose,
        )
        t.run()

        # Determina quem avança (top metade, mínimo 2)
        total_bots = len(list(dict.fromkeys(n for pair in t.results for n in pair)))
        n_advancing = max(2, total_bots // 2)
        advancing = t.get_advancing_bots(n_advancing)

        sep = "=" * 60
        print(f"{sep}")
        print(f"  FASE 1 CONCLUÍDA — {n_advancing} de {total_bots} bots avançam")
        print(sep)
        for name in advancing:
            print(f"    {name}")
        print()
        print("  Próximos passos:")
        print("  1. Compartilhe todos os códigos com os participantes")
        print("  2. Colete os bots atualizados (v2) dos classificados")
        print("  3. Substitua os arquivos em players/ e rode a Fase 2:")
        bots_arg = ",".join(advancing)
        print(f'\n  python run_tournament.py --phase2 --bots "{bots_arg}"')
        print(f"{sep}\n")

    elif args.phase2:
        if not args.bots:
            print("Erro: --phase2 requer --bots com a lista de bots classificados.")
            print('Exemplo: python run_tournament.py --phase2 --bots "player_ana,player_joao"')
            sys.exit(1)

        whitelist = {name.strip() for name in args.bots.split(",") if name.strip()}
        print(f"\nTorneio de Poker — ITA Jr × Yamada  [FASE 2 — FINAL]")
        print(f"Bots: {', '.join(sorted(whitelist))}")
        print(f"Partidas por confronto: {args.games_per_matchup}")
        print()

        t = HeadsUpTournament(
            players_dir=players_dir,
            games_per_matchup=args.games_per_matchup,
            verbose=args.verbose,
            bot_whitelist=whitelist,
        )
        t.run()

    elif args.heads_up:
        print(f"\nTorneio de Poker — ITA Jr  [Heads-Up Round-Robin]")
        print(f"Bots: {players_dir}")
        print(f"Partidas por confronto: {args.games_per_matchup}")
        print()

        t = HeadsUpTournament(
            players_dir=players_dir,
            games_per_matchup=args.games_per_matchup,
            verbose=args.verbose,
        )
        t.run()

    else:
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
