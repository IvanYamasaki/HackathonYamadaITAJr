# Bots versão 15 / 16 — Reinforcement Learning (PPO)

Política aprendida por **PPO** em cima das features do v14. Treina na **GPU
(CUDA)**, é **retomável** (parar a qualquer momento não perde progresso) e
exporta os pesos para um forward **numpy puro** dentro de
`players/player_versao_15.py` (sem torch no torneio → inferência em
microssegundos, zero risco do timeout de 50 ms).

> **Dois treinos independentes** (mesma rede, mesmo pool v14,v13,v8,v1, do zero):
> - **v15** = `treinar.bat` → run `runs/v15_chip/`, reward **denso** (`chip`), pesos `weights_v15.npz`.
> - **v16** = `treinar_sparse.bat` → run `runs/v16_sparse/`, reward **esparso** (`win_loss`), pesos `weights_v16.npz`.
>
> Cada run tem seu próprio `treino.log` e `evolucao.png`. A única diferença
> entre os dois é o sistema de recompensa.

## Arquivos

| Arquivo | O quê |
|---|---|
| `../players_ivan/player_versao_15.py` | O bot. Carrega `weights_v15.npz` (ou usa fallback heurístico se não houver). **Self-contained.** O `player_versao_16.py` mora ao lado e herda dele. |
| `RELATORIO_v15_v16.md` | **Relatório completo**: implementação, diferença v15×v16, resultados de treino e a medição de 500 partidas/oponente. Comece por aqui. |
| `env.py` | Ambiente heads-up sobre a **engine real** (preserva o "pedágio"). |
| `model.py` | Rede Actor-Critic (PyTorch). |
| `train.py` | Loop PPO: CUDA, checkpoint atômico, resume, parada limpa. |
| `export.py` | Converte um checkpoint `.pt` → `weights_v15.npz`. |
| `avaliar.py` / `comparacao.py` / `contagem.py` | Medem a força real (greedy) vs cada bot antigo; `contagem.py` reporta **partidas vencidas**. |
| `treinar.bat` / `treinar_sparse.bat` | Atalhos: iniciam/retomam o treino do v15 / v16 na GPU. |
| `runs/{v15_chip,v16_sparse}/treino.log` | Log de treino de cada run (evidência por trás das tabelas do relatório). |
| `assets_relatorio/` | Gráficos usados no relatório (curvas de treino + partidas vencidas). |
| `weights_v15.npz` / `weights_v16.npz` | Pesos que os bots usam de fato. |

> **Não versionado** (ver `.gitignore`): os checkpoints `runs/**/checkpoints/*.pt`
> (estado de treino, pesado e regenerável — os bots jogam a partir dos `.npz`) e a
> pasta `_arquivo_pre_retreino_2026-06-27/` (processo anterior, já superado). Para
> retomar o treino numa máquina nova, rode `treinar.bat` com `--fresh` ou traga os
> `.pt` à parte.

## Como INICIAR o treino (você mesmo)

**Jeito fácil:** duplo-clique em `rl\treinar.bat`.

**Pelo terminal** (PowerShell, na raiz do projeto):

```powershell
& "C:\Users\ivang\AppData\Local\Python\bin\python.exe" rl\train.py --device cuda
```

A primeira vez começa do zero. Toda vez seguinte ele **retoma sozinho** do
último checkpoint — é só rodar o mesmo comando de novo.

## Como PARAR (sem perder nada)

- Na janela do treino, aperte **Ctrl+C** uma vez. Ele termina o update atual,
  salva o checkpoint e sai. (Apertar Ctrl+C duas vezes força saída sem salvar.)
- Mesmo se faltar energia / fechar no tapa: o treino salva sozinho a cada
  `--save-every` updates (padrão 10), com escrita **atômica** — o checkpoint
  nunca corrompe. No pior caso você perde só os últimos minutos.

## Como RETOMAR

Só rodar de novo (`treinar.bat` ou o comando acima). Ele acha
`checkpoints/latest.pt`, restaura modelo + optimizer + contadores + RNG e
continua. Para **recomeçar do zero**: adicione `--fresh` (apaga o progresso
lógico ao salvar por cima).

## Acompanhar / usar o bot

- Cada linha do log mostra: update, passos, **WR** (win-rate recente vs o pool
  de oponentes), recompensa média e perdas.
- O bot `versao_15` já joga com a política mais recente assim que o primeiro
  checkpoint é salvo (o treino exporta `weights_v15.npz` junto).
- Testar contra os outros bots (exemplo com seu sweeper):
  ```powershell
  & "C:\Users\ivang\AppData\Local\Python\bin\python.exe" sweep_v14.py --games 1000
  ```
  (ou rode o torneio normal — o `player_versao_15.py` é descoberto sozinho.)

## Opções úteis do `train.py`

| Flag | Padrão | O quê |
|---|---|---|
| `--device` | `cuda` | `cpu` força CPU. |
| `--num-envs` | 16 | partidas em paralelo (mais = rollout maior). |
| `--horizon` | 128 | passos por update. |
| `--save-every` | 20 (bat usa 10) | de quantos em quantos updates salva. |
| `--lr` | 3e-4 | taxa de aprendizado. |
| `--ent-coef` | 0.01 | bônus de entropia (exploração). |
| `--updates` | 100000 | quantos updates no total (deixe rodar e pare no Ctrl+C). |
| `--fresh` | — | ignora checkpoint e recomeça. |

## Recompensa (fácil, como pedido)

`r_t = (Δ fichas próprias)/(fichas totais)` a cada decisão **+** bônus terminal
(+1 ganhou a partida / −1 perdeu). Como a soma telescópica dá o resultado da
partida, o sinal denso aponta direto para **vencer**. Knobs em `env.py`
(`REWARD_*`). Dá pra evoluir depois (ex.: pesar mais o endgame).

## Pool de oponentes

Editável em `train.py` (`OPP_POOL`): hoje v14, v13, v8 e v1. Treinar contra um
mix evita criar um exploiter frágil de um bot só.
