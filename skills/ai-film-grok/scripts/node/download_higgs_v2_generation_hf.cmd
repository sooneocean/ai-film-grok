@echo off
setlocal EnableExtensions

set "AIFILM_NODE_ROOT=C:\aifilm-audio-node"
set "AIFILM_MODEL_DIR=%AIFILM_NODE_ROOT%\models\higgs-v2-generation"
set "AIFILM_EXPECTED_BYTES=11542613696"
set "AIFILM_HF=%AIFILM_NODE_ROOT%\venv-clean\Scripts\hf.exe"

if not exist "%AIFILM_MODEL_DIR%" mkdir "%AIFILM_MODEL_DIR%"
"%AIFILM_HF%" download bosonai/higgs-audio-v2-generation-3B-base model.safetensors ^
  --local-dir "%AIFILM_MODEL_DIR%"
if errorlevel 1 exit /b %errorlevel%

for %%I in ("%AIFILM_MODEL_DIR%\model.safetensors") do if not "%%~zI"=="%AIFILM_EXPECTED_BYTES%" exit /b 2
exit /b 0
