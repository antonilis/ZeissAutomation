@echo off
setlocal
rem ==========================================================================
rem  download.bat - run on a computer WITH internet.
rem
rem  Puts everything the microscope PC needs into the folder env\ next to this
rem  file: a portable Python, every package, the cellpose model. Afterwards copy
rem  the WHOLE folder to the microscope PC and run install.bat there; that one
rem  needs no internet.
rem
rem    download.bat          asks whether the microscope PC has an NVIDIA card
rem    download.bat --gpu    torch with CUDA, about 2.5 GB
rem    download.bat --cpu    torch for the CPU only, about 200 MB
rem ==========================================================================
cd /d "%~dp0"

rem Portable CPython from python-build-standalone. Change both lines together.
set "PY_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%%2B20261026-x86_64-pc-windows-msvc-install_only.tar.gz"
set "PY_SHA256=590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5"

set "ENV=%~dp0env"
set "PY=%ENV%\python\python.exe"

where curl.exe >nul 2>&1 || (echo ERROR: curl.exe not found, Windows 10 version 1803 or newer is needed. & goto :fail)
where tar.exe >nul 2>&1 || (echo ERROR: tar.exe not found, Windows 10 version 1803 or newer is needed. & goto :fail)

if exist "%PY%" goto :have_python

if not exist "%ENV%" mkdir "%ENV%"
echo Downloading Python 3.12 ...
curl.exe -L --fail -o "%ENV%\python.tar.gz" "%PY_URL%" || goto :fail
certutil -hashfile "%ENV%\python.tar.gz" SHA256 | findstr /i /c:"%PY_SHA256%" >nul || (echo ERROR: the Python download is damaged, checksum mismatch. & goto :fail)
tar -xzf "%ENV%\python.tar.gz" -C "%ENV%" || goto :fail
del "%ENV%\python.tar.gz"

:have_python
echo Python: %PY%
"%PY%" "%~dp0installer\download.py" %* || goto :fail

echo.
pause
exit /b 0

:fail
echo.
echo download.bat did NOT finish, see the messages above.
pause
exit /b 1
