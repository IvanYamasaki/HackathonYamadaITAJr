from itertools import combinations
from collections import Counter

try:
    # Quando `cards` é um pacote/namespace (rodando a partir de `src`)
    from cards.cards import Card, Deck, Hand, Board
except ModuleNotFoundError:
    # Quando `cards` é o arquivo `cards.py` (rodando dentro de `src/cards`)
    from cards import Card, Deck, Hand, Board

# Valores numéricos das cartas (A = 14 alto, 1 para sequência baixa)
VALORES = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
           "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}

# Ranks das mãos (maior = melhor). Royal Flush é straight flush máximo.
RANK_ROYAL_FLUSH = 9
RANK_STRAIGHT_FLUSH = 8
RANK_QUADRA = 7
RANK_FULL_HOUSE = 6
RANK_FLUSH = 5
RANK_STRAIGHT = 4
RANK_TRINCA = 3
RANK_DOIS_PARES = 2
RANK_UM_PAR = 1
RANK_CARTA_ALTA = 0

# Base para codificar desempate: 5 cartas até 14 -> 15^5
BASE_DESEMPATE = 15 ** 5


def valor_carta(carta: Card) -> int:
    """Retorna o valor numérico da carta (A=14, 2=2, ..., K=13)."""
    return VALORES[carta.value]


def valores_ordenados(cartas: list[Card], alto: bool = True) -> list[int]:
    """Retorna valores numéricos das cartas ordenados (alto: descendente)."""
    vals = [valor_carta(c) for c in cartas]
    return sorted(vals, reverse=alto)


def eh_flush(cartas: list[Card]) -> bool:
    """True se as 5 cartas forem do mesmo naipe."""
    if len(cartas) != 5:
        return False
    naipe = cartas[0].suit
    return all(c.suit == naipe for c in cartas)


def _valores_para_straight(vals: list[int]) -> list[int] | None:
    """
    Se os 5 valores formam uma sequência, retorna a lista ordenada alta.
    Considera A-2-3-4-5 (wheel) com A=1. Retorna None se não for straight.
    """
    unicos = sorted(set(vals), reverse=True)
    if len(unicos) < 5:
        return None
    # Verifica sequência normal (ex: 10,9,8,7,6)
    for i in range(len(unicos) - 4):
        janela = unicos[i:i + 5]
        if janela[0] - janela[-1] == 4:
            return janela
    # Wheel: A,2,3,4,5 -> tratar A como 1
    substituidos = [1 if v == 14 else v for v in vals]
    unicos_w = sorted(set(substituidos), reverse=True)
    if len(unicos_w) < 5:
        return None
    for i in range(len(unicos_w) - 4):
        janela = unicos_w[i:i + 5]
        if janela[0] - janela[-1] == 4:
            # Retornar com 5 como alta no wheel
            return [5, 4, 3, 2, 1]
    return None


def eh_straight(cartas: list[Card]) -> list[int] | None:
    """Se as 5 cartas formam sequência, retorna a lista de valores [alta, ..., baixa]. Senão None."""
    vals = [valor_carta(c) for c in cartas]
    return _valores_para_straight(vals)


def avaliar_cinco_cartas(cartas: list[Card]) -> tuple[int, list[int]]:
    """
    Avalia exatamente 5 cartas. Retorna (rank_da_mao, lista_de_desempate).
    A lista de desempate deve ser usada na ordem para comparar (ex: [tripla, par, kicker] ou [c1,c2,c3,c4,c5]).
    """
    if len(cartas) != 5:
        raise ValueError("precisa de exatamente 5 cartas")
    vals = valores_ordenados(cartas)
    contagem = Counter(vals)
    mais_comuns = contagem.most_common(5)
    flush = eh_flush(cartas)
    straight_val = eh_straight(cartas)

    # Straight flush (inclui royal)
    if flush and straight_val is not None:
        return (RANK_STRAIGHT_FLUSH, straight_val)

    # Quadra
    if mais_comuns[0][1] == 4:
        quadra = mais_comuns[0][0]
        kicker = mais_comuns[1][0]
        return (RANK_QUADRA, [quadra, kicker])

    # Full house
    if mais_comuns[0][1] == 3 and mais_comuns[1][1] >= 2:
        tripla = mais_comuns[0][0]
        par = mais_comuns[1][0]
        return (RANK_FULL_HOUSE, [tripla, par])

    # Flush
    if flush:
        return (RANK_FLUSH, vals)

    # Straight
    if straight_val is not None:
        return (RANK_STRAIGHT, straight_val)

    # Trinca
    if mais_comuns[0][1] == 3:
        tripla = mais_comuns[0][0]
        kickers = sorted([v for v in vals if v != tripla], reverse=True)[:2]
        return (RANK_TRINCA, [tripla] + kickers)

    # Dois pares
    pares = [v for v, c in mais_comuns if c == 2]
    if len(pares) >= 2:
        pares_ord = sorted(pares, reverse=True)[:2]
        kicker = next(v for v, c in contagem.items() if c == 1)
        return (RANK_DOIS_PARES, pares_ord + [kicker])

    # Um par
    if mais_comuns[0][1] == 2:
        par = mais_comuns[0][0]
        kickers = sorted([v for v in vals if v != par], reverse=True)[:3]
        return (RANK_UM_PAR, [par] + kickers)

    # Carta alta
    return (RANK_CARTA_ALTA, vals)


def desempate_para_numero(tiebreaker: list[int]) -> int:
    """Codifica a lista de desempate em um único inteiro (base 15)."""
    n = 0
    for v in tiebreaker[:5]:
        n = n * 15 + min(v, 14)
    return n


def score_cinco_cartas(cartas: list[Card]) -> int:
    """Score de uma mão de 5 cartas: rank domina, depois desempate."""
    rank, tiebreaker = avaliar_cinco_cartas(cartas)
    desempate = desempate_para_numero(tiebreaker)
    return rank * BASE_DESEMPATE + desempate


class FullHand(Deck):
    """
    Representa a mão completa do jogador (cartas do jogador + board).
    """
    def __init__(self, hand: Hand, board: Board) -> None:
        cards = set(hand.cards) | set(board.cards)
        super().__init__(cards)

    def score_hand(self) -> int:
        """
        Retorna o score da melhor mão de 5 cartas formada pelas cartas
        do jogador mais as comunitárias. Maior score = melhor mão.
        O score incorpora tanto o tipo de sequência (rank) quanto o desempate.
        """
        cartas_lista = list(self.cards)
        if len(cartas_lista) < 5:
            return 0
        melhor = 0
        for cinco in combinations(cartas_lista, 5):
            s = score_cinco_cartas(list(cinco))
            if s > melhor:
                melhor = s
        return melhor
