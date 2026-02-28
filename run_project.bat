@echo off
echo =====================================
echo AI Interview Platform - Quick Start
echo =====================================
echo.

echo [Step 1] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Virtual environment not found!
    echo Creating new virtual environment...
    py -m venv venv
    call venv\Scripts\activate.bat
)
echo Virtual environment activated!
echo.

echo [Step 2] Upgrading pip...
python -m pip install --upgrade pip
echo.

echo [Step 3] Installing dependencies (this may take several minutes)...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    echo Please check the error messages above
    pause
    exit /b 1
)
echo Dependencies installed successfully!
echo.

echo [Step 4] Downloading spaCy language model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo WARNING: spaCy model download failed
    echo You may need to run this manually later
)
echo.

echo [Step 5] Starting the application...
echo.
echo =====================================
echo Server will start at http://localhost:5000
echo Press Ctrl+C to stop the server
echo =====================================
echo.
python run.py

pause
