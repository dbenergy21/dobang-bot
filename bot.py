"""
🐷 도방육종 업무봇 — 텍스트 자동 분류 강화 버전
"""
import os, logging, requests, asyncio, re, json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()
TOKEN              = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOTION_TOKEN       = os.getenv("NOTION_TOKEN", "")
ADMIN_ID           = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

NOTION_DB_SHIPOUT  = "399eb8a5-ba53-4754-85bb-63828f75f6a6"
NOTION_DB_LOG      = "1b6d6904-aed1-46e8-b378-0de23d614e10"
NOTION_DB_VACATION = "82299f8a-772f-4bac-b470-470c2aa1b170"
NOTION_DB_ORDER    = "c8ce6eac-dae2-429a-aa73-e43c63fe6704"

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 메뉴 버튼 — /메뉴 또는 /m 입력 시 팝업
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🐷 출하 보고"), KeyboardButton("💀 폐사 보고")],
        [KeyboardButton("⚠️ 이상 보고"), KeyboardButton("✅ 작업 완료")],
        [KeyboardButton("🏖️ 휴무 신청"), KeyboardButton("🌾 사료 주문")],
        [KeyboardButton("💊 약품 주문"), KeyboardButton("📦 소모품 주문")],
    ],
    resize_keyboard=True,
    is_persistent=False,   # 평소엔 고정 안 함
    one_time_keyboard=True,  # 선택 후 자동으로 닫힘
)

# 버튼 없이 메시지만 보내기 위한 keyboard 제거용
HIDE_KEYBOARD = ReplyKeyboardRemove()

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ══════════════════════════════════════════════════════════
# 🔍 강화된 자동 분류 엔진
# ══════════════════════════════════════════════════════════

# 출하 키워드
KW_SHIPOUT = [
    "출하", "xuất", "출하함", "출하했", "출하완료", "출하 완료",
    "나갔", "나감", "ship", "出荷", "마리 나", "두 나", "두수 출",
]

# 폐사 키워드
KW_DEATH = [
    "폐사", "죽", "죽었", "죽음", "사망", "chết", "폐사됨", "폐사했",
    "못 살", "숨졌", "절명", "die", "dead", "폐사두수",
    "폐사 ", " 폐사", "마리 죽", "두 죽",
]

# 이상/긴급 키워드
KW_ISSUE = [
    "이상", "고장", "문제", "누수", "누출", "화재", "긴급", "사고",
    "오작동", "멈춤", "멈췄", "작동안", "불량", "파손", "파열",
    "sự cố", "hỏng", "broken", "error", "alarm", "알람",
    "경보", "연기", "냄새", "악취", "온도 높", "온도 낮",
    "급하", "빨리", "빨리요", "urgent", "emergency",
]

# 작업완료 키워드
KW_DONE = [
    "완료", "끝", "마침", "다했", "했습니다", "했어요", "했어",
    "xong", "hoàn", "done", "finish", "완성", "마무리",
    "처리완료", "처리 완료", "작업 완료", "끝났",
]

# 휴무 키워드
KW_VACATION = [
    "휴무", "휴가", "쉬", "nghỉ", "쉬고싶", "쉬겠", "쉬어도",
    "day off", "off", "쉬는날", "휴일", "쉬는 날", "쉴게",
    "쉴게요", "쉬겠습니다", "휴무신청", "휴가신청",
]

# 휴무변경 전용 키워드
KW_VACATION_CHANGE = [
    "휴무변경", "휴무 변경", "휴무날짜변경", "휴무날짜 변경",
    "휴무변경신청", "휴무 변경 신청", "날짜변경", "휴가변경",
    "휴무수정", "휴무 수정",
]

# 사료 키워드 (사료 주문 전용 — 빈번호/톤수 동반 필수)
KW_FEED = [
    "사료 주문", "사료주문", "주문주세요", "사전주문",
    "젖돈 주문", "육돈 주문", "임신 주문", "포유 주문",
    "배합지시", "사료 부탁", "발주",
    # ── 입고 요청 패턴 (신기철 농장장 등)
    "입고해 주세요", "입고해주세요", "입고 해주세요",
    "사료 입고", "입고 부탁", "입고해",
    "넣어 주세요", "넣어주세요", "채워 주세요", "채워주세요",
]

# 벌크빈 위치 변경 키워드
KW_BIN_CHANGE = [
    "번으로 변경", "번을 변경", "변경해 주세요", "변경해주세요",
    "벌크빈변경", "벌크빈 변경", "벌크 변경", "사료변경",
    "사료 변경", "번에서", "번 → ", "번->",
    # 배합지시 수정 요청 패턴
    "배합 변경", "배합지시 변경", "배합수정", "배합 수정",
]

# 약품 주문 키워드
KW_MEDICINE_ORDER = [
    "병", "통", "박스", "포", "주문 부탁", "주문부탁",
    "약품 주문", "약 주문", "구매 부탁", "주문해 주세요",
]

# 사료 급이 현황 키워드 (주문 아님 — DM 안 보냄)
KW_FEED_STATUS = [
    "사료많아요", "사료 많아요", "사료없어요", "사료 없어요",
    "사료더주세요", "사료 더주세요", "사료줄여", "사료 줄여",
    "사료늘려", "사료 늘려", "급이", "많이먹어", "못먹어",
    "사료조절", "줄여달라", "늘려달라", "조절해",
    "사료가 많", "사료가 없", "밥그릇",
]

# 약품 키워드
KW_MEDICINE = [
    "약품", "약", "백신", "주사", "소독약", "항생제", "소염제",
    "thuốc", "vaccine", "medicine", "injection",
    "써코", "마이코", "구제역", "돼지열병", "PCV",
    "타이신", "암피실린", "린코마이신", "치료제",
    "약품 주문", "약 주문", "백신 주문",
]

# 소모품 키워드
KW_SUPPLY = [
    "소모품", "장갑", "마스크", "비닐", "소독", "청소",
    "vật tư", "supply", "글러브", "위생복", "방역복",
    "주사기", "바늘", "청소도구", "빗자루", "삽",
    "세제", "살균제", "소독제", "포대", "마대",
    "소모품 주문", "소모품주문",
]


KW_PREGNANCY = [
    "임신진단", "임신 진단", "임신확인", "임신 확인",
    "임진", "양성", "음성", "재발정", "발정재귀",
    "진단결과",
]


def classify(text: str) -> tuple:
    """
    텍스트를 분석해서 (카테고리, 신뢰도, 추출데이터) 반환
    신뢰도: 'high' = 확실 / 'medium' = 보통 / 'low' = 불확실
    """
    t = text.lower().strip()

    # 1. 폐사 (최우선 — 긴급도 높음)
    death_score = sum(1 for k in KW_DEATH if k in t)
    if death_score >= 1:
        nums = re.findall(r"\d+", text)
        두수 = nums[0] if nums else "미상"
        # 위치 패턴 추출 (A2, B4, 돈공 등)
        location = re.search(r"[A-Za-z가-힣]+\d+[\-\.\s]?\d*|돈공\d+|비육\w+|모돈\w+", text)
        loc_str = location.group() if location else ""
        return ("death", "high", {"두수": 두수, "위치": loc_str})

    # 2. 출하
    shipout_score = sum(1 for k in KW_SHIPOUT if k in t)
    if shipout_score >= 1:
        nums = re.findall(r"\d+", text)
        두수 = int(nums[0]) if nums else 0
        return ("shipout", "high" if 두수 > 0 else "medium", {"두수": 두수})

    # 3. 이상/긴급
    issue_score = sum(1 for k in KW_ISSUE if k in t)
    if issue_score >= 1:
        confidence = "high" if issue_score >= 2 else "medium"
        return ("issue", confidence, {})

    # 4-0. 사료 급이 현황 (주문 아님 — 먼저 체크해서 오탐 방지)
    feed_status_score = sum(1 for k in KW_FEED_STATUS if k in t)
    # 돈사 코드 패턴 감지 (C1, C3, A3, B2 등) + 사료 키워드 = 급이현황
    has_barn_code = bool(re.search('[A-Za-z][0-9 .]+', text))
    # 빈번호 패턴 (3-1, 7-2 등) = 주문 가능성
    has_bin_number = bool(re.search('[0-9]-[0-9]', text))
    # 톤수 패턴 (5톤, 3톤 등) = 주문 가능성
    has_ton = bool(re.search('[0-9]+톤', text))
    # 시간차 패턴 (2시차, 10시차) = 주문 가능성
    has_time_slot = bool(re.search('[0-9]+시차', text))

    if feed_status_score >= 1 or (has_barn_code and "사료" in t and not has_bin_number):
        return ("feed_status", "high", {"내용": text[:100]})

    # 4. 사료 주문 (빈번호 or 톤수 or 시간차 동반)
    feed_score = sum(1 for k in KW_FEED if k in t)
    # 사료 주문은 반드시 빈번호 or 톤수가 있어야 함
    if feed_score >= 1 and not (has_bin_number or has_ton or has_time_slot):
        # 사료 단어만 있고 주문 근거 없으면 → 일반 메시지로 처리
        feed_score = 0

    # 빈번호 + 입고 패턴 → 사료 주문으로 인식
    # 예: "4-2, 7-3, 15번 사료 입고해 주세요"
    has_ingo = any(k in text for k in ["입고", "넣어", "채워"])
    if feed_score == 0 and has_bin_number and has_ingo:
        feed_score = 8  # 입고 요청 패턴

    # 사료 키워드 없어도 빈번호+톤수 조합이면 대표님 주문으로 인식
    if feed_score == 0 and has_bin_number and has_ton:
        feed_score = 5  # 대표님 직접 주문 패턴

    # 날짜 + 빈번호 + 사료 = 사료 주문 확실
    has_date_mention = bool(re.search('[0-9]+월[0-9]+일|[0-9]+/[0-9]+', text))
    if feed_score == 0 and has_bin_number and has_date_mention and "사료" in text:
        feed_score = 7  # 날짜+빈번호+사료 패턴
    if feed_score >= 1:
        nums = re.findall(r"\d+", text)
        수량 = nums[0] + "포" if nums else ""
        return ("order_feed", "high", {"수량": 수량})

    # 5. 약품 주문
    med_score = sum(1 for k in KW_MEDICINE if k in t)
    if med_score >= 1:
        nums = re.findall(r"\d+", text)
        수량 = nums[0] if nums else ""
        return ("order_medicine", "high", {"수량": 수량})

    # 6. 소모품 주문
    supply_score = sum(1 for k in KW_SUPPLY if k in t)
    if supply_score >= 1:
        return ("order_supply", "high", {})

    # 5-1. 이유 보고 (먼저 체크 — "이유" 단어가 다른 분류와 겹칠 수 있음)
    weaning_kw_classify = [
        "이유", "이유예정", "이유완료", "이유함", "이유했", "이유하",
        "모돈 이유", "자돈 이유", "분만사 이유",
        "weaning", "wean",
    ]
    weaning_score = sum(1 for k in weaning_kw_classify if k in text)
    if weaning_score >= 1:
        return ("weaning", "high", {"원문": text[:100]})

    # 6-1. 벌크빈 위치 변경 (가장 먼저 체크)
    bin_change_score = sum(1 for k in KW_BIN_CHANGE if k in text)
    has_bin_from = bool(re.search(r'[0-9]+-[0-9]+번', text))
    if bin_change_score >= 1 and has_bin_from:
        # 변경 빈번호 추출
        bins = re.findall(r'([0-9]+-[0-9]+)번', text)
        return ("bin_change", "high", {"bins": bins, "원문": text[:100]})

    # 6-2. 약품 주문 자동 감지
    # 약품명 + 수량 + 단위 패턴 (병/통/박스/포)
    med_items = re.findall(r'([가-힣A-Za-z0-9\.]+)\s+(\d+(?:\.\d+)?)\s*(병|통|박스|포|개|set|Set)', text)
    if len(med_items) >= 2:  # 2개 이상 품목이면 약품 주문으로 판단
        return ("medicine_order", "high", {"items": med_items})

    # 7-0. 임신진단 보고 (먼저 체크)
    pregnancy_score = sum(1 for k in KW_PREGNANCY if k in text)
    if pregnancy_score >= 1:
        return ("pregnancy", "high", {"원문": text[:100]})

    # 7-1. 휴무변경 (휴무보다 먼저 체크)
    change_score = sum(1 for k in KW_VACATION_CHANGE if k in t)
    if change_score >= 1:
        return ("vacation_change", "high", {})

    # 7. 휴무
    vacation_score = sum(1 for k in KW_VACATION if k in t)
    if vacation_score >= 1:
        날짜 = parse_date(text)
        return ("vacation", "high" if 날짜 else "medium", {"날짜": 날짜})

    # 8. 완료
    done_score = sum(1 for k in KW_DONE if k in t)
    if done_score >= 1:
        return ("done", "medium", {})

    return ("general", "low", {})


def parse_date(text: str):
    """
    다양한 날짜 형식 인식:
    4/7  4-7  4.7  4월7일  4월 7일  07  7일  2026-04-07  20260407
    """
    now = datetime.now()
    t = str(text).strip()

    # YYYY-MM-DD 또는 YYYY/MM/DD 완전 형식 (연도 4자리)
    m = re.search(r"(20\d{2})[\-./](\d{1,2})[\-./](\d{1,2})", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # YYYYMMDD
    m = re.match(r"^(20\d{2})(\d{2})(\d{2})$", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # N월M일 또는 N월 M일 (월 먼저 처리)
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일?", t)
    if m:
        return f"{now.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    # M/D  (슬래시)
    m = re.search(r"(\d{1,2})/(\d{1,2})(?!\d)", t)
    if m:
        mon, day = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12 and 1 <= day <= 31:
            return f"{now.year}-{mon:02d}-{day:02d}"

    # M-D  (하이픈, 두 자리씩) — 빈번호(7-3)와 구별하기 위해 단독으로 있을 때만
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", t.strip())
    if m:
        mon, day = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12 and 1 <= day <= 31:
            return f"{now.year}-{mon:02d}-{day:02d}"

    # 숫자만 (예: "15" → 이번달 15일)
    m = re.fullmatch(r"(\d{1,2})", t.strip())
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return f"{now.year}-{now.month:02d}-{day:02d}"

    # N일
    m = re.search(r"(\d{1,2})일", t)
    if m:
        return f"{now.year}-{now.month:02d}-{int(m.group(1)):02d}"

    return None


def get_vacation_month_limit() -> int:
    """이번 달 휴무 한도 계산 — 설날/추석/8월=6일, 나머지=4일"""
    from datetime import datetime
    now = datetime.now()
    month = now.month
    # 설날 (1~2월), 추석 (9~10월), 8월 여름휴가
    if month in (1, 2, 9, 10, 8):
        return 6
    return 4


def get_pay_period():
    """현재 급여 계산 기간 반환 (전월 14일 ~ 당월 13일)"""
    from datetime import datetime, date
    now = datetime.now()
    if now.day >= 14:
        # 이번달 14일 ~ 다음달 13일
        start = date(now.year, now.month, 14)
        if now.month == 12:
            end = date(now.year + 1, 1, 13)
        else:
            end = date(now.year, now.month + 1, 13)
    else:
        # 전달 14일 ~ 이번달 13일
        if now.month == 1:
            start = date(now.year - 1, 12, 14)
        else:
            start = date(now.year, now.month - 1, 14)
        end = date(now.year, now.month, 13)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def get_vacation_history(staff: str, confirmed_date: str = None) -> str:
    """
    급여 계산 기간 내 직원 휴무 횟수 조회
    confirmed_date: 방금 확정된 날짜 (노션 반영 딜레이 보완용)
    반환: "4회 중 1회차 사용 / 잔여 3회"
    """
    try:
        period_start, period_end = get_pay_period()
        limit = get_vacation_month_limit()

        # 휴무 확정 DB 조회
        NOTION_DB_VACATION_CONFIRMED = "fcb20fc0-aa5c-4ef4-be3a-90ee6efeac1f"
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_VACATION_CONFIRMED}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "직원명", "select": {"equals": staff}},
                        {"property": "확정날짜", "date": {"on_or_after": period_start}},
                        {"property": "확정날짜", "date": {"on_or_before": period_end}},
                        {"property": "변경상태", "select": {"equals": "확정"}},
                    ]
                },
                "page_size": 20,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        # 사용 날짜 목록 추출
        dates = []
        for p in pages:
            d = p.get("properties", {}).get("확정날짜", {}).get("date", {})
            if d and d.get("start"):
                dates.append(d["start"])

        # 방금 확정된 날짜가 아직 노션에 미반영이면 직접 포함
        if confirmed_date and confirmed_date not in dates:
            dates.append(confirmed_date)

        # 날짜 정렬
        dates.sort()
        used   = len(dates)
        remain = max(0, limit - used)
        dates_str = ", ".join(dates) if dates else "-"

        # 회차별 날짜 표시 생성
        date_lines = []
        for idx, d in enumerate(dates, 1):
            # YYYY-MM-DD → M/D 형식으로 짧게
            try:
                parts = d.split("-")
                short = str(int(parts[1])) + "/" + str(int(parts[2]))
            except Exception:
                short = d
            date_lines.append(str(idx) + "회차: " + short)

        lines_out = [
            "이번 기간 (" + period_start + "~" + period_end + ")",
            str(limit) + "회 중 " + str(used) + "회 사용 / 잔여 " + str(remain) + "회",
        ]
        if date_lines:
            lines_out.extend(date_lines)
        return "\n".join(lines_out)
    except Exception as e:
        logger.warning(f"휴무 이력 조회 실패: {e}")
        # 조회 실패해도 방금 확정된 것만으로 기본 표시
        if confirmed_date:
            limit = get_vacation_month_limit()
            try:
                parts = confirmed_date.split("-")
                short = str(int(parts[1])) + "/" + str(int(parts[2]))
            except Exception:
                short = confirmed_date
            return (
                "이번 기간\n"
                + str(limit) + "회 중 1회 사용 / 잔여 " + str(limit - 1) + "회\n"
                + "1회차: " + short
            )
        return ""

# ══════════════════════════════════════════════════════════
# 직원명 매핑
# ══════════════════════════════════════════════════════════
STAFF_MAP = {
    "콰": "콰", "쾌": "콰", "kwa": "콰", "qua": "콰",
    "썬": "썬", "선": "썬", "sun": "썬",
    "츠엉": "츠엉", "쯔엉": "츠엉", "truong": "츠엉", "trưng": "츠엉",
    "하우": "하우", "hau": "하우",
    "박태식": "박태식", "태식": "박태식", "박": "박태식",
    "동": "동", "dong": "동",
}

def get_staff(name: str) -> str:
    nl = name.lower()
    for k, v in STAFF_MAP.items():
        if k in nl: return v
    return name

# ══════════════════════════════════════════════════════════
# 노션 함수들
# ══════════════════════════════════════════════════════════
def notion_log(업무: str, 상태: str, 비고: str = ""):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_LOG}, "properties": {
                "Name":    {"title": [{"text": {"content": f"{today} {업무[:20]}"}}]},
                "날짜":     {"date": {"start": today}},
                "업무내용": {"rich_text": [{"text": {"content": 업무}}]},
                "회사":     {"select": {"name": "도방육종"}},
                "수행여부": {"select": {"name": 상태}},
                "보고자":   {"select": {"name": "도비"}},
                "비고":     {"rich_text": [{"text": {"content": 비고}}]},
            }}, timeout=10)
    except Exception as e: logger.error(f"노션 로그 오류: {e}")

def notion_shipout(두수: int, 비고: str = ""):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_SHIPOUT}, "properties": {
                "Name":    {"title": [{"text": {"content": f"{today} 출하 {두수}두"}}]},
                "날짜":     {"date": {"start": today}},
                "출하두수": {"number": 두수},
                "확인자":   {"select": {"name": "도비"}},
                "메모":     {"rich_text": [{"text": {"content": 비고}}]},
            }}, timeout=10)
    except Exception as e: logger.error(f"출하 노션 오류: {e}")

def notion_order(직원명: str, 유형: str, 품목: str):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_ORDER}, "properties": {
                "Name":       {"title": [{"text": {"content": f"{today} {유형} {품목[:15]}"}}]},
                "date:주문날짜:start": today, "date:주문날짜:is_datetime": 0,
                "직원명":     {"select": {"name": 직원명}},
                "주문유형":   {"select": {"name": 유형}},
                "품목":       {"rich_text": [{"text": {"content": 품목}}]},
                "상태":       {"select": {"name": "📋 접수"}},
            }}, timeout=10)
    except Exception as e: logger.error(f"주문 노션 오류: {e}")

def notion_vacation_create(직원명: str, 날짜: str) -> str:
    if not NOTION_TOKEN: return ""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_VACATION}, "properties": {
                "Name":    {"title": [{"text": {"content": f"{직원명} 휴무신청 {날짜}"}}]},
                "직원명":   {"select": {"name": 직원명}},
                "date:신청일:start": today, "date:신청일:is_datetime": 0,
                "date:희망날짜:start": 날짜, "date:희망날짜:is_datetime": 0,
                "상태":     {"select": {"name": "🟡 대기중"}},
                "소스":     {"select": {"name": "텔레그램"}},
                "월":       {"number": now.month},
            }}, timeout=10)
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"휴무 노션 오류: {e}")
        return ""

def notion_vacation_update(page_id: str, 상태: str):
    if not NOTION_TOKEN or not page_id: return
    try:
        requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": {"상태": {"select": {"name": 상태}}}},
            timeout=10)
    except Exception as e: logger.error(f"휴무 업데이트 오류: {e}")

# ══════════════════════════════════════════════════════════
# 승인 키보드
# ══════════════════════════════════════════════════════════
# 승인/반려 버튼 데이터 임시 저장소 (64바이트 제한 우회)
_approval_store: dict = {}
_approval_counter: int = 0

def make_approval_kb(action_type: str, data: dict) -> InlineKeyboardMarkup:
    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {"type": action_type, **data}
    # callback_data는 짧은 키만 전달 (64바이트 이내)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 승인",     callback_data=f"approve|{key}"),
        InlineKeyboardButton("✏️ 수정승인", callback_data=f"modify|{key}"),
        InlineKeyboardButton("❌ 반려",     callback_data=f"reject|{key}"),
    ]])

# ══════════════════════════════════════════════════════════
# 🏖️ 휴무 승인 키보드 (앞당기기/뒤로 모두 가능)
# ══════════════════════════════════════════════════════════
def make_vacation_kb(data: dict) -> InlineKeyboardMarkup:
    """
    휴무 승인 버튼 4개:
    ✅ 승인 | 📅 날짜변경제안 | ❌ 반려
    날짜변경제안 = 앞당기기 또는 뒤로 미루기 모두 가능
    """
    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {"type": "vacation", **data}
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 승인",         callback_data=f"approve|{key}"),
        InlineKeyboardButton("📅 날짜변경제안", callback_data=f"vac_suggest|{key}"),
        InlineKeyboardButton("❌ 반려",         callback_data=f"reject|{key}"),
    ]])


def notion_vacation_change(page_id: str, new_date: str,
                            orig_date: str = "", changed_at: str = "") -> bool:
    """
    노션 휴무 확정 DB에서 날짜 변경 반영
    - 확정날짜를 new_date로 업데이트
    - 변경이력 기록
    - 상태를 ✅ 확정으로 변경
    """
    if not NOTION_TOKEN or not page_id:
        return False
    changed_at = changed_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    change_note = f"[{changed_at}] {orig_date} → {new_date} 변경"
    try:
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": {
                "date:휴무날짜:start":      new_date,
                "date:휴무날짜:is_datetime": 0,
                "상태":  {"select": {"name": "✅ 확정"}},
                "비고":  {"rich_text": [{"text": {"content": change_note}}]},
            }},
            timeout=10)
        logger.info(f"휴무 날짜 변경: {page_id} {orig_date}→{new_date}")
        return True
    except Exception as e:
        logger.error(f"휴무 날짜 변경 오류: {e}")
        return False


