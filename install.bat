@echo off
setlocal
rem ==========================================================================
rem  install.bat - run on the microscope PC. Needs no internet.
rem
rem  Uses what download.bat put into env\: installs the packages, the cellpose
rem  model, copies ZeissAPI into ZEN's macro folder and writes path_config.json.
rem  Run it again after updating or moving this folder.
rem ==========================================================================
cd /d "%~dp0"

set "PY=%~dp0env\python\python.exe"

if exist "%PY%" goto :have_python
echo The folder env\python is missing.
echo Run download.bat first, on a computer with internet, then copy the whole folder here.
goto :fail

:have_python
"%PY%" "%~dp0installer\install.py" || goto :fail

echo.
pause
exit /b 0

:fail
echo.
echo install.bat did NOT finish, see the messages above.
pause
exit /b 1
