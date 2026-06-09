"""
Torneio de Poker completo com geração de imagens — ITA Jr | Yamada Poker Clube
==============================================================================

Execute da raiz do projeto:

    # Fase 1 (todos os bots, padrão)
    python3 run_full_tournament.py
    python3 run_full_tournament.py --phase1

    # Fase 2 (bots classificados)
    python3 run_full_tournament.py --phase2 --bots "player_ana,player_joao"

    # Debug rápido (menos partidas)
    python3 run_full_tournament.py --games-per-matchup 50

Imagens salvas em results/:
    matrix_fase1.png     — Heatmap de win rates (linha vs coluna)
    leaderboard_fase1.png — Barras horizontais com pontuação e IC 95%
"""
import os

# Força bibliotecas de álgebra (numpy/BLAS) a usarem 1 thread por processo.
# Sem isso, cada worker do torneio dispara N threads de BLAS → N×workers threads
# em CPU-bound → relógio de cada decisão infla e estoura o timeout de 50 ms.
# Precisa vir ANTES de importar numpy/matplotlib.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sem janela (salva diretamente em arquivo)
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from tournament.tournament import HeadsUpTournament


# ─── Visualizações ────────────────────────────────────────────────────────────

def _sorted_names(tournament: HeadsUpTournament) -> list[str]:
    """Nomes dos bots na ordem do leaderboard (melhor primeiro)."""
    rows = tournament._build_leaderboard_rows()
    return [r[0] for r in rows]


def plot_match_matrix(tournament: HeadsUpTournament, phase_label: str, output_dir: Path) -> Path:
    """Salva heatmap N×N de win rates (linha vence coluna em %)."""
    names = _sorted_names(tournament)
    n = len(names)
    idx = {name: i for i, name in enumerate(names)}

    # Monta matriz: cell[i][j] = WR do bot i contra bot j
    data = np.full((n, n), np.nan)
    for i, row in enumerate(names):
        for j, col in enumerate(names):
            if row != col:
                data[i, j] = tournament._wr_of(row, col)

    fig_w = max(10, n * 1.4)
    fig_h = max(8, n * 1.1)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Colormap divergente: vermelho < 50% < verde
    norm = mcolors.TwoSlopeNorm(vmin=0.0, vcenter=0.5, vmax=1.0)
    cmap = plt.get_cmap("RdYlGn")

    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, cmap=cmap, norm=norm, aspect="auto")

    # Diagonal cinza
    for k in range(n):
        ax.add_patch(plt.Rectangle((k - 0.5, k - 0.5), 1, 1, color="#CCCCCC", zorder=0))

    # Anotações nas células
    for i in range(n):
        for j in range(n):
            if i == j:
                ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#888888")
            else:
                wr = data[i, j]
                txt_color = "white" if (wr < 0.35 or wr > 0.65) else "black"
                ax.text(j, i, f"{wr:.0%}", ha="center", va="center",
                        fontsize=8, color=txt_color, fontweight="bold")

    # Eixos
    short_names = [_shorten(name) for name in names]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(short_names, fontsize=9)
    ax.set_xlabel("Oponente (coluna)", fontsize=11)
    ax.set_ylabel("Bot (linha)", fontsize=11)
    ax.set_title(
        f"Matriz de Confrontos — {phase_label}\n"
        f"({tournament.games_per_matchup} partidas/par  ·  win rate da linha contra a coluna)",
        fontsize=13, fontweight="bold", pad=14,
    )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Win Rate", fontsize=10)
    cbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    plt.tight_layout()
    path = output_dir / f"matrix_{_slug(phase_label)}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Imagem salva: {path}")
    return path