# ══════════════════════════════════════════════════════════
# 콜백 핸들러 (승인/반려)
# ══════════════════════════════════════════════════════════
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "|" not in query.data: return
    action, key = query.data.split("|", 1)

    # ── 사료회사 문자 발송 콜백 (우선 처리) ──
    if await handle_company_msg_callback(action, key, query, ctx):
        return

    # 저장소에서 데이터 꺼내기
    payload = _approval_store.get(key)
    if not payload:
        await query.edit_message_text("⚠️ 만료된 요청입니다. 다시 시도해주세요.")
        return

    atype   = payload.get("type")
    staff   = payload.get("staff", "")
    content = payload.get("content", "")
    gid     = payload.get("group_id", 0)

    # ── 벌크빈 변경 승인 처리 ──
    if atype == "bin_change":
        from_bin  = payload.get("from_bin", "")
        to_bin    = payload.get("to_bin", "")
        feed_type = payload.get("feed_type", "사료")
        ton       = payload.get("ton", "5톤")
        gid       = payload.get("group_id", 0) or ctx.bot_data.get("main_group_id", 0)
        sender    = payload.get("sender", "")
        company_msg = payload.get("company_msg", "")

        if action == "approve":
            # 1. 노션 주문DB 업데이트 (변경이력)
            notion_log(
                f"벌크빈 변경 확정: {from_bin}→{to_bin}",
                "✅ 완료", 비고=f"대표님 승인")

            # 2. 배합지시 재생성 안내
            dispatch_msg = (
                "\u2705 \ubc8c\ud06c\ube48 \ubcc0\uacbd \ud655\uc815\n"
                + from_bin + "\ubc88 \u2192 " + to_bin + "\ubc88\n\n"
                + "\ubc30\ud569\uc9c0\uc2dc:\n"
                + feed_type + " " + ton + " " + to_bin + "\ubc88\n\n"
                + "\u2500\u2500 \uc0ac\ub8cc\ud68c\uc0ac \ubc1c\uc1a1 \ubb38\uc790 \u2500\u2500\n"
                + company_msg
            )
            await query.edit_message_text(dispatch_msg)

            # 3. 업무방 공지
            if gid:
                await ctx.bot.send_message(gid,
                    "🔄 벌크빈 변경 확정\n"
                    + from_bin + "번 → " + to_bin + "번\n"
                    + "배합지시에 반영됩니다")

        elif action == "modify":
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload": payload,
                "mode":    "bin_change",
                "chat_id": query.message.chat_id,
            }
            await query.edit_message_text(
                "✏️ 변경 내용 수정:\n/modify_" + key + " 수정된 내용 입력")

        else:
            await query.edit_message_text(
                "❌ 벌크빈 변경 반려\n" + from_bin + "→" + to_bin)
            if gid:
                await ctx.bot.send_message(gid, "🔄 벌크빈 변경 반려됨 (" + from_bin + "→" + to_bin + ")")

    # ── 작업지시 콜백 처리 ──
    if atype == "work_order":
        order_text = payload.get("order_text", "")
        barn       = payload.get("barn", "")
        gid        = payload.get("group_id", 0) or ctx.bot_data.get("main_group_id", 0)

        if action == "approve":
            if gid:
                await ctx.bot.send_message(gid, order_text)
            await query.edit_message_text(
                "✅ 작업지시 발송 완료\n\n" + order_text)
            # 노션 처리여부 업데이트
            notion_log(f"작업지시 발송: {barn}", "✅ 완료", 비고="대표님 승인")

        elif action == "modify":
            # 수정후발송 — 수정 내용 입력 요청
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload": payload,
                "mode":    "work_order",
                "chat_id": query.message.chat_id,
            }
            await query.edit_message_text(
                "✏️ 수정할 내용 입력:\n"
                + "/modify_" + key + " 수정된 작업지시 내용")

        else:  # reject
            await query.edit_message_text("❌ 작업지시 취소")
        return

    # ── 휴무변경 승인/반려 처리 ──
    if atype == "vacation_change":
        old_date = payload.get("old_date", "")
        new_date = payload.get("new_date", "")
        page_id  = payload.get("page_id", "")
        cal_id   = payload.get("cal_id", "")
        gid      = payload.get("group_id", 0)
        staff_id = payload.get("staff_id", 0)

        if action == "approve":
            # 노션 업데이트
            await update_vacation_in_notion(page_id, old_date, new_date, staff)
            # 구글 캘린더 업데이트
            await update_vacation_in_calendar(ctx, cal_id, staff, new_date)
            history = get_vacation_history(staff, new_date)
            # 구글 캘린더 업데이트 (도비가 처리)
            cal_updated = await update_vacation_in_calendar(ctx, cal_id, staff, new_date)
            cal_note = "구글 캘린더 자동 반영 예약됨" if cal_updated else ""

            confirm_msg = "\n".join(filter(None, [
                "🔄 휴무변경 확정",
                staff + " / " + old_date + " → " + new_date,
                cal_note,
                "",
                history,
            ]))
            await query.edit_message_text(confirm_msg)
            if gid:
                await ctx.bot.send_message(gid, confirm_msg)
            if staff_id:
                try:
                    await ctx.bot.send_message(staff_id, confirm_msg)
                except: pass
        else:
            await query.edit_message_text(
                "❌ 휴무변경 반려\n" + staff + " / " + old_date + " → " + new_date)
            if gid:
                await ctx.bot.send_message(gid,
                    "🔄 휴무변경 반려\n" + staff + " / " + old_date)
            if staff_id:
                try:
                    await ctx.bot.send_message(staff_id,
                        "❌ 휴무변경 반려\n" + old_date + " 변경 신청이 반려되었습니다")
                except: pass
        return

    if atype == "vacation":
        날짜    = payload.get("date", "")
        page_id = payload.get("page_id", "")
        staff_id = payload.get("staff_id", 0)  # 직원 텔레그램 chat_id

        if action == "approve":
            # 노션 저장 + 횟수 조회
            notion_vacation_update(page_id, "✅ 확정")
            notion_log(f"휴무 승인: {staff} {날짜}", "✅ 완료", 비고="대표님 승인")
            # 이번달 휴무 이력 조회
            history_text = get_vacation_history(staff, confirmed_date=날짜)
            confirm_msg = (
                f"🏖️ 휴무 확정!\n"
                f"직원: {staff}\n"
                f"날짜: {날짜}\n\n"
                f"{history_text}")
            await query.edit_message_text(confirm_msg)
            # 업무방 알림
            if gid:
                await ctx.bot.send_message(gid, confirm_msg)
            # 직원 개인 DM (chat_id 있을 때)
            if staff_id:
                try:
                    await ctx.bot.send_message(staff_id, confirm_msg)
                except Exception as e:
                    logger.warning(f"직원 DM 실패: {e}")

        elif action == "vac_suggest":
            # 날짜 변경 제안 — 대표님께 날짜 입력 요청
            ctx.bot_data[f"vac_suggest_wait_{key}"] = {
                "payload": payload,
                "chat_id": query.message.chat_id,
            }
            await query.edit_message_text(
                f"📅 제안 날짜 입력\n"
                f"직원: {staff} / 신청날짜: {날짜}\n\n"
                f"/날짜제안_{key} 날짜\n"
                f"예) /날짜제안_{key} 4/12\n"
                f"    /날짜제안_{key} 4월12일\n"
                f"    /날짜제안_{key} 2026-04-12")

        else:  # reject
            notion_vacation_update(page_id, "❌ 반려")
            notion_log(f"휴무 반려: {staff} {날짜}", "❌ 미수행", 비고="대표님 반려")
            await query.edit_message_text(
                f"❌ 휴무 반려\n직원: {staff}\n날짜: {날짜}")
            if gid:
                await ctx.bot.send_message(gid,
                    f"🏖️ 휴무 반려\n{staff} / {날짜}")
            if staff_id:
                try:
                    await ctx.bot.send_message(staff_id,
                        f"❌ 휴무 반려\n신청날짜: {날짜}")
                except: pass

    # ── 직원 수락/거절 콜백 ──
    elif atype == "vac_staff_response":
        orig_date    = payload.get("orig_date", "")
        suggest_date = payload.get("suggest_date", "")
        page_id      = payload.get("page_id", "")
        staff_name   = payload.get("staff", "")
        g_id2        = payload.get("group_id", 0)

        if action == "vac_accept":
            # 노션 확정날짜 변경 + 변경이력 기록
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            notion_vacation_change(
                page_id=page_id,
                new_date=suggest_date,
                orig_date=orig_date,
                changed_at=now_str,
            )
            history_text = get_vacation_history(staff_name, confirmed_date=final_date)
            confirm_msg = (
                f"🏖️ 휴무 확정! (날짜 변경)\n"
                f"직원: {staff_name}\n"
                f"🔴 원래 신청: {orig_date}\n"
                f"🟢 확정 날짜: {suggest_date}\n\n"
                f"{history_text}")
            await query.edit_message_text(confirm_msg)
            if g_id2:
                await ctx.bot.send_message(g_id2, confirm_msg)
            if ADMIN_ID:
                await ctx.bot.send_message(ADMIN_ID, confirm_msg)

        else:  # vac_reject
            await query.edit_message_text(
                f"❌ 날짜 변경 거절\n"
                f"{staff_name}님이 {suggest_date} 제안을 거절했습니다\n"
                f"다시 협의해주세요")
            if ADMIN_ID:
                await ctx.bot.send_message(ADMIN_ID,
                    f"⚠️ {staff_name}님이 날짜 제안 거절\n"
                    f"제안: {suggest_date}\n다시 날짜를 제안하거나 승인/반려 해주세요")

    # ── 배합지시 발송 처리 ──
    if action in ("dispatch_send", "dispatch_modify", "dispatch_cancel"):
        dispatch_payload = _approval_store.get(key)
        if not dispatch_payload:
            await query.edit_message_text("⚠️ 만료된 배합지시 요청입니다")
            return

        dispatch_text = dispatch_payload.get("dispatch_text", "")
        staff         = dispatch_payload.get("staff", "")

        if action == "dispatch_send":
            group_id = ctx.bot_data.get("main_group_id", 0)

            # 날짜 추출 → 예약 발송 DM 전송
            target_date = extract_dispatch_date(dispatch_text)
            original_order = dispatch_payload.get("vision_raw", "")
            await send_dispatch_schedule_kb(
                ctx, dispatch_text, target_date, original_order,
                edit_msg=query.message
            )
            _approval_store.pop(key, None)
            return

            # (하위 코드는 sched_* 콜백에서 처리)
            import re as _re
            time_hint = ""
            t_match = _re.search(r"(\d+)시차", dispatch_text)
            if t_match:
                arrival_hour = int(t_match.group(1))
                prep_hour    = arrival_hour - 1
                prep_min     = 30
                if prep_min == 60:
                    prep_hour += 1; prep_min = 0
                ampm = "오후" if arrival_hour >= 12 else "오전"
                prep_ampm = "오후" if prep_hour >= 12 else "오전"
                disp_hour = arrival_hour - 12 if arrival_hour > 12 else arrival_hour
                prep_disp = prep_hour - 12 if prep_hour > 12 else prep_hour
                time_hint = (
                    f"\n\n⏰ {ampm} {disp_hour}시 입고 예정"
                    f"\n{prep_ampm} {prep_disp}시 {prep_min:02d}분까지 배합 완료 부탁드립니다"
                )

            group_msg = "🌾 사료 배합지시\n\n" + dispatch_text + time_hint

            if group_id:
                await ctx.bot.send_message(group_id, group_msg)

            # 마지막 배합지시 저장
            ctx.bot_data["last_dispatch"] = {
                "text":    dispatch_text,
                "orders":  dispatch_payload.get("orders", []),
                "staff":   dispatch_payload.get("staff", ""),
                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            await query.edit_message_text(
                "✅ 배합지시 발송 완료\n\n" + dispatch_text +
                (time_hint if time_hint else "") +
                "\n\n변경 필요 시: /변경 또는 /추가 입력")
            _approval_store.pop(key, None)

        elif action == "dispatch_modify":
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload":  dispatch_payload,
                "chat_id":  query.message.chat_id,
                "mode":     "feed_dispatch",
            }
            await query.edit_message_text(
                f"✏️ 수정할 내용을 입력해주세요\n"
                f"원본:\n{dispatch_text}\n\n"
                f"/modify_{key} 수정된내용 입력")

        elif action == "dispatch_cancel":
            await query.edit_message_text("❌ 배합지시 취소됨")
            _approval_store.pop(key, None)
        return

    # ── 배합지시 예약 취소 콜백 ──
    if action == "cancel_dispatch":
        cancel_payload = _approval_store.get(key, {})
        page_id  = cancel_payload.get("page_id", "")
        dt_str   = cancel_payload.get("dt_str", "")
        preview  = cancel_payload.get("preview", "")
        if page_id:
            await update_dispatch_schedule_status(page_id, "❌ 취소")
        await query.edit_message_text(
            f"❌ 배합지시 예약 취소 완료\n{dt_str[:16]}\n{preview[:50]}")
        _approval_store.pop(key, None)
        return

    # ── 배합지시 예약발송 콜백 ──
    if action in ("sched_ok", "sched_edit", "sched_now", "sched_cancel"):
        sched_payload = _approval_store.get(key)
        if not sched_payload:
            await query.edit_message_text("⚠️ 만료된 예약 요청입니다")
            return

        dispatch_text = sched_payload.get("dispatch_text", "")
        target_date   = sched_payload.get("target_date", "")
        orig_order    = sched_payload.get("original_order", "")
        gid           = ctx.bot_data.get("main_group_id", 0)

        if action == "sched_ok":
            # 예약발송 — 노션 저장 + job_queue 등록
            page_id = await save_dispatch_schedule(dispatch_text, target_date, orig_order)
            _approval_store[key]["schedule_page_id"] = page_id

            schedule_dt = calc_schedule_time(target_date)
            delay = max(0, (schedule_dt - datetime.now()).total_seconds())

            async def _do_send(ctx_inner, dt=dispatch_text, g=gid, pid=page_id):
                await execute_scheduled_dispatch(ctx_inner, dt, g, pid)

            ctx.application.job_queue.run_once(_do_send, when=delay)

            # 구글 캘린더에 예약 등록 (참고용)
            schedule_str = schedule_dt.strftime("%Y-%m-%dT%H:%M:00")
            notion_log(
                f"배합지시 예약: {target_date} 07:00",
                "⏰ 예약중",
                비고=f"배합지시 예약발송 등록"
            )

            await query.edit_message_text(
                "⏰ 예약발송 등록 완료\n"
                + target_date + " 오전 7시에 단톡방 자동 발송\n\n"
                + dispatch_text + "\n\n"
                + "수정: /배합변경  |  취소: /배합취소")
            _approval_store.pop(key, None)

        elif action == "sched_now":
            # 지금 즉시 발송
            await execute_scheduled_dispatch(ctx, dispatch_text, gid)
            await query.edit_message_text(
                "✅ 배합지시 즉시 발송 완료\n\n" + dispatch_text)
            _approval_store.pop(key, None)

        elif action == "sched_edit":
            # 수정후예약
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload": sched_payload,
                "mode":    "dispatch_schedule",
                "chat_id": query.message.chat_id,
            }
            await query.edit_message_text(
                "✏️ 수정할 배합지시 입력:\n"
                + "/modify_" + key + " 수정된 배합지시")

        elif action == "sched_cancel":
            await query.edit_message_text("❌ 배합지시 예약 취소")
            _approval_store.pop(key, None)
        return

    # ── 배합지시 재발송 콜백 ──
    if action in ("resend_ok", "resend_edit", "resend_cancel"):
        resend_payload = _approval_store.get(key)
        if not resend_payload:
            await query.edit_message_text("⚠️ 만료된 재발송 요청입니다")
            return

        new_text  = resend_payload.get("new_text", "")
        orig_text = resend_payload.get("orig_text", "")
        g_id      = resend_payload.get("group_id") or ctx.bot_data.get("main_group_id", 0)
        mode      = resend_payload.get("mode", "change")
        label     = "변경" if mode == "change" else "추가"

        if action == "resend_ok":
            if g_id:
                send_text = f"🔄 배합지시 {label}" + "\n\n" + new_text
                await ctx.bot.send_message(g_id, send_text)
            # last_dispatch 업데이트
            changed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            ctx.bot_data["last_dispatch"] = {
                "text":    new_text,
                "sent_at": changed_at,
            }
            # ── 노션 주문 DB 자동 동기화 ──
            synced = notion_update_order_change(
                original_text=orig_text,
                new_text=new_text,
                change_mode=mode,
                changed_at=changed_at,
            )
            notion_msg = "\n✅ 노션 주문 DB 자동 업데이트 완료" if synced else "\n⚠️ 노션 수동 확인 필요"

            await query.edit_message_text(
                "✅ 배합지시 " + label + " 재발송 완료\n\n"
                "🔴 원본:\n" + orig_text + "\n\n"
                "🟢 " + label + ":\n" + new_text + "\n" + notion_msg + "\n\n"
                "추가 변경: /변경  |  품목추가: /추가  |  재발송: /재발송")
            _approval_store.pop(key, None)

        elif action == "resend_edit":
            # 한 번 더 수정
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload": resend_payload,
                "mode":    "feed_dispatch",
                "chat_id": query.message.chat_id,
            }
            await query.edit_message_text("✏️ 추가 수정 내용 입력:\n/modify_" + key + " 최종내용")


        elif action == "resend_cancel":
            await query.edit_message_text("❌ 재발송 취소됨")
            _approval_store.pop(key, None)
        return

    elif atype == "order":
        유형 = payload.get("order_type", "")
        if action == "approve":
            notion_log(f"{유형} 주문 승인: {content}", "✅ 완료", 비고=f"대표님 승인 — {staff}")

            # ── 사료 주문인 경우 추가 흐름 실행 ──
            if "사료" in 유형:
                await _handle_feed_order_approved(
                    ctx, query, content, staff, gid, key, payload)
                return

            # 사료 외 주문 (약품/소모품) — 기존 처리
            await query.edit_message_text(
                "✅ 주문 승인\n" + 유형 + "\n" + staff + ": " + content[:80])
            if gid:
                await ctx.bot.send_message(gid,
                    "✅ " + 유형 + " 주문 승인\n" + staff + " / " + content[:80])

        elif action == "modify":
            # 수정후승인 — 대표님께 수정 내용 입력 요청
            _approval_store[f"modify_{key}"] = payload  # 원본 보관
            await query.edit_message_text(
                f"✏️ 수정 내용을 입력해주세요\n"
                f"원본: {content}\n\n"
                f"아래 형식으로 답장해주세요:\n"
                f"/modify_{key} 수정된내용")
            # ctx에 수정 대기 상태 저장
            ctx.bot_data[f"modify_wait_{key}"] = {
                "payload": payload,
                "chat_id": query.message.chat_id,
            }

        else:  # reject
            반려사유 = payload.get("reject_reason", "")
            notion_log(f"{유형} 주문 반려: {content}", "❌ 미수행", 비고=f"대표님 반려 — {staff}")
            await query.edit_message_text(f"❌ 주문 반려\n{유형}\n{staff}: {content}")
            if gid:
                await ctx.bot.send_message(gid,
                    f"❌ {유형} 주문 반려\n{staff} / {text[:50]}")

# ══════════════════════════════════════════════════════════
# 일일 보고 (매일 07:00)
# ══════════════════════════════════════════════════════════
async def daily_report(ctx):
    if not ADMIN_ID: return
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_LOG}/query",
            headers=NOTION_HEADERS,
            json={"filter": {"property": "날짜", "date": {"equals": yesterday}}},
            timeout=10)
        results = res.json().get("results", [])
    except: results = []

    cats = {"🐷 출하": [], "💀 폐사": [], "⚠️ 이상": [],
            "🌾 사료": [], "💊 약품": [], "📦 소모품": [],
            "🏖️ 휴무": [], "📝 기타": []}

    for r in results:
        props = r.get("properties", {})
        업무 = props.get("업무내용", {}).get("rich_text", [{}])
        업무 = 업무[0].get("text", {}).get("content", "") if 업무 else ""
        비고 = props.get("비고", {}).get("rich_text", [{}])
        비고 = 비고[0].get("text", {}).get("content", "") if 비고 else ""

        matched = False
        for key in cats:
            if key.split()[-1] in 업무:
                cats[key].append(f"{업무[:30]} ({비고[:15]})")
                matched = True
                break
        if not matched:
            cats["📝 기타"].append(업무[:30])

    lines = [f"📊 도비 일일 보고 ({yesterday})\n"]
    total = 0
    for cat, items in cats.items():
        if items:
            lines.append(f"{cat} {len(items)}건")
            for item in items:
                lines.append(f"  └ {item}")
            total += len(items)
    lines.insert(1, f"총 {total}건\n")

    if total == 0:
        lines = [f"📊 도비 일일 보고 ({yesterday})\n보고된 내용이 없습니다."]

    await ctx.bot.send_message(chat_id=ADMIN_ID, text="\n".join(lines))

