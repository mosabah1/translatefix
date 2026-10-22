@echo off
rem Runs translatefix from source, in the background (tray icon, no console).
rem
rem It is launched through WMI on purpose: that makes the system service the
rem parent, so the tool outlives the terminal or session that started it.
rem A plain "start" leaves it inside the caller's job object, and some shells
rem (agent harnesses, CI runners) kill the whole job on exit.

rem %%~zi is the file size: the Microsoft Store "python" on PATH is a 0-byte
rem stub that only opens the Store page, and WMI cannot launch it. Skip it.
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do (
    if not defined PYW if %%~zi GTR 0 set "PYW=%%i"
)
if not defined PYW if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not defined PYW (
    echo pythonw.exe not found on PATH. Install Python first.
    exit /b 1
)

powershell -NoProfile -Command "$p='%PYW%'; $s='%~dp0translatefix.py'; $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=('\"'+$p+'\" \"'+$s+'\"'); CurrentDirectory='%~dp0'}; if ($r.ReturnValue -ne 0) { Write-Host ('WMI launch failed: ' + $r.ReturnValue) }"
