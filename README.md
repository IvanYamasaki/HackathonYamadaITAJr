# Poker Challenge — ITA Jr | Treinamento POO

Este repositório tem três documentos principais:

- **`README.md`** (este arquivo) — explica a lógica do programa: estrutura do código, conceitos de POO aplicados e como o motor do jogo funciona.
- **[`TOURNAMENT.md`](TOURNAMENT.md)** — explica o funcionamento do torneio: regras, formato, como criar seu bot e como entregar.
- **[`CONTEXTO_IA.md`](CONTEXTO_IA.md)** — arquivo para colar em uma IA (ChatGPT, Claude, etc.) e receber ajuda para implementar sua estratégia.

> **Trainee de dados participando do torneio? Comece pelo [`README.md`] para entender os conceitos de POO**

> **Participante do torneio? Pode ir direto para o [`TOURNAMENT.md`](TOURNAMENT.md).** Lá estão as regras, o formato, o que seu bot pode ver e como criar e entregar o arquivo. Volte ao `README.md` caso tenha alguma dúvida especifica de código.

---

## Sua missão

Criar um arquivo `players/player_SEU_NOME.py` e implementar o método `decision()` com a estratégia do seu bot.

```
1. Copie o template:
   cp players/player_template.py players/player_joao.py

2. Abra o arquivo e implemente decision()

3. Rode o torneio:
   python run_tournament.py --heads-up
```

Só isso. Você não precisa tocar em mais nenhum arquivo.

> **Entrega:** o único arquivo que você deve entregar é `players/player_SEU_NOME.py`. Nada mais.
>
> **Prazo v1: 07/06/2026 — Prazo v2: 14/06/2026.**

---

## Como rodar

```bash
# Torneio padrão (1000 partidas)
python run_tournament.py

# Escolher o número de partidas
python run_tournament.py --games 500

# Limitar quantos bots jogam por partida (útil com muitos bots)
python run_tournament.py --per-game 4

# Ver cada ação de jogo (bom para debug, lento em escala)
python run_tournament.py --verbose
```

---

## O método decision()

O motor do jogo chama `decision(game_view)` toda vez que é a sua vez de agir.

```python
def decision(self, game_view: GameView) -> int:
    ...
```

**O que retornar:**

| Valor | Ação |
|---|---|
| `-1` | **Fold** — desistir da mão |
| `0` | **Check/Call** — checar se não há aposta, ou pagar a aposta atual |
| `N > 0` | **Raise** — apostar um total de N nesta rodada |

> Exemplo de raise: se `current_bet = 20` e você quer ir para `60`, retorne `60`.
> Se o valor for menor que `current_bet`, o jogo trata como call automaticamente.

**O que você pode ver (`game_view`):**

```python
game_view.my_hand          # tuple de 2 Card — suas cartas privadas
game_view.my_chips         # seus chips atuais
game_view.board            # cartas comunitárias (0, 3, 4 ou 5 cartas)
game_view.pot              # total no pote
game_view.to_call          # quanto você precisa pagar para continuar
game_view.current_bet      # maior aposta total desta rodada
game_view.big_blind        # valor atual do big blind
game_view.small_blind      # valor atual do small blind
game_view.opponents        # informações públicas dos outros jogadores
  .opponents[i].name
  .opponents[i].chips
  .opponents[i].current_bet_in_round
  .opponents[i].is_active  # False = deu fold
```

**O que você NÃO pode ver** (encapsulado no motor, intencionalmente):
- As cartas dos adversários
- O deck restante

**Sobre as cartas (`Card`):**

```python
card.value   # "A", "2"..."10", "J", "Q", "K"
card.suit    # "s" espadas, "h" copas, "d" ouros, "c" paus
str(card)    # "As", "Kh", "10d", etc.
```

---

## Estrutura do projeto

