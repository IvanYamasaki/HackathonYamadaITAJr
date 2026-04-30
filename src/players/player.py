"""
player.py — Classe Base de Todo Bot de Poker
=============================================

CONCEITO DE POO: ABSTRAÇÃO
    `Player` define o que um bot PRECISA saber fazer (a interface),
    sem ditar COMO ele faz. Qualquer bot que herde de Player e
    implemente `decision()` pode jogar no torneio.

CONCEITO DE POO: HERANÇA
    Ao escrever `class MeuBot(Player):`, seu bot herda automaticamente
    os atributos `name`, `hand`, `chips` e `in_game` — você não precisa
    reescrever a inicialização, só a estratégia.

CONCEITO DE POO: POLIMORFISMO
    O Game chama `player.decision(game_view)` para qualquer bot.
    Não importa se é CallerPlayer, RaiserPlayer ou MeuBot — o Game
    trata todos igualmente pela interface comum `Player`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from cards.cards import Hand

if TYPE_CHECKING:
    from game.game_view import GameView


class Player:
    """
    Classe base abstrata para todos os bots do torneio.

    Atributos gerenciados pelo Game (não modifique diretamente):
        name    : nome do bot
        hand    : cartas privadas (Hand) — atualizado a cada mão
        chips   : saldo de fichas atual
        in_game : False quando o bot deu fold ou ficou sem fichas
    """

    def __init__(self, name: str, hand: Hand, chips: int) -> None:
        self.name = name
        self.hand = Hand()   # o Game repopula a mão antes de cada mão
        self.chips = chips
        self.in_game = True

    def __str__(self) -> str:
        return f"Player({self.name})"

    def __repr__(self) -> str:
        return f"Player({self.name})"

    def decision(self, game_view: "GameView") -> int:
        """
        Recebe o estado público do jogo e retorna uma ação.

        CONCEITO DE POO: POLIMORFISMO
            Cada subclasse implementa este método com sua própria estratégia.
            O Game chama `player.decision(view)` sem saber qual subclasse é.

        Retornos:
            -1   → fold  (desistir da mão)
             0   → check (se to_call == 0) ou call (pagar a aposta atual)
            N>0  → raise: apostar um total de N nesta rodada
                   Ex: se current_bet=20 e quer ir para 60, retorne 60.

        Implemente este método na sua subclasse. Se retornar None, o Game
        pedirá a ação via input() interativo (útil para testar manualmente).
        """
        pass
