@echo off
setlocal ENABLEDELAYEDEXPANSION

cd /d "%~dp0"

echo ==========================================
echo KOMIS Excel Updater 실행
echo ==========================================

if not exist ".venv" (
    echo [INFO] 가상환경(.venv) 생성 중...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 (
        python -m venv .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python 가상환경 생성 실패
    echo Python 설치 상태를 확인하세요.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] 필수 패키지 설치 실패
    pause
    exit /b 1
)

python src\main.py --base-dir "%~dp0"
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE%==0 (
    echo [SUCCESS] 작업이 완료되었습니다.
) else (
    echo [FAILED] 오류 코드: %EXIT_CODE%
)

echo.
echo 창을 닫으려면 아무 키나 누르세요.
pause >nul
exit /b %EXIT_CODE%
