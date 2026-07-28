@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\aifilm-audio-node\download_higgs_v2_generation_ranges.ps1
exit /b %errorlevel%
