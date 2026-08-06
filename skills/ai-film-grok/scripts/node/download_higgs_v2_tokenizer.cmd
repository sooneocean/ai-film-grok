@echo off
setlocal EnableExtensions

set "AIFILM_NODE_ROOT=C:\aifilm-audio-node"
set "AIFILM_TOKENIZER_DIR=%AIFILM_NODE_ROOT%\models\higgs-v2-tokenizer"
set "AIFILM_EXPECTED_BYTES=805665628"
set "AIFILM_URL=https://huggingface.co/bosonai/higgs-audio-v2-tokenizer/resolve/main/model.safetensors"

if not exist "%AIFILM_TOKENIZER_DIR%" mkdir "%AIFILM_TOKENIZER_DIR%"
curl.exe -C - -L --fail --retry 100 --retry-all-errors --retry-delay 10 --connect-timeout 30 ^
  -o "%AIFILM_TOKENIZER_DIR%\model.safetensors" "%AIFILM_URL%"
if errorlevel 1 exit /b %errorlevel%

for %%I in ("%AIFILM_TOKENIZER_DIR%\model.safetensors") do if not "%%~zI"=="%AIFILM_EXPECTED_BYTES%" exit /b 2
exit /b 0
