@echo off
REM run.bat - Starts the NetSage AI Streamlit application on Windows.

echo Starting NetSage AI...

REM Activate virtual environment if it exists
IF EXIST .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) ELSE (
    echo No .venv found. Continuing with system Python.
    echo Tip: python -m venv .venv  then  .venv\Scripts\activate  then  pip install -r requirements.txt
)

streamlit run src\app.py

pause