```
PokerEntregavel/
├── run_tournament.py        ← ponto de entrada do torneio
├── players/                 ← COLOQUE SEU BOT AQUI
│   ├── player_template.py   ← copie este arquivo para começar
│   ├── player_caller.py     ← exemplo: sempre check/call
│   ├── player_folder.py     ← exemplo: sempre fold
│   └── player_raiser.py     ← exemplo: sempre tenta aumentar
└── src/                     ← motor do jogo (não mexa aqui)
    ├── cards/
    │   ├── cards.py         ← Card, Deck, Hand, Board
    │   └── sequences.py     ← avaliação de mãos (força da mão)
    ├── game/
    │   ├── game.py          ← motor principal do Texas Hold'em
    │   └── game_view.py     ← visão pública do jogo (sem informações privadas)
    ├── players/
    │   └── player.py        ← classe base Player
    └── tournament/
        └── tournament.py    ← orquestrador: carrega bots, roda partidas, gera ranking
```

---

## Conceitos de POO no projeto

### Abstração

**O que é:** definir o "contrato" de uma classe — o que ela precisa fazer — sem dizer como.

**No projeto:** a classe `Player` exige que todo bot implemente `decision()`. O motor do jogo não sabe nada sobre a estratégia do seu bot; ele só chama `decision()` e recebe um número de volta. Você cumpre o contrato, o jogo funciona.

```python
# O motor só precisa saber isso sobre qualquer bot:
acao = player.decision(game_view)  # -1, 0 ou N > 0
```

---

### Herança

**O que é:** uma classe filha herda atributos e comportamentos da classe mãe, sem precisar reescrevê-los.

**No projeto:** ao escrever `class MeuBot(Player)`, você ganha `name`, `chips`, `hand` e `in_game` de graça. Só precisa implementar a parte nova: a sua estratégia.

```python
class MeuBot(Player):        # herda tudo de Player automaticamente
    def decision(self, game_view: GameView) -> int:
        return 0             # só isso você precisa escrever
```

---

### Polimorfismo

**O que é:** diferentes classes respondem à mesma chamada de formas diferentes.

**No projeto:** `CallerBot`, `RaiserBot` e `MeuBot` são todos `Player`. O torneio chama `player.decision(view)` para cada um da mesma forma — mas cada bot decide diferente. Mesma chamada, comportamentos distintos.

```python
for player in jogadores:
    acao = player.decision(view)  # cada bot responde à sua maneira
```

---

### Encapsulamento

**O que é:** proteger dados internos, expondo só o que é necessário para quem está de fora.

**No projeto:** o `GameView` é somente-leitura e não expõe as cartas dos adversários nem o deck restante. Isso é intencional — assim como no poker real, você toma decisões com informação incompleta. O motor protege o que não é seu.

```python
game_view.my_hand      # suas cartas: visível
game_view.board        # cartas da mesa: visível
# cartas do oponente  → encapsuladas no Game, inacessíveis
# deck restante       → encapsulado no Game, inacessível
```

---

### Resumo

| Conceito | Onde aparece no projeto |
|---|---|
| Abstração | Classe `Player` define `decision()` sem implementar |
| Herança | `class MeuBot(Player)` herda `name`, `chips`, `hand`, `in_game` |
| Polimorfismo | O torneio chama `decision()` igual para todos os bots |
| Encapsulamento | `GameView` oculta cartas dos adversários e o deck |

---

## Regras do Texas Hold'em simulado

1. Cada jogador começa com 1000 chips (100× o big blind inicial)
2. Blinds aumentam a cada 5 mãos (dobram)
3. Sequência de cada mão: pré-flop → flop (3 cartas) → turn (4ª carta) → river (5ª carta) → showdown
4. Vence a partida quem ficar com todos os chips
5. O torneio roda N partidas e contabiliza vitórias e chips ganhos por bot

---

## Exemplo mínimo de bot

```python
# players/player_exemplo.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand


class BotAgressivo(Player):
    def decision(self, game_view: GameView) -> int:
        # Raise sempre que tiver fichas; caso contrário, call
        if self.chips > game_view.to_call + game_view.big_blind:
            return game_view.current_bet + game_view.big_blind
        return 0


def create_player() -> Player:
    return BotAgressivo("BotAgressivo", Hand(), 0)
```

---

## Dependências

- Python >= 3.10
- numpy (usado internamente pela avaliação de mãos)

```bash
pip install numpy
```
