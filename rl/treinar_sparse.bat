@echo off
REM ============================================================
REM  TREINO v16 — reward ESPARSO (win_loss): SO +-1 ao fim da
REM  partida (sem sinal de fichas no meio).
REM  Run isolado em rl\runs\v16_sparse\ (checkpoints, log, grafico).
REM  Pesos de deploy estaveis em rl\weights_v16.npz.
REM
REM  MESMA estrategia do v15: do ZERO (sem warm-start), MESMO pool
REM  v14,v13,v8,v1. A UNICA diferenca para o v15 e o reward.
REM  Obs.: reward esparso do zero aprende devagar (sinal fraco) —
REM  acompanhe rl\runs\v16_sparse\evolucao.png.
REM
REM  - Duplo-clique para comecar/continuar o treino.
REM  - Ctrl+C: salva, atualiza o grafico e sai limpo.
REM  - Rode de novo: continua de onde parou.
REM  - Para comecar do zero de novo: treinar_sparse.bat --fresh
REM ============================================================
setlocal
set PY=C:\Users\ivang\AppData\Local\Python\bin\python.exe
if not exist "%PY%" set PY=py
echo Usando Python: %PY%
"%PY%" "%~dp0train.py" --device cuda ^
  --run-name v16_sparse --reward win_loss --opps v14,v13,v8,v1 ^
  --weights-out "%~dp0weights_v16.npz" --save-every 10 %*
echo.
echo (treino v16 encerrado — ver rl\runs\v16_sparse\evolucao.png)
pause