# ══════════════════════════════════════════════════════════
# start
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
# 📋 /메뉴 명령어 — 버튼 팝업
# ══════════════════════════════════════════════════════════
async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /메뉴 또는 /m 입력 시 버튼 팝업
    평소엔 버튼이 없어서 화면이 넓음
    필요할 때만 버튼 표시
    """
    msg = update.message
    if not msg: return
    await msg.reply_text(
        "📋 도방육종 봇\n\n텍스트로 바로 입력하세요:\n폐사보고 / 출하보고 / 이유 / 휴무신청\n\n/상태 /배합취소 /이유통계 /현황",
        
    )

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐷 도방육종 업무봇\n\n"
        "/메뉴 또는 /m — 버튼 메뉴 열기\n\n"
        "텍스트로 바로 입력 가능:\n"
        "폐사보고 / 출하보고 / 휴무신청\n"
        "사료주문 / 약품주문 / 이상보고",
        
    )

# ══════════════════════════════════════════════════════════
# 메인 핸들러
# ══════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.is_bot: return

    text     = msg.text or ""
    name     = msg.from_user.full_name
    staff    = get_staff(name)
    mode     = ctx.user_data.get("mode")
    group_id = msg.chat_id
    # 그룹방 ID 자동 저장 (배합지시 발송용)
    if msg.chat.type in ("group", "supergroup"):
        ctx.bot_data["main_group_id"] = group_id

    # ── 약품변경 우선 처리 ──
    if any(k in text for k in KW_MEDICINE_UPDATE):
        handled = await handle_medicine_update(msg, text, ctx)
        if handled: return

    # ── 버튼 직접 입력 ──────────────────────────────────────
    BUTTONS = {
        "🐷 출하 보고": ("shipout", "🐷 출하 보고\n몇 두 출하했나요?\nXuất bao nhiêu con?"),
        "💀 폐사 보고": ("death",   "💀 폐사 보고\n두수+위치 입력\n예) 돈공1.2 2두, B4 1두"),
        "⚠️ 이상 보고": ("issue",   "⚠️ 이상 보고\n이상 내용 입력\nNhập nội dung sự cố"),
        "🏖️ 휴무 신청": ("vacation","🏖️ 휴무 신청\n희망 날짜 입력\n예) 4/15"),
        "🌾 사료 주문": ("order_feed",     "🌾 사료 주문\n품목+수량 입력\n예) 자돈사료 5포"),
        "💊 약품 주문": ("order_medicine", "💊 약품 주문\n품목+수량 입력\n예) 써코백신 10병"),
        "📦 소모품 주문": ("order_supply", "📦 소모품 주문\n품목+수량 입력\n예) 비닐장갑 2박스"),
    }

    if text == "✅ 작업 완료":
        notion_log(f"작업완료 — {staff}", "✅ 완료", 비고=name)
        await msg.reply_text(f"✅ 수고하셨습니다 {name}님!\nCảm ơn {name}!")
        ctx.user_data["mode"] = None
        return

    if text in BUTTONS:
        m, prompt = BUTTONS[text]
        ctx.user_data["mode"] = m
        ctx.user_data["group_id"] = group_id
        ctx.user_data["staff"] = staff
        await msg.reply_text(prompt)
        return

    # ── 버튼 후 내용 입력 ────────────────────────────────────
    if mode == "shipout":
        try:
            두수 = int(re.sub(r"[^0-9]", "", text.strip()) or "0")
            if 두수 == 0: raise ValueError
            notion_shipout(두수, f"버튼 보고 — {name}")
            notion_log(f"🐷 출하 {두수}두", "✅ 완료", 비고=name)
            await msg.reply_text(f"✅ 출하 {두수}두 기록!\nĐã ghi nhận {두수} con!")
            if ADMIN_ID:
                await ctx.bot.send_message(ADMIN_ID, f"🐷 출하 보고\n직원: {name}\n두수: {두수}두")
            ctx.user_data["mode"] = None
        except ValueError:
            await msg.reply_text("❌ 숫자만 입력해주세요")
        return

    if mode == "death":
        notion_log(f"💀 폐사: {text}", "✅ 완료", 비고=name)
        await msg.reply_text(f"✅ 폐사 기록\n{text}")
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"🚨 폐사 보고\n직원: {name}\n내용: {text}")
        ctx.user_data["mode"] = None
        return

    if mode == "issue":
        notion_log(f"⚠️ 이상: {text}", "✅ 완료", 비고=name)
        await msg.reply_text(f"✅ 이상 기록\n{text}")
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"🚨 이상 보고\n직원: {name}\n내용: {text}")
        ctx.user_data["mode"] = None
        return

    if mode == "vacation":
        날짜 = parse_date(text)
        if not 날짜:
            await msg.reply_text("❌ 날짜 확인\n예) 4/15")
            return
        sname = ctx.user_data.get("staff", staff)
        gid   = ctx.user_data.get("group_id", group_id)
        pid   = notion_vacation_create(sname, 날짜)
        await msg.reply_text(
            f"🏖️ 휴무 신청 접수\n직원: {sname}\n날짜: {날짜}",
            )
        if ADMIN_ID:
            ctx.bot_data[f"staff_chat_{sname}"] = msg.chat_id
            await ctx.bot.send_message(ADMIN_ID,
                f"🏖️ 휴무 신청\n직원: {sname}\n날짜: {날짜}",
                reply_markup=make_vacation_kb(
                    {"staff": sname, "date": 날짜, "page_id": pid,
                     "group_id": gid, "staff_id": msg.chat_id}))
        ctx.user_data["mode"] = None
        return

    # ── 휴무변경 모드: 새 날짜 입력 받기 ──
    if mode == "vacation_change":
        새날짜 = parse_date(text)
        if not 새날짜:
            await msg.reply_text("❌ 날짜 확인\n예) 4/10  4월10일  4-10")
            return
        sname    = ctx.user_data.get("staff", staff)
        gid      = ctx.user_data.get("group_id", group_id)
        기존날짜  = ctx.user_data.get("vacation_change_from", "")
        page_id  = ctx.user_data.get("vacation_change_page_id", "")
        cal_id   = ctx.user_data.get("vacation_change_cal_id", "")

        await msg.reply_text(
            f"📅 휴무변경 신청 접수\n직원: {sname}\n{기존날짜} → {새날짜}\n대표님 승인 대기중",
            )

        if ADMIN_ID:
            global _approval_counter
            _approval_counter += 1
            key = str(_approval_counter)
            _approval_store[key] = {
                "type":       "vacation_change",
                "staff":      sname,
                "old_date":   기존날짜,
                "new_date":   새날짜,
                "page_id":    page_id,
                "cal_id":     cal_id,
                "group_id":   gid,
                "staff_id":   msg.chat_id,
            }
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ 승인", callback_data=f"approve|{key}"),
                InlineKeyboardButton("❌ 반려", callback_data=f"reject|{key}"),
            ]])
            await ctx.bot.send_message(ADMIN_ID,
                f"🔄 휴무변경 승인 요청\n직원: {sname}\n{기존날짜} → {새날짜}",
                reply_markup=kb)
        ctx.user_data["mode"] = None
        return

    ORDER_MODES = {
        "order_feed":     "🌾 사료",
        "order_medicine": "💊 약품",
        "order_supply":   "📦 소모품",
    }
    if mode in ORDER_MODES:
        유형   = ORDER_MODES[mode]
        sname  = ctx.user_data.get("staff", staff)
        gid    = ctx.user_data.get("group_id", group_id)
        notion_order(sname, 유형, text)
        notion_log(f"{유형} 주문: {text}", "✅ 완료", 비고=sname)
        await msg.reply_text(f"✅ {유형} 주문 접수\n{text}")
        if ADMIN_ID:
            if "사료" in 유형:
                # 사료 주문 → 즉시 사료회사 문자 DM (승인 불필요)
                await _send_feed_company_dm(ctx, text, sname, gid)
            else:
                # 약품/소모품 → 기존 승인 방식 유지
                await ctx.bot.send_message(ADMIN_ID,
                    f"📋 {유형} 주문 접수\n직원: {sname}\n내용: {text}",
                    reply_markup=make_approval_kb("order",
                        {"staff": sname, "content": text, "order_type": 유형, "group_id": gid}))
        ctx.user_data["mode"] = None
        return

    # ══════════════════════════════════════════════════════
    # 강화된 자유 텍스트 자동 분류
    # ══════════════════════════════════════════════════════
    cat, confidence, data = classify(text)
    logger.info(f"자동분류: [{name}] {cat} ({confidence}) / {text[:30]}")

    if cat == "death":
        두수   = data.get("두수", "미상")
        위치   = data.get("위치", "")
        내용   = f"💀 폐사: {text}"
        notion_log(내용, "✅ 완료", 비고=name)
        await msg.reply_text(
            f"✅ 폐사 기록 완료\n두수: {두수}두\n위치: {위치 or '미상'}",
            )
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID,
                f"🚨 폐사 감지\n직원: {name}\n{text}\n두수: {두수} / 위치: {위치 or '미상'}")

    elif cat == "shipout":
        두수 = data.get("두수", 0)
        if isinstance(두수, int) and 두수 > 0:
            notion_shipout(두수, f"텍스트 자동인식 — {name}")
        notion_log(f"🐷 출하: {text}", "✅ 완료", 비고=name)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID,
                f"🐷 출하 감지\n직원: {name}\n{text}")

    elif cat == "issue":
        notion_log(f"⚠️ 이상: {text}", "✅ 완료", 비고=name)
        await msg.reply_text("✅ 이상 기록 완료")
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID,
                f"🚨 이상 감지\n직원: {name}\n{text}")

    elif cat == "weaning":
        # 이유 보고 — 텍스트 파싱 + 노션 저장 + 대표님 알림
        await handle_weaning_report(msg, text, name, ctx, group_id)

    elif cat == "bin_change":
        # 벌크빈 위치 변경 요청
        await handle_bin_change(msg, text, name, ctx, group_id)

    elif cat == "medicine_order":
        # 약품 주문 자동 감지
        await handle_medicine_order_auto(msg, text, name, ctx, group_id)

    elif cat == "pregnancy":
        await handle_pregnancy_report(msg, text, name, ctx)

    elif cat == "vacation_change":
        # 휴무변경 신청 — 기존 확정 휴무 조회 후 날짜 입력 요청
        page_id, old_date, cal_id = await find_confirmed_vacation(staff, NOTION_DB_VACATION)
        ctx.user_data["mode"]                    = "vacation_change"
        ctx.user_data["group_id"]                = group_id
        ctx.user_data["staff"]                   = staff
        ctx.user_data["vacation_change_from"]    = old_date
        ctx.user_data["vacation_change_page_id"] = page_id
        ctx.user_data["vacation_change_cal_id"]  = cal_id
        if old_date:
            await msg.reply_text(
                f"🔄 휴무변경 신청\n현재 확정 날짜: {old_date}\n변경할 날짜를 입력해주세요\n예) 4/10  4월10일  4-10",
                )
        else:
            await msg.reply_text(
                f"🔄 휴무변경 신청\n확정된 휴무가 없습니다\n먼저 휴무 신청을 해주세요",
                )
            ctx.user_data["mode"] = None

    elif cat == "vacation":
        날짜 = data.get("날짜")
        if 날짜:
            pid = notion_vacation_create(staff, 날짜)
            await msg.reply_text(f"🏖️ 휴무 신청 접수: {날짜}")
            if ADMIN_ID:
                ctx.bot_data[f"staff_chat_{staff}"] = msg.chat_id
                await ctx.bot.send_message(ADMIN_ID,
                    f"🏖️ 휴무 신청\n직원: {staff}\n날짜: {날짜}",
                    reply_markup=make_vacation_kb(
                        {"staff": staff, "date": 날짜, "page_id": pid,
                         "group_id": group_id, "staff_id": msg.chat_id}))
        else:
            ctx.user_data["mode"] = "vacation"
            ctx.user_data["group_id"] = group_id
            ctx.user_data["staff"] = staff
            await msg.reply_text("🏖️ 희망 날짜를 입력해주세요\n예) 4/15")

    elif cat == "feed_status":
        # 사료 급이 현황 보고 — 연속 감지 + 작업지시 시스템 연동
        # 같은 사용자 사진 분석 대기 취소 (급이현황 메시지이므로)
        user_id = msg.from_user.id
        if user_id in _photo_pending:
            _photo_pending.pop(user_id, None)
            logger.info(f"사진 분석 취소 (급이현황 메시지): {name}")
        await handle_feed_status_message(msg, text, name, ctx, group_id)

    elif cat == "order_feed":
        # 사료 주문 감지 → 주문승인 없이 바로 사료회사 문자 DM
        notion_order(staff, "🌾 사료", text)
        notion_log(f"🌾 사료 주문: {text}", "✅ 완료", 비고=name)
        if ADMIN_ID:
            # 사료회사 문자 초안 바로 DM으로
            await _send_feed_company_dm(ctx, text, name, group_id)

    elif cat == "order_medicine":
        notion_order(staff, "💊 약품", text)
        notion_log(f"💊 약품 주문: {text}", "✅ 완료", 비고=name)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID,
                f"📋 약품 주문 감지\n직원: {name}\n{text}",
                reply_markup=make_approval_kb("order",
                    {"staff": staff, "content": text, "order_type": "💊 약품", "group_id": group_id}))

    elif cat == "order_supply":
        notion_order(staff, "📦 소모품", text)
        notion_log(f"📦 소모품 주문: {text}", "✅ 완료", 비고=name)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID,
                f"📋 소모품 주문 감지\n직원: {name}\n{text}",
                reply_markup=make_approval_kb("order",
                    {"staff": staff, "content": text, "order_type": "📦 소모품", "group_id": group_id}))

    elif cat == "done":
        notion_log(f"✅ 완료: {text}", "✅ 완료", 비고=name)

    else:
        # 일반 메시지도 노션에 조용히 기록
        notion_log(f"📝 {text}", "✅ 완료", 비고=name)

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    사진 수신 통합 핸들러
    우선순위:
      1. 이유 세션 중 → 모돈관리현황판 Vision 판독
      2. 사료주문 버튼 모드 OR 사료 키워드 → 사료주문 Vision 판독
      3. 폐사 키워드 → 대표님 DM 알림
      4. 기타 → 노션 로그만 저장
    """
    msg = update.message
    if not msg or msg.from_user.is_bot: return

    name    = msg.from_user.full_name
    caption = msg.caption or ""
    mode    = ctx.user_data.get("mode", "")

    # ── 1. 이유 세션 중 → 모돈관리현황판 판독 ──
    weaning_kw = ["이유", "현황판", "farmsco", "모돈", "분만사", "산차"]
    is_weaning = (
        mode == "weaning_photo" or
        "weaning_session" in ctx.bot_data or
        any(k in caption.lower() for k in weaning_kw)
    )
    if is_weaning:
        from weaning_vision import vision_read_card
        if "weaning_session" not in ctx.bot_data:
            ctx.bot_data["weaning_session"] = {
                "cards": [],
                "text_info": ctx.bot_data.get("weaning_text_info", {}),
                "start_time": datetime.now(),
            }
            await msg.reply_text(
                "📸 모돈관리현황판 사진 감지!\n"
                "판독 중... 모두 전송 후 '판독완료' 입력해주세요",
                )

        session = ctx.bot_data["weaning_session"]
        idx = len(session["cards"]) + 1
        await msg.reply_text(f"🔍 {idx}번째 카드 판독 중...")

        try:
            photo = msg.photo[-1]
            file  = await ctx.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())
            text_info = session.get("text_info", {})
            year = None
            if text_info.get("날짜"):
                try: year = int(text_info["날짜"][:4])
                except: year = datetime.now().year
            card = vision_read_card(image_bytes, weaning_year=year)
            session["cards"].append(card)
            if card.get("error"):
                await msg.reply_text(
                    f"⚠️ {idx}번째 카드 판독 실패: {card['error']}\n다음 사진 전송해주세요",
                    )
            else:
                await msg.reply_text(
                    f"✅ {idx}번째 카드\n"
                    f"  산차: {card.get('산차','?')}산 | "
                    f"일령: {card.get('이유일령','?')}일 | "
                    f"두수: {card.get('이유두수','?')}두\n"
                    f"  신뢰도: {card.get('신뢰도','')}",
                    )
        except Exception as e:
            logger.error(f"이유 사진 처리 오류: {e}")
            session["cards"].append({"error": str(e)[:80]})
        return

    # ── 2. 사료주문 버튼 모드 OR 사료 키워드 → 사료주문 Vision 판독 ──
    FEED_KW = ["주문", "사료", "사전주문", "주말주문", "빈번호", "젖돈", "육돈", "임신", "포유"]
    is_feed = (
        mode in ("order_feed", "feed_order") or
        any(k in caption for k in FEED_KW)
    )
    if is_feed:
        try:
            photo = msg.photo[-1]
            file  = await ctx.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())
            await handle_feed_order_photo(update, ctx, image_bytes, name)
        except Exception as e:
            logger.error(f"사료주문 사진 처리 오류: {e}")
            await msg.reply_text(
                f"⚠️ 사료 주문 판독 오류: {str(e)[:60]}\n"
                f"텍스트로 직접 입력해주세요\n예) 젖돈5톤 3-1번, 육돈5톤 7-2번",
                )
        return

    # ── 3. 일반 사진 — 스마트 분석 필터 ──
    caption_log = caption or ""
    cat, _, data = classify(caption_log) if caption_log else ("unknown", "low", {})

    if cat == "death" and ADMIN_ID:
        notion_log(f"📷 폐사사진: {caption_log}", "✅ 완료", 비고=name)
        await ctx.bot.send_message(ADMIN_ID,
            f"🚨 폐사 사진\n직원: {name}\n{caption_log}")

    elif caption_log:
        # 캡션 있는 사진 — 캡션으로 처리
        notion_log(f"📷 사진: {caption_log}", "✅ 완료", 비고=name)

    else:
        # 캡션 없는 사진 — 즉시분석 대상자 vs 타이머 대기
        try:
            photo = msg.photo[-1]
            file  = await ctx.bot.get_file(photo.file_id)
            photo_bytes = bytes(await file.download_as_bytearray())
            user_id = msg.from_user.id

            if is_instant_analyze_user(name):
                # ✅ 신기철 농장장 등 즉시 분석 대상자 → 바로 Vision 분석
                logger.info(f"즉시 분석 대상자 사진: {name}")
                asyncio.create_task(
                    _instant_analyze_photo(ctx, photo_bytes, name, msg, group_id))
            else:
                # 일반 직원 → 30초 대기 후 분석 (급이현황 메시지 오면 취소)
                _photo_pending[user_id] = {
                    "photo_bytes": photo_bytes,
                    "sender":      name,
                    "msg":         msg,
                    "group_id":    group_id,
                    "time":        datetime.now(),
                }
                asyncio.create_task(process_pending_photo(ctx, user_id))
                logger.info(f"사진 대기 등록: {name} (30초 후 분석)")
        except Exception as e:
            logger.error(f"사진 처리 오류: {e}")

# ══════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════

async def handle_date_suggest_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /날짜제안_키 날짜 처리
    다양한 날짜 형식 모두 허용: 4/12  4-12  4.12  4월12일  2026-04-12  12
    """
    msg  = update.message
    text = (msg.text or "").strip()

    m = re.match(r"/날짜제안_(\w+)\s*(.*)", text)
    if not m:
        await msg.reply_text("⚠️ 형식 오류\n예) /날짜제안_3 4/12")
        return

    key       = m.group(1)
    date_raw  = m.group(2).strip()

    wait = ctx.bot_data.get(f"vac_suggest_wait_{key}")
    if not wait:
        await msg.reply_text("⚠️ 만료된 요청입니다. 다시 시도해주세요.")
        return

    payload = wait["payload"]
    staff   = payload.get("staff", "")
    orig    = payload.get("date", "")
    gid     = payload.get("group_id", 0)
    page_id = payload.get("page_id", "")
    staff_id = payload.get("staff_id", 0)

    # 날짜 파싱 — 다양한 형식 허용
    parsed = parse_date(date_raw)
    if not parsed:
        await msg.reply_text(
            f"⚠️ 날짜를 인식하지 못했습니다\n"
            f"입력: {date_raw}\n\n"
            f"예) 4/12  4-12  4월12일  2026-04-12",
            )
        return

    # 직원에게 변경 제안 (직원 개인 DM 있으면 전송)
    if staff_id:
        try:
            global _approval_counter
            _approval_counter += 1
            resp_key = str(_approval_counter)
            _approval_store[resp_key] = {
                "type":         "vac_staff_response",
                "staff":        staff,
                "orig_date":    orig,
                "suggest_date": parsed,
                "page_id":      page_id,
                "group_id":     gid,
            }
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ 수락", callback_data=f"vac_accept|{resp_key}"),
                InlineKeyboardButton("❌ 거절", callback_data=f"vac_reject|{resp_key}"),
            ]])
            await ctx.bot.send_message(
                staff_id,
                f"📅 휴무 날짜 변경 제안\n"
                f"원본: {orig}\n"
                f"제안: {parsed}\n\n"
                f"수락하시겠어요?",
                reply_markup=kb)
            await msg.reply_text(
                f"✅ 직원에게 날짜 변경 제안 전송\n"
                f"{staff}: {orig} → {parsed}",
                )
        except Exception as e:
            logger.error(f"직원 DM 실패: {e}")
            # 직원 DM 실패 시 바로 확정
            notion_vacation_update(page_id, "✅ 확정")
            await msg.reply_text(
                f"✅ 날짜 변경 확정\n{staff}: {orig} → {parsed}",
                )
            if gid:
                await ctx.bot.send_message(gid, f"🏖️ 휴무 날짜변경\n{staff} / {parsed}")
    else:
        # 직원 DM 없으면 바로 확정
        notion_vacation_update(page_id, "✅ 확정")
        await msg.reply_text(
            f"✅ 날짜 변경 확정\n{staff}: {orig} → {parsed}",
            )
        if gid:
            await ctx.bot.send_message(gid, f"🏖️ 휴무 날짜변경\n{staff} / {parsed}")

    ctx.bot_data.pop(f"vac_suggest_wait_{key}", None)

async def handle_modify_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    대표님이 /modify_키 수정내용 입력 시 처리
    예) /modify_3 젖돈5톤 4-1번으로 변경
    """
    msg  = update.message
    text = msg.text or ""

    # /modify_키 파싱
    m = re.match(r"/modify_(\w+)\s*(.*)", text.strip())
    if not m:
        await msg.reply_text("⚠️ 형식 오류\n예) /modify_3 수정내용")
        return

    key      = m.group(1)
    modified = m.group(2).strip()

    wait_info = ctx.bot_data.get(f"modify_wait_{key}")
    if not wait_info:
        await msg.reply_text("⚠️ 만료된 수정 요청입니다. 다시 시도해주세요.")
        return

    payload  = wait_info["payload"]
    gid      = wait_info.get("chat_id") or payload.get("group_id", 0)
    staff    = payload.get("staff", "")
    atype    = payload.get("type", "")
    original = payload.get("content", "")

    if not modified:
        await msg.reply_text(
            f"✏️ 수정 내용을 입력해주세요\n"
            f"예) /modify_{key} 젖돈5톤 4-1번으로 변경",
            )
        return

    if atype == "order":
        유형 = payload.get("order_type", "주문")
        notion_log(
            f"{유형} 수정승인: 원본=[{original}] → 수정=[{modified}]",
            "✅ 완료", 비고=f"대표님 수정승인 — {staff}")
        await msg.reply_text(
            f"✅ 수정 승인 완료\n"
            f"직원: {staff}\n"
            f"원본: {original}\n"
            f"수정: {modified}",
            )
        if gid:
            await ctx.bot.send_message(gid,
                f"✏️ {유형} 수정 승인\n"
                f"{staff}님 주문이 아래 내용으로 수정 처리됩니다\n\n"
                f"🔴 원본: {original}\n"
                f"🟢 수정: {modified}")

    elif atype == "vacation":
        날짜    = payload.get("date", "")
        page_id = payload.get("page_id", "")
        notion_vacation_update(page_id, "✅ 확정")
        notion_log(
            f"휴무 수정승인: {staff} {날짜} → {modified}",
            "✅ 완료", 비고="대표님 수정승인")
        await msg.reply_text(
            f"✅ 휴무 수정 승인 완료\n"
            f"직원: {staff}\n"
            f"원본 날짜: {날짜}\n"
            f"수정: {modified}",
            )
        if gid:
            await ctx.bot.send_message(gid,
                f"✏️ 휴무 수정 승인\n"
                f"{staff}\n"
                f"🔴 원본: {날짜}\n"
                f"🟢 수정: {modified}")

    # 사료회사 문자 수정 처리
    elif wait_info.get("mode") == "company_msg":
        orig_payload  = wait_info["payload"]
        order_content = orig_payload.get("order_content", "")
        staff         = orig_payload.get("staff", "")
        gid           = orig_payload.get("gid", 0) or ctx.bot_data.get("main_group_id", 0)
        ipl           = orig_payload.get("orig_payload", {})

        await msg.reply_text(
            "✅ 사료회사 문자 수정 발송 확정\n\n" + modified,
            )
        await _after_company_send(ctx, modified, order_content, staff, gid, ipl)

    # 배합지시 예약 수정 처리
    elif wait_info.get("mode") == "dispatch_schedule":
        orig_payload  = wait_info["payload"]
        target_date   = orig_payload.get("target_date", "")
        orig_order    = orig_payload.get("original_order", "")
        gid           = ctx.bot_data.get("main_group_id", 0)

        # 수정된 내용으로 재예약
        page_id = await save_dispatch_schedule(modified, target_date, orig_order)
        schedule_dt = calc_schedule_time(target_date)
        delay = max(0, (schedule_dt - datetime.now()).total_seconds())

        async def _do_send_mod(ctx_inner, dt=modified, g=gid, pid=page_id):
            await execute_scheduled_dispatch(ctx_inner, dt, g, pid)

        ctx.application.job_queue.run_once(_do_send_mod, when=delay)
        await msg.reply_text(
            "⏰ 수정된 배합지시 예약 완료\n"
            + target_date + " 오전 7시 발송\n\n" + modified,
            )

    # 작업지시 수정 처리
    elif wait_info.get("mode") == "work_order":
        orig_payload = wait_info["payload"]
        gid = orig_payload.get("group_id", 0) or ctx.bot_data.get("main_group_id", 0)
        barn = orig_payload.get("barn", "")
        if gid:
            await ctx.bot.send_message(gid, modified)
        await msg.reply_text(
            "✅ 수정된 작업지시 발송\n\n" + modified,
            )
        notion_log(f"작업지시 발송(수정): {barn}", "✅ 완료", 비고="대표님 수정승인")

    # 배합지시 수정 처리
    elif wait_info.get("mode") == "feed_dispatch":
        orig_payload  = wait_info["payload"]
        orig_dispatch = orig_payload.get("dispatch_text", "")
        staff         = orig_payload.get("staff", "")
        group_id      = ctx.bot_data.get("main_group_id", 0)

        if group_id:
            await ctx.bot.send_message(group_id,
                f"🌾 사료 배합지시 (수정)\n\n{modified}")
        await msg.reply_text(
            f"✅ 수정된 배합지시 발송 완료\n\n"
            f"🔴 원본:\n{orig_dispatch}\n\n"
            f"🟢 발송:\n{modified}",
            )

    # 대기 상태 정리
    ctx.bot_data.pop(f"modify_wait_{key}", None)
    _approval_store.pop(f"modify_{key}", None)

