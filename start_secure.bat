@echo off
REM Imposta le variabili d'ambiente per la sicurezza
set FLASK_ENV=development
REM In produzione, usa 'production' invece di 'development'

REM Imposta una chiave segreta casuale (in produzione, usa una chiave fissa)
REM set SECRET_KEY=la-tua-chiave-segreta-molto-lunga-e-complessa

REM Avvia l'applicazione
python run.py