def plot_leaderboard(
    tournament: HeadsUpTournament,
    phase_label: str,
    output_dir: Path,
    n_advancing: int | None = None,
) -> Path:
    """Salva gráfico de barras horizontais com pontuação e IC 95%."""
    rows = tournament._build_leaderboard_rows()
    # rows: (name, matchup_wins, total_matchups, avg_wr, margin) — melhor primeiro
    n = len(rows)

    wrs     = [r[3] for r in rows]
    margins = [r[4] for r in rows]

    # Cores: ouro/prata/bronze para top 3, azul para os demais
    rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
    bar_colors = [rank_colors[i] if i < 3 else "#6BAED6" for i in range(n)]

    # y=0 para rank 1, y=n-1 para rank n; invert_yaxis coloca rank 1 no topo
    y_pos = list(range(n))

    # Labels com número do ranking embutido (evita sobreposição com texto externo)
    y_labels = [f"#{i + 1}  {_shorten(r[0])}" for i, r in enumerate(rows)]

    fig_h = max(6, n * 0.75 + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))

    bars = ax.barh(
        y_pos, wrs,
        xerr=margins,
        color=bar_colors,
        alpha=0.88,
        height=0.6,
        error_kw={"capsize": 4, "ecolor": "#333333", "elinewidth": 1.5},
    )

    # Rank 1 no topo (y=0 vira o topo após invert)
    ax.invert_yaxis()

    # Linha de 50%
    ax.axvline(x=0.5, color="#888888", linestyle="--", linewidth=1.2, alpha=0.7)

    # Linha de corte de avanço (Fase 1): entre rank n_advancing e n_advancing+1
    if n_advancing is not None and 0 < n_advancing < n:
        cutoff_y = n_advancing - 0.5
        ax.axhline(y=cutoff_y, color="#1F77B4", linestyle=":", linewidth=2.0, alpha=0.85)
        ax.text(
            0.51, cutoff_y - 0.15,
            f"← Avança para Fase 2  (top {n_advancing})",
            color="#1F77B4", fontsize=9, va="bottom",
        )

    # Anotações à direita: pontos + WR (mesmo índice que bars e rows)
    for bar, row in zip(bars, rows):
        _, mw, tm, wr, mg = row
        x_end = bar.get_width() + mg
        ax.text(
            x_end + 0.012, bar.get_y() + bar.get_height() / 2,
            f"{mw:g}/{tm} pts  |  {wr:.1%} [±{mg:.1%}]",
            va="center", fontsize=9, color="#222222",
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(y_labels, fontsize=10)
    ax.set_xlabel("Win Rate geral", fontsize=11)
    ax.set_xlim(0, 1.38)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.set_title(
        f"Leaderboard — {phase_label}\n"
        f"({tournament.games_per_matchup} partidas/confronto  ·  pontuação = confrontos vencidos (empate = ½)  ·  IC 95% Wald)",
        fontsize=13, fontweight="bold", pad=12,
    )

    plt.tight_layout()
    path = output_dir / f"leaderboard_{_slug(phase_label)}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Imagem salva: {path}")
    return path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _shorten(name: str, max_len: int = 22) -> str:
    return name if len(name) <= max_len else name[:max_len - 1] + "…"


def _slug(label: str) -> str:
    return label.lower().replace(" ", "_")


# ─── Salvamento de logs ─────────────────────────────────────────────────────────

def save_tournament_log(
    tournament: HeadsUpTournament,
    phase_label: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """
    Salva os resultados agregados do torneio:
      - log_<slug>_<timestamp>.json : config + matriz bruta de vitórias + leaderboard
      - console_<slug>.txt           : matriz de confrontos + leaderboard formatados

    Retorna (caminho_json, caminho_txt).
    """
    slug = _slug(phase_label)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Matriz bruta de vitórias por confronto (uma linha por par)
    matchups = [
        {"a": a, "b": b, "wins_a": wins[0], "wins_b": wins[1]}
        for (a, b), wins in tournament.results.items()
    ]

    # Leaderboard: (name, matchup_wins, total_matchups, avg_wr, margin)
    leaderboard = [
        {
            "rank": rank,
            "name": name,
            "matchup_wins": matchup_wins,
            "total_matchups": total_matchups,
            "avg_wr": avg_wr,
            "margin": margin,
        }
        for rank, (name, matchup_wins, total_matchups, avg_wr, margin)
        in enumerate(tournament._build_leaderboard_rows(), 1)
    ]

    n_bots = len(set(n for pair in tournament.results for n in pair))
    payload = {
        "phase": phase_label,
        "games_per_matchup": tournament.games_per_matchup,
        "timestamp": timestamp,
        "n_bots": n_bots,
        "matchups": matchups,
        "leaderboard": leaderboard,
    }

    json_path = output_dir / f"log_{slug}_{timestamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Log salvo: {json_path}")

    # Captura a saída formatada (matriz + leaderboard) reusando print_leaderboard()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        tournament.print_leaderboard()
    txt_path = output_dir / f"console_{slug}.txt"
    txt_path.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"  Console salvo: {txt_path}")

    return json_path, txt_path


