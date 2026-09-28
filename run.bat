@echo off
rem DendroPivot - lanceur Windows. Transmet les arguments a launcher.py.
setlocal
set "DIR=%~dp0"
where py >nul 2>nul && (py -3 "%DIR%launcher.py" %* & goto :end)
where python >nul 2>nul && (python "%DIR%launcher.py" %* & goto :end)
echo Python 3.10+ introuvable : https://www.python.org/downloads/ 1>&2
exit /b 1
:end
exit /b %ERRORLEVEL%
