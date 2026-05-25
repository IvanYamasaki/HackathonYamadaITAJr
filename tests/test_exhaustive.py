"""
test_exhaustive.py — Suite de testes exaustivos do motor de poker.

Grupos:
  1. Motor de cartas  — baralho, distribuição, avaliação de mãos
  2. Mecânica         — fold/call/raise, tipos inválidos, blinds
  3. GameView         — imutabilidade, campos, board ao longo das rodadas
  4. Partida completa — vencedor único, conservação de chips, bots sample
  5. Torneio          — heads-up round-robin, whitelist, consistência de stats
  6. Robustez         — bots que crasham, tipos inválidos, mutação de GameView
"""
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "src"
PLAYERS_DIR = ROOT / "players"
sys.path.insert(0, str(SRC))

from cards.cards import Card, FullDeck, Hand, Board
from cards.sequences import (
    FullHand, avaliar_cinco_cartas,
    RANK_STRAIGHT_FLUSH, RANK_QUADRA, RANK_FULL_HOUSE,
    RANK_FLUSH, RANK_STRAIGHT, RANK_TRINCA,
    RANK_DOIS_PARES, RANK_UM_PAR, RANK_CARTA_ALTA,
)
from game.game import Game
from game.game_view import GameView, PublicPlayerInfo
from players.player import Player


# ── Bots auxiliares ───────────────────────────────────────────────────────────

class FoldBot(Player):
    def decision(self, gv): return -1

class CallBot(Player):
    def decision(self, gv): return 0

class RaiseBot(Player):
    def decision(self, gv):
        return gv.current_bet + gv.big_blind

class CrashBot(Player):
    def decision(self, gv):
        raise RuntimeError("erro intencional")

class ReturnBot(Player):
    """Sempre retorna o mesmo valor, independente do tipo."""
    def __init__(self, name: str, ret_val):
        super().__init__(name, Hand(), 0)
        self._ret = ret_val
    def decision(self, gv):
        return self._ret


def new_game(*bots, verbose=False, no_blinds=True):
    g = Game(list(bots))
    g.verbose = verbose
    if no_blinds:
        g.blind_increase_every = 999_999
    return g


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 1 — Motor de cartas
# ═══════════════════════════════════════════════════════════════════════════════

def test_deck_has_52_cards():
    assert len(FullDeck().cards) == 52


def test_deck_all_cards_unique():
    strs = [str(c) for c in FullDeck().cards]
    assert len(strs) == len(set(strs))


def test_pull_card_reduces_deck_by_one():
    deck = FullDeck()
    deck.pull_card()
    assert len(deck.cards) == 51


def test_no_duplicate_cards_dealt_in_one_round():
    deck = FullDeck()
    hand = Hand()
    board = Board()
    hand.give_cards(deck)
    board.flop(deck)
    board.turn(deck)
    board.river(deck)
    all_strs = [str(c) for c in list(hand.cards) + list(board.cards)]
    assert len(all_strs) == len(set(all_strs)), f"Duplicadas: {sorted(all_strs)}"


def test_hand_ranking_order():
    """Royal flush > quadra > ... > carta alta."""
    sf = [Card("A","s"), Card("K","s"), Card("Q","s"), Card("J","s"), Card("10","s")]
    q4 = [Card("A","s"), Card("A","h"), Card("A","d"), Card("A","c"), Card("K","s")]
    fh = [Card("A","s"), Card("A","h"), Card("A","d"), Card("K","c"), Card("K","s")]
    fl = [Card("A","s"), Card("K","s"), Card("Q","s"), Card("J","s"), Card("9","s")]
    st = [Card("A","s"), Card("K","h"), Card("Q","d"), Card("J","c"), Card("10","s")]
    tr = [Card("A","s"), Card("A","h"), Card("A","d"), Card("K","c"), Card("Q","s")]
    dp = [Card("A","s"), Card("A","h"), Card("K","d"), Card("K","c"), Card("Q","s")]
    up = [Card("A","s"), Card("A","h"), Card("K","d"), Card("Q","c"), Card("J","s")]
    ca = [Card("A","s"), Card("K","h"), Card("Q","d"), Card("J","c"), Card("9","s")]

    ranks = [avaliar_cinco_cartas(h)[0] for h in [sf, q4, fh, fl, st, tr, dp, up, ca]]
    assert ranks == sorted(ranks, reverse=True), f"Ranking fora de ordem: {ranks}"
    assert len(set(ranks)) == len(ranks), "Rankings com empate inesperado"


