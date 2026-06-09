"""
tournament.py — Runner de Torneio
==================================

Carrega todos os bots da pasta `players/`, roda N partidas e produz um ranking.

CONCEITO DE POO: ENCAPSULAMENTO
    A classe `Tournament` encapsula toda a lógica de:
    - descoberta de bots
    - orquestração de partidas
    - coleta de estatísticas
    O chamador só precisa de: Tournament(...).run() + print_leaderboard()

CONCEITO DE POO: COMPOSIÇÃO
    Tournament usa objetos `Game` (sem herdar deles) e acumula `PlayerStats`
    — um bom exemplo de composição vs. herança.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
from typing import Callable


@dataclass
class PlayerStats:
    """
    Estatísticas de desempenho de um bot ao longo do torneio.

    CONCEITO DE POO: DATA CLASS
        @dataclass gera automaticamente __init__, __repr__ e __eq__,
        eliminando código repetitivo — um padrão moderno de POO em Python.
    """
    name: str
    wins: int = 0
    games_played: int = 0
    total_chips_gained: int = 0  # soma de (fichas_finais - fichas_iniciais) por partida

    @property
    def win_rate(self) -> float:
        """Taxa de vitória: wins / games_played."""
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    @property
    def avg_chips_gained(self) -> float:
        """Ganho médio de fichas por partida (positivo = lucrativo)."""
        if self.games_played == 0:
            return 0.0
        return self.total_chips_gained / self.games_played


class Tournament:
    """
    Orquestrador do torneio: carrega bots, roda partidas, acumula stats.

    Uso básico:
        t = Tournament(players_dir=Path("players"), num_games=1000)
        t.run()
        t.print_leaderboard()

    CONCEITO DE POO: ENCAPSULAMENTO
        O estado interno (stats, factories) é gerenciado internamente.
        A interface pública é minimalista: run() e print_leaderboard().
    """

    def __init__(
        self,
        players_dir: Path,
        num_games: int = 1000,
        players_per_game: int | None = None,
        verbose: bool = False,
    ) -> None:
        """
        players_dir      : pasta onde estão os arquivos player_*.py dos alunos
        num_games        : quantas partidas rodar no total
        players_per_game : se None, todos os bots jogam juntos; se N, seleciona N por partida
        verbose          : se True, imprime cada ação de jogo (lento — use para debug)
        """
        self.players_dir = players_dir
        self.num_games = num_games
        self.players_per_game = players_per_game
        self.verbose = verbose
        self.stats: dict[str, PlayerStats] = {}

    # ─── Interface pública ────────────────────────────────────────────────

    def run(self) -> list[PlayerStats]:
        """
        Executa o torneio completo e retorna o leaderboard ordenado.

        Para cada partida:
        1. Cria instâncias frescas dos bots (sem memória de partidas anteriores)
        2. Roda uma partida completa (até sobrar 1 bot)
        3. Registra os resultados
        """
        # Adiciona src/ ao path antes de carregar qualquer player
        src_dir = str(Path(__file__).resolve().parents[1])
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        from game.game import Game

        factories = self._load_player_factories()
        if len(factories) < 2:
            raise RuntimeError(
                f"Precisa de pelo menos 2 bots em {self.players_dir}/player*.py "
                f"(encontrados: {len(factories)})"
            )

        total = self.num_games
        for game_num in range(total):
            selected_factories = self._select_factories(factories, game_num)
            players = [f() for f in selected_factories]
            starting_chips = {p.name: p.chips for p in players}

            game = Game(players)
            game.verbose = self.verbose
            winner = game.play_game()

            self._record_results(players, starting_chips, winner)

            # Progresso a cada 10%
            if (game_num + 1) % max(1, total // 10) == 0:
                pct = (game_num + 1) / total * 100
                print(f"  {pct:5.1f}% — {game_num + 1}/{total} partidas concluídas")

        return self.leaderboard()

    def leaderboard(self) -> list[PlayerStats]:
        """Retorna os bots ordenados por win_rate (decrescente)."""
        return sorted(self.stats.values(), key=lambda s: s.win_rate, reverse=True)

    def print_leaderboard(self) -> None:
        """Imprime a tabela de resultados do torneio."""
        board = self.leaderboard()
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  LEADERBOARD — {self.num_games} partidas")
        print(sep)
        print(f"  {'#':<4} {'Bot':<22} {'Vitórias':<10} {'Win %':<10} {'Fichas/jogo'}")
        print(f"  {'-'*55}")
        for rank, s in enumerate(board, 1):
            print(
                f"  {rank:<4} {s.name:<22} {s.wins:<10} "
                f"{s.win_rate:>6.1%}    {s.avg_chips_gained:>+.0f}"
            )
        print(f"{sep}\n")

    # ─── Métodos privados ─────────────────────────────────────────────────

    def _load_player_factories(self) -> list[Callable]:
        """
        Descobre bots em `players_dir` e retorna uma lista de callables.
        Cada callable, quando chamado, cria uma instância fresca do bot.

        Retornar factories (não instâncias) garante que cada partida comece
        com bots sem estado residual de partidas anteriores.
        """
        factories: list[Callable] = []

        for py_file in sorted(self.players_dir.glob("player*.py")):
            if py_file.name in ("player.py", "player_template.py"):
                continue

            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"  [aviso] Erro ao carregar {py_file.name}: {e}")
                continue

            create_fn = getattr(module, "create_player", None)
            if create_fn is None or not callable(create_fn):
                print(f"  [aviso] {py_file.name} não tem função create_player() — ignorado")
                continue

            try:
                params = list(signature(create_fn).parameters.values())
            except Exception:
                params = []

            # Cria uma factory que gera instâncias com nome baseado no arquivo
            if len(params) == 0:
                factory = create_fn
            elif len(params) == 1:
                stem = py_file.stem
                factory = lambda s=stem, fn=create_fn: fn(s)
            else:
                print(f"  [aviso] create_player() em {py_file.name} tem muitos parâmetros — ignorado")
                continue

            factories.append(factory)

        return factories

    def _select_factories(self, factories: list[Callable], game_num: int) -> list[Callable]:
        """
        Seleciona quais bots jogarão esta partida.
        Se players_per_game for None ou >= total de bots, usa todos.
        Caso contrário, rotaciona para que todos joguem quantidade igual de partidas.
        """
        n = len(factories)
        k = self.players_per_game
        if k is None or k >= n:
            return factories

        # Rotação: desloca a janela de k bots a cada partida
        start = game_num % n
        indices = [(start + i) % n for i in range(k)]
        return [factories[i] for i in indices]

    def _record_results(self, players, starting_chips: dict[str, int], winner) -> None:
        """Atualiza as estatísticas de cada bot após uma partida."""
        for p in players:
            if p.name not in self.stats:
                self.stats[p.name] = PlayerStats(p.name)
            s = self.stats[p.name]
            s.games_played += 1
            s.total_chips_gained += p.chips - starting_chips.get(p.name, 0)
            if winner is not None and winner.name == p.name:
                s.wins += 1


# ─── Workers de paralelização (nível de módulo, picláveis) ─────────────────────
#
# Cada processo-worker recarrega as factories dos bots uma única vez (via
# _worker_init) e depois executa confrontos inteiros. As factories (lambdas +
# módulos importados via importlib) NÃO são picláveis, por isso são reconstruídas
# dentro de cada worker em vez de enviadas por pickle — só nomes e ints trafegam.

_WORKER_FACTORIES: dict[str, Callable] = {}
_WORKER_VERBOSE: bool = False


def _physical_core_count() -> int:
    """
    Estima o nº de núcleos FÍSICOS (não threads/hyperthreads).

    O timeout de 50 ms por decisão é medido em relógio de parede. Rodar mais
    processos CPU-bound do que núcleos físicos faz cada decisão demorar mais em
    relógio (contenção de hyperthread), disparando timeouts espúrios que
    distorceriam os resultados. Por isso o padrão é núcleos físicos.
    """
    # /proc/cpuinfo: conta pares (physical id, core id) distintos no Linux.
    try:
        physical: set[tuple[str, str]] = set()
        phys_id = core_id = None
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("physical id"):
                    phys_id = line.split(":")[1].strip()
                elif line.startswith("core id"):
                    core_id = line.split(":")[1].strip()
                elif line.strip() == "" and phys_id is not None and core_id is not None:
                    physical.add((phys_id, core_id))
                    phys_id = core_id = None
        if physical:
            return len(physical)
    except OSError:
        pass
    # Fallback: assume 2 threads por núcleo.
    logical = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    return max(1, logical // 2)


def _default_workers() -> int:
    """Padrão de workers: núcleos físicos, respeitando a afinidade do processo."""
    phys = _physical_core_count()
    if hasattr(os, "sched_getaffinity"):
        phys = min(phys, len(os.sched_getaffinity(0)))
    return max(1, phys)


def _worker_init(players_dir_str: str, verbose: bool) -> None:
    """Inicializador de cada processo-worker: carrega as factories uma vez."""
    global _WORKER_FACTORIES, _WORKER_VERBOSE
    # Garante BLAS single-thread também sob 'spawn' (no 'fork' já vem do pai).
    for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(_var, "1")
    _WORKER_VERBOSE = verbose
    # Reusa o loader existente (mesma semântica de nome: f().name).
    t = HeadsUpTournament(Path(players_dir_str), verbose=verbose)
    _WORKER_FACTORIES = {f().name: f for f in t._load_player_factories()}


def _run_matchup_worker(task: tuple[str, str, int]) -> tuple[str, str, int, int, int]:
    """Roda um lote de `games` partidas. Retorna (a, b, wins_a, wins_b, timeouts)."""
    name_a, name_b, games = task
    from game.game import Game

    fa, fb = _WORKER_FACTORIES[name_a], _WORKER_FACTORIES[name_b]
    wins_a = wins_b = timeouts = 0
    for _ in range(games):
        game = Game([fa(), fb()])
        game.verbose = _WORKER_VERBOSE
        # Silencia o spam de avisos por-decisão (bots lentos geram milhões deles).
        game.suppress_warnings = True
        winner = game.play_game()
        timeouts += game.timeouts
        if winner is not None:
            if winner.name == name_a:
                wins_a += 1
            else:
                wins_b += 1
    return name_a, name_b, wins_a, wins_b, timeouts


class HeadsUpTournament(Tournament):
    """
    Torneio round-robin heads-up: cada par de bots disputa
    games_per_matchup partidas 1v1 e os resultados são exibidos
    numa matriz de confrontos com intervalo de confiança de 95%.

    CONCEITO DE POO: HERANÇA
        Herda _load_player_factories() do Tournament sem duplicar código.
        Apenas run() e print_leaderboard() são sobrescritos.
    """

    def __init__(
        self,
        players_dir: Path,
        games_per_matchup: int = 2000,
        verbose: bool = False,
        bot_whitelist: set[str] | None = None,
        workers: int | None = None,
    ) -> None:
        super().__init__(players_dir=players_dir, num_games=0, verbose=verbose)
        self.games_per_matchup = games_per_matchup
        self.bot_whitelist = bot_whitelist
        # Nº de processos paralelos. None = padrão (núcleos físicos).
        self.workers = workers
        # Total de decisões estouradas por timeout no torneio (preenchido em run()).
        self.timeouts: int = 0
        # (name_a, name_b) -> [wins_a, wins_b]
        self.results: dict[tuple[str, str], list[int, int]] = {}

    # ─── Interface pública ────────────────────────────────────────────────

    def run(self) -> None:  # type: ignore[override]
        """
        Executa o torneio round-robin: todos os pares possíveis, cada um
        com games_per_matchup partidas. Ao final chama print_leaderboard().
        """
        src_dir = str(Path(__file__).resolve().parents[1])
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        factories = self._load_player_factories()
        names = [f().name for f in factories]

        if self.bot_whitelist:
            filtered = [(n, f) for n, f in zip(names, factories) if n in self.bot_whitelist]
            unknown = self.bot_whitelist - {n for n, _ in filtered}
            if unknown:
                print(f"  [aviso] Bots não encontrados: {', '.join(sorted(unknown))}")
            names = [n for n, _ in filtered]
            factories = [f for _, f in filtered]

        if len(factories) < 2:
            raise RuntimeError(
                f"Precisa de pelo menos 2 bots em {self.players_dir}/player*.py "
                f"(encontrados: {len(factories)})"
            )

        pairs = [(i, j) for i in range(len(names)) for j in range(i + 1, len(names))]
        total_matchups = len(pairs)
        workers = self.workers or _default_workers()

        # Divide as partidas de CADA confronto em lotes, distribuídos entre os
        # workers. Isso evita que o confronto mais lento (bots que estouram o
        # timeout de 50 ms) vire um piso de tempo numa única CPU: os 2000 jogos
        # de um par espalham-se por vários núcleos.
        tasks: list[tuple[str, str, int]] = []
        for (i, j) in pairs:
            for chunk in self._chunk_sizes(self.games_per_matchup, workers):
                tasks.append((names[i], names[j], chunk))

        # Inicializa o placar de cada par (acumulado a partir dos lotes).
        for (i, j) in pairs:
            self.results[(names[i], names[j])] = [0, 0]

        print(
            f"  {len(names)} bots → {total_matchups} confronto(s) "
            f"× {self.games_per_matchup} partidas cada\n"
            f"  {len(tasks)} lote(s) em {workers} processo(s) paralelo(s)…\n"
        )

        done_games = 0
        total_timeouts = 0
        total_games = total_matchups * self.games_per_matchup
        step = max(1, total_games // 20)
        next_mark = step

        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(str(self.players_dir), self.verbose),
        ) as executor:
            for name_a, name_b, wins_a, wins_b, timeouts in executor.map(
                _run_matchup_worker, tasks
            ):
                acc = self.results[(name_a, name_b)]
                acc[0] += wins_a
                acc[1] += wins_b
                done_games += wins_a + wins_b
                total_timeouts += timeouts
                if done_games >= next_mark:
                    pct = done_games / total_games * 100
                    print(f"  {pct:5.1f}%  ({done_games}/{total_games} partidas)")
                    next_mark += step

        self.timeouts = total_timeouts
        print(
            f"\n  Decisões estouradas por timeout (50 ms): {total_timeouts:,} "
            f"(~{total_timeouts / max(1, total_games):.1f}/partida)"
        )
        self.print_leaderboard()

    @staticmethod
    def _chunk_sizes(total: int, workers: int) -> list[int]:
        """
        Divide `total` partidas em lotes balanceados.

        Alvo: ~`workers` lotes por confronto (mas com no máx. ~250 partidas/lote),
        para que confrontos lentos se espalhem por vários núcleos sem criar
        tarefas minúsculas demais. Retorna a lista de tamanhos (somam `total`).
        """
        if total <= 0:
            return []
        n_chunks = max(1, min(workers, math.ceil(total / 250)))
        base, rem = divmod(total, n_chunks)
        return [base + (1 if k < rem else 0) for k in range(n_chunks)]

    def get_advancing_bots(self, n: int) -> list[str]:
        """Retorna os nomes dos top-n bots pelo leaderboard (pontos de confronto, depois WR)."""
        rows = self._build_leaderboard_rows()
        return [name for name, *_ in rows[:n]]

    def print_leaderboard(self) -> None:  # type: ignore[override]
        """Imprime a matriz de confrontos e o leaderboard com IC 95%."""
        all_names = list(dict.fromkeys(n for pair in self.results for n in pair))
        col_w = max(10, max(len(n) for n in all_names) + 1)
        sep = "=" * max(60, col_w * (len(all_names) + 1) + 4)

        # ── Matriz de confrontos ──────────────────────────────────────
        print(f"\n{sep}")
        print("  MATRIZ DE CONFRONTOS (win rate de cada linha vs coluna)")
        print(sep)

        print("  " + " " * col_w + "".join(f"  {nm:>{col_w}}" for nm in all_names))
        for row in all_names:
            line = f"  {row:>{col_w}}"
            for col in all_names:
                if row == col:
                    line += f"  {'—':>{col_w}}"
                else:
                    wr = self._wr_of(row, col)
                    line += f"  {wr:>{col_w - 1}.1%}"
            print(line)

        # ── Leaderboard ───────────────────────────────────────────────
        print(f"\n{sep}")
        print(
            f"  LEADERBOARD — Round-Robin Heads-Up "
            f"({self.games_per_matchup} partidas/par)"
        )
        print(sep)
        print(f"  {'#':<4} {'Bot':<22} {'Pontos':<10} {'WR geral':<12} {'IC 95%'}")
        print(f"  {'-'*57}")

        rows = self._build_leaderboard_rows()

        for rank, (name, mw, total_m, avg_wr, margin) in enumerate(rows, 1):
            print(
                f"  {rank:<4} {name:<22} {mw:g}/{total_m:<8} "
                f"{avg_wr:>8.1%}    [±{margin:.1%}]"
            )
        print(f"{sep}\n")

    # ─── Helpers privados ─────────────────────────────────────────────────

    def _build_leaderboard_rows(self) -> list[tuple]:
        """Constrói e ordena as linhas do leaderboard (pontos de confronto, depois WR)."""
        all_names = list(dict.fromkeys(n for pair in self.results for n in pair))
        rows = []
        for name in all_names:
            matchup_wins = 0.0
            total_game_wins = 0
            total_games = 0
            for other in all_names:
                if other == name:
                    continue
                wr = self._wr_of(name, other)
                if wr > 0.5:
                    matchup_wins += 1          # venceu o confronto → 1 ponto
                elif wr == 0.5:
                    matchup_wins += 0.5        # empate (50%) → meio ponto p/ cada
                wa, wb = self._raw(name, other)
                total_game_wins += wa
                total_games += wa + wb
            avg_wr, margin = self._ci(total_game_wins, total_games)
            rows.append((name, matchup_wins, len(all_names) - 1, avg_wr, margin))
        rows.sort(key=lambda r: (r[1], r[3]), reverse=True)
        return rows

    def _raw(self, name_a: str, name_b: str) -> tuple[int, int]:
        """Retorna (wins_a, wins_b) para o par, independente da ordem armazenada."""
        if (name_a, name_b) in self.results:
            return tuple(self.results[(name_a, name_b)])
        wa, wb = self.results[(name_b, name_a)]
        return wb, wa

    def _wr_of(self, name_a: str, name_b: str) -> float:
        """Win rate de name_a contra name_b."""
        wa, wb = self._raw(name_a, name_b)
        total = wa + wb
        return wa / total if total else 0.5

    def _ci(self, wins: int, n: int) -> tuple[float, float]:
        """Retorna (win_rate, margem_IC_95%) pelo método de Wald."""
        if n == 0:
            return 0.0, 0.0
        p = wins / n
        margin = 1.96 * math.sqrt(p * (1 - p) / n)
        return p, margin
