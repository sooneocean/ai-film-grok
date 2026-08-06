@echo off
setlocal EnableExtensions
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0node.env") do set "%%A=%%B"
if not defined AIFILM_AUDIO_NODE_BIND_HOST set "AIFILM_AUDIO_NODE_BIND_HOST=127.0.0.1"
if /I not "%AIFILM_AUDIO_NODE_BIND_HOST%"=="127.0.0.1" (
  echo Audio node must bind to loopback and be reached through an SSH tunnel. 1>&2
  exit /b 2
)
set "HF_HUB_CACHE=C:\AI_Models\hf-cache"
set "HF_HUB_OFFLINE=1"
if defined AIFILM_AUDIO_NODE_FFMPEG for %%I in ("%AIFILM_AUDIO_NODE_FFMPEG%") do set "PATH=%%~dpI;%PATH%"
if defined AIFILM_AUDIO_NODE_SOX for %%I in ("%AIFILM_AUDIO_NODE_SOX%") do set "PATH=%%~dpI;%PATH%"
call "%~dp0venv-clean\Scripts\activate.bat"
cd /d "%~dp0"
python -m uvicorn audio_node_service:app --host "%AIFILM_AUDIO_NODE_BIND_HOST%" --port 8788