def test_wheel_straight_recognized():
    wheel = [Card("A","s"), Card("2","h"), Card("3","d"), Card("4","c"), Card("5","s")]
    rank, vals = avaliar_cinco_cartas(wheel)
    assert rank == RANK_STRAIGHT
    assert vals == [5, 4, 3, 2, 1]


def test_board_card_progression():
    deck = FullDeck()
    board = Board()
    assert len(board.cards) == 0
    board.flop(deck);  assert len(board.cards) == 3
    board.turn(deck);  assert len(board.cards) == 4
    board.river(deck); assert len(board.cards) == 5


def test_fullhand_score_increases_with_better_hand():
    """Uma quadra deve ter score maior que um par."""
    deck_q = FullDeck()
    deck_p = FullDeck()

    # Monta hand/board com quadra de Ás manualmente
    hand_q = Hand()
    hand_q.cards = [Card("A","s"), Card("A","h")]
    board_q = Board()
    board_q.cards = {Card("A","d"), Card("A","c"), Card("K","s")}

    # Monta hand/board com um par de 2s
    hand_p = Hand()
    hand_p.cards = [Card("2","s"), Card("2","h")]
    board_p = Board()
    board_p.cards = {Card("3","d"), Card("4","c"), Card("K","s")}

    score_q = FullHand(hand_q, board_q).score_hand()
    score_p = FullHand(hand_p, board_p).score_hand()
    assert score_q > score_p


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 2 — Mecânica de apostas
# ═══════════════════════════════════════════════════════════════════════════════

def test_folder_loses_chips_to_caller():
    """FoldBot sempre folda e deve perder chips para CallBot."""
    folder = FoldBot("folder", Hand(), 0)
    caller = CallBot("caller", Hand(), 0)
    g = new_game(folder, caller)
    g.play_game()
    assert folder.chips < caller.chips


def test_chips_conserved_during_full_game():
    """Soma de chips deve ser constante ao longo de toda a partida."""
    p1 = CallBot("a", Hand(), 0)
    p2 = RaiseBot("b", Hand(), 0)
    g = new_game(p1, p2)
    total_before = sum(p.chips for p in g.players)
    g.play_game()
    total_after = sum(p.chips for p in g.players)
    assert total_after == total_before, (
        f"Chips: antes={total_before}, depois={total_after}"
    )


def test_chips_conserved_repeated():
    """Chips conservados em 30 partidas distintas."""
    for i in range(30):
        p1 = CallBot(f"a{i}", Hand(), 0)
        p2 = RaiseBot(f"b{i}", Hand(), 0)
        g = new_game(p1, p2, no_blinds=False)
        total = sum(p.chips for p in g.players)
        g.play_game()
        assert sum(p.chips for p in g.players) == total, f"Partida {i}: chips vazaram"


def test_invalid_action_string_no_crash():
    bot = ReturnBot("str_bot", "fold")
    caller = CallBot("caller", Hand(), 0)
    bot.chips = 5000
    caller.chips = 5000
    g = new_game(bot, caller)
    g.play_game()  # não deve levantar exceção


def test_invalid_action_float_no_crash():
    bot = ReturnBot("float_bot", 2.5)
    caller = CallBot("caller", Hand(), 0)
    bot.chips = 5000
    caller.chips = 5000
    g = new_game(bot, caller)
    g.play_game()


def test_invalid_action_none_no_crash():
    bot = ReturnBot("none_bot", None)
    caller = CallBot("caller", Hand(), 0)
    bot.chips = 5000
    caller.chips = 5000
    g = new_game(bot, caller)
    g.play_game()


def test_invalid_action_bool_no_crash():
    bot = ReturnBot("bool_bot", True)
    caller = CallBot("caller", Hand(), 0)
    bot.chips = 5000
    caller.chips = 5000
    g = new_game(bot, caller)
    g.play_game()


def test_invalid_action_negative_no_crash():
    """Ação -5 (negativo inválido) não deve causar crash nem ação silenciosa."""
    bot = ReturnBot("neg_bot", -5)
    caller = CallBot("caller", Hand(), 0)
    bot.chips = 5000
    caller.chips = 5000
    g = new_game(bot, caller)
    g.play_game()
    # -5 deve ser convertido para call (0); chips devem ser conservados
    total = bot.chips + caller.chips
    assert total == 10_000


