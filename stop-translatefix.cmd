@echo off
rem Stops any running translatefix instance, from source or as the packaged exe.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'translatefix.exe' -or ($_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*translatefix.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
