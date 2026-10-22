@echo off
rem Builds dist\translatefix.exe - a single file that needs no Python installed.
rem
rem --noupx matters: UPX-packed executables trip far more antivirus heuristics,
rem and this tool already looks suspicious to them (it sends keystrokes, reads
rem the clipboard and talks to the network). The few MB saved are not worth it.

set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" make_icon.py
"%PY%" -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --noupx ^
    --clean ^
    --name translatefix ^
    --icon translatefix.ico ^
    --version-file version.txt ^
    translatefix.py

echo.
echo Built: dist\translatefix.exe
