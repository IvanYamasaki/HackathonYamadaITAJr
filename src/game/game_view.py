"""
game_view.py — Camada de Segurança do Jogo
===========================================

CONCEITO DE POO: ENCAPSULAMENTO
    O objeto `Game` contém todo o estado interno do jogo (cartas dos adversários,
    deck restante, etc.). Para que os bots não possam "trapacear", o jogo NUNCA
    passa o objeto `Game` diretamente para o bot. Em vez disso, cria um `GameView`:
    um snapshot somente-leitura com apenas as informações públicas.

CONCEITO DE POO: ABSTRAÇÃO
    `GameView` é a "interface" entre a engine e o bot. O bot não precisa saber
    como o jogo funciona por dentro; só precisa reagir às informações desta classe.

Por que `frozen=True`?
    Dataclasses com frozen=True são imutáveis: qualquer tentativa de escrever
    `game_view.pot = 9999` levanta FrozenInstanceError. Isso garante que o bot
    não possa corromper o estado do jogo por acidente.
"""
from __future__ import annotations

from dataclasses import dataclass
from cards.cards import Card


@dataclass(frozen=True)
class PublicPlayerInfo:
    """
    Informações PÚBLICAS de um oponente — o que qualquer jogador veria na mesa.

    Propositalmente NÃO contém: hand (cartas privadas do oponente).
    """
    name: str
    chips: int
    current_bet_in_round: int  # quanto este oponente já apostou nesta rodada
    is_active: bool            # False = deu fold nesta mão


@dataclass(frozen=True)
class GameView:
    """
    Visão pública do estado do jogo no momento em que o bot precisa decidir.

    CONCEITO DE POO: ENCAPSULAMENTO
        Não existe nenhum campo que dê acesso ao objeto `Game` interno.
        O bot só vê o que um jogador real veria sentado à mesa.

    Campos disponíveis
    ------------------
    board          : cartas comunitárias visíveis na mesa (0, 3, 4 ou 5 cartas)
    my_hand        : suas 2 cartas privadas
    my_chips       : seus chips atuais
    my_name        : seu nome
    pot            : total de chips no pote
    current_bet    : maior aposta total nesta rodada (valor que todos devem igualar)
    to_call        : quanto VOCÊ especificamente ainda precisa pagar para ficar
    dealer_position: índice do dealer na lista de oponentes
    small_blind    : valor atual do small blind
    big_blind      : valor atual do big blind
    opponents      : tuple de PublicPlayerInfo (sem cartas dos adversários)
    """

    # --- Cartas na mesa (visíveis a todos) ---
    board: tuple[Card, ...]         # 0 no pré-flop, 3 no flop, 4 no turn, 5 no river

    # --- Suas informações privadas ---
    my_hand: tuple[Card, ...]       # suas 2 cartas
    my_chips: int
    my_name: str

    # --- Pote e apostas ---
    pot: int
    current_bet: int                # maior aposta total desta rodada
    to_call: int                    # chips que você precisa pagar para continuar

    # --- Informações da mesa ---
    dealer_position: int
    small_blind: int
    big_blind: int

    # --- Oponentes (informações públicas apenas) ---
    opponents: tuple[PublicPlayerInfo, ...]
