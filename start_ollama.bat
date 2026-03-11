@echo off
echo ============================================
echo   Starting Ollama with Qwen3.5-27B
echo ============================================
echo.
echo Pulling model (skips if already downloaded)...
ollama pull qwen3.5:27b
echo.
echo Model ready! Ollama serves automatically at http://localhost:11434
echo You can now start the bot in another terminal.
echo.
echo Press Ctrl+C to stop, or close this window.
ollama serve
pause
