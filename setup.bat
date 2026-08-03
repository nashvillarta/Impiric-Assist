@echo off
title Installing SpaceWalker Assistant Dependencies
echo ==================================================
echo Installing Python dependencies for Voice Assistant...
echo ==================================================
ollama run phi3
/bye

pip install SpeechRecognition PyAudio pyautogui
pip install pyttsx3
pip install vosk pyaudio
pip install requests
echo.
echo ==================================================
echo Installation Complete! 
echo Now double-click 'run.bat' to start listening.
echo ==================================================
pause