@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\aifilm-audio-node\download-higgs-v2-ranges.ps1
exit /b %errorlevel%