# ─── Runner de fase ───────────────────────────────────────────────────────────

def run_phase(
    phase_label: str,
    players_dir: Path,
    games_per_matchup: int,
    verbose: bool,
    bot_whitelist: set[str] | None = None,
    workers: int | None = None,
) -> HeadsUpTournament:
    """Roda uma fase do torneio e gera as imagens. Retorna o objeto do torneio."""
    print(f"\nTorneio de Poker — ITA Jr × Yamada  [{phase_label.upper()}]")
    if bot_whitelist:
        print(f"Bots: {', '.join(sorted(bot_whitelist))}")
    else:
        print(f"Bots: {players_dir}")
    print(f"Partidas por confronto: {games_per_matchup}\n")

    t = HeadsUpTournament(
        players_dir=players_dir,
        games_per_matchup=games_per_matchup,
        verbose=verbose,
        bot_whitelist=bot_whitelist,
        workers=workers,
    )
    t.run()

    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    print("\nGerando imagens…")
    plot_match_matrix(t, phase_label, results_dir)

    all_names = list(dict.fromkeys(n for pair in t.results for n in pair))
    n_advancing = max(2, len(all_names) // 2) if phase_label.lower() == "fase 1" else None
    plot_leaderboard(t, phase_label, results_dir, n_advancing=n_advancing)

    print("\nSalvando logs…")
    save_tournament_log(t, phase_label, results_dir)

    return t


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Torneio de Poker com geração de imagens — ITA Jr"
    )
    parser.add_argument("--phase1", action="store_true", dest="phase1",
                        help="Fase 1: round-robin com todos os bots (padrão)")
    parser.add_argument("--phase2", action="store_true", dest="phase2",
                        help="Fase 2: round-robin apenas com os bots em --bots")
    parser.add_argument("--bots", type=str, default=None,
                        help="Lista de bots para Fase 2, separados por vírgula")
    parser.add_argument("--games-per-matchup", type=int, default=2000,
                        dest="games_per_matchup",
                        help="Partidas por confronto (padrão: 2000)")
    parser.add_argument("--verbose", action="store_true",
                        help="Imprime cada ação (muito lento)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Nº de processos paralelos (padrão: todos os núcleos)")
    args = parser.parse_args()

    players_dir = ROOT / "players"
    if not players_dir.exists():
        print(f"Pasta '{players_dir}' não encontrada.")
        sys.exit(1)

    if args.phase2:
        if not args.bots:
            print("Erro: --phase2 requer --bots com a lista de bots classificados.")
            print('Exemplo: python3 run_full_tournament.py --phase2 --bots "player_ana,player_joao"')
            sys.exit(1)
        whitelist = {name.strip() for name in args.bots.split(",") if name.strip()}
        run_phase("Fase 2", players_dir, args.games_per_matchup, args.verbose,
                  bot_whitelist=whitelist, workers=args.workers)
    else:
        # Fase 1 (padrão quando nenhum flag ou --phase1 explícito)
        t = run_phase("Fase 1", players_dir, args.games_per_matchup, args.verbose,
                      workers=args.workers)

        all_names = list(dict.fromkeys(n for pair in t.results for n in pair))
        n_advancing = max(2, len(all_names) // 2)
        advancing = t.get_advancing_bots(n_advancing)

        sep = "=" * 62
        print(f"\n{sep}")
        print(f"  FASE 1 CONCLUÍDA — {n_advancing} de {len(all_names)} bots avançam")
        print(sep)
        for name in advancing:
            print(f"    {name}")
        print()
        print("  Próximos passos:")
        print("  1. Compartilhe todos os códigos com os participantes")
        print("  2. Colete os bots atualizados (v2) dos classificados")
        print("  3. Substitua os arquivos em players/ e rode a Fase 2:")
        bots_arg = ",".join(advancing)
        print(f'\n  python3 run_full_tournament.py --phase2 --bots "{bots_arg}"')
        print(f"{sep}\n")


if __name__ == "__main__":
    main()
