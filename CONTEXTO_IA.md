# Contexto para IA — Torneio de Poker ITA Jr

> Copie este arquivo inteiro e cole como contexto ao conversar com uma IA (ChatGPT, Claude, etc.).
> A IA terá tudo que precisa para te ajudar a implementar a estratégia do seu bot.

---

## O que você precisa entregar

Um único arquivo Python: `players/player_SEU_NOME.py`

O arquivo deve conter uma classe que herda de `Player` e implementa o método `decision()`, mais uma função `create_player()`. Você **não deve modificar nenhum outro arquivo** do repositório.

---

## Estrutura obrigatória do bot

```python
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class MeuBot(Player):

    def decision(self, game_view: GameView) -> int:
        # sua estratégia aqui
        return 0  # padrão: sempre check/call


def create_player() -> Player:
    return MeuBot("MeuBot", Hand(), 0)
```

---

## Regras do torneio

- **Formato:** round-robin heads-up — cada bot enfrenta todos os outros em partidas 1 contra 1.
- **Por confronto:** 2.000 partidas. Vence o confronto quem ganhar mais de 50% das partidas.
- **Por partida:** ambos começam com **5.000 fichas**. A partida termina quando um bot fica com 0.
- **Classificação:** número de confrontos vencidos; win rate geral desempata.

---

## Regras do Texas Hold'em simulado

### Estrutura de cada mão

```
Pré-flop → Flop (3 cartas) → Turn (4ª carta) → River (5ª carta) → Showdown
```

Em cada etapa há uma rodada de apostas.

### Blinds

- Small blind: 5 fichas iniciais | Big blind: 10 fichas iniciais
- **Os blinds dobram a cada 50 mãos.** Um bot 100% passivo é eliminado pelos blinds.

### Posições no heads-up

| Posição     | Pré-flop          | Pós-flop           |
|-------------|-------------------|--------------------|
| Small blind | Age **primeiro**  | Age **por último** |
| Big blind   | Age **por último**| Age **primeiro**   |

A posição alterna a cada mão. Agir por último (ter posição) é vantagem enorme.

```python
# Como identificar sua posição:
# dealer_position == 0  →  oponente é o dealer (SB)  →  você é BB
eu_sou_bb = (game_view.dealer_position == 0)
eu_sou_sb = not eu_sou_bb
```

### Ranking de mãos (do menor para o maior)

1. Carta alta
2. Um par
3. Dois pares
4. Trinca
5. Sequência (straight)
6. Flush
7. Full house
8. Quadra
9. Straight flush / Royal flush

---

## O que retornar em `decision()`

| Retorno | Ação                                                               |
|:-------:|--------------------------------------------------------------------|
| `-1`    | **Fold** — desiste da mão, perde o que já apostou                  |
| `0`     | **Check** (se `to_call == 0`) ou **Call** (paga a aposta atual)    |
| `N > 0` | **Raise** — aposta um total de N nesta rodada                      |

> **Detalhe importante:** `N` é o **total apostado na rodada**, não o incremento.
> Se `current_bet = 20` e você quer ir para `60`, retorne `60`, não `40`.
> Se `N < current_bet`, o jogo converte automaticamente para call.

> **Validação e timeout:** retorno de tipo errado, valor negativo diferente de `-1` ou exceção em `decision()` são convertidos para call com aviso no console. Cada chamada tem **timeout de 50 ms** — bots lentos (ex: Monte Carlo pesado) também recebem call automático.

---

## Tudo que seu bot pode ver: `GameView`

```python
def decision(self, game_view: GameView) -> int:

    # --- Suas cartas e fichas ---
    game_view.my_hand       # tuple com seus 2 Card privados
    game_view.my_chips      # suas fichas atuais (int)
    game_view.my_name       # seu nome (str)

    # --- Cartas da mesa ---
    game_view.board         # tuple de Card
                            # pré-flop: vazio | flop: 3 | turn: 4 | river: 5

    # --- Pote e apostas ---
    game_view.pot           # total de fichas no pote (int)
    game_view.current_bet   # maior aposta total da rodada (int)
    game_view.to_call       # fichas que você precisa pagar para continuar (int)
                            # to_call == 0 → pode dar check de graça

    # --- Blinds e posição ---
    game_view.small_blind   # valor atual do small blind (int)
    game_view.big_blind     # valor atual do big blind (int)
    game_view.dealer_position  # índice do dealer na lista de oponentes

    # --- Oponente (no heads-up: sempre 1 elemento) ---
    oponente = game_view.opponents[0]
    oponente.name                   # nome do oponente (str)
    oponente.chips                  # fichas do oponente (int)
    oponente.current_bet_in_round   # quanto ele apostou nesta rodada (int)
    oponente.is_active              # False se deu fold (bool)
```

### Sobre as cartas (`Card`)

```python
card.value  # "A", "2", "3", ..., "10", "J", "Q", "K"
card.suit   # "s" (espadas), "h" (copas), "d" (ouros), "c" (paus)
str(card)   # "As", "Kh", "10d", "2c", etc.
```

**Você NÃO tem acesso a:** cartas do oponente, deck restante.

---

## Estado entre mãos

Uma **nova instância** do bot é criada para cada partida (não para cada mão).

