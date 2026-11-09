@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
if "%~1"=="test" goto tests
if "%~1"=="run" shift
python src\main.py %1 %2 %3 %4 %5
exit /b %errorlevel%
:tests
python -m unittest discover -s tests -v