async def handle_dispatch_change(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /변경, /추가, /재발송 명령어 처리
    발송된 배합지시를 변경하거나 품목을 추가해서 재발송
    """
    global _approval_counter
    msg  = update.message
    text = (msg.text or "").strip()
    last = ctx.bot_data.get("last_dispatch", {})

    if not last:
        await msg.reply_text(
            "⚠️ 발송된 배합지시가 없습니다\n"
            "사료주문 버튼으로 주문 후 배합지시를 먼저 발송해주세요",
            )
        return

    last_text    = last.get("text", "")
    sent_at      = last.get("sent_at", "")
    group_id     = ctx.bot_data.get("main_group_id", 0)

    # ── /재발송 ── 그대로 다시 발송 (노션은 변경 없음)
    if text.startswith("/재발송"):
        if group_id:
            await ctx.bot.send_message(group_id,
                f"🔄 배합지시 재발송\n\n{last_text}")
        await msg.reply_text(
            f"✅ 재발송 완료 (노션 내용 변경 없음)\n\n{last_text}",
            )
        return

    # ── /변경 ── 전체 내용 변경
    if text.startswith("/변경"):
        변경내용 = text[3:].strip()
        if not 변경내용:
            # 내용 없으면 현재 배합지시 보여주고 입력 요청
            _approval_counter += 1
            key = str(_approval_counter)
            ctx.bot_data[f"dispatch_change_wait_{key}"] = {
                "mode":      "change",
                "last_text": last_text,
                "group_id":  group_id,
            }
            await msg.reply_text(
                f"✏️ 변경할 내용을 입력해주세요\n\n"
                f"현재 배합지시 (발송: {sent_at}):\n"
                f"{'─'*20}\n"
                f"{last_text}\n"
                f"{'─'*20}\n\n"
                f"/변경_{key} 변경된내용 으로 입력\n\n"
                f"예)\n"
                f"/변경_{key} 4월7일 화요일\n2시차\n젖돈5톤 4-1번\n임신2톤 11번",
                )
            return

        # 내용 있으면 바로 미리보기
        await _preview_changed_dispatch(msg, ctx, 변경내용, "change", group_id, last_text)
        return

    # ── /추가 ── 기존 내용에 품목 추가
    if text.startswith("/추가"):
        추가내용 = text[3:].strip()
        if not 추가내용:
            _approval_counter += 1
            key = str(_approval_counter)
            ctx.bot_data[f"dispatch_change_wait_{key}"] = {
                "mode":      "add",
                "last_text": last_text,
                "group_id":  group_id,
            }
            await msg.reply_text(
                f"➕ 추가할 품목을 입력해주세요\n\n"
                f"현재 배합지시 (발송: {sent_at}):\n"
                f"{'─'*20}\n"
                f"{last_text}\n"
                f"{'─'*20}\n\n"
                f"/추가_{key} 추가품목 으로 입력\n\n"
                f"예)\n"
                f"/추가_{key} 육돈5톤 7-2번\n1호 10포",
                )
            return

        # 내용 있으면 바로 추가
        merged = last_text + "\n" + 추가내용
        await _preview_changed_dispatch(msg, ctx, merged, "add", group_id, last_text)
        return

async def handle_dispatch_change_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /변경_키 또는 /추가_키 입력 시 처리
    예) /변경_5 젖돈5톤 4-1번\n임신2톤 11번
    """
    msg  = update.message
    text = (msg.text or "").strip()

    # /변경_키 또는 /추가_키 파싱
    m = re.match(r"/(변경|추가)_(\w+)\s*([\s\S]*)", text)
    if not m:
        return

    cmd_type = m.group(1)   # "변경" or "추가"
    key      = m.group(2)
    new_part = m.group(3).strip()

    wait = ctx.bot_data.get(f"dispatch_change_wait_{key}")
    if not wait:
        await msg.reply_text("⚠️ 만료된 변경 요청입니다. /변경 또는 /추가 다시 입력해주세요")
        return

    last_text = wait.get("last_text", "")
    group_id  = wait.get("group_id", 0)
    mode      = wait.get("mode", "change")

    if mode == "add":
        new_text = last_text + "\n" + new_part
    else:
        new_text = new_part

    await _preview_changed_dispatch(msg, ctx, new_text, mode, group_id, last_text)
    ctx.bot_data.pop(f"dispatch_change_wait_{key}", None)


# ── 재발송 콜백 처리는 handle_callback에 통합 ──
# handle_callback의 dispatch 처리 블록 끝에서 resend 처리


# ══════════════════════════════════════════════════════════
# 📦 노션 주문 DB 변경 동기화
# ══════════════════════════════════════════════════════════

def notion_update_order_change(
    original_text: str,
    new_text: str,
    change_mode: str,
    changed_at: str = None,
) -> bool:
    """
    배합지시 변경 시 노션 주문 관리 DB 동기화
    - 오늘 날짜의 사료 주문 건을 찾아서
    - 품목 수정 + 변경이력 기록 + 입고상태 변경됨으로 업데이트
    """
    if not NOTION_TOKEN:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    changed_at = changed_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    label = "변경" if change_mode == "change" else "추가"

    try:
        # 오늘 날짜 사료 주문 조회
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ORDER}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "주문날짜", "date": {"equals": today}},
                        {"property": "주문유형", "select": {"equals": "🌾 사료"}},
                        {"property": "입고상태", "select": {"does_not_equal": "❌ 취소"}},
                    ]
                },
                "sorts": [{"property": "주문날짜", "direction": "descending"}],
                "page_size": 5,
            },
            timeout=10,
        )
        pages = res.json().get("results", [])

        if not pages:
            # 오늘 날짜 없으면 최근 발주 건 조회 (날짜 무관)
            res2 = requests.post(
                f"https://api.notion.com/v1/databases/{NOTION_DB_ORDER}/query",
                headers=NOTION_HEADERS,
                json={
                    "filter": {
                        "and": [
                            {"property": "주문유형", "select": {"equals": "🌾 사료"}},
                            {"property": "입고상태", "select": {"equals": "📋 발주"}},
                        ]
                    },
                    "sorts": [{"timestamp": "created_time", "direction": "descending"}],
                    "page_size": 3,
                },
                timeout=10,
            )
            pages = res2.json().get("results", [])

        updated = 0
        for page in pages:
            page_id = page["id"]
            # 현재 변경이력 가져오기
            props = page.get("properties", {})
            cur_history = ""
            rt = props.get("변경이력", {}).get("rich_text", [])
            if rt:
                cur_history = rt[0].get("text", {}).get("content", "")
            cur_count = props.get("변경횟수", {}).get("number", 0) or 0
            cur_original = ""
            rt2 = props.get("원본내용", {}).get("rich_text", [])
            if rt2:
                cur_original = rt2[0].get("text", {}).get("content", "")

            # 최초 변경 시 원본 저장
            if not cur_original:
                cur_original = original_text[:2000]

            # 변경이력 추가
            new_history = (
                f"[{changed_at}] {label}: {new_text[:500]}\n" + cur_history
            )[:2000]

            # 노션 업데이트
            requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=NOTION_HEADERS,
                json={
                    "properties": {
                        "품목":    {"rich_text": [{"text": {"content": new_text[:2000]}}]},
                        "입고상태": {"select": {"name": "🔄 변경됨"}},
                        "변경이력": {"rich_text": [{"text": {"content": new_history}}]},
                        "원본내용": {"rich_text": [{"text": {"content": cur_original}}]},
                        "변경횟수": {"number": cur_count + 1},
                        "메모":    {"rich_text": [{"text": {"content":
                            f"배합지시 {label} — {changed_at}"
                        }}]},
                    }
                },
                timeout=10,
            )
            updated += 1
            logger.info(f"노션 주문 변경 동기화: {page_id} ({label})")

        return updated > 0

    except Exception as e:
        logger.error(f"노션 주문 변경 동기화 오류: {e}")
        return False



# ══════════════════════════════════════════════════════════
# 🔄 /업데이트 명령어 — GitHub에서 최신 bot.py pull 후 재시작
# ══════════════════════════════════════════════════════════

async def handle_update_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """대표님 전용 — GitHub에서 최신 코드 받아서 봇 재시작"""
    msg = update.message
    if not msg: return

    # 대표님만 사용 가능
    if ADMIN_ID and msg.from_user.id != ADMIN_ID:
        await msg.reply_text("⚠️ 권한 없음")
        return

    await msg.reply_text("🔄 GitHub에서 최신 버전 확인 중...")

    import subprocess, sys, os

    try:
        # git pull 실행
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        if "Already up to date" in result.stdout:
            await msg.reply_text("✅ 이미 최신 버전입니다")
            return

        if result.returncode == 0:
            await msg.reply_text(
                f"✅ 업데이트 완료\n재시작 중...\n\n{result.stdout[:200]}")

            # 새 프로세스로 봇 재시작
            await asyncio.sleep(1)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            await msg.reply_text(
                f"⚠️ 업데이트 실패\n{result.stderr[:200]}")

    except FileNotFoundError:
        await msg.reply_text("⚠️ git이 설치되어 있지 않습니다\n수동으로 파일을 교체해주세요")
    except Exception as e:
        await msg.reply_text(f"⚠️ 오류: {str(e)[:100]}")


# ══════════════════════════════════════════════════════════
# ⚠️ A1. 전역 에러 핸들러 — 오류 발생 시 대표님 DM 알림
# ══════════════════════════════════════════════════════════

_last_error_time: dict = {}  # 중복 오류 방지용 {오류키: 마지막발생시각}

async def error_handler(update, ctx: ContextTypes.DEFAULT_TYPE):
    """전역 예외 핸들러 — 모든 핸들러 오류를 캐치해서 DM 알림"""
    import traceback, time

    err = ctx.error
    err_type  = type(err).__name__
    err_msg   = str(err)[:200]
    tb_lines  = traceback.format_exception(type(err), err, err.__traceback__)
    tb_str    = "".join(tb_lines)[-300:]

    # 핸들러/함수명 추출
    handler_name = "unknown"
    for line in tb_lines:
        if "bot.py" in line and "in " in line:
            handler_name = line.strip().split("in ")[-1]

    logger.error(f"봇 오류 [{err_type}] {handler_name}: {err_msg}")

    # 중복 오류 방지 (같은 오류 60초 내 재발 시 스킵)
    err_key   = f"{err_type}:{handler_name}"
    now_ts    = time.time()
    last_ts   = _last_error_time.get(err_key, 0)
    if now_ts - last_ts < 60:
        return
    _last_error_time[err_key] = now_ts

    # 대표님 DM 발송
    if ADMIN_ID:
        try:
            now_str = datetime.now().strftime("%H:%M:%S")
            dm_text = (
                f"⚠️ 봇 오류 알림\n"
                f"시각: {now_str}\n"
                f"오류: {err_type}\n"
                f"위치: {handler_name}\n"
                f"내용: {err_msg}\n\n"
                f"추적:\n{tb_str[-200:]}"
            )
            await ctx.bot.send_message(ADMIN_ID, dm_text[:4000])
        except Exception as e:
            logger.error(f"에러핸들러 DM 발송 실패: {e}")
# 🐷 이유 보고 자동 처리 (bot.py 하단에 추가)
# ══════════════════════════════════════════════════════════
# 이유 관련 노션 DB IDs
NOTION_DB_WEANING   = "877cf48e-e04f-40b9-92d3-3069ac02fa1f"  # 이유 기록 DB
NOTION_DB_GROUP     = "3341d244-3b59-442e-bc9e-b7f124c4f31a"  # 군 관리 DB
NOTION_DB_WEEKLY    = "a4a16901-dadd-4b0f-8349-8c62a7c71a15"  # 주간 관리 DB

# 이유 키워드
KW_WEANING = [
    "이유", "이유예정", "이유완료", "이유함", "이유했",
    "분만사 이유", "모돈 이유", "자돈 이유",
    "복", "모돈", "자돈", "분만사",
]

def parse_weaning_text(text: str) -> dict:
    """
    이유 보고 텍스트에서 핵심 데이터 추출
    지원 형식:
      4월7일 2분만사 이유예정 모돈20복 자돈217두
      이유 4/7 3분만사 모돈 15복 자돈 189두
      4월7일이유 분만2사 20복 217두
      오늘 1분만사 이유 20복 210두
    """
    result = {}
    now = datetime.now()

    # ── 날짜 파싱 (다양한 형식)
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        result["날짜"] = f"{now.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    else:
        # 4/7 또는 4-7 형식 (연도 포함 형식 우선)
        m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
        if m:
            result["날짜"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            m = re.search(r"(\d{1,2})[/\-](\d{1,2})(?!\d)", text)
            if m:
                mon, day = int(m.group(1)), int(m.group(2))
                if 1 <= mon <= 12 and 1 <= day <= 31:
                    result["날짜"] = f"{now.year}-{mon:02d}-{day:02d}"
    if "날짜" not in result:
        result["날짜"] = now.strftime("%Y-%m-%d")

    # ── 분만사 번호 (다양한 패턴)
    # 패턴1: "2분만사", "3분만사"
    m = re.search(r"(\d+)\s*분만사", text)
    if m:
        result["분만사"] = f"{m.group(1)}분만사"
    else:
        # 패턴2: "분만2사", "분만3사"
        m = re.search(r"분만\s*(\d+)\s*사", text)
        if m:
            result["분만사"] = f"{m.group(1)}분만사"
        else:
            # 패턴3: "분만사1", "분만사 2"
            m = re.search(r"분만사\s*(\d+)", text)
            if m:
                result["분만사"] = f"{m.group(1)}분만사"

    # ── 인큐 번호
    m = re.search(r"인큐\s*(\d+)", text)
    if not m:
        m = re.search(r"(\d+)\s*인큐", text)
    if m:
        result["인큐"] = m.group(1)

    # ── 모돈 두수 (복 또는 두) — 우선순위: "모돈N복" > "N복"
    m = re.search(r"모돈\s*(\d+)\s*(?:복|두|마리)", text)
    if m:
        result["모돈"] = int(m.group(1))
    else:
        m = re.search(r"(\d+)\s*복", text)
        if m:
            result["모돈"] = int(m.group(1))

    # ── 자돈 두수 — 우선순위: "자돈N두" > "N두"
    m = re.search(r"자돈\s*(\d+)\s*(?:두|마리)", text)
    if m:
        result["자돈"] = int(m.group(1))
    else:
        # "두" 앞 숫자 (단, 이미 모돈으로 잡힌 숫자 제외)
        matches = re.findall(r"(\d+)\s*두", text)
        for v in matches:
            if int(v) != result.get("모돈", -1):
                result["자돈"] = int(v)
                break

    # 군번호 자동 생성 (YYMM-NN 형식)
    yymm = now.strftime("%y%m")
    result["군번호"] = f"{yymm}-01"  # 실제로는 노션에서 당월 카운트 조회 필요

    # 예상 출하일 (이유일 + 170일)
    try:
        weaning_date = datetime.strptime(result["날짜"], "%Y-%m-%d")
        expected = weaning_date + timedelta(days=170)
        result["예상출하일"] = expected.strftime("%Y-%m-%d")
    except:
        result["예상출하일"] = ""

    return result

def notion_weaning_create(data: dict, staff: str) -> str:
    """이유 기록 DB에 저장"""
    if not NOTION_TOKEN: return ""
    군번호 = data.get("군번호", "")
    날짜 = data.get("날짜", datetime.now().strftime("%Y-%m-%d"))
    분만사 = data.get("분만사", "")
    모돈 = data.get("모돈", 0)
    자돈 = data.get("자돈", 0)
    인큐 = data.get("인큐", "")

    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_WEANING}, "properties": {
                "Name":    {"title": [{"text": {"content": f"{군번호} 이유기록 ({분만사})"}}]},
                "date:이유날짜:start": 날짜, "date:이유날짜:is_datetime": 0,
                "분만사":   {"select": {"name": 분만사}} if 분만사 else None,
                "인큐번호": {"rich_text": [{"text": {"content": 인큐}}]},
                "모돈두수": {"number": 모돈},
                "자돈두수": {"number": 자돈},
                "군번호":   {"rich_text": [{"text": {"content": 군번호}}]},
                "특이사항": {"rich_text": [{"text": {"content": f"텔레그램 보고 — {staff}. 산차/일령/체중 추가 확인 필요."}}]},
            }}, timeout=10)
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"이유 기록 오류: {e}")
        return ""

def notion_group_create(data: dict) -> str:
    """군 관리 DB에 군 생성"""
    if not NOTION_TOKEN: return ""
    군번호 = data.get("군번호", "")
    날짜 = data.get("날짜", datetime.now().strftime("%Y-%m-%d"))
    자돈 = data.get("자돈", 0)
    분만사 = data.get("분만사", "")
    예상출하일 = data.get("예상출하일", "")

    props = {
        "Name":    {"title": [{"text": {"content": f"{군번호} 군"}}]},
        "date:이유날짜:start": 날짜, "date:이유날짜:is_datetime": 0,
        "군번호":   {"rich_text": [{"text": {"content": 군번호}}]},
        "군상태":   {"select": {"name": "🐣 이유직후"}},
        "초기두수": {"number": 자돈},
        "현재두수": {"number": 자돈},
        "누적폐사": {"number": 0},
        "누적환돈": {"number": 0},
        "폐사율":   {"number": 0},
        "특이사항": {"rich_text": [{"text": {"content": f"이유일 {날짜} + 170일 = 예상출하 {예상출하일}"}}]},
    }
    if 분만사:
        props["분만사"] = {"select": {"name": 분만사}}
    if 예상출하일:
        props["date:예상출하일:start"] = 예상출하일
        props["date:예상출하일:is_datetime"] = 0

    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_GROUP}, "properties": props},
            timeout=10)
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"군 생성 오류: {e}")
        return ""


# ══════════════════════════════════════════════════════════
# 📸 모돈관리현황판 사진 자동 판독 핸들러
# ══════════════════════════════════════════════════════════
from weaning_vision import vision_read_card, aggregate_cards, format_report

# 이유 세션 저장 (사진 여러 장을 한 묶음으로 처리)
# key: chat_id, value: {"cards": [], "text_info": {}, "timer": datetime}
weaning_sessions = {}

WEANING_PHOTO_KEYWORDS = [
    "farmsco", "모돈", "현황판", "이유", "분만사",
    "산차", "포유", "이유두수"
]

def is_weaning_photo_context(caption: str, ctx_mode: str) -> bool:
    """이 사진이 모돈관리현황판 사진인지 판단"""
    if ctx_mode == "weaning_photo": return True
    if not caption: return False
    caption_lower = caption.lower()
    return any(k in caption_lower for k in WEANING_PHOTO_KEYWORDS)

async def handle_photo_enhanced(update, ctx):
    """사진 수신 — 모돈관리현황판 자동 판독 포함"""
    msg = update.message
    if not msg or msg.from_user.is_bot: return

    name    = msg.from_user.full_name
    caption = msg.caption or ""
    chat_id = msg.chat_id
    mode    = ctx.user_data.get("mode", "")

    # ── 모돈관리현황판 판독 세션 확인 ──
    is_weaning = is_weaning_photo_context(caption, mode)

    if is_weaning or chat_id in weaning_sessions:
        # 세션 시작 or 기존 세션에 추가
        if chat_id not in weaning_sessions:
            weaning_sessions[chat_id] = {
                "cards": [],
                "text_info": ctx.bot_data.get("weaning_text_info", {}),
                "start_time": datetime.now(),
                "name": name,
            }
            await msg.reply_text(
                "📸 모돈관리현황판 사진 감지!\n"
                "판독 중입니다... 사진을 모두 전송해주세요.\n"
                "마지막 사진 전송 후 '판독완료' 를 입력해주세요",
                )

        # Vision API로 카드 판독
        try:
            photo = msg.photo[-1]  # 최고 해상도
            file = await ctx.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()

            card_result = vision_read_card(bytes(image_bytes))
            weaning_sessions[chat_id]["cards"].append(card_result)

            # 판독 성공 시 간단히 알림
            if not card_result.get("error") and card_result.get("산차"):
                await msg.reply_text(
                    f"✅ {len(weaning_sessions[chat_id]['cards'])}번째 카드 판독\n"
                    f"  산차: {card_result['산차']}산 / "
                    f"  이유일령: {card_result.get('이유일령', '?')}일 / "
                    f"  이유두수: {card_result.get('이유두수', '?')}두",
                    )
            else:
                await msg.reply_text(
                    f"⚠️ {len(weaning_sessions[chat_id]['cards'])}번째 카드 — 판독 어려움\n"
                    f"  다음 사진을 전송해주세요",
                    )

        except Exception as e:
            logger.error(f"Vision 판독 오류: {e}")
            weaning_sessions[chat_id]["cards"].append({"error": str(e)})

    else:
        # 일반 사진 처리
        notion_log(f"📷 사진: {caption}", "✅ 완료", 비고=name)
        cat, _, data = classify(caption)
        if cat == "death" and ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"🚨 폐사 사진\n직원: {name}\n{caption}")

async def handle_weaning_complete(update, ctx):
    """
    '판독완료' 입력 시 집계 처리
    bot.py의 handle_message에서 호출
    """
    msg = update.message
    chat_id = msg.chat_id
    name = msg.from_user.full_name

    session = weaning_sessions.get(chat_id)
    if not session or not session["cards"]:
        await msg.reply_text("❌ 판독할 카드가 없습니다")
        return

    cards      = session["cards"]
    text_info  = session.get("text_info", {})
    군번호     = text_info.get("군번호", "미정")
    이유날짜   = text_info.get("날짜", datetime.now().strftime("%Y-%m-%d"))

    # 집계 계산
    agg = aggregate_cards(cards)
    report = format_report(agg, 군번호, 이유날짜)

    await msg.reply_text(report)

    # 노션 이유 기록 업데이트
    if agg["평균산차"] or agg["평균일령"]:
        page_id = text_info.get("notion_page_id", "")
        if page_id and NOTION_TOKEN:
            try:
                update_props = {}
                if agg["평균산차"]:
                    update_props["평균산차"] = {"number": agg["평균산차"]}
                if agg["평균일령"]:
                    update_props["평균일령"] = {"number": agg["평균일령"]}
                if agg["총이유두수"]:
                    update_props["자돈두수"] = {"number": agg["총이유두수"]}

                requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=NOTION_HEADERS,
                    json={"properties": update_props},
                    timeout=10)
                await msg.reply_text("✅ 노션 이유 기록 업데이트 완료!")
            except Exception as e:
                logger.error(f"노션 업데이트 오류: {e}")

    # 대표님께 보고
    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID, f"📊 이유 판독 완료\n\n{report}")

    # 세션 정리
    del weaning_sessions[chat_id]
    ctx.user_data["mode"] = None



