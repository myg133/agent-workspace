@echo off
setlocal
set "SCRIPT=%~dp0aw.py"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%" %*
) else (
  python "%SCRIPT%" %*
)
exit /b %errorlevel%