def test_bot_exception_in_decision_no_crash():
    """Bot que lança RuntimeError em decision() não deve interromper o torneio."""
    crash = CrashBot("crash", Hand(), 0)
    caller = CallBot("caller", Hand(), 0)
    crash.chips = 5000
    caller.chips = 5000
    g = new_game(crash, caller)
    g.play_game()  # deve terminar normalmente


def test_blind_increase_every_5_hands():
    p1 = CallBot("a", Hand(), 0)
    p2 = CallBot("b", Hand(), 0)
    g = new_game(p1, p2)
    g.blind_increase_every = 5
    initial_sb = g.small_blind
    initial_bb = g.big_blind

    for _ in range(5):
        g.increase_blinds_if_needed()

    assert g.big_blind == initial_bb * 2
    assert g.small_blind == initial_sb * 2


def test_blind_no_increase_before_threshold():
    p1 = CallBot("a", Hand(), 0)
    p2 = CallBot("b", Hand(), 0)
    g = new_game(p1, p2)
    g.blind_increase_every = 5
    initial_bb = g.big_blind

    for _ in range(4):
        g.increase_blinds_if_needed()

    assert g.big_blind == initial_bb  # ainda não dobrou


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 3 — GameView
# ═══════════════════════════════════════════════════════════════════════════════

def test_gameview_is_immutable():
    gv = GameView(
        board=(), my_hand=(), my_chips=100, my_name="x",
        pot=0, current_bet=0, to_call=0,
        dealer_position=0, small_blind=5, big_blind=10, opponents=()
    )
    with pytest.raises(Exception):
        gv.pot = 9999  # type: ignore


def test_publicplayerinfo_has_no_hand_field():
    opp = PublicPlayerInfo(name="x", chips=100, current_bet_in_round=0, is_active=True)
    assert not hasattr(opp, "hand")
    assert not hasattr(opp, "cards")


def test_gameview_opponents_carry_no_cards():
    views = []

    class SpyBot(Player):
        def decision(self, gv):
            views.append(gv)
            return 0

    spy = SpyBot("spy", Hand(), 0)
    spy.chips = 5000
    caller = CallBot("caller", Hand(), 0)
    caller.chips = 5000

    g = new_game(spy, caller)
    g.play_game()

    assert len(views) > 0
    for gv in views:
        for opp in gv.opponents:
            assert not hasattr(opp, "hand")
            assert not hasattr(opp, "cards")


def test_gameview_board_never_empty_after_preflop():
    """Após o pre-flop, o board deve sempre ter ≥ 3 cartas no GameView."""
    sizes = []

    class SizeSpy(Player):
        def decision(self, gv):
            sizes.append(len(gv.board))
            return 0

    spy = SizeSpy("spy", Hand(), 0)
    spy.chips = 5000
    caller = CallBot("caller", Hand(), 0)
    caller.chips = 5000

    g = new_game(spy, caller)
    g.play_game()

    assert all(s in (3, 4, 5) for s in sizes), f"Board inesperado: {sizes}"
    assert 5 in sizes, "Board nunca chegou a 5 cartas (river não foi alcançado)"


def test_gameview_my_hand_has_two_cards():
    hands_seen = []

    class HandSpy(Player):
        def decision(self, gv):
            hands_seen.append(len(gv.my_hand))
            return 0

    spy = HandSpy("spy", Hand(), 0)
    spy.chips = 5000
    caller = CallBot("caller", Hand(), 0)
    caller.chips = 5000

    g = new_game(spy, caller)
    g.play_game()

    assert all(h == 2 for h in hands_seen), f"Mão com tamanho errado: {hands_seen}"


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 4 — Partida completa
# ═══════════════════════════════════════════════════════════════════════════════

def test_game_ends_with_single_winner():
    p1 = CallBot("a", Hand(), 0)
    p2 = RaiseBot("b", Hand(), 0)
    winner = new_game(p1, p2).play_game()
    assert winner is not None
    assert winner.name in ("a", "b")


def test_folder_always_loses_to_caller():
    """FoldBot deve ganhar 0 de 50 partidas contra CallerBot."""
    folder_wins = 0
    for _ in range(50):
        folder = FoldBot("folder", Hand(), 0)
        caller = CallBot("caller", Hand(), 0)
        winner = new_game(folder, caller).play_game()
        if winner is not None and winner.name == "folder":
            folder_wins += 1
    assert folder_wins == 0, f"FolderBot ganhou {folder_wins}/50 (deveria ser 0)"


