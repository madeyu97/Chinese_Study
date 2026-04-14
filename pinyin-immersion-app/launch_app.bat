@echo off
title Pinyin Immersion Launcher
cd /d "%~dp0"

echo Starting Pinyin Immersion App...
python -m streamlit run src/main_app.py

pause