# Torneio de Poker — ITA Jr

## Formato

O torneio usa o formato **round-robin heads-up**: cada bot enfrenta todos os outros bots em partidas individuais **1 contra 1**. Não há eliminação — todos jogam contra todos.

Para N bots inscritos, o número de confrontos é:

```
confrontos = N × (N - 1) / 2
```

Exemplos:

| Bots inscritos | Confrontos | Partidas totais (2000/par) |
|:--------------:|:----------:|:--------------------------:|
| 4              | 6          | 12.000                     |
| 6              | 15         | 30.000                     |
| 8              | 28         | 56.000                     |
| 10             | 45         | 90.000                     |

Cada confronto é disputado em **2.000 partidas**. Uma partida termina quando um dos dois bots fica sem fichas.

---

## Regras do jogo

### Estrutura de uma partida

Cada partida começa com ambos os bots tendo **1.000 fichas**. As mãos são jogadas em sequência até um bot zerar.

Cada mão segue a estrutura padrão do Texas Hold'em:

```
Pré-flop  →  Flop (3 cartas)  →  Turn (4ª carta)  →  River (5ª carta)  →  Showdown
```

Em cada etapa há uma rodada de apostas.

### Blinds

| Blind       | Valor inicial |
|-------------|:-------------:|
| Small blind | 5 fichas      |
| Big blind   | 10 fichas     |

Os blinds **dobram a cada 5 mãos**, forçando o jogo a terminar mesmo que nenhum bot arrisque. Não existe stack infinito — quem não jogar será eliminado pelos blinds.

### Posições em heads-up

No heads-up (1v1), as posições se alternam a cada mão:

| Posição      | Pré-flop         | Pós-flop         |
|--------------|------------------|------------------|
| Small blind  | Age **primeiro** | Age **por último** |
| Big blind    | Age **por último** | Age **primeiro** |

Isso é diferente do poker com múltiplos jogadores. **Posição importa muito no heads-up.**

### Ações disponíveis

| Retorno de `decision()` | Ação realizada                                                  |
|:-----------------------:|------------------------------------------------------------------|
| `-1`                    | **Fold** — desiste da mão, perde o que já apostou               |
| `0`                     | **Check** (se `to_call == 0`) ou **Call** (paga a aposta atual) |
| `N > 0`                 | **Raise** — aposta um total de N nesta rodada                    |

> **Detalhe do raise:** `N` é o total apostado na rodada, não o incremento.
> Se `current_bet = 20` e você quer ir para 60, retorne `60`, não `40`.
> Se `N < current_bet`, o jogo trata como call automaticamente.

### Ranking de mãos (do menor para o maior)

1. Carta alta
2. Um par
3. Dois pares
4. Trinca
5. Sequência (straight)
6. Flush (cinco do mesmo naipe)
7. Full house
8. Quadra
9. Straight flush / Royal flush

---

## Classificação final

O leaderboard é calculado em duas camadas:

1. **Pontos de confronto**: quantos dos N-1 adversários seu bot venceu (win rate > 50% no par)
2. **Win rate geral**: percentual de partidas individuais ganhas em todo o torneio

Em caso de empate em pontos, o maior win rate geral desempata.

O resultado de cada confronto é exibido com **intervalo de confiança de 95%** (método de Wald), mostrando a margem de erro estatística:

```
#  Bot           Pontos   WR geral    IC 95%
1  meu_bot        3/3      71.4%     [±2.0%]
2  bot_adversario 2/3      54.8%     [±2.2%]
```

Com 2.000 partidas por par, diferenças de **4,4% ou mais** são detectáveis com 95% de confiança.

---

## Como criar seu bot

### 1. Copie o template

```bash
cp players/player_template.py players/player_SEU_NOME.py
```

### 2. Estrutura obrigatória do arquivo

```python
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

Dois pontos obrigatórios:
- A classe deve herdar de `Player` e implementar `decision()`
- O arquivo deve ter uma função `create_player()` sem parâmetros (ou com um parâmetro de nome)

### 3. Execute o torneio

```bash
# Modo heads-up (formato oficial do torneio)
python3 run_tournament.py --heads-up

# Com menos partidas para testar mais rápido
python3 run_tournament.py --heads-up --games-per-matchup 200

# Modo clássico (múltiplos bots por partida, útil para debug)
python3 run_tournament.py --games 500
```

---

## O que seu bot pode ver: `GameView`

O `GameView` é um snapshot **somente-leitura** do estado público do jogo no momento da sua decisão. Você nunca tem acesso às cartas do oponente nem ao deck restante.

```python
def decision(self, game_view: GameView) -> int:

    # --- Suas cartas e fichas ---
    game_view.my_hand       # tuple com seus 2 Card privados
    game_view.my_chips      # suas fichas atuais (int)
    game_view.my_name       # seu nome (str)

    # --- Cartas da mesa ---
    game_view.board         # tuple de Card: vazio no pré-flop,
                            # 3 cartas no flop, 4 no turn, 5 no river

    # --- Pote e apostas ---
    game_view.pot           # total de fichas no pote (int)
    game_view.current_bet   # maior aposta total da rodada (int)
    game_view.to_call       # fichas que você precisa pagar para continuar (int)
                            # to_call == 0 significa que pode dar check de graça

    # --- Blinds e posição ---
    game_view.small_blind   # valor atual do small blind (dobra a cada 5 mãos)
    game_view.big_blind     # valor atual do big blind
    game_view.dealer_position  # índice do dealer na lista de oponentes

    # --- Oponente (em heads-up: sempre 1 elemento) ---
    oponente = game_view.opponents[0]
    oponente.name                  # nome do oponente
    oponente.chips                 # fichas do oponente
    oponente.current_bet_in_round  # quanto ele apostou nesta rodada
    oponente.is_active             # False se deu fold
