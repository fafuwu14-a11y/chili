@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   ChiLi / 赤鲤 - starting...
echo.
rem --data auto：有真实数据就用真实数据，没有才退回演示数据
rem --lan：顺便打印局域网地址，手机连同一个 Wi-Fi 就能开
python run.py --data auto --lan
if errorlevel 1 pause
