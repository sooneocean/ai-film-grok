@echo off
setlocal EnableExtensions
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0node.env") do set "%%A=%%B"
call "%~dp0venv\Scripts\activate.bat"
cd /d "%~dp0"
python -m uvicorn audio_node_service:app --host 192.168.88.52 --port 8788