```

### Sobre as cartas (`Card`)

```python
card.value  # "A", "2", "3", ..., "10", "J", "Q", "K"
card.suit   # "s" (espadas), "h" (copas), "d" (ouros), "c" (paus)
str(card)   # "As", "Kh", "10d", "2c", etc.
```

---

## Implicações do formato heads-up no código

### Sempre haverá exatamente 1 oponente

No torneio clássico (múltiplos bots), `game_view.opponents` podia ter 2, 3 ou mais elementos. No heads-up, **sempre terá exatamente 1**:

```python
# Seguro no heads-up — sempre funciona
oponente = game_view.opponents[0]
stack_dele = oponente.chips

# Código que pressupõe múltiplos oponentes vai quebrar
for op in game_view.opponents:   # ainda funciona (itera 1 elemento)
    ...
```

### Posição é determinante

No heads-up, a posição (quem é SB e quem é BB) alterna a cada mão. Você pode identificar sua posição assim:

```python
# dealer_position é o índice do dealer na lista de oponentes.
# No heads-up: se dealer_position == 0, o seu oponente é o dealer (= SB),
# portanto você é o BB (age por último no pré-flop).

eu_sou_bb = (game_view.dealer_position == 0)
eu_sou_sb = not eu_sou_bb
```

Quem está na posição vantajosa (age por último no pós-flop) tem informação sobre a ação do oponente antes de decidir. Estratégias que ignoram posição deixam valor na mesa.

### Stack sizes importam mais

Sem outros jogadores para diluir a variância, a relação entre seu stack e o do oponente dita o quanto você pode arriscar:

```python
meu_stack = game_view.my_chips
stack_oponente = game_view.opponents[0].chips
spr = meu_stack / game_view.pot  # Stack-to-Pot Ratio
```

Com blinds crescendo, stacks curtos forçam situações de all-in. Um bot que nunca abre mão será eliminado pelos blinds em poucas mãos.

### Não existe informação de "outros jogadores no pote"

Cálculos de pot odds em jogos com múltiplos jogadores levam em conta quantas pessoas já entraram no pote. No heads-up isso não se aplica — há apenas um oponente, e seu comportamento (raise, call, fold) já está refletido em `current_bet` e `to_call`.

```python
# Pot odds simplificado para heads-up
to_call = game_view.to_call
pot_total = game_view.pot + to_call
pot_odds = to_call / pot_total if pot_total > 0 else 0
# Se sua equidade estimada > pot_odds, é matematicamente correto chamar
```

### Estado entre mãos não persiste (por padrão)

O torneio cria uma **instância nova** do seu bot para cada partida (não para cada mão). Isso significa:

- Atributos de instância **persistem entre mãos** dentro de uma mesma partida
- Ao começar uma nova partida contra um novo adversário, o bot é recriado do zero

```python
class MeuBot(Player):

    def __init__(self, name, hand, chips):
        super().__init__(name, hand, chips)
        self.historico_raises = 0   # reseta a cada nova partida, persiste entre mãos

    def decision(self, game_view: GameView) -> int:
        if game_view.current_bet > game_view.big_blind * 3:
            self.historico_raises += 1  # acumula ao longo das mãos da partida
        ...
```

---

## Dicas para estratégias heads-up

- **Nunca dê fold no big blind sem custo adicional** — se `to_call == 0`, dar fold é sempre incorreto
- **Blinds crescem** — uma estratégia 100% passiva perde fichas por inação
- **Acompanhe o stack do oponente** — oponente com stack curto tende a ir all-in; prepare-se para chamadas ou folds calculados
- **Varie seu jogo** — bots determinísticos são previsíveis; se possível, use aleatoriedade controlada

---

## Resumo rápido

| O que fazer                          | Como fazer                                      |
|--------------------------------------|-------------------------------------------------|
| Criar bot                            | Copiar `player_template.py` → `player_SEU_NOME.py` |
| Implementar estratégia               | Método `decision(self, game_view) -> int`       |
| Registrar bot                        | Função `create_player()` no mesmo arquivo       |
| Rodar torneio oficial                | `python3 run_tournament.py --heads-up`          |
| Testar rápido                        | `python3 run_tournament.py --heads-up --games-per-matchup 200` |
| Ver ações de cada mão (debug)        | `python3 run_tournament.py --heads-up --verbose` |
