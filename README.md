# Poker Heads-Up com Aprendizado por Reforço — Agentes v15 e v16

Agentes autônomos para um torneio de poker *heads-up* (1 contra 1). O foco atual
do projeto são os agentes **v15** e **v16**, treinados por **Aprendizado por
Reforço (PPO)** diretamente sobre a *engine* real do torneio — a primeira
geração da linhagem que abandona as heurísticas escritas à mão.

📄 **Artigo completo:** [`Artigo_RL_Poker_v15_v16.pdf`](Artigo_RL_Poker_v15_v16.pdf)
— metodologia, experimentos e resultados. **Comece por aqui.**
(Versão estendida em [`rl/RELATORIO_v15_v16.md`](rl/RELATORIO_v15_v16.md).)

---

## Resultado principal

Mantendo **tudo constante exceto a função de recompensa**, isolamos o efeito
dela:

- **Ambos** os agentes de RL superam o melhor heurístico da linhagem (o **v14**,
  campeão da Fase 2 do torneio), quebrando a barreira de **70%** que o ajuste
  manual nunca cruzou.
- O **v16** (recompensa esparsa de vitória/derrota) é o mais forte: vence
  **1593/2000 (79,7%)** partidas contra o conjunto {v14, v13, v8, v1} e
  **451/500** contra o próprio v15 no confronto direto.
- Mesma rede e mesmos hiperparâmetros: só a recompensa muda — e ela sozinha
  esculpe estilos de jogo opostos (v15 agressivo × v16 disciplinado).

Tabelas, figuras e a discussão completa estão no
[artigo](Artigo_RL_Poker_v15_v16.pdf).

---

## Estrutura do repositório

```
players_ivan/   ← linhagem própria v1–v16 (v15/v16 são os agentes de RL)
players/        ← bots dos participantes do torneio (usados como oponentes)
rl/             ← pipeline de RL
  train.py      ← treino PPO (CUDA, robusto a interrupções/retomada)
  env.py        ← ambiente vetorizado sobre a engine real (inversão de controle)
  model.py      ← rede Actor-Critic (MLP 23→128→128→{π, V})
  avaliar.py    ← avaliação greedy (força real, como no torneio)
  export.py     ← exporta os pesos para .npz (inferência 100% NumPy)
  RELATORIO_v15_v16.md ← relatório técnico detalhado
src/            ← motor do jogo (Texas Hold'em heads-up) — não alterar
results/        ← saídas de torneios
run_tournament.py / run_full_tournament.py  ← rodam o torneio entre os bots
```

Mais detalhes do pipeline em [`rl/README.md`](rl/README.md).

---

## Como rodar

```bash
# Treinar por PPO (usa GPU CUDA por padrão; retoma sozinho se interrompido)
py rl/train.py --reward win_loss --run-name v16_sparse   # esparso (v16)
py rl/train.py --reward chip     --run-name v15_chip     # denso  (v15)

# Avaliar a força real (greedy/argmax, exatamente como joga no torneio)
py rl/avaliar.py --opp all --games 500

# Rodar o torneio entre os bots
py run_tournament.py --heads-up
```

A inferência no torneio é **100% NumPy** (sem PyTorch), concluída em
microssegundos — PyTorch é necessário apenas para treinar.

---

## Origem do projeto (hackathon)

Este repositório nasceu de um *hackathon* de IA para poker da **ITA Jr**. A
linhagem **heurística** (v1–v14) dominou o pódio do torneio oficial — **v14
campeão** e **v13 vice** na Fase 2 — e os agentes de RL (v15/v16) são a evolução
direta desse trabalho, com o objetivo explícito de vencer o v14. A história
completa da linhagem está no [artigo](Artigo_RL_Poker_v15_v16.pdf).

Documentação do desafio original (para quem quer criar um bot):

- [`TOURNAMENT.md`](TOURNAMENT.md) — regras, formato e entrega do torneio.
- [`CONTEXTO_IA.md`](CONTEXTO_IA.md) — contexto da *engine* e da API
  (`decision()`, `GameView`) para colar em uma IA e receber ajuda.

---

## Dependências

- **Python ≥ 3.10** (testado em 3.14) e **NumPy**
- **PyTorch (com CUDA)** apenas para o treino

```bash
pip install numpy torch
```
