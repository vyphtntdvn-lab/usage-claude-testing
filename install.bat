@echo off
rem Cai dat mot cham: kiem tra moi truong, tai repo, chay thu, dang ky chay hang ngay.
rem Chay "install.bat check" de chi kiem tra ma khong dong gi.
setlocal enabledelayedexpansion

set "REPO_URL=https://github.com/tuanla-ntd-vn/ntd-claude-usage.git"
set "TARGET=%USERPROFILE%\ntd-claude-usage"
set "CHECKONLY="
if /i "%~1"=="check" set "CHECKONLY=1"

echo.
echo ============================================
echo   Claude Code usage - cai dat
echo ============================================
echo.

rem --- 1. python ---------------------------------------------------------
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [X] Khong tim thay Python 3.
    echo     Cai bang lenh:  winget install Python.Python.3.12
    echo     Roi mo lai file nay.
    goto :fail
)
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [OK] Python !PYVER!

rem --- 2. git -----------------------------------------------------------
git --version >nul 2>&1
if errorlevel 1 (
    echo [X] Khong tim thay Git. Script day du lieu len bang git nen bat buoc phai co.
    echo     Cai bang lenh:  winget install Git.Git
    echo     Cai xong mo cua so moi roi chay lai file nay.
    goto :fail
)
for /f "tokens=3" %%v in ('git --version') do set "GITVER=%%v"
echo [OK] Git !GITVER!

rem --- 3. transcript cua Claude Code -------------------------------------
if not exist "%USERPROFILE%\.claude\projects" (
    echo [!] Khong thay "%USERPROFILE%\.claude\projects".
    echo     May nay chua chay Claude Code bang tai khoan mac dinh, se khong co so lieu.
    echo     Van cai duoc, hom nao dung thi tu co du lieu.
) else (
    echo [OK] Co transcript trong %USERPROFILE%\.claude\projects
)

rem --- 4. repo ------------------------------------------------------------
if exist "%~dp0tools\claude_usage.py" (
    set "TARGET=%~dp0"
    if "!TARGET:~-1!"=="\" set "TARGET=!TARGET:~0,-1!"
    echo [OK] Dang chay tu trong repo san co: !TARGET!
) else if exist "%TARGET%\tools\claude_usage.py" (
    echo [OK] Da co repo tai %TARGET%, se cap nhat ban moi nhat
    if not defined CHECKONLY git -C "%TARGET%" pull --ff-only
) else (
    echo [ ] Se tai repo ve %TARGET%
    if not defined CHECKONLY (
        git clone "%REPO_URL%" "%TARGET%"
        if errorlevel 1 (
            echo [X] Tai repo that bai. Kiem tra mang hoac quyen truy cap repo.
            goto :fail
        )
    )
)

rem --- 5. ten may ---------------------------------------------------------
for /f "delims=" %%v in ('%PY% -c "import platform;print(platform.node())"') do set "DEFAULTMACHINE=%%v"
if "!DEFAULTMACHINE!"=="" set "DEFAULTMACHINE=%COMPUTERNAME%"
set "MACHINE=!DEFAULTMACHINE!"
if not defined CHECKONLY (
    set /p "MACHINE=Ten may hien trong bao cao [!DEFAULTMACHINE!]: "
    if "!MACHINE!"=="" set "MACHINE=!DEFAULTMACHINE!"
)
echo [OK] Ten may: !MACHINE!

if defined CHECKONLY (
    echo.
    echo Kiem tra xong, chua dong gi. Bo chu "check" de cai that.
    goto :done
)
> "%TARGET%\.machine" echo|set /p="!MACHINE!"

rem --- 6. chay thu (lan nay Git se hoi dang nhap mot lan) -----------------
echo.
echo --- Chay thu lan dau ---
echo Git co the hoi dang nhap o buoc nay. Dang nhap di, no nho luon cho nhung lan sau.
echo.
%PY% "%TARGET%\tools\claude_usage.py"
if errorlevel 1 (
    echo.
    echo [X] Chay thu that bai. Chua dang ky chay tu dong.
    echo     Xem chi tiet:  %TARGET%\.run.log
    goto :fail
)

rem --- 7. dang ky chay hang ngay ------------------------------------------
echo.
echo --- Dang ky chay tu dong ---
powershell -ExecutionPolicy Bypass -File "%TARGET%\tools\install-task.ps1" -Machine "!MACHINE!"
if errorlevel 1 (
    echo [X] Dang ky task that bai. Thu mo file nay bang chuot phai - Run as administrator.
    goto :fail
)

echo.
echo ============================================
echo   Xong. Moi ngay 23:47 se tu gom va day len.
echo   Bao cao: https://github.com/tuanla-ntd-vn/ntd-claude-usage
echo ============================================
goto :done

:fail
echo.
echo Cai dat chua hoan tat.
:done
echo.
pause