```python
class MeuBot(Player):

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self.maos_jogadas = 0       # persiste entre mãos da mesma partida
        self.raises_do_oponente = 0 # reseta ao começar uma nova partida

    def decision(self, game_view: GameView) -> int:
        self.maos_jogadas += 1
        ...
```

---

## Exemplos de estratégias comentadas

### 1. Sempre check/call (baseline)

```python
def decision(self, game_view: GameView) -> int:
    return 0
```

### 2. Sempre raise (agressivo simples)

```python
def decision(self, game_view: GameView) -> int:
    raise_alvo = game_view.current_bet + game_view.big_blind
    if game_view.my_chips > game_view.to_call + game_view.big_blind:
        return raise_alvo
    return 0  # sem fichas suficientes: call
```

### 3. Força da carta alta (pré-flop)

```python
VALORES = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,
           "9":9,"10":10,"J":11,"Q":12,"K":13,"A":14}

def decision(self, game_view: GameView) -> int:
    if not game_view.board:  # pré-flop
        carta_alta = max(VALORES[c.value] for c in game_view.my_hand)
        if carta_alta >= 11:  # J, Q, K ou A: raise
            return game_view.current_bet + game_view.big_blind * 2
        if carta_alta <= 6:   # cartas fracas: fold se tiver custo
            if game_view.to_call > 0:
                return -1
    return 0
```

### 4. Detectar par na mão

```python
def tem_par_na_mao(self, hand):
    return hand[0].value == hand[1].value

def decision(self, game_view: GameView) -> int:
    if self.tem_par_na_mao(game_view.my_hand):
        return game_view.current_bet + game_view.big_blind * 3
    return 0
```

### 5. Pot odds básico (se vale a pena chamar)

```python
def decision(self, game_view: GameView) -> int:
    to_call = game_view.to_call
    if to_call == 0:
        return 0  # check grátis

    pot_total = game_view.pot + to_call
    pot_odds = to_call / pot_total  # ex: 0.25 = preciso ganhar 25% das vezes

    # Estimar equidade como número de outs (simplificado)
    # Se equidade estimada > pot_odds: matematicamente correto chamar
    equidade_estimada = 0.35  # substitua por cálculo real
    if equidade_estimada > pot_odds:
        return 0  # call
    return -1  # fold
```

### 6. Estratégia com posição

```python
def decision(self, game_view: GameView) -> int:
    eu_sou_bb = (game_view.dealer_position == 0)

    if eu_sou_bb and game_view.to_call == 0:
        return 0  # nunca fold no BB sem custo adicional

    if not eu_sou_bb:
        # Fora de posição (SB): jogue mais conservador
        if game_view.to_call > game_view.big_blind * 3:
            return -1
    else:
        # Em posição (BB pós-flop): pode ser mais agressivo
        if game_view.board:  # a partir do flop
            return game_view.current_bet + game_view.big_blind

    return 0
```

### 7. Bot com memória de mãos anteriores

```python
class BotComMemoria(Player):

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self.raises_sofridos = 0

    def decision(self, game_view: GameView) -> int:
        oponente = game_view.opponents[0]

        # Conta quantas vezes o oponente apostou nesta mão
        if oponente.current_bet_in_round > game_view.big_blind:
            self.raises_sofridos += 1

        # Oponente agressivo: jogue mais conservador
        if self.raises_sofridos > 5:
            if game_view.to_call > game_view.big_blind * 2:
                return -1

        return 0
```

### 8. All-in com stack curto

```python
def decision(self, game_view: GameView) -> int:
    oponente = game_view.opponents[0]
    meu_stack = game_view.my_chips
    bb = game_view.big_blind

    # Com menos de 5 big blinds: push or fold
    if meu_stack < bb * 5:
        carta_alta = max(VALORES[c.value] for c in game_view.my_hand)
        if carta_alta >= 10 or self.tem_par_na_mao(game_view.my_hand):
            return meu_stack  # all-in
        if game_view.to_call > 0:
            return -1  # fold

    return 0
```

---

## Dicas importantes

- **Nunca dê fold no big blind sem custo adicional** — se `to_call == 0`, fold é sempre errado.
- **Blinds crescem** — estratégia 100% passiva perde fichas e perde partidas.
- **Vary your play** — bots determinísticos são previsíveis; use `import random` para variar.
- **Stack-to-Pot Ratio (SPR):** `meu_stack / pot` — SPR baixo = mais inclinado a all-in.
- **Posição importa** — agir por último (pós-flop) dá informação extra; use-a.
- **Oponente com stack curto** vai all-in mais cedo; prepare-se para chamar ou foldar.

---

## Como rodar localmente

```bash
# Torneio oficial
python3 run_tournament.py --heads-up

# Teste rápido (200 partidas por confronto)
python3 run_tournament.py --heads-up --games-per-matchup 200

# Debug detalhado (mostra cada ação)
python3 run_tournament.py --heads-up --verbose
```

---

## Checklist antes de entregar

- [ ] Arquivo nomeado `players/player_SEU_NOME.py`
- [ ] Classe com nome único herdando de `Player`
- [ ] Método `decision(self, game_view: GameView) -> int` implementado
- [ ] Função `create_player()` presente no arquivo
- [ ] Bot roda sem erros: `python3 run_tournament.py --heads-up --games-per-matchup 50`
- [ ] Apenas um arquivo entregue — nenhum outro arquivo do repositório modificado
