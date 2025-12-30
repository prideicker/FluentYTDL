@echo off
setlocal
cd /d "%~dp0"

echo Checking for package script...
if not exist "package_v2.ps1" (
    echo Error: package_v2.ps1 not found in current directory!
    echo Current dir: %CD%
    pause
    exit /b 1
)

:MENU
cls
echo ==============================================
echo FluentYTDL Packaging Helper (V2)
echo ==============================================
echo.
echo 1. Build Shell (Single EXE, No Tools)
echo 2. Build Full  (Single EXE + Tools in Zip)
echo 3. Build Dir   (Folder + Tools in Zip)
echo 4. Quit
echo.
set /p choice=Select [1-4]: 

if "%choice%"=="1" goto DO_SHELL
if "%choice%"=="2" goto DO_FULL_ZIP
if "%choice%"=="3" goto DO_DIR_FULL
if "%choice%"=="4" goto EOF
echo Invalid choice.
pause
goto MENU

:DO_SHELL
echo.
echo [CMD] Launching PowerShell Build (Shell)...
powershell -NoProfile -ExecutionPolicy Bypass -File "package_v2.ps1" -Mode onefile -Flavor shell -NoZip
goto CHECK_ERROR

:DO_FULL_ZIP
echo.
echo [CMD] Launching PowerShell Build (Full Zip)...
powershell -NoProfile -ExecutionPolicy Bypass -File "package_v2.ps1" -Mode onefile -Flavor full
goto CHECK_ERROR

:DO_DIR_FULL
echo.
echo [CMD] Launching PowerShell Build (Portable Folder)...
powershell -NoProfile -ExecutionPolicy Bypass -File "package_v2.ps1" -Mode onedir -Flavor full
goto CHECK_ERROR

:CHECK_ERROR
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build script failed with exit code %ERRORLEVEL%.
) else (
    echo.
    echo [SUCCESS] Build script completed successfully.
)
goto END

:EOF
exit /b 0

:END
echo.
pause
endlocal
