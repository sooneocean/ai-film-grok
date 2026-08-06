@echo off
setlocal EnableExtensions

set "AIFILM_NODE_ROOT=C:\aifilm-audio-node"
set "AIFILM_MODEL_DIR=%AIFILM_NODE_ROOT%\models\higgs-v2-generation"
set "AIFILM_EXPECTED_BYTES=11542613696"
set "AIFILM_URL=https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base/resolve/main/model.safetensors"

if not exist "%AIFILM_MODEL_DIR%" mkdir "%AIFILM_MODEL_DIR%"
curl.exe -C - -L --fail --retry 100 --retry-all-errors --retry-delay 10 --connect-timeout 30 ^
  -o "%AIFILM_MODEL_DIR%\model.safetensors" "%AIFILM_URL%"
if errorlevel 1 exit /b %errorlevel%

for %%I in ("%AIFILM_MODEL_DIR%\model.safetensors") do if not "%%~zI"=="%AIFILM_EXPECTED_BYTES%" exit /b 2
exit /b 0
