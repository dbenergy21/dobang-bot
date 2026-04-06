═══════════════════════════════════════════════════════
🤖 도방육종 봇 GitHub 자동배포 설정 가이드
═══════════════════════════════════════════════════════

━━━ STEP 1: GitHub 레포 초기 설정 (최초 1회) ━━━

PowerShell에서 실행:

  cd C:\Users\User\Downloads\dobang-telegram-bot
  git init
  git remote add origin https://github.com/dbenergy21/dobang-bot.git
  git add .
  git commit -m "초기 설정"
  git push -u origin main

━━━ STEP 2: GitHub Secrets 등록 (최초 1회) ━━━

1. https://github.com/dbenergy21/dobang-bot 접속
2. Settings → Secrets and variables → Actions
3. New repository secret 으로 4개 등록:

   TELEGRAM_BOT_TOKEN  = 봇 토큰값
   NOTION_TOKEN        = 노션 API 키
   ADMIN_TELEGRAM_ID   = 대표님 텔레그램 숫자 ID
   ANTHROPIC_API_KEY   = Claude API 키

━━━ STEP 3: GitHub Actions Runner 설치 (최초 1회) ━━━

Runner = PC가 GitHub의 명령을 받아서 실행하는 프로그램

1. https://github.com/dbenergy21/dobang-bot/settings/actions/runners
2. "New self-hosted runner" 클릭
3. Windows 선택
4. 화면에 나오는 명령어 PowerShell에서 그대로 실행
5. 마지막에 "./run.cmd" 실행하면 Runner 시작

Runner를 항상 켜두려면 (백그라운드 서비스로 등록):
  .\svc.sh install
  .\svc.sh start

━━━ STEP 4: 이후 사용법 ━━━

도비가 bot.py를 수정해서 파일을 줍니다
    ↓
bot.py 파일을 봇 폴더에 교체
    ↓
push_update.bat 더블클릭
    ↓
완료! (30초 내 자동 재시작)

또는 텔레그램에서: /update_bot

━━━ 파일 목록 ━━━

bot.py                     봇 메인 파일
.github/workflows/deploy.yml  자동배포 설정
push_update.bat            업데이트 클릭 파일
requirements.txt           필요 패키지 목록
.gitignore                 .env 보호
.env                       환경변수 (GitHub에 올라가지 않음)

═══════════════════════════════════════════════════════