# ═══ 이유 사진 저장 핸들러 (판독완료 처리) ═══
async def handle_weaning_done(update, ctx):
    msg = update.message
    chat_id = msg.chat_id
    session = ctx.user_data.get("weaning_session", {})
    photos = session.get("photos", [])
    text_info = session.get("text_info", {})
    folder = session.get("folder", "")

    if not photos:
        await msg.reply_text("❌ 저장된 사진이 없습니다")
        return

    from weaning_photo_handler import format_admin_notification
    from pathlib import Path

    count = len(photos)
    folder_path = Path(folder) if folder else Path(".")

    notify_msg = format_admin_notification(
        session_key=chat_id,
        photo_count=count,
        folder=folder_path,
        text_info=text_info
    )

    await msg.reply_text(
        f"✅ 이유 사진 {count}장 저장 완료\n\n"
        f"대표님께 판독 요청 알림을 보냈습니다",
        )

    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID, notify_msg)

    # 세션 초기화 (사진 파일은 유지 — 판독 완료 후 삭제)
    ctx.user_data.pop("weaning_session", None)
    ctx.user_data["mode"] = None


# handle_photo 강화버전이 위에 있습니다

# ══════════════════════════════════════════════════════════
# 📸 이유 판독완료 처리
# ══════════════════════════════════════════════════════════
async def process_weaning_complete(update, ctx):
    """'판독완료' 입력 시 집계 및 노션 저장"""
    msg     = update.message
    session = ctx.user_data.get("weaning_session", {})
    cards   = session.get("cards", [])
    info    = session.get("text_info", {})

    if not cards:
        await msg.reply_text("❌ 판독된 카드가 없습니다")
        return

    from weaning_vision import aggregate_cards, format_report

    await msg.reply_text(f"📊 {len(cards)}장 집계 중...")

    agg       = aggregate_cards(cards)
    군번호    = info.get("군번호", "미정")
    이유날짜  = info.get("날짜", datetime.now().strftime("%Y-%m-%d"))
    분만사    = info.get("분만사", "")
    자돈두수  = info.get("자돈", 0)
    모돈두수  = info.get("모돈", 0)

    report = format_report(agg, 군번호, 이유날짜)
    await msg.reply_text(report)

    # 노션 이유기록DB 저장
    if NOTION_TOKEN:
        try:
            산차분포_str = " / ".join(
                [f"{k}:{v}두" for k, v in sorted(agg.get("산차분포", {}).items())])

            props = {
                "Name":    {"title": [{"text": {"content": f"{군번호} 이유기록 ({분만사})"}}]},
                "date:이유날짜:start": 이유날짜, "date:이유날짜:is_datetime": 0,
                "군번호":     {"rich_text": [{"text": {"content": 군번호}}]},
                "모돈두수":   {"number": 모돈두수 or 0},
                "자돈두수":   {"number": 자돈두수 or agg.get("총이유두수") or 0},
                "판독카드수": {"number": agg["판독성공"]},
                "산차분포":   {"rich_text": [{"text": {"content": 산차분포_str}}]},
                "체중측정여부": {"select": {"name": "미완료"}},
                "판독신뢰도": {"select": {"name": "높음" if agg["판독성공"] >= agg["총카드"] * 0.8 else "보통"}},
                "특이사항":   {"rich_text": [{"text": {"content": f"Vision 자동판독 {agg['판독성공']}/{agg['총카드']}장 성공"}}]},
            }
            if 분만사:
                props["분만사"] = {"select": {"name": 분만사}}
            if agg.get("평균산차") is not None:
                props["평균산차"] = {"number": agg["평균산차"]}
            if agg.get("평균일령") is not None:
                props["평균일령"] = {"number": agg["평균일령"]}

            res = requests.post("https://api.notion.com/v1/pages",
                headers=NOTION_HEADERS,
                json={"parent": {"database_id": "877cf48e-e04f-40b9-92d3-3069ac02fa1f"},
                      "properties": props},
                timeout=15)

            if res.status_code == 200:
                await msg.reply_text("✅ 노션 이유기록DB 저장 완료!")
            else:
                logger.error(f"노션 저장 실패: {res.status_code}")

        except Exception as e:
            logger.error(f"노션 이유 저장 오류: {e}")

    # 군 관리 DB 군 생성
    if NOTION_TOKEN and 군번호 != "미정":
        try:
            now = datetime.now()
            예상출하일 = (now + timedelta(days=170)).strftime("%Y-%m-%d") if 이유날짜 else ""

            group_props = {
                "Name":    {"title": [{"text": {"content": f"{군번호} 군"}}]},
                "date:이유날짜:start": 이유날짜, "date:이유날짜:is_datetime": 0,
                "군번호":     {"rich_text": [{"text": {"content": 군번호}}]},
                "군상태":     {"select": {"name": "🐣 이유직후"}},
                "초기두수":   {"number": 자돈두수 or agg.get("총이유두수") or 0},
                "현재두수":   {"number": 자돈두수 or agg.get("총이유두수") or 0},
                "누적폐사":   {"number": 0},
                "누적환돈":   {"number": 0},
                "폐사율":     {"number": 0},
                "예상생존율": {"number": 92},
                "특이사항":   {"rich_text": [{"text": {"content": f"이유일 {이유날짜} + 170일 = 예상출하 {예상출하일}"}}]},
            }
            if 분만사:
                group_props["분만사"] = {"select": {"name": 분만사}}
            if agg.get("평균산차") is not None:
                group_props["평균산차"] = {"number": agg["평균산차"]}
            if agg.get("평균일령") is not None:
                group_props["평균일령"] = {"number": agg["평균일령"]}
            if 예상출하일:
                group_props["date:예상출하일:start"] = 예상출하일
                group_props["date:예상출하일:is_datetime"] = 0

            requests.post("https://api.notion.com/v1/pages",
                headers=NOTION_HEADERS,
                json={"parent": {"database_id": "3341d244-3b59-442e-bc9e-b7f124c4f31a"},
                      "properties": group_props},
                timeout=15)

        except Exception as e:
            logger.error(f"군 생성 오류: {e}")

    # 대표님 DM
    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID,
            f"📊 이유 판독 완료\n\n{report}")

    # 세션 정리
    ctx.user_data.pop("weaning_session", None)
    ctx.user_data.pop("weaning_text_info", None)
    ctx.user_data["mode"] = None


# ══════════════════════════════════════════════════════════
# 📸 사료 주문 사진 Vision 판독
# ══════════════════════════════════════════════════════════

FEED_ORDER_PROMPT = """이 사진은 돼지 농장의 사료 주문 메모 또는 카카오톡 화면입니다.

판독 규칙:
1. 날짜 정보 (요일 또는 날짜숫자, 예: 4월7일, 월요일) 찾기
2. 각 날짜에 해당하는 사료 빈 번호 목록 읽기
   예: 8-1, 12, 13 / 2-2, 3-1, 7-3 / 4-2,7-3,15번
3. 사료 종류 있으면 읽기 (젖돈/육돈/임신/포유/1호/3호 등)
4. 도착 시간 있으면 읽기 (2시차/10시차 등)
5. "입고해 주세요", "넣어 주세요" 등 입고 요청도 주문으로 처리

반드시 아래 JSON만 반환하세요. 다른 텍스트 없이:
{
  "주문목록": [
    {"날짜": "요일 또는 날짜", "빈번호": ["번호1", "번호2"], "시간": "2시차", "비고": ""},
    {"날짜": "요일 또는 날짜", "빈번호": ["번호1"], "시간": "", "비고": ""}
  ],
  "신뢰도": "높음 또는 낮음",
  "원문": "사진에서 읽은 텍스트 전체"
}

번호가 불명확하면 null 사용. 사진이 잘렸으면 비고에 "잘림" 표시."""


async def vision_read_feed_order(image_bytes: bytes) -> dict:
    """사료 주문 사진 Vision 판독"""
    import base64, requests as req, json, re

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY 미설정"}

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 800,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        }},
                        {"type": "text", "text": FEED_ORDER_PROMPT}
                    ],
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()
        raw_clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(raw_clean)

    except json.JSONDecodeError:
        return {"error": "JSON 파싱 실패", "raw": raw[:200]}
    except Exception as e:
        return {"error": str(e)[:80]}


def format_feed_order_message(result: dict, sender: str) -> str:
    """판독 결과를 보기 좋게 포맷"""
    if result.get("error"):
        return f"⚠️ 사료 주문 판독 실패: {result['error']}"

    orders = result.get("주문목록", [])
    신뢰도 = result.get("신뢰도", "알수없음")
    lines = [f"📦 사료 주문 판독 완료 ({신뢰도})", f"보고자: {sender}", ""]

    for o in orders:
        날짜 = o.get("날짜", "날짜미상")
        빈번호 = ", ".join(o.get("빈번호") or [])
        시간 = o.get("시간", "")
        비고 = o.get("비고", "")
        line = f"📅 {날짜}: {빈번호}"
        if 시간: line += f" ({시간})"
        if 비고: line += f" ⚠️{비고}"
        lines.append(line)

    if not orders:
        lines.append("주문 내용을 읽지 못했습니다")

    return "\n".join(lines)


def notion_save_feed_order(result: dict, sender: str, image_date: str = None) -> bool:
    """사료 주문 판독 결과를 노션 주문 관리 DB에 저장"""
    if not NOTION_TOKEN or result.get("error"):
        return False

    orders = result.get("주문목록", [])
    today = image_date or datetime.now().strftime("%Y-%m-%d")

    for o in orders:
        날짜텍스트 = o.get("날짜", "")
        빈번호 = ", ".join(o.get("빈번호") or [])
        시간 = o.get("시간", "")
        비고 = o.get("비고", "")

        # 날짜 추정
        order_date = today
        if "토" in 날짜텍스트 or "토요일" in 날짜텍스트:
            order_date = today  # 당일 이후 가장 가까운 토요일 (간단히 today 사용)
        elif "월" in 날짜텍스트 or "월요일" in 날짜텍스트:
            order_date = today

        # 날짜에서 숫자 추출 (4일, 6일 등)
        import re as _re
        num_m = _re.search(r"(\d+)일", 날짜텍스트)
        if num_m:
            day = int(num_m.group(1))
            month = datetime.now().month
            year = datetime.now().year
            order_date = f"{year}-{month:02d}-{day:02d}"

        잘림여부 = "⚠️사진잘림" if 비고 and "잘림" in 비고 else ""
        메모내용 = f"사진 주문 Vision 판독 ({sender}). {시간} {잘림여부}".strip()

        try:
            requests.post(
                "https://api.notion.com/v1/pages",
                headers=NOTION_HEADERS,
                json={
                    "parent": {"database_id": "c8ce6eac-dae2-429a-aa73-e43c63fe6704"},
                    "properties": {
                        "Name":       {"title": [{"text": {"content": f"🌾 사료주문 — {날짜텍스트} {빈번호}"}}]},
                        "date:주문날짜:start": order_date,
                        "date:주문날짜:is_datetime": 0,
                        "주문유형":   {"select": {"name": "🌾 사료"}},
                        "품목":       {"rich_text": [{"text": {"content": 빈번호}}]},
                        "수량":       {"rich_text": [{"text": {"content": 시간 or "미상"}}]},
                        "메모":       {"rich_text": [{"text": {"content": 메모내용}}]},
                        "상태":       {"select": {"name": "📋 접수"}},
                    }
                },
                timeout=10,
            )
        except Exception as e:
            logger.error(f"사료주문 노션 저장 오류: {e}")

    return True


# ── 사진 수신 핸들러에 사료주문 판독 통합 ──
# handle_photo 함수에서 weaning이 아닌 경우
# caption에 "주문", "사료", "사전주문" 키워드 있으면 사료 주문 판독 실행

FEED_ORDER_KEYWORDS = ["주문", "사료", "사전주문", "주말주문", "빈번호", "젖돈", "육돈"]

async def handle_feed_order_photo(update, ctx, image_bytes: bytes, sender: str):
    """사료 주문 사진 처리"""
    msg = update.message

    await msg.reply_text("📸 사료 주문 사진 판독 중...")

    result = await vision_read_feed_order(image_bytes)
    reply_text = format_feed_order_message(result, sender)

    await msg.reply_text(reply_text)

    # 노션 저장
    if not result.get("error"):
        saved = notion_save_feed_order(result, sender)
        if saved:
            await msg.reply_text("✅ 노션 주문 관리 DB 저장 완료!")

    # 대표님 DM 알림
    if ADMIN_ID:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"📦 사료 주문 사진 수신\n보고자: {sender}\n\n{reply_text}")

    # 배합지시 문자 자동 생성 (판독 성공 시)
    if not result.get("error") and result.get("주문목록"):
        orders = parse_vision_to_orders(result, datetime.now().strftime("%Y-%m-%d"))
        if orders:
            await send_feed_dispatch_to_admin(ctx, orders, sender, reply_text)


# ══════════════════════════════════════════════════════════
# ✏️ 수정후승인 처리 핸들러
# ══════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════
# 🌾 배합지시 문자 생성 시스템
# ══════════════════════════════════════════════════════════

def build_feed_dispatch(orders: list, base_date: str = None) -> str:
    """
    승인된 주문 목록 → 배합지시 문자 형식으로 변환
    orders: [{"사료종류": "젖돈", "수량": "5톤", "빈번호": "3-1번", "예정일": "2026-04-06", "시간": "2시차"}, ...]
    """
    from datetime import datetime
    import re

    if not orders:
        return ""

    # 날짜별 그룹핑
    groups = {}
    for o in orders:
        key = (o.get("예정일", ""), o.get("시간", ""))
        groups.setdefault(key, []).append(o)

    lines = []
    for (date_str, time_str), items in sorted(groups.items()):
        # 날짜 포맷
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekdays = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
            date_line = f"{dt.month}월 {dt.day}일 {weekdays[dt.weekday()]}"
        except:
            date_line = date_str

        lines.append(date_line)
        if time_str:
            lines.append(time_str)

        for o in items:
            종류  = o.get("사료종류", "")
            수량  = o.get("수량", "")
            빈번호 = o.get("빈번호", "")
            if 빈번호:
                lines.append(f"{종류} {수량} {빈번호}번".strip())
            else:
                lines.append(f"{종류} {수량}".strip())

        lines.append("")  # 날짜 구분 빈줄

    return "\n".join(lines).strip()


def parse_vision_to_orders(vision_result: dict, approved_date: str = None) -> list:
    """Vision 판독 결과 → 주문 목록 변환"""
    from datetime import datetime, timedelta
    orders = []
    today = approved_date or datetime.now().strftime("%Y-%m-%d")

    weekday_map = {
        "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
        "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4,
        "토요일": 5, "일요일": 6,
    }

    for item in vision_result.get("주문목록", []):
        날짜텍스트 = item.get("날짜", "")
        빈번호목록  = item.get("빈번호") or []
        시간        = item.get("시간", "")

        # 날짜 계산
        order_date = today
        try:
            base = datetime.strptime(today, "%Y-%m-%d")
            # 요일 파싱
            for key, wday in weekday_map.items():
                if key in 날짜텍스트:
                    diff = (wday - base.weekday()) % 7
                    if diff == 0: diff = 7  # 오늘이면 다음 주로
                    order_date = (base + timedelta(days=diff)).strftime("%Y-%m-%d")
                    break
            # 날짜 숫자 직접 파싱 (예: 4/6, 4월6일)
            import re as _re
            m = _re.search(r"(\d+)[월/](\d+)[일]?", 날짜텍스트)
            if m:
                mo, dy = int(m.group(1)), int(m.group(2))
                year = base.year
                order_date = f"{year}-{mo:02d}-{dy:02d}"
        except:
            pass

        # 빈번호별 주문 생성
        for 빈 in 빈번호목록:
            if not 빈: continue
            # 사료종류 추정 (빈번호 패턴으로)
            import re as _re
            종류 = "사료"
            수량 = ""
            # "젖돈5톤 3-1번" 형식 파싱
            m = _re.match(r"(젖돈|육돈|임신|포유|1호|2호|3호|개사료)\s*(\d+(?:톤|포))\s*(\d+[-\d]*)?", str(빈))
            if m:
                종류  = m.group(1)
                수량  = m.group(2)
                빈_no = m.group(3) or ""
            else:
                빈_no = str(빈).replace("번", "")

            orders.append({
                "사료종류": 종류,
                "수량":    수량,
                "빈번호":  빈_no,
                "예정일":  order_date,
                "시간":    시간,
            })

    return orders


async def send_feed_dispatch_to_admin(ctx, orders: list, sender: str, vision_text: str = ""):
    """배합지시 초안을 대표님 DM으로 전송"""
    if not ADMIN_ID or not orders:
        return

    # 빈번호 기반 사료종류 매핑 보정
    for o in orders:
        if not o.get("사료종류") or o["사료종류"] == "사료":
            t, v = parse_bin_number(o.get("빈번호", ""))
            o["사료종류"] = t
            if not o.get("톤수"): o["톤수"] = v
    # 약품 포함 배합지시 생성
    date_str = orders[0].get("예정일", datetime.now().strftime("%Y-%m-%d")) if orders else ""
    time_str = orders[0].get("시간", "2시차") if orders else "2시차"
    dispatch_text = build_dispatch_with_medicine(orders, date_str, time_str, include_medicine=True)
    if not dispatch_text:
        dispatch_text = build_feed_dispatch(orders)
    if not dispatch_text:
        return

    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {
        "type":         "feed_dispatch",
        "orders":       orders,
        "dispatch_text": dispatch_text,
        "staff":        sender,
        "vision_raw":   vision_text[:200],
    }

    msg_text = (
        f"🌾 배합지시 문자 초안\n"
        f"보고자: {sender}\n"
        f"{'─'*20}\n"
        f"{dispatch_text}\n"
        f"{'─'*20}\n"
        f"위 내용으로 업무방에 발송할까요?"
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 발송",     callback_data=f"dispatch_send|{key}"),
        InlineKeyboardButton("✏️ 수정발송", callback_data=f"dispatch_modify|{key}"),
        InlineKeyboardButton("❌ 취소",     callback_data=f"dispatch_cancel|{key}"),
    ]])

    await ctx.bot.send_message(ADMIN_ID, msg_text, reply_markup=kb)

# ══════════════════════════════════════════════════════════
# 🔄 배합지시 변경/추가/재발송 핸들러
# ══════════════════════════════════════════════════════════



async def _preview_changed_dispatch(msg, ctx, new_text: str, mode: str,
                                     group_id: int, original: str):
    """변경된 배합지시 미리보기 + 발송 확인 버튼"""
    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)

    label = "변경" if mode == "change" else "추가"

    _approval_store[key] = {
        "type":       "dispatch_resend",
        "new_text":   new_text,
        "orig_text":  original,
        "group_id":   group_id,
        "mode":       mode,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ {label}후 재발송", callback_data=f"resend_ok|{key}"),
        InlineKeyboardButton("✏️ 추가수정",           callback_data=f"resend_edit|{key}"),
        InlineKeyboardButton("❌ 취소",               callback_data=f"resend_cancel|{key}"),
    ]])

    diff_line = "🔴 원본 → 🟢 변경" if mode == "change" else "🟢 추가됨"

    await msg.reply_text(
        f"📋 {label}된 배합지시 미리보기\n"
        f"{'─'*20}\n"
        f"{new_text}\n"
        f"{'─'*20}\n"
        f"{diff_line}\n\n"
        f"이 내용으로 업무방에 재발송할까요?",
        reply_markup=kb)




# ══════════════════════════════════════════════════════════
# 🔄 휴무변경 핵심 함수
# ══════════════════════════════════════════════════════════

async def find_confirmed_vacation(staff: str, db_id: str):
    """
    노션 휴무 확정 DB에서 해당 직원의 이번 기간 최신 확정 휴무 조회
    반환: (page_id, old_date, cal_event_id)
    """
    try:
        period_start, period_end = get_pay_period()
        NOTION_DB_CONFIRMED = "fcb20fc0-aa5c-4ef4-be3a-90ee6efeac1f"

        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_CONFIRMED}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "직원명", "select": {"equals": staff}},
                        {"property": "확정날짜", "date": {"on_or_after": period_start}},
                        {"property": "확정날짜", "date": {"on_or_before": period_end}},
                        {"property": "변경상태", "select": {"equals": "확정"}},
                    ]
                },
                "sorts": [{"property": "확정날짜", "direction": "descending"}],
                "page_size": 5,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])
        if not pages:
            return ("", "", "")

        # 가장 최근 확정 건
        page    = pages[0]
        page_id = page["id"]
        d       = page.get("properties", {}).get("확정날짜", {}).get("date", {})
        old_date = d.get("start", "") if d else ""

        # 구글 캘린더 이벤트 ID는 메모 컬럼에 저장해두거나 없으면 빈 문자열
        memo_rt = page.get("properties", {}).get("메모", {}).get("rich_text", [])
        cal_id  = ""
        if memo_rt:
            memo_text = memo_rt[0].get("text", {}).get("content", "")
            import re as _re
            m = _re.search(r"cal_id:(\S+)", memo_text)
            if m:
                cal_id = m.group(1)

        return (page_id, old_date, cal_id)
    except Exception as e:
        logger.error(f"확정 휴무 조회 실패: {e}")
        return ("", "", "")


async def update_vacation_in_notion(page_id: str, old_date: str,
                                     new_date: str, staff: str) -> bool:
    """노션 휴무 확정 DB에서 날짜 변경 + 변경이력 기록"""
    if not page_id or not NOTION_TOKEN:
        return False
    try:
        changed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={
                "properties": {
                    "date:확정날짜:start":       new_date,
                    "date:확정날짜:is_datetime": 0,
                    "변경상태":   {"select": {"name": "변경됨"}},
                    "변경이력":   {"rich_text": [{"text": {"content":
                        "[" + changed_at + "] 변경: " + old_date + "→" + new_date
                    }}]},
                    "변경횟수":  {"number": 1},
                    "원본날짜":  {"rich_text": [{"text": {"content": old_date}}]},
                    "메모":      {"rich_text": [{"text": {"content":
                        "휴무변경 확정 — " + changed_at
                    }}]},
                }
            },
            timeout=10,
        )
        logger.info(f"노션 휴무 변경: {staff} {old_date}→{new_date}")
        return True
    except Exception as e:
        logger.error(f"노션 휴무 변경 오류: {e}")
        return False


async def update_vacation_in_calendar(ctx, old_cal_id: str,
                                       staff: str, new_date: str) -> bool:
    """
    구글 캘린더: 기존 이벤트 삭제 + 새 날짜로 재등록
    Anthropic API 직접 호출로 캘린더 조작
    """
    try:
        import base64, requests as req

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY 없음 — 캘린더 업데이트 스킵")
            return False

        # 새 날짜 다음날 계산
        from datetime import datetime as _dt, timedelta as _td
        end_date = (_dt.strptime(new_date, "%Y-%m-%d") + _td(days=1)).strftime("%Y-%m-%d")

        # 캘린더 MCP 직접 호출 대신
        # 봇이 Anthropic API로 캘린더 이벤트 정보를 ctx.bot_data에 저장
        # 실제 캘린더 업데이트는 도비(Claude.ai)가 별도로 처리
        ctx.bot_data[f"pending_cal_update_{staff}"] = {
            "old_cal_id": old_cal_id,
            "staff":      staff,
            "new_date":   new_date,
            "end_date":   end_date,
            "summary":    "[" + staff + "] 휴무",
            "description": "확정 휴무 1.0일 | 변경확정 | 검증완료",
        }
        logger.info(f"캘린더 업데이트 예약: {staff} → {new_date}")
        return True
    except Exception as e:
        logger.error(f"캘린더 업데이트 오류: {e}")
        return False


# ══════════════════════════════════════════════════════════
# 🌾 배합지시 약품 설정 시스템
# ══════════════════════════════════════════════════════════

NOTION_DB_FEED_MEDICINE = "0a1d92d5-d377-4331-ab34-67eac78280ae"

