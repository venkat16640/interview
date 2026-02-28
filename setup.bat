@echo off
echo =====================================
echo Intelligent Interview Platform Setup
echo =====================================
echo.

echo [1/6] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)
echo ✓ Virtual environment created

echo.
echo [2/6] Activating virtual environment...
call venv\Scripts\activate.bat
echo ✓ Virtual environment activated

echo.
echo [3/6] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo ✓ Dependencies installed

echo.
echo [4/6] Downloading spaCy model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo WARNING: spaCy model download failed. You may need to run this manually.
)
echo ✓ spaCy model downloaded

echo.
echo [5/6] Checking .env file...
if not exist .env (
    echo Creating .env from template...
    copy .env.example .env
    echo.
    echo WARNING: Please edit .env file and add your GEMINI_API_KEY
    echo.
)
echo ✓ Environment file ready

echo.
echo [6/6] Initializing database...
python run.py --init-only
echo ✓ Database initialized

echo.
echo =====================================
echo Setup Complete!
echo =====================================
echo.
echo IMPORTANT: Before running the application:
echo 1. Edit .env file and add your Google Gemini API key
echo 2. Ensure you have a working webcam and microphone
echo.
echo To start the application, run:
echo   python run.py
echo.
echo The application will be available at http://localhost:5000
echo.
pause
