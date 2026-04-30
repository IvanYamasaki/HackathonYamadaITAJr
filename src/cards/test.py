from cards import Card, Deck, Hand, Board, FullDeck
from sequences import FullHand

full_deck = FullDeck()
hand = Hand()
board = Board()

hand.give_cards(full_deck)
board.flop(full_deck)
board.turn(full_deck)
board.river(full_deck)

full_hand = FullHand(hand, board)

print(full_hand)
print(full_hand.score_hand())
