@echo off
REM Ban BACKUP khong on-chain (Code 1, Nhom 4): cai thu vien -> dung panel tu cache -> test.
REM Mac dinh chay OFFLINE (chi dung du lieu da luu trong data\raw). Muon tai lai tu nguon: run_all.bat refresh
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo === 1/3 Cai thu vien ===
python -m pip install -r requirements.txt
if errorlevel 1 goto :loi

echo.
echo === 2/3 Dung panel (v1) ===
if /I "%1"=="refresh" (
  python -m src.data.build_panel --version v1 --refresh
) else (
  python -m src.data.build_panel --version v1 --offline
)
if errorlevel 1 goto :loi

echo.
echo === 3/3 Chay test (khong can mang) ===
python -m pytest -q
if errorlevel 1 goto :loi

echo.
echo XONG. Ket qua: data\processed\panel.parquet, outputs\tables\, outputs\appendix\
pause
exit /b 0

:loi
echo.
echo CO LOI. Chup lai man hinh va gui de duoc ho tro.
pause
exit /b 1
