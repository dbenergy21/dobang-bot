@echo off
title 도방봇 GitHub 업로드
cd /d %~dp0

echo 🐷 도방육종 봇 업데이트 업로드 중...

git add bot.py
git add weaning_vision.py 2>NUL
git add weaning_photo_handler.py 2>NUL

:: 변경사항 있으면 commit + push
git diff --cached --quiet
if errorlevel 1 (
    for /f "tokens=*" %%i in ('powershell -command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set DATETIME=%%i
    git commit -m "봇 업데이트 %DATETIME%"
    git push origin main
    echo ✅ 업로드 완료! GitHub Actions가 자동으로 봇을 재시작합니다.
    echo 약 30초 후 봇이 재시작됩니다.
) else (
    echo ⚠️ 변경사항 없음
)

pause
