@echo off
title Installing SpaceWalker Assistant Dependencies
echo ==================================================
echo Installing Python dependencies for Voice Assistant...
echo ==================================================

REM 'pull' not 'run': run opens an interactive REPL and blocks the script.
ollama pull phi3

REM Only what assistant.py actually imports.
pip install vosk pyaudio pyautogui requests

echo.
echo ==================================================
echo Rendering the voice pack...
echo ==================================================
python tools\generate_voice_pack.py

echo.
echo ==================================================
echo Installation Complete!
echo Now double-click 'run.bat' to start listening.
echo ==================================================
pause
