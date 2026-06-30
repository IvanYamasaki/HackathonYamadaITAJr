@echo off
REM ============================================================
REM  TREINO v15 — reward DENSO (chip): Dfichas + terminal +-1.
REM  Run isolado em rl\runs\v15_chip\ (checkpoints, log, grafico).
REM  Pesos de deploy estaveis em rl\weights_v15.npz.
REM  Do ZERO, pool v14,v13,v8,v1 (mesmo do v16; so muda o reward).
REM
REM  - Duplo-clique para comecar/continuar o treino.
REM  - Ctrl+C: salva o checkpoint, atualiza o grafico e sai limpo.
REM  - Rode de novo: continua de onde parou.
REM  - Para comecar do zero de novo: treinar.bat --fresh
REM ============================================================
setlocal
set PY=C:\Users\ivang\AppData\Local\Python\bin\python.exe
if not exist "%PY%" set PY=py
echo Usando Python: %PY%
"%PY%" "%~dp0train.py" --device cuda ^
  --run-name v15_chip --reward chip --opps v14,v13,v8,v1 ^
  --weights-out "%~dp0weights_v15.npz" --save-every 10 %*
echo.
echo (treino v15 encerrado — ver rl\runs\v15_chip\evolucao.png)
pause