# ── 빈번호 → 사료종류 매핑 (대표님 규칙 반영) ──
BIN_TO_FEED_TYPE = {
    # 육돈 (7x, 8x)
    "7-2": ("육돈", "5톤"), "7-3": ("육돈", "5톤"),
    "8-1": ("육돈", "5톤"), "8-2": ("육돈", "5톤"),
    # 젖돈 (3x, 4x, 5번)
    "3-1": ("젖돈", "5톤"), "4-1": ("젖돈", "5톤"),
    "4-2": ("젖돈", "3톤"), "5":   ("젖돈", "3톤"),
    "3-1_3t": ("젖돈", "3톤"),  # 3톤 버전
    # 임신 (11~14번)
    "11":  ("임신", "2톤"), "12":  ("임신", "2톤"),
    "13":  ("임신", "2톤"), "14":  ("임신", "2톤"),
    # 포유 (15~16번)
    "15":  ("포유", "2톤"), "16":  ("포유", "1톤"),
    # 소형빈
    "2-2": ("2호", "1톤"),
    "3-2": ("3호", "1톤"),
}

# ── 사료종류 정렬 우선순위 (육돈 > 젖돈 > 임신 > 포유 > 소형) ──
FEED_SORT_ORDER = {"육돈": 0, "젖돈": 1, "임신": 2, "포유": 3, "2호": 4, "3호": 5}

# ── 약품 캐시 (봇 시작 시 로드, 변경 시 갱신) ──
_medicine_cache: dict = {}  # {"육돈": "진프로 2kg\n...", ...}
_medicine_cache_loaded = False

# ── 약품 페이지 ID 캐시 ──
_medicine_page_ids: dict = {}  # {"육돈": "page_id", ...}


def load_medicine_cache() -> dict:
    """노션 약품 DB에서 전체 로드"""
    global _medicine_cache, _medicine_page_ids, _medicine_cache_loaded
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_FEED_MEDICINE}/query",
            headers=NOTION_HEADERS,
            json={"filter": {"property": "활성", "select": {"equals": "✅ 사용중"}},
                  "page_size": 10},
            timeout=8,
        )
        for page in res.json().get("results", []):
            props = page.get("properties", {})
            종류 = props.get("사료종류", {}).get("select", {})
            if not 종류: continue
            종류명 = 종류.get("name", "")
            약품rt = props.get("약품목록", {}).get("rich_text", [])
            약품텍스트 = 약품rt[0].get("text", {}).get("content", "") if 약품rt else ""
            _medicine_cache[종류명] = 약품텍스트
            _medicine_page_ids[종류명] = page["id"]
        _medicine_cache_loaded = True
        logger.info(f"약품 캐시 로드: {list(_medicine_cache.keys())}")
    except Exception as e:
        logger.error(f"약품 캐시 로드 실패: {e}")
    return _medicine_cache


def get_medicine_for_type(feed_type: str) -> str:
    """사료종류에 맞는 약품 목록 반환 (2호·3호 통합)"""
    if not _medicine_cache_loaded:
        load_medicine_cache()
    # 2호·3호는 같은 약품
    if feed_type in ("2호", "3호"):
        return _medicine_cache.get("2호", "") or _medicine_cache.get("3호", "")
    return _medicine_cache.get(feed_type, "")


def parse_bin_number(bin_str: str) -> tuple:
    """
    빈번호 문자열 → (사료종류, 톤수)
    입력: "8-1", "3-1", "12", "2-2" 등
    """
    b = bin_str.strip().replace("번", "")
    if b in BIN_TO_FEED_TYPE:
        return BIN_TO_FEED_TYPE[b]
    # 숫자만인 경우
    try:
        n = int(b)
        if 11 <= n <= 14: return ("임신", "2톤")
        if n == 15:       return ("포유", "2톤")
        if n == 16:       return ("포유", "1톤")
    except: pass
    return ("사료", "")


def build_dispatch_with_medicine(orders: list, date_str: str,
                                  time_str: str = "2시차",
                                  include_medicine: bool = True) -> str:
    """
    주문 목록 → 배합지시 문자 생성
    orders: [{"빈번호": "8-1", "사료종류": "육돈", "톤수": "5톤"}, ...]
    대표님 규칙: 육돈>젖돈>임신>포유>소형 정렬, 5/3/2톤 최적화
    """
    if not orders:
        return ""

    # 날짜 포맷
    try:
        from datetime import datetime as _dt
        dt = _dt.strptime(date_str, "%Y-%m-%d")
        weekdays = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
        date_line = f"{dt.month}월 {dt.day}일 {weekdays[dt.weekday()]}"
    except:
        date_line = date_str

    # 우선순위 정렬
    sorted_orders = sorted(orders, key=lambda x: FEED_SORT_ORDER.get(x.get("사료종류",""), 9))

    lines = [date_line, time_str]

    # 1호(포대) 있으면 맨 앞
    for o in sorted_orders:
        if o.get("사료종류") == "1호":
            lines.append(f"1호 {o.get('톤수', '10포')}")

    # 벌크빈 (사료 + 약품 세트)
    prev_type = None
    for o in sorted_orders:
        종류 = o.get("사료종류", "")
        톤수 = o.get("톤수", "")
        빈번호 = o.get("빈번호", "")
        if 종류 == "1호": continue

        # 사료 라인
        if 빈번호:
            lines.append(f"{종류} {톤수} {빈번호}번")
        else:
            lines.append(f"{종류} {톤수}")

        # 약품 세트 (종류가 바뀔 때만 출력) + 품목 사이 빈줄
        if 종류 != prev_type:
            if prev_type is not None and lines:
                # 마지막 항목 끝에 \n 추가해서 실제 빈줄 생성
                lines[-1] = lines[-1] + "\n"
            if include_medicine:
                약품 = get_medicine_for_type(종류)
                if 약품:
                    for med_line in 약품.split("\n"):
                        if med_line.strip():
                            lines.append(med_line.strip())
            prev_type = 종류

    return "\n".join(lines)


# ── 약품 변경 키워드 ──
KW_MEDICINE_UPDATE = [
    "약품변경", "약품 변경", "약 바꿔", "약바꿔", "약 변경",
    "약품추가", "약품 추가", "약추가", "약 추가",
    "약품제거", "약품 제거", "빼줘", "제거해줘",
    "배합약품", "배합 약품",
]


async def handle_medicine_update(msg, text: str, ctx) -> bool:
    """
    약품 변경 메시지 처리
    예) "육돈 약품변경: 서울린코산 빼고 파마신 1.1kg 추가"
        "젖돈 골든펜다 → 파마신 1.1kg"
        "임신 진프로 2kg→3kg"
    반환: True if 처리됨
    """
    if not any(k in text for k in KW_MEDICINE_UPDATE):
        return False

    # Claude API로 자유형식 파싱
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        await msg.reply_text("⚠️ API 키 없음 — 약품 변경 불가")
        return True

    import base64, requests as req

    prompt = f"""다음 메시지에서 약품 변경 정보를 추출하세요.

메시지: "{text}"

현재 약품 설정:
{chr(10).join(f"{k}: {v}" for k, v in _medicine_cache.items())}

JSON으로만 반환 (다른 텍스트 없이):
{{
  "사료종류": "육돈|젖돈|임신|포유|2호|3호",
  "변경유형": "전체교체|추가|제거|용량변경",
  "새약품목록": "변경 후 전체 약품 목록 (줄바꿈으로 구분)",
  "변경요약": "한 줄 요약"
}}"""

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        raw = resp.json()["content"][0]["text"].strip()
        import re as _re, json as _json
        raw = _re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = _json.loads(raw)
    except Exception as e:
        await msg.reply_text(f"⚠️ 약품 변경 파싱 실패: {e}")
        return True

    종류 = parsed.get("사료종류", "")
    새목록 = parsed.get("새약품목록", "")
    요약 = parsed.get("변경요약", "")

    if not 종류 or not 새목록:
        await msg.reply_text("⚠️ 사료종류 또는 약품 목록을 인식하지 못했습니다\n다시 입력해주세요",
                             )
        return True

    # 노션 업데이트
    page_id = _medicine_page_ids.get(종류)
    if not page_id:
        await msg.reply_text(f"⚠️ {종류} 약품 설정을 찾을 수 없습니다")
        return True

    now_str = datetime.now().strftime("%Y-%m-%d")
    기존목록 = _medicine_cache.get(종류, "")
    이력 = f"[{now_str}] {요약} | 이전: {기존목록[:50]}"

    try:
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": {
                "약품목록":    {"rich_text": [{"text": {"content": 새목록}}]},
                "수정이력":   {"rich_text": [{"text": {"content": 이력}}]},
                "date:최종수정일:start":       now_str,
                "date:최종수정일:is_datetime": 0,
            }},
            timeout=10,
        )
        # 캐시 갱신
        _medicine_cache[종류] = 새목록
        logger.info(f"약품 변경 완료: {종류} — {요약}")

        await msg.reply_text(
            f"✅ {종류} 약품 변경 완료\n\n변경 전:\n{기존목록}\n\n변경 후:\n{새목록}",
            )

        if ADMIN_ID and msg.chat_id != ADMIN_ID:
            await msg.bot.send_message(ADMIN_ID,
                f"🔔 약품 변경 알림\n사료종류: {종류}\n{요약}\n\n변경 후:\n{새목록}")

    except Exception as e:
        await msg.reply_text(f"⚠️ 노션 저장 실패: {e}")

    return True


# ══════════════════════════════════════════════════════════
# 🌾 사료급이 현황 추적 & 작업지시 시스템
# ══════════════════════════════════════════════════════════

NOTION_DB_FEED_STATUS = "64601697-a7aa-48c3-af51-c0f466f3be62"

# 연속 감지 기준일수 (N일 이상 같은 상태 반복 시 지시 발송)
FEED_ALERT_DAYS = 2

# 돈방코드 파싱 (C3...1.2.3 → C3 / B1.2 → B1)
def parse_barn_code(text: str) -> str:
    """메시지에서 돈방 코드 추출 — 가장 앞의 알파벳+숫자 조합"""
    import re as _re
    m = _re.search(r'([A-Za-z]+[0-9]+(?:[.\-][0-9]+)?)', text)
    if m:
        code = m.group(1)
        # "C3...1.2.3" 같은 경우 첫 부분만
        code = _re.match(r'([A-Za-z]+[0-9]+)', code)
        return code.group(1) if code else m.group(1)
    return ""

# 급이 상태 판단
def classify_feed_status(text: str) -> str:
    """
    사료 급이 상태 분류
    반환: '🟡 사료많음' | '🔴 사료없음' | '📋 보고'
    """
    t = text
    if any(k in t for k in ["많아요", "많습니다", "많아", "줄여", "줄이", "오버"]):
        return "🟡 사료많음"
    if any(k in t for k in ["없어요", "없습니다", "없어", "더주", "부족", "비었", "모자"]):
        return "🔴 사료없음"
    return "📋 보고"

# 작업지시 초안 생성
def make_work_order(barn: str, status: str, days: int, dates: list) -> str:
    """
    연속 급이 이슈 → 작업지시 초안 생성
    """
    dates_str = ", ".join(dates[-3:])  # 최근 3일만 표시

    if status == "🟡 사료많음":
        action = "급이량 줄이세요"
        reason = f"사료 많음 {days}일 연속 ({dates_str})"
        detail = f"{barn} 급이량 10~20% 감소 조치 바랍니다"
    else:
        action = "급이량 늘리세요"
        reason = f"사료 부족 {days}일 연속 ({dates_str})"
        detail = f"{barn} 급이량 10~20% 증가 조치 바랍니다"

    return (
        f"[작업지시]\n"
        f"대상: {barn}\n"
        f"상황: {reason}\n"
        f"지시: {detail}"
    )


async def save_feed_status_to_notion(barn: str, status: str,
                                      text: str, sender: str,
                                      date_str: str) -> str:
    """사료급이 현황을 노션 DB에 저장. 반환: page_id"""
    try:
        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DB_FEED_STATUS},
                "properties": {
                    "Name":        {"title": [{"text": {"content":
                        f"{date_str} {barn} {status}"}}]},
                    "date:날짜:start":       date_str,
                    "date:날짜:is_datetime": 0,
                    "돈방코드":   {"rich_text": [{"text": {"content": barn}}]},
                    "상태":       {"select": {"name": status}},
                    "원본메시지": {"rich_text": [{"text": {"content": text[:200]}}]},
                    "보고자":     {"rich_text": [{"text": {"content": sender}}]},
                    "연속일수":   {"number": 1},
                    "처리여부":   {"select": {"name": "미처리"}},
                }
            },
            timeout=10,
        )
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"사료급이 노션 저장 오류: {e}")
        return ""


async def check_feed_consecutive(barn: str, status: str) -> tuple:
    """
    특정 돈방의 연속 급이 이슈 감지
    반환: (연속일수, 날짜목록)
    """
    try:
        from datetime import datetime as _dt, timedelta as _td

        # 최근 7일 데이터 조회
        since = (_dt.now() - _td(days=7)).strftime("%Y-%m-%d")

        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_FEED_STATUS}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "돈방코드", "rich_text": {"equals": barn}},
                        {"property": "상태",     "select": {"equals": status}},
                        {"property": "날짜",     "date": {"on_or_after": since}},
                    ]
                },
                "sorts": [{"property": "날짜", "direction": "descending"}],
                "page_size": 10,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])
        if not pages:
            return (1, [])

        # 날짜 추출 및 연속성 확인
        dates = []
        for p in pages:
            d = p.get("properties", {}).get("날짜", {}).get("date", {})
            if d and d.get("start"):
                dates.append(d["start"])

        dates = sorted(set(dates), reverse=True)  # 중복 제거, 최신순
        today = _dt.now().strftime("%Y-%m-%d")
        if today not in dates:
            dates.insert(0, today)

        # 연속일 계산
        consecutive = 1
        for i in range(len(dates) - 1):
            d1 = _dt.strptime(dates[i], "%Y-%m-%d")
            d2 = _dt.strptime(dates[i+1], "%Y-%m-%d")
            if (d1 - d2).days == 1:
                consecutive += 1
            else:
                break

        return (consecutive, dates[:consecutive])
    except Exception as e:
        logger.error(f"연속 감지 오류: {e}")
        return (1, [])


async def handle_feed_status_message(msg, text: str, sender: str, ctx,
                                      group_id: int):
    """
    사료 급이 현황 메시지 처리
    1. 돈방 코드 + 상태 추출
    2. 노션 저장
    3. 연속 N일 감지 → 작업지시 DM 발송
    """
    barn = parse_barn_code(text)
    if not barn:
        # 돈방 코드 없으면 그냥 로그만
        notion_log(f"🌾 급이현황: {text[:50]}", "✅ 완료", 비고=sender)
        return

    status = classify_feed_status(text)
    today  = datetime.now().strftime("%Y-%m-%d")

    # 노션 저장
    await save_feed_status_to_notion(barn, status, text, sender, today)
    logger.info(f"급이현황 저장: {barn} {status} ({sender})")

    # 연속 감지
    days, dates = await check_feed_consecutive(barn, status)

    if days >= FEED_ALERT_DAYS and ADMIN_ID:
        # 작업지시 초안 생성
        order_text = make_work_order(barn, status, days, dates)

        global _approval_counter
        _approval_counter += 1
        key = str(_approval_counter)
        _approval_store[key] = {
            "type":      "work_order",
            "barn":      barn,
            "status":    status,
            "days":      days,
            "order_text": order_text,
            "group_id":  group_id,
        }

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ 단톡방 발송",   callback_data=f"approve|{key}"),
            InlineKeyboardButton("✏️ 수정후발송",    callback_data=f"modify|{key}"),
            InlineKeyboardButton("❌ 취소",          callback_data=f"reject|{key}"),
        ]])

        await ctx.bot.send_message(
            ADMIN_ID,
            f"⚠️ 급이 미개선 감지\n\n{order_text}\n\n단톡방으로 발송할까요?",
            reply_markup=kb
        )
        logger.info(f"작업지시 DM 발송: {barn} {days}일 연속")


# ══════════════════════════════════════════════════════════
# 🔄 벌크빈 변경 처리 시스템
# ══════════════════════════════════════════════════════════

import re as _re_global

def parse_bin_change(text: str) -> dict:
    """
    벌크빈 변경 메시지 파싱
    "7-3번을 8-2번으로 변경" → {"from": "7-3", "to": "8-2"}
    """
    # 패턴1: "A번을 B번으로"
    m = _re_global.search(r'([0-9]+-[0-9]+)번을?\s*([0-9]+-[0-9]+)번으로', text)
    if m:
        return {"from": m.group(1), "to": m.group(2)}

    # 패턴2: "A → B" or "A -> B"
    m = _re_global.search(r'([0-9]+-[0-9]+)\s*[→\->]+\s*([0-9]+-[0-9]+)', text)
    if m:
        return {"from": m.group(1), "to": m.group(2)}

    # 패턴3: 숫자만 변경 "7-2번을 8-1번"
    m = _re_global.search(r'([0-9]+-[0-9]+)번\s+([0-9]+-[0-9]+)번', text)
    if m:
        return {"from": m.group(1), "to": m.group(2)}

    return {}


async def handle_bin_change(msg, text: str, sender: str, ctx, group_id: int):
    """
    벌크빈 변경 요청 처리
    1. 변경 빈번호 파싱
    2. 배합지시 재생성 초안
    3. 사료회사 변경문자 초안
    4. 대표님 DM 발송
    """
    change = parse_bin_change(text)
    if not change:
        notion_log(f"벌크빈변경(파싱실패): {text[:50]}", "⚠️ 확인필요", 비고=sender)
        return

    from_bin = change["from"]
    to_bin   = change["to"]

    # 사료종류 추정
    feed_type, ton = parse_bin_number(to_bin)

    # 배합지시 변경 예시
    dispatch_change = (
        f"[배합지시 변경]\n"
        f"{feed_type} {ton} {from_bin}번\n"
        f"→ {feed_type} {ton} {to_bin}번"
    )

    # 사료회사 변경문자 초안
    feed_company_msg = (
        f"안녕하세요,\n"
        f"오늘 배합지시 변경 요청드립니다.\n\n"
        f"변경 전: {from_bin}번\n"
        f"변경 후: {to_bin}번\n\n"
        f"확인 부탁드립니다."
    )

    # 노션 주문DB 변경이력 저장
    notion_log(
        f"벌크빈 변경 요청: {from_bin}→{to_bin}",
        "⚠️ 승인대기",
        비고=f"요청자: {sender}"
    )

    if not ADMIN_ID:
        return

    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {
        "type":             "bin_change",
        "from_bin":         from_bin,
        "to_bin":           to_bin,
        "feed_type":        feed_type,
        "ton":              ton,
        "dispatch_change":  dispatch_change,
        "company_msg":      feed_company_msg,
        "group_id":         group_id,
        "sender":           sender,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 변경 승인",    callback_data=f"approve|{key}"),
        InlineKeyboardButton("✏️ 수정후승인",   callback_data=f"modify|{key}"),
        InlineKeyboardButton("❌ 반려",          callback_data=f"reject|{key}"),
    ]])

    dm_text = (
        f"🔄 벌크빈 변경 요청\n"
        f"요청자: {sender}\n"
        f"원문: {text[:80]}\n\n"
        f"── 배합지시 변경 ──\n"
        f"{dispatch_change}\n\n"
        f"── 사료회사 발송 문자 초안 ──\n"
        f"{feed_company_msg}\n\n"
        f"승인 시 → 배합지시 재생성 + 노션 업데이트"
    )

    await ctx.bot.send_message(ADMIN_ID, dm_text, reply_markup=kb)
    logger.info(f"벌크빈 변경 DM 발송: {from_bin}→{to_bin}")


# ══════════════════════════════════════════════════════════
# 💊 약품 주문 자동 인식 시스템
# ══════════════════════════════════════════════════════════

def parse_medicine_order(text: str) -> list:
    """
    약품 주문 텍스트 파싱
    "수이생DA 20병\nPTR2 4통\n페리에이드 1박스" → 목록 반환
    """
    items = []
    lines = text.replace(',', '\n').split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        m = _re_global.search(
            r'([가-힣A-Za-z0-9\.]+(?:\s+[A-Za-z0-9]+)?)\s+'
            r'(\d+(?:\.\d+)?)\s*(병|통|박스|포|개|set|Set|정|ml|L)',
            line
        )
        if m:
            items.append({
                "품목":  m.group(1).strip(),
                "수량":  m.group(2),
                "단위":  m.group(3),
            })
    return items


async def handle_medicine_order_auto(msg, text: str, sender: str,
                                      ctx, group_id: int):
    """
    약품 주문 자동 감지 처리
    1. 약품 목록 파싱
    2. 노션 주문DB 저장
    3. 대표님 DM 승인 요청
    """
    items = parse_medicine_order(text)
    if not items:
        return

    # 주문 내용 포맷
    order_lines = [f"{o['품목']} {o['수량']}{o['단위']}" for o in items]
    order_text  = "\n".join(order_lines)
    today       = datetime.now().strftime("%Y-%m-%d")

    # 노션 주문DB 저장
    try:
        requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DB_ORDER},
                "properties": {
                    "Name":       {"title": [{"text": {"content":
                        f"💊 약품주문 — {today} ({sender})"}}]},
                    "date:주문날짜:start":       today,
                    "date:주문날짜:is_datetime": 0,
                    "주문유형":   {"select": {"name": "💊 약품"}},
                    "품목":       {"rich_text": [{"text": {"content": order_text}}]},
                    "수량":       {"rich_text": [{"text": {"content":
                        f"{len(items)}개 품목"}}]},
                    "상태":       {"select": {"name": "📋 접수"}},
                    "입고상태":   {"select": {"name": "📋 발주"}},
                }
            },
            timeout=10,
        )
    except Exception as e:
        logger.error(f"약품주문 노션 저장 오류: {e}")

    if not ADMIN_ID:
        return

    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {
        "type":       "order",
        "order_type": "💊 약품",
        "staff":      sender,
        "content":    order_text,
        "group_id":   group_id,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 승인",     callback_data=f"approve|{key}"),
        InlineKeyboardButton("✏️ 수정승인", callback_data=f"modify|{key}"),
        InlineKeyboardButton("❌ 반려",     callback_data=f"reject|{key}"),
    ]])

    await ctx.bot.send_message(
        ADMIN_ID,
        f"💊 약품 주문 접수\n"
        f"요청자: {sender}\n\n"
        f"{order_text}",
        reply_markup=kb
    )
    logger.info(f"약품주문 DM 발송: {len(items)}개 품목 ({sender})")


# ══════════════════════════════════════════════════════════
# 📸 사진 분석 스마트 필터 시스템
# ══════════════════════════════════════════════════════════

# 사진 대기 세션 {user_id: {"photo_bytes": bytes, "time": datetime, "msg": msg}}
_photo_pending: dict = {}
PHOTO_WAIT_SECONDS = 30  # 30초 이내 후속 메시지 있으면 분석 스킵

# ── 사진 즉시 분석 대상자 (이름 키워드로 매칭)
# 텔레그램 full_name에 이 키워드가 포함되면 사진 즉시 분석
INSTANT_ANALYZE_NAMES = [
    "신기철",      # 농장장 — 모든 사진 즉시 분석
    "기철",
    "SinKiCheol",
    "Shin",        # 영문명 포함 시
]

def is_instant_analyze_user(sender_name: str) -> bool:
    """즉시 분석 대상자인지 확인"""
    return any(k in sender_name for k in INSTANT_ANALYZE_NAMES)


async def analyze_unknown_photo(ctx, photo_bytes: bytes,
                                 sender: str, msg) -> str:
    """
    급이현황 메시지 없는 사진 → Vision API로 분석
    무엇을 위한 사진인지 파악
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    import base64, requests as req, json as _json

    b64 = base64.b64encode(photo_bytes).decode("utf-8")
    prompt = """이 사진은 돼지 농장 직원이 업무 보고를 위해 찍은 사진입니다.

사진을 보고 아래 중 어떤 목적인지 판단해서 JSON으로만 답하세요:

