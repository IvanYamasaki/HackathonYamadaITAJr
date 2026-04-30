"""
TEMPLATE DO BOT DE POKER — ITA Jr | Treinamento POO
====================================================

INSTRUÇÕES
----------
1. Copie este arquivo: cp player_template.py player_SEU_NOME.py
2. Renomeie a classe `MeuBot` para algo único (ex: `BotAgressivo`)
3. Implemente a estratégia no método `decision()` abaixo
4. Coloque o arquivo na pasta `players/` e rode o torneio:
       python run_tournament.py

Não é necessário entender o resto do código — só o método `decision()` importa!

─────────────────────────────────────────────────────────────────────────────
CONCEITOS DE POO NESTE PROJETO
─────────────────────────────────────────────────────────────────────────────

ABSTRAÇÃO
    `Player` define a interface (o "contrato"): qualquer bot que herde de
    Player e implemente decision() pode jogar. Você não precisa saber como
    o Game funciona por dentro.

HERANÇA
    `class MeuBot(Player)` — seu bot herda name, hand, chips, in_game.
    Você só precisa escrever a lógica de decisão.

POLIMORFISMO
    O Game chama `player.decision(view)` para CallerPlayer, RaiserPlayer e
    MeuBot da mesma forma. Cada um responde diferentemente — isso é polimorfismo.

ENCAPSULAMENTO
    Você recebe um `GameView` somente-leitura. As cartas dos adversários e o
    deck restante ficam encapsulados dentro do Game — inacessíveis para você.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import sys
from pathlib import Path

# Adiciona src/ ao path para importar a engine do jogo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class MeuBot(Player):
    """
    Seu bot de poker. Renomeie esta classe para algo único.

    HERANÇA: MeuBot(Player) herda automaticamente:
        self.name   → nome do bot
        self.chips  → fichas disponíveis
        self.hand   → suas cartas (também acessíveis via game_view.my_hand)
        self.in_game → False se você deu fold ou ficou sem fichas
    """

    def decision(self, game_view: GameView) -> int:
        """
        Recebe o estado público do jogo e retorna uma ação.

        POLIMORFISMO: este método é chamado pelo Game para qualquer Player.
        Cada bot implementa sua estratégia aqui — mesma assinatura, comportamentos diferentes.

        O QUE VOCÊ PODE VER (game_view)
        ────────────────────────────────────────────────────────────────────
        game_view.my_hand          → tuple de 2 Card — suas cartas privadas
                                     Ex: (As, Kh) para Ás de espadas e Rei de copas
        game_view.my_chips         → int — suas fichas atuais

        game_view.board            → tuple de Card — cartas comunitárias (mesa)
                                     0 cartas no pré-flop, 3 no flop, 4 no turn, 5 no river
        game_view.pot              → int — total de fichas no pote
        game_view.to_call          → int — fichas que você precisa pagar para continuar
                                     (0 = pode dar check de graça)
        game_view.current_bet      → int — maior aposta total nesta rodada
        game_view.small_blind      → int — valor atual do small blind
        game_view.big_blind        → int — valor atual do big blind
        game_view.dealer_position  → int — índice do dealer na lista de oponentes

        game_view.opponents        → tuple de PublicPlayerInfo (SEM as cartas deles!)
          .opponents[i].name              → nome do oponente
          .opponents[i].chips             → fichas do oponente
          .opponents[i].current_bet_in_round → quanto ele apostou nesta rodada
          .opponents[i].is_active         → False = já deu fold

        SOBRE AS CARTAS (Card)
        ────────────────────────────────────────────────────────────────────
        card.value  → "A", "2"..."10", "J", "Q", "K"
        card.suit   → "s" (spades/espadas), "h" (hearts/copas),
                      "d" (diamonds/ouros), "c" (clubs/paus)
        str(card)   → "As", "Kh", "10d", etc.

        RETORNO
        ────────────────────────────────────────────────────────────────────
        -1       → fold  (desistir desta mão)
         0       → check (se to_call == 0) ou call (pagar a aposta atual)
         N > 0   → raise: apostar um total de N nesta rodada
                   Ex: se current_bet=20 e quer ir para 60, retorne 60
                   O Game automaticamente converte valores menores que current_bet para call.
        """

        # ─── IMPLEMENTE SUA ESTRATÉGIA AQUI ───────────────────────────────

        # Exemplos de acesso:
        # minhas_cartas = game_view.my_hand       # tuple de 2 Card
        # mesa = game_view.board                  # tuple de 0-5 Card
        # preciso_pagar = game_view.to_call       # int
        # meu_saldo = game_view.my_chips          # int
        # adversarios_ativos = [op for op in game_view.opponents if op.is_active]

        # Estratégia padrão: sempre check/call (nunca fold, nunca raise)
        return 0

        # ──────────────────────────────────────────────────────────────────


def create_player() -> Player:
    """
    Função obrigatória: o sistema de torneio chama esta função para criar
    uma instância do seu bot antes de cada partida.

    Não modifique a assinatura — apenas troque MeuBot pelo nome da sua classe.
    """
    return MeuBot("MeuBot", Hand(), 0)
