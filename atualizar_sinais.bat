@echo off
REM Atualiza os sinais (CNO + PNCP) e publica para o painel.
REM Agendar 1x/dia no Agendador de Tarefas apontando para este arquivo.
cd /d "%~dp0"
if not exist logs mkdir logs
set PY=.venv\Scripts\python.exe
echo ===== %date% %time% ===== >> logs\agendador.log

"%PY%" jobs\coletar_cno.py  >> logs\agendador.log 2>&1
echo cno exit: %errorlevel% >> logs\agendador.log
"%PY%" jobs\coletar_pncp.py >> logs\agendador.log 2>&1
echo pncp exit: %errorlevel% >> logs\agendador.log

git add -f data\processed\SINAIS_CNO.csv data\processed\SINAIS_PNCP.csv data\processed\LOG_FONTES.csv >> logs\agendador.log 2>&1
git commit -m "Sinais automaticos %date%" >> logs\agendador.log 2>&1
git push origin sinais-cno >> logs\agendador.log 2>&1