{
  "목적": "급이현황|폐사|시설이상|이유|입식|출하|작업완료|기타",
  "요약": "한 줄 요약 (30자 이내)",
  "긴급도": "높음|보통|낮음"
}

판단 기준:
- 급이현황: 사료통/밥그릇/사료 양이 보임
- 폐사: 죽은 돼지가 보임
- 시설이상: 기계/파이프/시설 이상 보임
- 이유: 새끼 돼지 이동 작업
- 입식: 돼지 입식 장면
- 출하: 돼지 출하 장면
- 작업완료: 작업 완료 현장"""

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 200,
                  "messages": [{"role": "user", "content": [
                      {"type": "image", "source": {
                          "type": "base64", "media_type": "image/jpeg", "data": b64}},
                      {"type": "text", "text": prompt}
                  ]}]},
            timeout=20,
        )
        raw = resp.json()["content"][0]["text"].strip()
        import re as _re
        raw = _re.sub(r"```(?:json)?|```", "", raw).strip()
        result = _json.loads(raw)
        return result
    except Exception as e:
        logger.error(f"사진 분석 오류: {e}")
        return {}


async def process_pending_photo(ctx, user_id: int):
    """
    30초 후 실행 — 후속 메시지 없으면 Vision 분석
    """
    await asyncio.sleep(PHOTO_WAIT_SECONDS)

    pending = _photo_pending.pop(user_id, None)
    if not pending:
        return  # 이미 처리됨 (급이현황 메시지 왔었음)

    photo_bytes = pending["photo_bytes"]
    sender      = pending["sender"]
    msg         = pending["msg"]
    group_id    = pending["group_id"]

    logger.info(f"사진 Vision 분석 시작: {sender}")
    result = await analyze_unknown_photo(ctx, photo_bytes, sender, msg)

    if not result:
        return

    목적 = result.get("목적", "기타")
    요약 = result.get("요약", "")
    긴급 = result.get("긴급도", "보통")

    # 노션 로그
    notion_log(f"📷 사진분석: {목적} — {요약}", "✅ 완료", 비고=sender)

    # 긴급 또는 폐사/시설이상이면 DM 알림
    if ADMIN_ID and (긴급 == "높음" or 목적 in ("폐사", "시설이상")):
        emoji = "🚨" if 목적 in ("폐사", "시설이상") else "⚠️"
        await ctx.bot.send_message(
            ADMIN_ID,
            f"{emoji} 사진 분석 결과\n"
            f"직원: {sender}\n"
            f"내용: {목적} — {요약}\n"
            f"긴급도: {긴급}"
        )

    logger.info(f"사진 분석 완료: {목적} / {요약}")


# ══════════════════════════════════════════════════════════
# 📸 즉시 분석 대상자 전용 핸들러
# ══════════════════════════════════════════════════════════

async def _instant_analyze_photo(ctx, photo_bytes: bytes,
                                  sender: str, msg, group_id: int):
    """
    신기철 농장장 등 즉시 분석 대상자 사진 처리
    타이머 없이 바로 Vision API 분석 후 결과 보고
    """
    result = await analyze_unknown_photo(ctx, photo_bytes, sender, msg)
    if not result:
        return

    목적   = result.get("목적", "기타")
    요약   = result.get("요약", "")
    긴급도 = result.get("긴급도", "보통")

    # 노션 로그 저장
    notion_log(
        f"📷 즉시분석({sender}): {목적} — {요약}",
        "✅ 완료",
        비고=sender
    )

    # 대표님 DM — 항상 전송 (즉시 분석 대상자는 전부 보고)
    if ADMIN_ID:
        emoji_map = {
            "폐사":    "🚨",
            "시설이상": "🔧",
            "급이현황": "🌾",
            "이유":    "🐷",
            "출하":    "🚛",
            "입식":    "📥",
            "작업완료": "✅",
        }
        emoji = emoji_map.get(목적, "📷")
        긴급표시 = " ⚠️긴급" if 긴급도 == "높음" else ""

        await ctx.bot.send_message(
            ADMIN_ID,
            f"{emoji} {sender} 사진 분석{긴급표시}\n"
            f"내용: {목적} — {요약}\n"
            f"긴급도: {긴급도}"
        )
        logger.info(f"즉시분석 DM 발송: {sender} / {목적}")


# ══════════════════════════════════════════════════════════
# ⏰ 배합지시 예약 발송 시스템
# ══════════════════════════════════════════════════════════

NOTION_DB_DISPATCH_SCHEDULE = "69c209e1-66e2-4a7c-9cb6-176fb8655e9f"
NOTION_DB_DEATH     = "8a35becc-b23b-490a-829a-9a058dd88b8d"
NOTION_DB_LOG       = "1b6d6904-aed1-46e8-b378-0de23d614e10"
NOTION_DB_ORDER     = "c8ce6eac-dae2-429a-aa73-e43c63fe6704"
NOTION_DB_WEANING   = "877cf48e-e04f-40b9-92d3-3069ac02fa1f"
NOTION_DB_VACATION_CONF = "fcb20fc0-aa5c-4ef4-be3a-90ee6efeac1f"

# 예약 발송 기본 시간 (오전 7시)
DISPATCH_SCHEDULE_HOUR = 7
DISPATCH_SCHEDULE_MIN  = 0


def calc_schedule_time(target_date: str) -> datetime:
    """
    배합지시 예약 발송 시간 계산
    target_date: "2026-04-07" → 2026-04-07 07:00
    """
    from datetime import datetime as _dt
    try:
        d = _dt.strptime(target_date, "%Y-%m-%d")
        return d.replace(hour=DISPATCH_SCHEDULE_HOUR,
                         minute=DISPATCH_SCHEDULE_MIN, second=0)
    except:
        return datetime.now().replace(hour=DISPATCH_SCHEDULE_HOUR,
                                      minute=DISPATCH_SCHEDULE_MIN)


def extract_dispatch_date(dispatch_text: str) -> str:
    """
    배합지시 문자에서 날짜 추출
    "4월 7일 화요일\n2시차\n..." → "2026-04-07"
    """
    import re as _re
    m = _re.search(r'(\d+)월\s*(\d+)일', dispatch_text)
    if m:
        month = int(m.group(1))
        day   = int(m.group(2))
        year  = datetime.now().year
        # 월이 현재보다 작으면 내년
        if month < datetime.now().month:
            year += 1
        return f"{year}-{month:02d}-{day:02d}"
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


async def save_dispatch_schedule(dispatch_text: str, target_date: str,
                                  original_order: str = "") -> str:
    """노션 예약발송 DB에 저장. 반환: page_id"""
    try:
        schedule_dt = calc_schedule_time(target_date)
        schedule_iso = schedule_dt.strftime("%Y-%m-%dT%H:%M:%S")

        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DB_DISPATCH_SCHEDULE},
                "properties": {
                    "Name": {"title": [{"text": {"content":
                        f"⏰ 배합지시 예약 — {target_date} 07:00"}}]},
                    "date:예약발송일시:start":      schedule_iso,
                    "date:예약발송일시:is_datetime": 1,
                    "배합지시내용": {"rich_text": [{"text": {"content": dispatch_text[:2000]}}]},
                    "원본주문":    {"rich_text": [{"text": {"content": original_order[:500]}}]},
                    "발송상태":   {"select": {"name": "⏰ 예약중"}},
                    "수정횟수":   {"number": 0},
                }
            },
            timeout=10,
        )
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"예약발송 노션 저장 오류: {e}")
        return ""


async def update_dispatch_schedule_status(page_id: str, status: str,
                                           new_text: str = "") -> bool:
    """예약발송 DB 상태 업데이트"""
    if not page_id:
        return False
    try:
        props = {"발송상태": {"select": {"name": status}}}
        if new_text:
            props["배합지시내용"] = {"rich_text": [{"text": {"content": new_text[:2000]}}]}
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": props},
            timeout=10,
        )
        return True
    except Exception as e:
        logger.error(f"예약발송 상태 업데이트 오류: {e}")
        return False


async def send_dispatch_schedule_kb(ctx, dispatch_text: str,
                                     target_date: str, original_order: str,
                                     edit_msg=None):
    """
    배합지시 예약 발송 DM 전송
    [✅ 예약발송] [✏️ 수정후예약] [🚀 지금발송] [❌ 취소]
    """
    if not ADMIN_ID:
        return

    schedule_dt = calc_schedule_time(target_date)
    today_str   = datetime.now().strftime("%Y-%m-%d")
    is_today    = target_date == today_str

    # 오늘 입고분이면 "지금 발송" 강조
    if is_today:
        time_note = "⚡ 오늘 입고분 — 지금 발송 또는 취소를 선택하세요"
    else:
        time_note = f"📅 {target_date} 오전 7시에 단톡방 자동 발송 예정"

    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {
        "type":           "dispatch_schedule",
        "dispatch_text":  dispatch_text,
        "target_date":    target_date,
        "original_order": original_order,
        "schedule_page_id": "",  # 저장 후 업데이트
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⏰ 예약발송",   callback_data=f"sched_ok|{key}"),
        InlineKeyboardButton("✏️ 수정후예약", callback_data=f"sched_edit|{key}"),
        InlineKeyboardButton("🚀 지금발송",   callback_data=f"sched_now|{key}"),
        InlineKeyboardButton("❌ 취소",        callback_data=f"sched_cancel|{key}"),
    ]])

    msg_text = (
        f"📋 배합지시 확인\n"
        f"{'─'*20}\n"
        f"{dispatch_text}\n"
        f"{'─'*20}\n"
        f"{time_note}\n\n"
        f"어떻게 처리할까요?"
    )

    if edit_msg:
        await edit_msg.edit_text(msg_text, reply_markup=kb)
    else:
        await ctx.bot.send_message(ADMIN_ID, msg_text, reply_markup=kb)


async def execute_scheduled_dispatch(ctx, dispatch_text: str,
                                      group_id: int, page_id: str = ""):
    """실제 단톡방 발송 실행"""
    import re as _re
    time_hint = ""
    t_match = _re.search(r"(\d+)시차", dispatch_text)
    if t_match:
        ah = int(t_match.group(1))
        ph, pm = ah - 1, 30
        ampm = "오후" if ah >= 12 else "오전"
        pampm = "오후" if ph >= 12 else "오전"
        dh = ah - 12 if ah > 12 else ah
        pdh = ph - 12 if ph > 12 else ph
        time_hint = (
            f"\n\n⏰ {ampm} {dh}시 입고 예정"
            f"\n{pampm} {pdh}시 {pm:02d}분까지 배합 완료 부탁드립니다"
        )

    final_msg = "🌾 사료 배합지시\n\n" + dispatch_text + time_hint

    if group_id:
        await ctx.bot.send_message(group_id, final_msg)

    # 노션 상태 업데이트
    if page_id:
        await update_dispatch_schedule_status(page_id, "✅ 발송완료")

    # last_dispatch 업데이트
    ctx.bot_data["last_dispatch"] = {
        "text":    dispatch_text,
        "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    logger.info(f"배합지시 발송 완료: {dispatch_text[:30]}")


async def restore_scheduled_dispatches(app):
    """
    봇 재시작 시 노션에서 미발송 예약 복원
    발송 예정이지만 아직 안 보낸 것들 job_queue에 재등록
    """
    try:
        now = datetime.now()
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DISPATCH_SCHEDULE}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "발송상태", "select": {"equals": "⏰ 예약중"}},
                        {"property": "예약발송일시", "date": {"on_or_after": now.strftime("%Y-%m-%d")}},
                    ]
                },
                "page_size": 10,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])
        count = 0
        for page in pages:
            props = page.get("properties", {})
            dt_info = props.get("예약발송일시", {}).get("date", {})
            if not dt_info or not dt_info.get("start"):
                continue

            schedule_str = dt_info["start"]
            try:
                schedule_dt = datetime.fromisoformat(schedule_str)
            except:
                continue

            if schedule_dt <= now:
                continue  # 이미 지난 시간

            # 배합지시 내용
            rt = props.get("배합지시내용", {}).get("rich_text", [])
            dispatch_text = rt[0].get("text", {}).get("content", "") if rt else ""
            page_id = page["id"]

            delay = (schedule_dt - now).total_seconds()
            group_id = app.bot_data.get("main_group_id", 0)

            async def _send_later(ctx, dt=dispatch_text, gid=group_id, pid=page_id):
                await execute_scheduled_dispatch(ctx, dt, gid, pid)

            app.job_queue.run_once(_send_later, when=delay)
            count += 1
            logger.info(f"예약 복원: {schedule_str} — {dispatch_text[:30]}")

        if count > 0:
            logger.info(f"✅ 예약발송 {count}건 복원 완료")
    except Exception as e:
        logger.error(f"예약발송 복원 오류: {e}")


# ══════════════════════════════════════════════════════════
# 🌾 사료 주문 승인 완전 흐름
# 승인 → 사료회사 문자 DM → 단톡방 주문확정 → 배합지시 예약
# ══════════════════════════════════════════════════════════

def make_feed_company_msg(order_content: str, orders: list = None) -> str:
    """
    사료회사 발송용 문자 초안 생성
    빈번호 + 사료종류 + 톤수 형식으로 변환
    """
    import re as _re

    # 빈번호 추출
    bins = _re.findall(r'([0-9]+-[0-9]+|[0-9]{1,2})번?', order_content)

    if not bins:
        return order_content

    lines = []
    # 날짜 추출
    date_m = _re.search(r'(\d+월\d+일|\d+/\d+)', order_content)
    if date_m:
        lines.append(date_m.group(1) + " 입고 사료")

    for b in bins:
        feed_type, ton = parse_bin_number(b)
        if feed_type and feed_type != "사료":
            lines.append(f"{feed_type} {ton} {b}번")

    return "\n".join(lines) if lines else order_content


def make_order_confirm_msg(order_content: str, staff: str) -> str:
    """
    단톡방 주문 확정 알림 메시지
    직원이 보고 어느 빈에 얼마가 주문됐는지 확인 가능
    """
    import re as _re
    bins = _re.findall(r'([0-9]+-[0-9]+|[0-9]{1,2})번?', order_content)

    lines = ["✅ 사료 주문 확정"]

    # 날짜 추출
    date_m = _re.search(r'(\d+월\s*\d+일|\d+/\d+)', order_content)
    if date_m:
        lines.append(date_m.group(1) + " 입고")
    lines.append("")

    for b in bins:
        feed_type, ton = parse_bin_number(b)
        if feed_type and feed_type != "사료":
            lines.append(f"{feed_type} {ton} {b}번")

    return "\n".join(lines)


async def _handle_feed_order_approved(ctx, query, order_content: str,
                                       staff: str, gid: int,
                                       key: str, payload: dict):
    """
    사료 주문 승인 후 전체 흐름 처리:
    1. 사료회사 문자 DM
    2. 단톡방 주문 확정 알림
    3. 배합지시 초안 + 예약 DM
    """
    # ── STEP 1: 사료회사 문자 초안 DM ──
    company_msg = make_feed_company_msg(order_content)

    global _approval_counter
    _approval_counter += 1
    company_key = str(_approval_counter)
    _approval_store[company_key] = {
        "type":          "feed_company_msg",
        "company_msg":   company_msg,
        "order_content": order_content,
        "staff":         staff,
        "gid":           gid,
        "orig_payload":  payload,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 발송확정",   callback_data=f"company_send|{company_key}"),
        InlineKeyboardButton("✏️ 수정후발송", callback_data=f"company_edit|{company_key}"),
        InlineKeyboardButton("❌ 취소",        callback_data=f"company_cancel|{company_key}"),
    ]])

    await query.edit_message_text(
        "📱 사료회사 발송 문자 확인\n"
        "─" * 20 + "\n"
        + company_msg + "\n"
        "─" * 20 + "\n"
        "위 내용으로 사료회사에 발송할까요?",
        reply_markup=kb
    )


async def _after_company_send(ctx, company_msg: str, order_content: str,
                               staff: str, gid: int, payload: dict):
    """
    사료회사 문자 발송 확정 후:
    1. 단톡방에 주문 확정 알림
    2. 배합지시 초안 + 예약 DM
    """
    # ── STEP 2: 단톡방 주문 확정 알림 ──
    confirm_msg = make_order_confirm_msg(order_content, staff)
    if gid:
        await ctx.bot.send_message(gid, confirm_msg)

    # 노션 로그
    notion_log(f"사료 주문 확정 단톡방 알림: {order_content[:50]}", "✅ 완료")

    # ── STEP 3: 배합지시 초안 생성 후 예약 DM ──
    import re as _re
    bins = _re.findall(r'([0-9]+-[0-9]+|[0-9]{1,2})번?', order_content)
    orders = []
    for b in bins:
        feed_type, ton = parse_bin_number(b)
        if feed_type and feed_type != "사료":
            orders.append({
                "빈번호":   b + "번",
                "사료종류": feed_type,
                "톤수":     ton,
                "예정일":   extract_dispatch_date(order_content),
                "시간":     "2시차",
            })

    if orders:
        dispatch_text = build_dispatch_with_medicine(
            orders,
            orders[0]["예정일"],
            orders[0]["시간"],
            include_medicine=True
        )
    else:
        dispatch_text = order_content

    target_date = extract_dispatch_date(order_content)

    # 배합지시 예약 DM
    await send_dispatch_schedule_kb(
        ctx, dispatch_text, target_date, order_content
    )


# ── feed_company_msg 콜백 처리 (handle_callback에 추가 필요)
# 아래 함수를 handle_callback 맨 앞에서 체크

async def handle_company_msg_callback(action: str, key: str,
                                       query, ctx) -> bool:
    """
    사료회사 문자 발송 콜백 처리
    반환: True if 처리됨
    """
    if action not in ("company_send", "company_edit", "company_cancel"):
        return False

    payload = _approval_store.get(key)
    if not payload:
        await query.edit_message_text("⚠️ 만료된 요청입니다")
        return True

    company_msg   = payload.get("company_msg", "")
    order_content = payload.get("order_content", "")
    staff         = payload.get("staff", "")
    gid           = payload.get("gid", 0) or ctx.bot_data.get("main_group_id", 0)
    orig_payload  = payload.get("orig_payload", {})

    if action == "company_send":
        # 발송 확정 → 단톡방 + 배합지시 DM
        await query.edit_message_text(
            "✅ 사료회사 문자 발송 확정\n\n" + company_msg)
        _approval_store.pop(key, None)
        await _after_company_send(ctx, company_msg, order_content, staff, gid, orig_payload)

    elif action == "company_edit":
        # 수정 요청
        ctx.bot_data[f"modify_wait_{key}"] = {
            "payload": payload,
            "mode":    "company_msg",
            "chat_id": query.message.chat_id,
        }
        await query.edit_message_text(
            "✏️ 수정할 사료회사 문자 입력:\n"
            "/modify_" + key + " 수정된 문자")

    elif action == "company_cancel":
        await query.edit_message_text("❌ 사료회사 문자 발송 취소")
        _approval_store.pop(key, None)

    return True


# ══════════════════════════════════════════════════════════
# 🌾 사료주문 → 사료회사 문자 DM 직접 발송 (승인 단계 없음)
# ══════════════════════════════════════════════════════════

async def _send_feed_company_dm(ctx, order_text: str, sender: str, group_id: int):
    """
    사료 주문 감지 즉시 → 사료회사 발송 문자 초안 DM
    승인 단계 없이 바로 문자 확인 → 단톡방 공유 → 배합지시 예약
    """
    if not ADMIN_ID:
        return

    company_msg = make_feed_company_msg(order_text)
    if not company_msg.strip():
        company_msg = order_text  # 파싱 실패 시 원문 그대로

    global _approval_counter
    _approval_counter += 1
    key = str(_approval_counter)
    _approval_store[key] = {
        "type":          "feed_company_msg",
        "company_msg":   company_msg,
        "order_content": order_text,
        "staff":         sender,
        "gid":           group_id,
        "orig_payload":  {},
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 발송확정",   callback_data=f"company_send|{key}"),
        InlineKeyboardButton("✏️ 수정후발송", callback_data=f"company_edit|{key}"),
        InlineKeyboardButton("❌ 취소",        callback_data=f"company_cancel|{key}"),
    ]])

    await ctx.bot.send_message(
        ADMIN_ID,
        "📱 사료회사 발송 문자\n"
        "─" * 20 + "\n"
        + company_msg + "\n"
        "─" * 20 + "\n"
        "요청자: " + sender + "\n\n"
        "발송 확정 시 → 단톡방 공유 + 배합지시 예약 DM",
        reply_markup=kb
    )


# ══════════════════════════════════════════════════════════
# 🐷 이유(Weaning) 보고 처리 시스템
# handle_weaning_report — classify()에서 "weaning" 반환 시 호출
# ══════════════════════════════════════════════════════════

NOTION_DB_WEANING_CONFIRMED = "877cf48e-e04f-40b9-92d3-3069ac02fa1f"


def notion_weaning_save(data: dict, staff: str) -> str:
    """
    이유 기록 DB에 저장 (실제 컬럼명 기반)
    반환: page_id
    """
    if not NOTION_TOKEN:
        return ""
    날짜   = data.get("날짜", datetime.now().strftime("%Y-%m-%d"))
    분만사 = data.get("분만사", "")
    모돈   = data.get("모돈", 0)
    자돈   = data.get("자돈", 0)
    인큐   = data.get("인큐", "")
    군번호 = data.get("군번호", "")
    평균일령 = data.get("평균일령", 0)
    평균산차 = data.get("평균산차", 0)
    산차분포 = data.get("산차분포", "")
    카드수   = data.get("카드수", 0)

    # 제목 생성
    title = f"이유 {날짜}"
    if 분만사:
        title += f" {분만사}"
    if 자돈:
        title += f" {자돈}두"

    props = {
        "Name": {"title": [{"text": {"content": title}}]},
        "date:이유날짜:start":       날짜,
        "date:이유날짜:is_datetime": 0,
        "자돈두수":   {"number": int(자돈) if 자돈 else 0},
        "모돈두수":   {"number": int(모돈) if 모돈 else 0},
    }

    if 분만사:
        # "1분만사", "2분만사" 형식으로 변환
        분만사_val = 분만사 if 분만사.endswith("분만사") else f"{분만사}분만사"
        props["분만사"] = {"select": {"name": 분만사_val}}
    if 인큐:
        props["인큐번호"]  = {"rich_text": [{"text": {"content": str(인큐)}}]}
    if 군번호:
        props["군번호"]    = {"rich_text": [{"text": {"content": str(군번호)}}]}
    if 평균일령:
        props["평균일령"]  = {"number": float(평균일령)}
    if 평균산차:
        props["평균산차"]  = {"number": float(평균산차)}
    if 산차분포:
        props["산차분포"]  = {"rich_text": [{"text": {"content": str(산차분포)}}]}
    if 카드수:
        props["판독카드수"] = {"number": int(카드수)}
    if staff:
        props["특이사항"]  = {"rich_text": [{"text": {"content": f"보고자: {staff}"}}]}

    try:
        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_WEANING_CONFIRMED},
                  "properties": props},
            timeout=10,
        )
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"이유 노션 저장 오류: {e}")
        return ""


async def handle_weaning_report(msg, text: str, sender: str,
                                 ctx, group_id: int):
    """
    이유 보고 처리:
    1. 텍스트에서 이유 데이터 파싱
    2. 노션 이유 기록 DB 저장
    3. weaning_session 활성화 (이후 사진이 오면 카드 판독)
    4. 대표님 DM 알림
    """
    data = parse_weaning_text(text)
    날짜   = data.get("날짜", datetime.now().strftime("%Y-%m-%d"))
    분만사 = data.get("분만사", "")
    모돈   = data.get("모돈", 0)
    자돈   = data.get("자돈", 0)
    인큐   = data.get("인큐", "")

    # 노션 저장
    page_id = notion_weaning_save(data, sender)
    logger.info(f"이유 보고 저장: {날짜} {분만사} 자돈{자돈}두 ({sender})")

    # ── weaning_session 활성화
    # 이후 업로드되는 사진을 모돈관리현황판으로 판독
    # bot_data에 저장 (단체방 전체 공유 — user_data는 사용자별이라 덮어쓰여짐)
    ctx.bot_data["weaning_session"] = {
        "date":      날짜,
        "분만사":    분만사,
        "모돈":      모돈,
        "자돈":      자돈,
        "인큐":      인큐,
        "page_id":   page_id,
        "cards":     [],
        "text_info": data,
        "group_id":  group_id,
        "sender":    sender,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    logger.info(f"weaning_session 활성화 (bot_data): {날짜} {분만사}")

    # ── 단체방 응답 (간단히)
    summary_parts = [f"🐷 이유 보고 접수"]
    if 날짜:
        try:
            d = datetime.strptime(날짜, "%Y-%m-%d")
            summary_parts.append(f"날짜: {d.month}/{d.day}")
        except: pass
    if 분만사:  summary_parts.append(f"분만사: {분만사}")
    if 모돈:   summary_parts.append(f"모돈: {모돈}복")
    if 자돈:   summary_parts.append(f"자돈: {자돈}두")
    if 인큐:   summary_parts.append(f"인큐: {인큐}번")
    summary_parts.append("📸 현황판 사진을 올려주세요")

    reply_text = "\n".join(summary_parts)
    await msg.reply_text(reply_text)

    # ── 대표님 DM 알림
    if ADMIN_ID:
        dm_lines = ["🐷 이유 보고", ""]
        if 날짜:
            try:
                d = datetime.strptime(날짜, "%Y-%m-%d")
                dm_lines.append(f"날짜: {d.month}/{d.day}")
            except: dm_lines.append(f"날짜: {날짜}")
        if 분만사: dm_lines.append(f"분만사: {분만사}")
        if 모돈:   dm_lines.append(f"모돈: {모돈}복")
        if 자돈:   dm_lines.append(f"자돈: {자돈}두")
        if 인큐:   dm_lines.append(f"인큐: {인큐}번")
        dm_lines.append("")
        dm_lines.append("📸 현황판 사진 대기중...")
        await ctx.bot.send_message(ADMIN_ID, "\n".join(dm_lines))

    # ── 대표님 DM 알림
    if ADMIN_ID:
        dm_lines = [
            "🐷 이유 보고",
            f"보고자: {sender}",
            "",
        ] + summary_parts[1:-1]  # 날짜/분만사/모돈/자돈/인큐
        dm_lines.append(f"\n노션 저장 완료 ✅")
        await ctx.bot.send_message(ADMIN_ID, "\n".join(dm_lines))

    notion_log(
        f"이유 보고: {날짜} {분만사} 자돈{자돈}두",
        "✅ 완료",
        비고=sender
    )


# ══════════════════════════════════════════════════════════
# A3. /배합취소 — 예약된 배합지시 취소
# ══════════════════════════════════════════════════════════

async def handle_dispatch_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/배합취소 — 노션에서 예약중인 배합지시 조회 후 취소"""
    msg = update.message
    if not msg: return
    if ADMIN_ID and msg.from_user.id != ADMIN_ID:
        await msg.reply_text("⚠️ 대표님만 사용 가능합니다")
        return

    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DISPATCH_SCHEDULE}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {"property": "발송상태", "select": {"equals": "⏰ 예약중"}},
                "sorts":  [{"property": "예약발송일시", "direction": "ascending"}],
                "page_size": 5,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        if not pages:
            await msg.reply_text(
                "📋 현재 예약된 배합지시가 없습니다",
                )
            return

        # 예약 목록 표시
        lines = ["⏰ 예약된 배합지시 목록\n"]
        keys  = []
        for i, page in enumerate(pages, 1):
            props   = page.get("properties", {})
            dt_info = props.get("예약발송일시", {}).get("date", {})
            dt_str  = dt_info.get("start", "") if dt_info else ""
            rt      = props.get("배합지시내용", {}).get("rich_text", [])
            content_preview = rt[0].get("text", {}).get("content", "")[:50] if rt else ""
            page_id = page["id"]

            global _approval_counter
            _approval_counter += 1
            key = str(_approval_counter)
            _approval_store[key] = {
                "type":    "cancel_dispatch",
                "page_id": page_id,
                "dt_str":  dt_str,
                "preview": content_preview,
            }
            keys.append(key)
            lines.append(f"{i}. {dt_str[:16]} | {content_preview[:30]}")

        # 취소 버튼 생성
        kb_rows = []
        for i, key in enumerate(keys, 1):
            page = pages[i-1]
            props = page.get("properties", {})
            dt_info = props.get("예약발송일시", {}).get("date", {})
            dt_str = dt_info.get("start", "")[:10] if dt_info else ""
            kb_rows.append([
                InlineKeyboardButton(
                    f"❌ {i}번 취소 ({dt_str})",
                    callback_data=f"cancel_dispatch|{key}"
                )
            ])

        await msg.reply_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(kb_rows))

    except Exception as e:
        logger.error(f"배합취소 조회 오류: {e}")
        await msg.reply_text(f"⚠️ 조회 오류: {e}")


