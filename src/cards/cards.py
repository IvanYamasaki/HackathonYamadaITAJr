import random

class Card:
    """
    Represents a card in a deck of cards.
    """
    def __init__(self, value: str, suit: str) -> None:
        self.value = value
        self.suit = suit

    def __str__(self):
        return f"{self.value}{self.suit}"

    def __repr__(self):
        return f"{self.value}{self.suit}"

class Deck:
    """
    Represents a deck of cards.
    """
    def __init__(self, cards: set[Card]) -> None:
        self.cards = cards

    def __str__(self):
        return f"Deck({sorted(str(c) for c in self.cards)})"
    
    def __repr__(self):
        return self.__str__()

class FullDeck(Deck):
    """
    Represents a full deck of cards.
    """
    def __init__(self):
        values = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        suits = ["s", "h", "d", "c"]
        cards = set[Card]([Card(v, s) for v in values for s in suits])
        super().__init__(cards)

    def pull_card(self) -> Card:
        if not self.cards:
            raise ValueError("No cards left in the deck")
        rmd = random.choice(list(self.cards))
        self.cards.remove(rmd)
        return rmd

class Hand(Deck):
    """
    Represents a hand of player's cards.
    """
    def __init__(self) -> None:
        cards = set[Card]()
        super().__init__(cards)

    def give_cards(self, full_deck: FullDeck) -> None:
        if len(self.cards) != 0:
            raise ValueError("Hand must be empty")
        self.cards = [full_deck.pull_card() for i in range(2)]


class Board(Deck):
    """
    Represents a board of cards.
    """
    def __init__(self) -> None:
        cards = set[Card]()
        super().__init__(cards)

    def flop(self, full_deck: FullDeck) -> None:
        if len(self.cards) != 0:
            raise ValueError("Board must be empty")
        self.cards = set[Card]([full_deck.pull_card() for i in range(3)])

    def turn(self, full_deck: FullDeck) -> None:
        if len(self.cards) != 3:
            raise ValueError("Board must have 3 cards")
        self.cards.add(full_deck.pull_card())

    def river(self, full_deck: FullDeck) -> None:
        if len(self.cards) != 4:
            raise ValueError("Board must have 4 cards")
        self.cards.add(full_deck.pull_card())



if __name__ == "__main__":

    # --- Teste ---
    full_deck = FullDeck()
    print(f"Deck inicial: {len(full_deck.cards)} cartas")

    hand = Hand()
    hand.give_cards(full_deck)

    print(f"Sua mão: {hand}")
    print(f"Restam no deck: {len(full_deck.cards)} cartas")


    board = Board()
    board.flop(full_deck)
    print(f"Flop: {board}")
    print(f"Restam no deck: {len(full_deck.cards)} cartas")

    board.turn(full_deck)
    print(f"Turn: {board}")
    print(f"Restam no deck: {len(full_deck.cards)} cartas")

    board.river(full_deck)
    print(f"River: {board}")
    print(f"Restam no deck: {len(full_deck.cards)} cartas")