def test_raiser_beats_caller_majority():
    """RaiserBot deve ter win rate > 50% em 300 partidas contra CallerBot."""
    raiser_wins = 0
    total = 300
    for _ in range(total):
        raiser = RaiseBot("raiser", Hand(), 0)
        caller = CallBot("caller", Hand(), 0)
        winner = new_game(raiser, caller).play_game()
        if winner is not None and winner.name == "raiser":
            raiser_wins += 1
    wr = raiser_wins / total
    assert wr > 0.50, f"RaiserBot win rate: {wr:.1%} (esperado > 50%)"


def test_three_player_game_ends():
    """Partida com 3 bots deve terminar com 1 vencedor."""
    p1 = CallBot("a", Hand(), 0)
    p2 = RaiseBot("b", Hand(), 0)
    p3 = FoldBot("c", Hand(), 0)
    g = new_game(p1, p2, p3)
    winner = g.play_game()
    assert winner is not None
    assert winner.name in ("a", "b", "c")


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 5 — Torneio
# ═══════════════════════════════════════════════════════════════════════════════

def test_headsup_matchup_count():
    """3 bots → C(3,2)=3 confrontos."""
    from tournament.tournament import HeadsUpTournament
    t = HeadsUpTournament(PLAYERS_DIR, games_per_matchup=30)
    t.run()
    assert len(t.results) == 3


def test_headsup_stats_sum_to_games_per_matchup():
    """wins_a + wins_b deve igualar games_per_matchup em todo confronto."""
    from tournament.tournament import HeadsUpTournament
    gpm = 30
    t = HeadsUpTournament(PLAYERS_DIR, games_per_matchup=gpm)
    t.run()
    for pair, (wa, wb) in t.results.items():
        assert wa + wb == gpm, f"Confronto {pair}: {wa}+{wb} != {gpm}"


def test_headsup_all_bots_appear_in_leaderboard():
    """Todos os bots carregados devem aparecer no leaderboard."""
    from tournament.tournament import HeadsUpTournament
    t = HeadsUpTournament(PLAYERS_DIR, games_per_matchup=30)
    t.run()
    all_names = {n for pair in t.results for n in pair}
    assert len(all_names) >= 3


def test_phase2_whitelist_filters_folder():
    """Whitelist com caller e raiser não deve incluir folder."""
    from tournament.tournament import HeadsUpTournament
    t = HeadsUpTournament(
        PLAYERS_DIR,
        games_per_matchup=30,
        bot_whitelist={"player_caller", "player_raiser"},
    )
    t.run()
    all_names = {n for pair in t.results for n in pair}
    assert "player_folder" not in all_names
    assert len(t.results) == 1  # C(2,2)=1


def test_caller_dominates_folder():
    """CallerBot deve ter win rate > 60% contra FolderBot (true WR ~75%)."""
    from tournament.tournament import HeadsUpTournament
    t = HeadsUpTournament(PLAYERS_DIR, games_per_matchup=300)
    t.run()
    wr = t._wr_of("player_caller", "player_folder")
    assert wr > 0.60, f"caller vs folder: {wr:.1%} (esperado > 60%)"


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPO 6 — Robustez
# ═══════════════════════════════════════════════════════════════════════════════

def test_mutating_gameview_raises_frozen_error():
    """Bot que tenta modificar GameView deve receber FrozenInstanceError/AttributeError."""
    frozen_errors = []

    class MutatorBot(Player):
        def decision(self, gv):
            try:
                gv.pot = 9999  # type: ignore
            except Exception as e:
                frozen_errors.append(e)
            return 0

    mutator = MutatorBot("mutator", Hand(), 0)
    mutator.chips = 5000
    caller = CallBot("caller", Hand(), 0)
    caller.chips = 5000

    g = new_game(mutator, caller)
    g.play_game()

    assert len(frozen_errors) > 0, "GameView não levantou erro ao ser modificado"
    # Em Python ≥3.11: FrozenInstanceError; em 3.10: AttributeError
    assert all(isinstance(e, (AttributeError,)) for e in frozen_errors)


def test_example_bots_load_correctly():
    """Os 3 bots de exemplo devem carregar sem erro e jogar 1 partida."""
    from game.game import find_players
    players = find_players()
    assert len(players) >= 3, f"Esperado ≥3 bots de exemplo, encontrado {len(players)}"


def test_example_bots_run_full_game():
    """Uma partida com todos os bots de exemplo deve terminar sem erro."""
    from game.game import find_players
    players = find_players()
    g = Game(players)
    g.verbose = False
    winner = g.play_game()
    assert winner is not None
    assert sum(p.chips for p in g.players) > 0