# ══════════════════════════════════════════════════════════
# B1. 폐사 일일 보고서 — 매일 오후 6시 자동 집계
# ══════════════════════════════════════════════════════════

async def daily_death_report(ctx: ContextTypes.DEFAULT_TYPE):
    """매일 오후 6시 — 오늘 폐사 집계 → 대표님 DM"""
    if not ADMIN_ID:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DEATH}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "date:폐사일자:start" if False else "폐사일자",
                    "date": {"equals": today}
                },
                "page_size": 50,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        total = 0
        barn_counts: dict = {}
        for page in pages:
            props = page.get("properties", {})
            # 두수
            cnt_prop = props.get("폐사두수", {})
            cnt = int(cnt_prop.get("number", 1) or 1)
            total += cnt
            # 위치
            loc_rt = props.get("돈방위치", {}).get("rich_text", [])
            loc = loc_rt[0].get("text", {}).get("content", "미상")[:5] if loc_rt else "미상"
            barn_counts[loc] = barn_counts.get(loc, 0) + cnt

        # 집계 메시지
        if total == 0:
            dm_text = f"🐷 오늘({today}) 폐사 없음 ✅"
        else:
            barn_lines = "\n".join(
                f"  {loc}: {cnt}두"
                for loc, cnt in sorted(barn_counts.items())
            )
            dm_text = (
                f"💀 일일 폐사 보고 ({today})\n"
                f"총 폐사: {total}두\n\n"
                f"위치별:\n{barn_lines}"
            )

        await ctx.bot.send_message(ADMIN_ID, dm_text)
        notion_log(f"일일폐사보고: {total}두", "✅ 완료", 비고=today)
        logger.info(f"일일 폐사 보고 발송: {total}두")

    except Exception as e:
        logger.error(f"일일 폐사 보고 오류: {e}")
        await ctx.bot.send_message(ADMIN_ID, f"⚠️ 폐사 보고 오류: {e}")


# ══════════════════════════════════════════════════════════
# B2. 사료 입고 확인 알림 — 배합지시 당일 오전 8시
# ══════════════════════════════════════════════════════════

async def feed_arrival_check(ctx: ContextTypes.DEFAULT_TYPE):
    """매일 오전 8시 — 오늘 입고 예정 배합지시 확인 요청"""
    if not ADMIN_ID:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DISPATCH_SCHEDULE}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "발송상태", "select": {"equals": "✅ 발송완료"}},
                        {"property": "예약발송일시", "date": {"equals": today + "T07:00:00"}},
                    ]
                },
                "page_size": 5,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        if not pages:
            return  # 오늘 발송된 배합지시 없으면 스킵

        for page in pages:
            rt = page.get("properties", {}).get("배합지시내용", {}).get("rich_text", [])
            content_preview = rt[0].get("text", {}).get("content", "")[:100] if rt else ""

            # 단체방에 입고 확인 요청
            gid = ctx.bot_data.get("main_group_id", 0)
            if gid:
                await ctx.bot.send_message(gid,
                    f"📦 오늘 사료 입고 예정\n\n"
                    f"{content_preview}\n\n"
                    f"입고 완료 시 '입고완료' 또는 '입고됐어요' 입력해주세요")
    except Exception as e:
        logger.error(f"입고 확인 알림 오류: {e}")


# ══════════════════════════════════════════════════════════
# B3. 주간 요약 보고 — 매주 금요일 오후 5시
# ══════════════════════════════════════════════════════════

async def weekly_summary_report(ctx: ContextTypes.DEFAULT_TYPE):
    """매주 금요일 오후 5시 — 주간 요약 → 대표님 DM"""
    if not ADMIN_ID:
        return

    from datetime import timedelta
    now   = datetime.now()
    start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")

    summary_lines = [f"📊 주간 요약 ({start} ~ {end})\n"]

    # 폐사 집계
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DEATH}/query",
            headers=NOTION_HEADERS,
            json={"filter": {
                "property": "폐사일자",
                "date": {"on_or_after": start}
            }, "page_size": 100},
            timeout=8,
        )
        pages = res.json().get("results", [])
        total_death = sum(
            int(p.get("properties", {}).get("폐사두수", {}).get("number", 1) or 1)
            for p in pages
        )
        summary_lines.append(f"💀 폐사: {total_death}두")
    except: summary_lines.append("💀 폐사: 조회 오류")

    # 이유 집계
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_WEANING}/query",
            headers=NOTION_HEADERS,
            json={"filter": {
                "property": "이유날짜",
                "date": {"on_or_after": start}
            }, "page_size": 20},
            timeout=8,
        )
        pages = res.json().get("results", [])
        total_weaning = sum(
            int(p.get("properties", {}).get("자돈두수", {}).get("number", 0) or 0)
            for p in pages
        )
        summary_lines.append(f"🐷 이유: {total_weaning}두 ({len(pages)}회)")
    except: summary_lines.append("🐷 이유: 조회 오류")

    # 사료 주문 횟수
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ORDER}/query",
            headers=NOTION_HEADERS,
            json={"filter": {
                "and": [
                    {"property": "주문유형", "select": {"equals": "🌾 사료"}},
                    {"property": "주문날짜", "date": {"on_or_after": start}},
                ]
            }, "page_size": 30},
            timeout=8,
        )
        pages = res.json().get("results", [])
        summary_lines.append(f"🌾 사료주문: {len(pages)}회")
    except: summary_lines.append("🌾 사료주문: 조회 오류")

    # 휴무 현황
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_VACATION}/query",
            headers=NOTION_HEADERS,
            json={"filter": {
                "property": "확정날짜",
                "date": {"on_or_after": start}
            }, "page_size": 20},
            timeout=8,
        )
        pages = res.json().get("results", [])
        if pages:
            vacation_lines = []
            for p in pages:
                props = p.get("properties", {})
                name = props.get("직원명", {}).get("select", {}).get("name", "")
                d = props.get("확정날짜", {}).get("date", {})
                date = d.get("start", "")[:10] if d else ""
                if name: vacation_lines.append(f"{name}({date})")
            summary_lines.append(f"🏖️ 휴무: " + ", ".join(vacation_lines))
        else:
            summary_lines.append("🏖️ 휴무: 없음")
    except: summary_lines.append("🏖️ 휴무: 조회 오류")

    await ctx.bot.send_message(ADMIN_ID, "\n".join(summary_lines))
    logger.info("주간 요약 보고 발송")


# ══════════════════════════════════════════════════════════
# C1. /상태 명령어 — 봇 현황 한눈에
# ══════════════════════════════════════════════════════════

async def handle_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/상태 — 봇 현황, 예약발송, 오늘 폐사 등 표시"""
    msg = update.message
    if not msg: return
    if ADMIN_ID and msg.from_user.id != ADMIN_ID:
        await msg.reply_text("⚠️ 대표님만 사용 가능합니다")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    lines = ["🐷 도방육종 봇 상태\n"]

    # 약품 캐시
    if _medicine_cache:
        lines.append(f"💊 약품캐시: {len(_medicine_cache)}종류 로드")
    else:
        lines.append("💊 약품캐시: ⚠️ 미로드")

    # 예약 배합지시
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DISPATCH_SCHEDULE}/query",
            headers=NOTION_HEADERS,
            json={"filter": {"property": "발송상태", "select": {"equals": "⏰ 예약중"}},
                  "page_size": 5},
            timeout=5,
        )
        sched_pages = res.json().get("results", [])
        if sched_pages:
            sched_items = []
            for p in sched_pages:
                d = p.get("properties", {}).get("예약발송일시", {}).get("date", {})
                dt = d.get("start", "")[:16] if d else ""
                sched_items.append(dt)
            lines.append(f"⏰ 예약발송: {len(sched_pages)}건 ({', '.join(sched_items)})")
        else:
            lines.append("⏰ 예약발송: 없음")
    except:
        lines.append("⏰ 예약발송: 조회 오류")

    # 오늘 폐사
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_DEATH}/query",
            headers=NOTION_HEADERS,
            json={"filter": {"property": "폐사일자", "date": {"equals": today}},
                  "page_size": 20},
            timeout=5,
        )
        death_pages = res.json().get("results", [])
        total_death = sum(
            int(p.get("properties", {}).get("폐사두수", {}).get("number", 1) or 1)
            for p in death_pages
        )
        lines.append(f"💀 오늘 폐사: {total_death}두 ({len(death_pages)}건)")
    except:
        lines.append("💀 오늘 폐사: 조회 오류")

    # weaning_session 여부
    if ctx.bot_data.get("weaning_session"):
        ws = ctx.bot_data["weaning_session"]
        lines.append(
            f"🐷 이유세션: 진행중 ({ws.get('분만사','?')}, "
            f"{ws.get('started_at','?')})"
        )
    else:
        lines.append("🐷 이유세션: 없음")

    # 봇 가동 시각
    lines.append(f"\n실행시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    await msg.reply_text("\n".join(lines))


# ══════════════════════════════════════════════════════════
# C2. /이유통계 — 이번 달 이유 현황
# ══════════════════════════════════════════════════════════

async def handle_weaning_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/이유통계 — 이번 달 이유 집계"""
    msg = update.message
    if not msg: return

    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"
    lines = [f"🐷 이유 통계 ({now.month}월)\n"]

    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_WEANING}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "이유날짜",
                    "date": {"on_or_after": month_start}
                },
                "page_size": 50,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        if not pages:
            await msg.reply_text(f"🐷 {now.month}월 이유 기록 없음")
            return

        total_piglets = 0
        total_sows    = 0
        barn_counts: dict = {}
        일령_list: list = []
        산차_list: list = []

        for p in pages:
            props = p.get("properties", {})
            piglets = props.get("자돈두수", {}).get("number", 0) or 0
            sows    = props.get("모돈두수", {}).get("number", 0) or 0
            barn_sel = props.get("분만사", {}).get("select", {})
            barn    = barn_sel.get("name", "미상") if barn_sel else "미상"
            일령    = props.get("평균일령", {}).get("number", 0) or 0
            산차    = props.get("평균산차", {}).get("number", 0) or 0

            total_piglets += piglets
            total_sows    += sows
            barn_counts[barn] = barn_counts.get(barn, 0) + 1
            if 일령 > 0: 일령_list.append(일령)
            if 산차 > 0: 산차_list.append(산차)

        avg_piglets = round(total_piglets / len(pages), 1) if pages else 0
        avg_일령    = round(sum(일령_list) / len(일령_list), 1) if 일령_list else 0
        avg_산차    = round(sum(산차_list) / len(산차_list), 1) if 산차_list else 0

        lines.append(f"총 이유: {len(pages)}회 / {total_piglets}두")
        lines.append(f"평균 이유두수: {avg_piglets}두/회")
        if avg_일령: lines.append(f"평균 이유일령: {avg_일령}일")
        if avg_산차: lines.append(f"평균 산차: {avg_산차}산")
        lines.append("")
        lines.append("분만사별:")
        for barn, cnt in sorted(barn_counts.items()):
            lines.append(f"  {barn}: {cnt}회")

        await msg.reply_text("\n".join(lines))

    except Exception as e:
        await msg.reply_text(f"⚠️ 조회 오류: {e}")


# ══════════════════════════════════════════════════════════
# B4. 임신진단 자동 처리
# ══════════════════════════════════════════════════════════

NOTION_DB_PREGNANCY = "998594cd-f307-4a6f-a92f-d0a3bddee167"
async def handle_pregnancy_report(msg, text: str, sender: str, ctx):
    """임신진단 메시지 → 노션 저장 + 예정일 계산"""
    import re as _re
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 두수 파싱
    m = _re.search(r"(\d+)\s*(?:두|복|마리)", text)
    count = int(m.group(1)) if m else 0

    # 결과 파싱
    result = "미상"
    if any(k in text for k in ["양성", "임신확인", "임신됨"]): result = "양성"
    elif any(k in text for k in ["음성", "임신아님", "미임신"]): result = "음성"
    elif any(k in text for k in ["재발정", "발정재귀"]): result = "재발정"

    # 분만 예정일 (임신 114일)
    from datetime import timedelta
    due_date = (now + timedelta(days=114)).strftime("%Y-%m-%d")

    try:
        requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DB_PREGNANCY},
                "properties": {
                    "Name": {"title": [{"text": {"content":
                        f"임신진단 {today} {result}"}}]},
                    "date:진단일자:start":       today,
                    "date:진단일자:is_datetime": 0,
                    "진단결과":   {"select": {"name": result}},
                    "두수":       {"number": count},
                    "보고자":     {"rich_text": [{"text": {"content": sender}}]},
                    "원본내용":   {"rich_text": [{"text": {"content": text[:200]}}]},
                }
            },
            timeout=8,
        )
        logger.info(f"임신진단 저장: {today} {result} {count}두")
    except Exception as e:
        logger.error(f"임신진단 노션 저장 오류: {e}")

    await msg.reply_text(
        f"🐷 임신진단 기록\n결과: {result}\n두수: {count}두\n"
        f"(분만예정: {due_date})",
        )


# ══════════════════════════════════════════════════════════
# C3. /현황 — 오늘 직원별 업무 현황
# ══════════════════════════════════════════════════════════

async def handle_staff_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/현황 — 오늘 각 직원 보고 현황"""
    msg = update.message
    if not msg: return

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"👥 직원 현황 ({datetime.now().strftime('%m/%d')})\n"]

    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_LOG}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "date:날짜:start" if False else "날짜",
                    "date": {"equals": today}
                },
                "page_size": 100,
            },
            timeout=8,
        )
        pages = res.json().get("results", [])

        # 직원별 보고 카운트
        staff_reports: dict = {}
        for p in pages:
            props = p.get("properties", {})
            비고 = props.get("비고", {}).get("rich_text", [])
            비고_text = 비고[0].get("text", {}).get("content", "") if 비고 else ""
            for staff in ["콰", "썬", "츠엉", "하우", "박태식", "동", "신기철"]:
                if staff in 비고_text:
                    staff_reports[staff] = staff_reports.get(staff, 0) + 1

        # 전체 직원 목록
        ALL_STAFF = ["콰", "썬", "츠엉", "하우", "박태식", "동"]
        for staff in ALL_STAFF:
            cnt = staff_reports.get(staff, 0)
            icon = "✅" if cnt >= 3 else ("⚠️" if cnt >= 1 else "❌")
            lines.append(f"  {icon} {staff}: {cnt}건")

        if not pages:
            lines.append("오늘 보고 기록 없음")

    except Exception as e:
        lines.append(f"조회 오류: {e}")

    await msg.reply_text("\n".join(lines))


# ══════════════════════════════════════════════════════════
# C4. 다국어 응답 — 외국인 직원 자동 감지
# ══════════════════════════════════════════════════════════

# 외국인 직원 이름 (베트남어 병기 대상)
FOREIGN_STAFF = ["콰", "츠엉", "하우", "kwa", "truong", "hau"]

# 핵심 메시지 베트남어 대역
VI_TRANSLATIONS = {
    "휴무 확정":           "Nghỉ phép đã được xác nhận",
    "휴무 반려":           "Nghỉ phép bị từ chối",
    "휴무 신청 접수":      "Đơn xin nghỉ phép đã được tiếp nhận",
    "이유 보고 접수":      "Báo cáo cai sữa đã được tiếp nhận",
    "작업지시":            "Chỉ thị công việc",
    "사료 배합지시":       "Hướng dẫn phối trộn thức ăn",
    "오늘 입고 예정":      "Dự kiến nhập hàng hôm nay",
    "배합 완료 부탁드립니다": "Vui lòng hoàn thành phối trộn",
}

def add_vietnamese(text: str, staff_name: str) -> str:
    """외국인 직원 대상 메시지에 베트남어 병기 추가"""
    is_foreign = any(k in staff_name for k in FOREIGN_STAFF)
    if not is_foreign:
        return text
    for ko, vi in VI_TRANSLATIONS.items():
        if ko in text:
            text = text + f"\n({vi})"
            break
    return text


async def run_bot():
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN 없음")
        return
    logger.info("🐷 도방육종 봇 시작! v4.0 (사진판독 통합버전)")
    # 약품 캐시 사전 로드 (런타임에 호출 — 정의 위치 무관)
    try:
        load_medicine_cache()
        logger.info(f"💊 약품 캐시 로드: {list(_medicine_cache.keys())}")
    except NameError:
        logger.warning("load_medicine_cache 미정의 — 스킵")
    except Exception as e:
        logger.error(f"약품 캐시 로드 오류: {e}")

    # 미발송 예약 복원
    try:
        asyncio.create_task(restore_scheduled_dispatches(app))
    except NameError:
        logger.warning("restore_scheduled_dispatches 미정의 — 스킵")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("m", show_menu))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    # 수정후승인 명령어 핸들러 (패턴: /modify_숫자)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/modify_\w+"), handle_modify_command))
    # 배합지시 변경/추가/재발송
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/(변경|추가|재발송)"), handle_dispatch_change))
    # 배합지시 변경_키 / 추가_키
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/(변경|추가)_\w+"), handle_dispatch_change_key))
    # 휴무 날짜변경 제안 (다양한 날짜 형식)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/date_\w+"), handle_date_suggest_command))

    app.add_handler(CommandHandler("update_bot", handle_update_command))
    app.add_handler(CommandHandler("update", handle_update_command))
    # A3. 배합취소
    app.add_handler(CommandHandler("cancel_dispatch", handle_dispatch_cancel))
    # C1. 상태 확인
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("status", handle_status))
    # C2. 이유 통계
    app.add_handler(CommandHandler("weaning_stats", handle_weaning_stats))
    # C3. 직원 현황
    app.add_handler(CommandHandler("staff_status", handle_staff_status))

    if ADMIN_ID and app.job_queue:
        import datetime as dt
        # 기존: 일일 보고 07:00
        app.job_queue.run_daily(daily_report, time=dt.time(7, 0, 0))
        logger.info("📊 일일 보고 07:00 등록")
        # B1. 폐사 일일 보고 18:00
        app.job_queue.run_daily(daily_death_report, time=dt.time(19, 30, 0))
        logger.info("💀 폐사 일일 보고 19:30 등록")
        # B2. 사료 입고 확인 08:00
        app.job_queue.run_daily(feed_arrival_check, time=dt.time(8, 0, 0))
        logger.info("📦 입고 확인 08:00 등록")
        # B3. 주간 요약 금요일 17:00
        app.job_queue.run_daily(
            weekly_summary_report,
            time=dt.time(17, 0, 0),
            days=(4,)  # 금요일=4
        )
        logger.info("📊 주간 요약 금요일 17:00 등록")

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ 봇 폴링 시작! (명령어: /menu /status /cancel_dispatch /weaning_stats /staff_status /update_bot)")
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    import sys
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n⛔ 봇 종료")
        sys.exit(0)
    except RuntimeError as e:
        if "This Application is still running" in str(e):
            print("⚠️ 이전 봇이 아직 실행 중입니다. 잠시 후 다시 시도하세요.")
        else:
            raise

# ══════════════════════════════════════════════════════════