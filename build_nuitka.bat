@echo off
setlocal enabledelayedexpansion

echo ===============================================================================
echo                     NUITKA BUILD SCRIPT - "3rd break.exe"
echo           Translated from auto-py-to-exe configuration (execonfig.json)
echo ===============================================================================
echo.

:: -----------------------------------------------------------------------------
:: 1. Navigate to script directory so it works from any location
:: -----------------------------------------------------------------------------
cd /d "%~dp0"

:: -----------------------------------------------------------------------------
:: 2. Activate Virtual Environment (if available)
:: -----------------------------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment .venv...
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] .venv not found. Using current system Python environment.
)

:: -----------------------------------------------------------------------------
:: 3. Ensure Nuitka and required build tools are installed
:: -----------------------------------------------------------------------------
echo [INFO] Checking Nuitka installation...
python -c "import nuitka" 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Nuitka not found. Installing Nuitka and build utilities...
    uv pip install nuitka zstandard ordered-set
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Nuitka. Please check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Nuitka is already installed.
)

:: -----------------------------------------------------------------------------
:: 4. Resolve Icon Path (local fallback first, then absolute path from config)
:: -----------------------------------------------------------------------------
set "ICON_PATH=_internal\black_red.ico"
if not exist "%ICON_PATH%" (
    set "ICON_PATH=C:\Users\aksha\OneDrive\Documents\3 CANDLE ALL FIX\3 CANDLE FIX WEB\_internal\black_red.ico"
)

:: -----------------------------------------------------------------------------
:: 5. Run Nuitka Build
:: -----------------------------------------------------------------------------
echo.
echo [INFO] Starting Nuitka compilation for new_main.py...
echo [INFO] Target Executable: "3rd break.exe"
echo [INFO] Build Mode: Standalone distribution (Directory)
echo [INFO] Using Icon: %ICON_PATH%
echo.

:: =============================================================================
:: Nuitka Flag Mapping from execonfig.json:
::   --standalone                     : Standalone folder build ("onefile": false)
::                                      (Change to --onefile if you want a single EXE file)
::   --windows-console-mode=disable   : Hide console window ("console": false)
::                                      (Change to --windows-console-mode=force to debug logs)
::   --output-filename="3rd break.exe": Output binary name ("name": "3rd break")
::   --windows-icon-from-ico=...      : Windows EXE Icon ("icon_file")
::   --enable-plugin=pyqt6            : Required for PyQt6 GUI (new_ui.py)
::   --enable-plugin=numpy            : Required for Numpy optimizations
::   --include-package=NorenRestApiPy : Include local NorenRestApiPy package
::   --include-package-data=certifi   : Include SSL root certificates (cacert.pem)
::   --include-package-data=tzdata    : Include timezone data files
::   --include-module=runtime         : Include runtime.PY module ("runtime_hooks")
::   --output-dir=output\nuitka       : Build inside output\nuitka directory
::   --remove-output                  : Remove build temporary files ("noconfirm": true)
::   --assume-yes-for-downloads       : Automatically download C compiler if not installed
::   --show-progress                  : Show compilation progress in console
:: =============================================================================

python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --output-filename="3rd break.exe" ^
    --windows-icon-from-ico="%ICON_PATH%" ^
    --enable-plugin=pyqt6 ^
    --enable-plugin=numpy ^
    --include-package=NorenRestApiPy ^
    --include-package-data=certifi ^
    --include-package-data=tzdata ^
    --include-module=runtime ^
    --output-dir=output\nuitka ^
    --remove-output ^
    --assume-yes-for-downloads ^
    --show-progress ^
    new_main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Nuitka compilation failed!
    pause
    exit /b 1
)

:: -----------------------------------------------------------------------------
:: 6. Post-Build: Copy essential runtime configuration & data files
:: -----------------------------------------------------------------------------
echo.
echo [INFO] Compilation successful! Copying config and data files to distribution folder...

set "DIST_DIR=output\nuitka\new_main.dist"

:: Copy config YAML/JSON/CSV/TXT files if they exist in project root
if exist "*.yaml" copy /y "*.yaml" "%DIST_DIR%\" >nul
if exist "*.json" copy /y "*.json" "%DIST_DIR%\" >nul
if exist "*.csv" copy /y "*.csv" "%DIST_DIR%\" >nul
if exist "symbols.txt" copy /y "symbols.txt" "%DIST_DIR%\" >nul
if exist "symbols.zip" copy /y "symbols.zip" "%DIST_DIR%\" >nul

:: Copy _internal folder (for icons/credentials) if it exists
if exist "_internal" (
    if not exist "%DIST_DIR%\_internal" mkdir "%DIST_DIR%\_internal"
    xcopy /e /y /i "_internal\*" "%DIST_DIR%\_internal\" >nul
)

echo.
echo ===============================================================================
echo                       BUILD COMPLETED SUCCESSFULLY!
echo ===============================================================================
echo Executable location: %CD%\%DIST_DIR%\3rd break.exe
echo ===============================================================================
echo.
pause
