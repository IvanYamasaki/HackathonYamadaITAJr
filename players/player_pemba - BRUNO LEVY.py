from __future__ import annotations

import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from players.player import Player
from game.game_view import GameView
from cards.cards import Hand

class pembaBot(Player):
    VALORES_CARTAS = {
        "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
        "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14
    }

    def decision(self, game_view: GameView) -> int:
        try:
            to_call = game_view.to_call
            bb = game_view.big_blind
            current_bet = game_view.current_bet
            pot = game_view.pot
            meu_stack = game_view.my_chips
            board = game_view.board
            minhas_cartas = game_view.my_hand
            
            eu_sou_sb = (game_view.dealer_position == 1)
            tenho_posicao_pos_flop = eu_sou_sb
            
            v1 = self.VALORES_CARTAS[minhas_cartas[0].value]
            v2 = self.VALORES_CARTAS[minhas_cartas[1].value]
            carta_alta = max(v1, v2)
            carta_baixa = min(v1, v2)
            is_par = (v1 == v2)
            is_suited = (minhas_cartas[0].suit == minhas_cartas[1].suit)

            if meu_stack < 10 * bb:
                if is_par or carta_alta >= 10 or (is_suited and carta_alta >= 8):
                    return meu_stack 
                return -1 if to_call > 0 else 0
            
            if not board:
                if (is_par and carta_alta >= 9) or (carta_alta >= 13 and carta_baixa >= 11):
                    return current_bet + (bb * 3)
                
                if is_par or carta_alta >= 11 or (is_suited and carta_alta >= 10):
                    if to_call <= bb * 2 and random.random() < 0.3:
                        return current_bet + (bb * 2)
                    return 0 
                
                if to_call > 0:
                    return -1
                return 0

            valores_mesa = [self.VALORES_CARTAS[c.value] for c in board]
            naipes_totais = [c.suit for c in board] + [minhas_cartas[0].suit, minhas_cartas[1].suit]
            
            acertei_par = v1 in valores_mesa or v2 in valores_mesa
            tenho_overcards = carta_alta > max(valores_mesa) if valores_mesa else False
            
            contagem_naipes = {naipe: naipes_totais.count(naipe) for naipe in set(naipes_totais)}
            flush_draw = any(qtd >= 4 for qtd in contagem_naipes.values())
            flush_feito = any(qtd >= 5 for qtd in contagem_naipes.values())

            if flush_feito or (is_par and acertei_par) or (acertei_par and carta_alta >= 11):
                aposta_valor = int(pot * 0.5)
                return max(current_bet + bb, current_bet + aposta_valor)

            if flush_draw or acertei_par or (is_par and tenho_overcards):
                if to_call > pot: 
                    return -1
                return 0 

            if tenho_posicao_pos_flop and to_call == 0:
                if random.random() < 0.20: 
                    return current_bet + int(pot * 0.4)
            
            return -1 if to_call > 0 else 0

        except Exception:
            return 0

def create_player() -> Player:
    return pembaBot("pembaBot", Hand(), 0)
