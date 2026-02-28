@echo off
TITLE AI Interview Platform - Startup
color 0A

echo =============================================================
echo       AI INTERVIEW PLATFORM - STARTING...
echo =============================================================
echo.

:: Step 1: Find the best Python
set PYEXE=
if exist "venv\Scripts\python.exe" (
    set PYEXE=venv\Scripts\python.exe
    echo [OK] Using existing venv Python
    goto :check_flask
)

:: Try system Python
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYEXE=python
    echo [OK] Using system Python
    goto :create_venv
)

py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYEXE=py
    echo [OK] Using py launcher
    goto :create_venv
)

echo [ERROR] Python not found! Please install Python 3.9+
pause
exit /b 1

:create_venv
echo.
echo [Step] Creating virtual environment...
%PYEXE% -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Could not create venv — using system Python
    set PYEXE=python
    goto :install_deps
)
set PYEXE=venv\Scripts\python.exe
echo [OK] Virtual environment created

:check_flask
%PYEXE% -c "import flask" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Dependencies already installed
    goto :download_spacy
)

:install_deps
echo.
echo [Step] Installing dependencies (this may take 2-5 minutes)...
%PYEXE% -m pip install --upgrade pip --quiet
%PYEXE% -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Some packages may have failed. Trying core packages only...
    %PYEXE% -m pip install flask flask-sqlalchemy flask-cors google-generativeai opencv-python-headless deepface numpy spacy textblob SpeechRecognition librosa soundfile PyPDF2 python-docx pandas matplotlib reportlab Pillow python-dotenv requests --quiet
)
echo [OK] Dependencies installed

:download_spacy
echo.
echo [Step] Checking spaCy language model...
%PYEXE% -c "import spacy; spacy.load('en_core_web_sm')" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Step] Downloading spaCy model...
    %PYEXE% -m spacy download en_core_web_sm --quiet
)
echo [OK] spaCy model ready

:start_app
echo.
echo =============================================================
echo   Starting Flask Server at http://localhost:5000
echo   Press Ctrl+C to stop
echo =============================================================
echo.
%PYEXE% run.py

echo.
echo Server stopped.
pause
