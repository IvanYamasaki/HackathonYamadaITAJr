# Poker Challenge — ITA Jr | Treinamento POO

Este repositório tem dois documentos principais:

- **`README.md`** (este arquivo) — explica a lógica do programa: estrutura do código, conceitos de POO aplicados e como o motor do jogo funciona.
- **[`TOURNAMENT.md`](TOURNAMENT.md)** — explica o funcionamento do torneio: regras, formato, como criar seu bot e como entregar.

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

| Conceito | Onde aparece |
|---|---|
| **Abstração** | `Player.decision()` define a interface; o motor não sabe qual subclasse está usando |
| **Herança** | `class MeuBot(Player)` — seu bot herda `name`, `chips`, `hand`, `in_game` |
| **Polimorfismo** | O motor chama `player.decision(view)` para qualquer bot, independente da estratégia |
| **Encapsulamento** | `GameView(frozen=True)` expõe só informações públicas; cartas dos adversários ficam ocultas |
| **Composição** | `Game` é composto por `Board`, `FullDeck` e lista de `Player` |
| **Data classes** | `GameView`, `PublicPlayerInfo`, `PlayerStats` usam `@dataclass` |

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
