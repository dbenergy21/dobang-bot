"""
도방육종 업무봇 v6.1
- 약품 주문 전용 처리 + 주문 문자 DM
- 사료없어요 폐사 오인식 수정
- 텔레그램 업데이트 버튼 (대표님 전용)
"""
import os, logging, requests, asyncio, re, json, time, sys, subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()
TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
ADMIN_ID     = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
BOT_DIR      = os.path.dirname(os.path.abspath(__file__))

NOTION_DB_SHIPOUT  = "399eb8a5-ba53-4754-85bb-63828f75f6a6"
NOTION_DB_LOG      = "1b6d6904-aed1-46e8-b378-0de23d614e10"
NOTION_DB_VACATION = "82299f8a-772f-4bac-b470-470c2aa1b170"
NOTION_DB_ORDER    = "c8ce6eac-dae2-429a-aa73-e43c63fe6704"
NOTION_DB_WEANING  = "877cf48e-e04f-40b9-92d3-3069ac02fa1f"
NOTION_DB_GROUP    = "3341d244-3b59-442e-bc9e-b7f124c4f31a"

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("출하 보고"),  KeyboardButton("폐사 보고")],
    [KeyboardButton("이상 보고"),  KeyboardButton("작업 완료")],
    [KeyboardButton("휴무 신청"),  KeyboardButton("사료 주문")],
    [KeyboardButton("약품 주문"),  KeyboardButton("소모품 주문")],
], resize_keyboard=True, is_persistent=True)

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ============================================================
# callback_data 저장소 (64바이트 제한 해결)
# ============================================================
_pending = {}

def _short_id(prefix="x"):
    return f"{prefix}{str(int(time.time()*1000))[-7:]}"

def make_kb(action_type, data):
    sid = _short_id(action_type[0])
    _pending[sid] = {"type": action_type, **data}
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("승인", callback_data=f"apv_{sid}"),
        InlineKeyboardButton("반려", callback_data=f"rej_{sid}"),
    ]])

def make_kb3(action_type, data):
    sid = _short_id(action_type[0])
    _pending[sid] = {"type": action_type, **data}
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("승인", callback_data=f"apv_{sid}"),
        InlineKeyboardButton("수정후승인", callback_data=f"mod_{sid}"),
        InlineKeyboardButton("반려", callback_data=f"rej_{sid}"),
    ]])

# ============================================================
# 업데이트 기능 (대표님 전용)
# ============================================================
async def do_update(msg_or_query, ctx):
    """git pull + 봇 재시작"""
    is_query = hasattr(msg_or_query, 'edit_message_text')
    
    async def reply(text):
        if is_query:
            try: await msg_or_query.edit_message_text(text)
            except: pass
        else:
            await msg_or_query.reply_text(text)

    await reply("업데이트 확인 중...")
    
    try:
        # git fetch로 변경 확인
        fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=15
        )
        
        local  = subprocess.run(["git", "rev-parse", "HEAD"],          cwd=BOT_DIR, capture_output=True, text=True).stdout.strip()
        remote = subprocess.run(["git", "rev-parse", "origin/main"],   cwd=BOT_DIR, capture_output=True, text=True).stdout.strip()
        
        if local == remote:
            await reply("이미 최신 버전입니다.\n업데이트 없음.")
            return
        
        # git pull
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=30
        )
        
        if pull.returncode != 0:
            await reply(f"업데이트 실패\n{pull.stderr[:100]}")
            return
        
        await reply("업데이트 완료!\n3초 후 재시작합니다...")
        await asyncio.sleep(3)
        
        # 봇 재시작
        os.execv(sys.executable, [sys.executable] + sys.argv)
        
    except Exception as e:
        await reply(f"오류: {str(e)[:80]}")

# ============================================================
# 분류 엔진 v2 (맥락 기반)
# ============================================================
FEED_ISSUE_KW = [
    "사료없", "사료 없", "사료많", "사료 많", "사료부족",
    "사료없어요", "사료많아요", "급수안", "급수 안", "급수없",
    "물없", "단수", "사료떨어", "빈통",
]
FACILITY_KW = [
    "고장", "누수", "화재", "연기", "경보", "알람",
    "작동안", "멈췄", "오작동", "파손", "파열",
    "모터", "펌프", "보일러", "환기",
]
DEATH_WORDS  = ["폐사", "죽었", "사망", "죽음", "절명", "chết"]
SHIPOUT_KW   = ["출하", "xuất", "나갔", "나감"]
DONE_KW      = ["완료", "끝", "done", "finish", "마무리", "했습니다"]
VACATION_KW  = ["휴무", "휴가", "쉬겠", "쉴게", "nghỉ"]
MEDICINE_KW  = [
    "약품", "백신", "주사", "항생제", "써코", "마이코",
    "타이신", "암피실린", "린코마이신", "아목시", "엔로",
    "진프로", "서울린코", "서울아목", "토탈멕", "골든펜다",
    "파마신", "티아싸이클린", "인섹트밸런스",
    "약품 주문", "백신 주문",
]
SUPPLY_KW    = ["소모품", "장갑", "마스크", "비닐", "주사기", "세제"]

def classify(text):
    t = text.lower().strip()
    if any(k in t for k in FEED_ISSUE_KW):
        return ("feed_issue", {})
    if any(k in t for k in FACILITY_KW):
        return ("issue", {})
    if any(k in t for k in DEATH_WORDS):
        nums = re.findall(r"\d+", text)
        loc  = re.search(r"[A-Za-z가-힣]+\d+[\-\.]?\d*|돈공\d*", text)
        return ("death", {"두수": nums[0] if nums else "미상", "위치": loc.group() if loc else ""})
    location_count = re.findall(r"([A-Za-z가-힣]+[\d]+[\-\.\s]+[\d]*)\s*[\.\s]+(\d+)", text)
    if location_count and not any(k in t for k in ["사료","이상","완료","쉬","주문","출하","휴무"]):
        total = sum(int(c) for _, c in location_count)
        locs  = [l.strip() for l, _ in location_count]
        return ("death_auto", {"두수": str(total), "위치": ", ".join(locs), "원문": text})
    if any(k in t for k in SHIPOUT_KW):
        nums = re.findall(r"\d+", text)
        return ("shipout", {"두수": int(nums[0]) if nums else 0})
    if any(k in t for k in MEDICINE_KW):
        return ("order_medicine", {})
    if any(k in t for k in SUPPLY_KW):
        return ("order_supply", {})
    if any(k in t for k in ["사료", "feed", "급이"]):
        return ("order_feed", {})
    if any(k in t for k in VACATION_KW):
        return ("vacation", {"날짜": parse_date(text)})
    if any(k in t for k in DONE_KW):
        return ("done", {})
    return ("general", {})

def parse_date(text):
    now = datetime.now()
    m = re.search(r"(\d{1,2})[/월](\d{1,2})", text)
    if m: return f"{now.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})일", text)
    if m: return f"{now.year}-{now.month:02d}-{int(m.group(1)):02d}"
    return None

STAFF_MAP = {
    "콰":"콰","kwa":"콰","qua":"콰","haukaka":"콰",
    "썬":"썬","sun":"썬","jay":"썬",
    "츠엉":"츠엉","truong":"츠엉",
    "하우":"하우","hau":"하우",
    "박태식":"박태식","태식":"박태식","신기철":"박태식",
    "동":"동","dong":"동",
}
def get_staff(name):
    n = name.lower()
    for k,v in STAFF_MAP.items():
        if k in n: return v
    return name

# ============================================================
# 노션 함수
# ============================================================
def n_log(업무, 상태, 비고=""):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json={
            "parent": {"database_id": NOTION_DB_LOG},
            "properties": {
                "Name":    {"title": [{"text": {"content": f"{today} {업무[:20]}"}}]},
                "날짜":     {"date": {"start": today}},
                "업무내용": {"rich_text": [{"text": {"content": 업무}}]},
                "회사":     {"select": {"name": "도방육종"}},
                "수행여부": {"select": {"name": 상태}},
                "보고자":   {"select": {"name": "도비"}},
                "비고":     {"rich_text": [{"text": {"content": 비고}}]},
            }}, timeout=10)
    except Exception as e: logger.error(f"노션 로그: {e}")

def n_shipout(두수, 비고=""):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json={
            "parent": {"database_id": NOTION_DB_SHIPOUT},
            "properties": {
                "Name":    {"title": [{"text": {"content": f"{today} 출하 {두수}두"}}]},
                "날짜":     {"date": {"start": today}},
                "출하두수": {"number": 두수},
                "확인자":   {"select": {"name": "도비"}},
                "메모":     {"rich_text": [{"text": {"content": 비고}}]},
            }}, timeout=10)
    except Exception as e: logger.error(f"출하 노션: {e}")

def n_order(직원, 유형, 품목):
    if not NOTION_TOKEN: return
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json={
            "parent": {"database_id": NOTION_DB_ORDER},
            "properties": {
                "Name":     {"title": [{"text": {"content": f"{today} {유형} {품목[:15]}"}}]},
                "date:주문날짜:start": today, "date:주문날짜:is_datetime": 0,
                "직원명":   {"select": {"name": 직원}},
                "주문유형": {"select": {"name": 유형}},
                "품목":     {"rich_text": [{"text": {"content": 품목}}]},
                "상태":     {"select": {"name": "접수"}},
            }}, timeout=10)
    except Exception as e: logger.error(f"주문 노션: {e}")

def n_vacation_create(직원, 날짜):
    if not NOTION_TOKEN: return ""
    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now()
    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json={
            "parent": {"database_id": NOTION_DB_VACATION},
            "properties": {
                "Name":   {"title": [{"text": {"content": f"{직원} 휴무신청 {날짜}"}}]},
                "직원명":  {"select": {"name": 직원}},
                "date:신청일:start": today, "date:신청일:is_datetime": 0,
                "date:희망날짜:start": 날짜, "date:희망날짜:is_datetime": 0,
                "상태":    {"select": {"name": "대기중"}},
                "소스":    {"select": {"name": "텔레그램"}},
                "월":      {"number": now.month},
            }}, timeout=10)
        return res.json().get("id", "")
    except Exception as e:
        logger.error(f"휴무 노션: {e}")
        return ""

def n_vacation_update(page_id, 상태):
    if not NOTION_TOKEN or not page_id: return
    try:
        requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": {"상태": {"select": {"name": 상태}}}},
            timeout=10)
    except Exception as e: logger.error(f"휴무 업데이트: {e}")

# ============================================================
# 약품 주문 파싱 + 주문 문자 생성
# ============================================================
def parse_medicine_items(text):
    items = []
    lines = re.split(r"[,\n、]", text)
    for line in lines:
        line = line.strip()
        if not line: continue
        m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s*(kg|g|병|박스|포|개|ml|L|통)?", line)
        if m:
            items.append({"품목": m.group(1).strip(), "수량": m.group(2), "단위": m.group(3) or "개"})
        else:
            items.append({"품목": line, "수량": "1", "단위": "개"})
    return items

def format_medicine_sms(items, staff, today):
    lines = [f"[약품 주문] {today} ({staff})", "-"*20]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['품목']} {item['수량']}{item['단위']}")
    lines += ["-"*20, f"총 {len(items)}품목"]
    return "\n".join(lines)

# ============================================================
# 콜백 핸들러
# ============================================================
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # 업데이트 확인 버튼
    if data == "do_update":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("대표님만 사용 가능합니다.")
            return
        await do_update(query, ctx)
        return

    if data.startswith("apv_") or data.startswith("rej_") or data.startswith("mod_"):
        action = "approve" if data.startswith("apv_") else ("modify" if data.startswith("mod_") else "reject")
        sid     = data[4:]
        payload = _pending.pop(sid, None) if action != "modify" else _pending.get(sid)
        if not payload:
            await query.edit_message_text("처리 기한 만료. 다시 신청해주세요.")
            return

        atype  = payload.get("type")
        staff  = payload.get("staff", "")
        gid    = payload.get("group_id", 0)

        if atype == "vacation":
            날짜 = payload.get("date", "")
            pid  = payload.get("page_id", "")
            if action == "approve":
                n_vacation_update(pid, "확정")
                n_log(f"휴무 승인: {staff} {날짜}", "완료", 비고="대표님 승인")
                await query.edit_message_text(f"휴무 승인\n직원: {staff}\n날짜: {날짜}")
                if gid: await ctx.bot.send_message(gid, f"휴무 승인\n{staff}님 {날짜} 확정")
            else:
                n_vacation_update(pid, "반려")
                await query.edit_message_text(f"휴무 반려\n직원: {staff}\n날짜: {날짜}")
                if gid: await ctx.bot.send_message(gid, f"휴무 반려\n{staff}님 신청 반려")

        elif atype == "order":
            유형    = payload.get("order_type", "")
            content = payload.get("content", "")
            if action == "approve":
                n_log(f"{유형} 주문 승인: {content}", "완료", 비고=f"승인 {staff}")
                await query.edit_message_text(f"주문 승인\n{유형} {staff}\n{content}")
                if gid: await ctx.bot.send_message(gid, f"{유형} 주문 승인\n{staff}님 처리됩니다")
            else:
                await query.edit_message_text(f"주문 반려\n{유형} {staff}")
                if gid: await ctx.bot.send_message(gid, f"{유형} 주문 반려")

        elif atype == "medicine":
            content = payload.get("content", "")
            items   = payload.get("items", [])
            if action == "approve":
                today = datetime.now().strftime("%Y-%m-%d")
                sms   = format_medicine_sms(items, staff, today)
                n_log(f"약품 주문 승인: {content[:40]}", "완료", 비고=f"승인 {staff}")
                await query.edit_message_text(f"약품 주문 승인\n\n{sms}")
                if gid: await ctx.bot.send_message(gid, f"약품 주문 승인\n{staff}님\n\n{sms}")
            else:
                await query.edit_message_text(f"약품 주문 반려\n{staff}")
                if gid: await ctx.bot.send_message(gid, f"약품 주문 반려\n{staff}님")

# ============================================================
# 일일 보고 07:00
# ============================================================
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

    death_list, order_list, other_list = [], [], []
    for r in results:
        props = r.get("properties", {})
        업무  = props.get("업무내용", {}).get("rich_text", [{}])
        업무  = 업무[0].get("text", {}).get("content", "") if 업무 else ""
        if "폐사" in 업무: death_list.append(업무[:40])
        elif "주문" in 업무: order_list.append(업무[:40])
        else: other_list.append(업무[:30])

    lines = [f"도비 일일 보고 ({yesterday})", f"총 {len(results)}건"]
    if death_list:
        lines.append(f"\n폐사 {len(death_list)}건")
        for d in death_list: lines.append(f"  {d}")
    if order_list:
        lines.append(f"\n주문 {len(order_list)}건")
        for o in order_list: lines.append(f"  {o}")
    if not results:
        lines = [f"도비 일일 보고 ({yesterday})\n보고 없음"]
    await ctx.bot.send_message(chat_id=ADMIN_ID, text="\n".join(lines))

# ============================================================
# start
# ============================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "도방육종 업무봇 v6.1\n버튼으로 보고하거나 텍스트로 입력하세요",
        reply_markup=MAIN_KEYBOARD)

# ============================================================
# 업데이트 명령어 (대표님 전용)
# ============================================================
async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("업데이트 실행", callback_data="do_update")
    ]])
    await update.message.reply_text("최신 버전으로 업데이트하시겠습니까?", reply_markup=kb)

# ============================================================
# 약품 주문 처리
# ============================================================
async def process_medicine_order(msg, staff, name, text, group_id, ctx):
    items = parse_medicine_items(text)
    today = datetime.now().strftime("%Y-%m-%d")
    for item in items:
        n_order(staff, "약품", f"{item['품목']} {item['수량']}{item['단위']}")
    n_log(f"약품 주문: {text[:60]}", "완료", 비고=name)
    sms = format_medicine_sms(items, staff, today)
    await msg.reply_text(
        f"약품 주문 접수 ({len(items)}품목)\n\n{sms}\n\n대표님 승인 대기중...",
        reply_markup=MAIN_KEYBOARD)
    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID,
            f"약품 주문 접수\n직원: {staff}\n\n{sms}",
            reply_markup=make_kb3("medicine", {
                "staff": staff, "content": text[:60],
                "items": items, "group_id": group_id,
            }))

# ============================================================
# 메인 메시지 핸들러
# ============================================================
BUTTONS = {
    "출하 보고":   ("shipout",       "몇 두 출하했나요?"),
    "폐사 보고":   ("death",         "두수+위치 입력\n예) 돈공1.2 2두"),
    "이상 보고":   ("issue",         "이상 내용 입력"),
    "휴무 신청":   ("vacation",      "희망 날짜 입력\n예) 4/15"),
    "사료 주문":   ("order_feed",    "품목+수량 입력"),
    "약품 주문":   ("order_medicine","약품명+수량 입력\n예) 써코백신 10병, 진프로 2kg"),
    "소모품 주문": ("order_supply",  "품목+수량 입력"),
}
ORDER_MAP = {"order_feed": "사료", "order_supply": "소모품"}

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.is_bot: return
    text     = msg.text or ""
    name     = msg.from_user.full_name
    staff    = get_staff(name)
    mode     = ctx.user_data.get("mode")
    group_id = msg.chat_id

    if text == "작업 완료":
        n_log(f"작업완료 {staff}", "완료", 비고=name)
        await msg.reply_text(f"수고하셨습니다 {name}님!", reply_markup=MAIN_KEYBOARD)
        ctx.user_data["mode"] = None
        return

    if text in BUTTONS:
        m, prompt = BUTTONS[text]
        ctx.user_data.update({"mode": m, "group_id": group_id, "staff": staff})
        await msg.reply_text(prompt, reply_markup=MAIN_KEYBOARD)
        return

    if mode == "shipout":
        try:
            두수 = int(re.sub(r"[^0-9]", "", text) or "0")
            if 두수 == 0: raise ValueError
            n_shipout(두수, name)
            n_log(f"출하 {두수}두", "완료", 비고=name)
            await msg.reply_text(f"출하 {두수}두 기록!", reply_markup=MAIN_KEYBOARD)
            if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"출하 보고\n{name}\n{두수}두")
            ctx.user_data["mode"] = None
        except:
            await msg.reply_text("숫자만 입력해주세요", reply_markup=MAIN_KEYBOARD)
        return

    if mode == "death":
        n_log(f"폐사: {text}", "완료", 비고=name)
        await msg.reply_text(f"폐사 기록\n{text}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"폐사 보고\n{name}\n{text}")
        ctx.user_data["mode"] = None
        return

    if mode == "issue":
        n_log(f"이상: {text}", "완료", 비고=name)
        await msg.reply_text(f"이상 기록\n{text}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"이상 보고\n{name}\n{text}")
        ctx.user_data["mode"] = None
        return

    if mode == "vacation":
        날짜 = parse_date(text)
        if not 날짜:
            await msg.reply_text("날짜 확인\n예) 4/15", reply_markup=MAIN_KEYBOARD)
            return
        s   = ctx.user_data.get("staff", staff)
        gid = ctx.user_data.get("group_id", group_id)
        pid = n_vacation_create(s, 날짜)
        await msg.reply_text(f"휴무 신청 접수\n{s} / {날짜}\n승인 대기중...", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"휴무 승인 요청\n{s} / {날짜}",
                reply_markup=make_kb("vacation", {"staff": s, "date": 날짜, "page_id": pid, "group_id": gid}))
        ctx.user_data["mode"] = None
        return

    if mode == "order_medicine":
        s   = ctx.user_data.get("staff", staff)
        gid = ctx.user_data.get("group_id", group_id)
        await process_medicine_order(msg, s, name, text, gid, ctx)
        ctx.user_data["mode"] = None
        return

    if mode in ORDER_MAP:
        유형 = ORDER_MAP[mode]
        s   = ctx.user_data.get("staff", staff)
        gid = ctx.user_data.get("group_id", group_id)
        n_order(s, 유형, text)
        n_log(f"{유형} 주문: {text}", "완료", 비고=s)
        await msg.reply_text(f"{유형} 주문 접수\n{text}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"{유형} 주문\n{s}\n{text[:60]}",
                reply_markup=make_kb("order", {"staff": s, "content": text[:60], "order_type": 유형, "group_id": gid}))
        ctx.user_data["mode"] = None
        return

    # 자동 분류
    cat, data = classify(text)
    logger.info(f"자동분류: [{name}] {cat} / {text[:40]}")

    if cat == "feed_issue":
        n_log(f"시설이슈: {text}", "완료", 비고=name)
        await msg.reply_text(f"사료/급수 이슈 기록\n{text}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"사료/급수 이슈\n{name}\n{text}")
    elif cat == "issue":
        n_log(f"이상: {text}", "완료", 비고=name)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"이상 감지\n{name}\n{text}")
    elif cat == "death":
        두수 = data.get("두수", "미상")
        위치 = data.get("위치", "")
        n_log(f"폐사: {text}", "완료", 비고=name)
        await msg.reply_text(f"폐사 기록\n두수:{두수} 위치:{위치 or '미상'}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"폐사 감지\n{name}\n{text}")
    elif cat == "death_auto":
        두수 = data.get("두수", "?")
        위치 = data.get("위치", "")
        원문 = data.get("원문", text)
        n_log(f"폐사(자동): {원문}", "완료", 비고=name)
        await msg.reply_text(f"폐사 자동 기록\n총 {두수}두\n{위치}", reply_markup=MAIN_KEYBOARD)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"폐사 자동 인식\n{name}\n{원문}\n추정: {두수}두 / {위치}")
    elif cat == "shipout":
        두수 = data.get("두수", 0)
        if isinstance(두수, int) and 두수 > 0: n_shipout(두수, name)
        n_log(f"출하: {text}", "완료", 비고=name)
        if ADMIN_ID: await ctx.bot.send_message(ADMIN_ID, f"출하 감지\n{name}\n{text}")
    elif cat == "order_medicine":
        await process_medicine_order(msg, staff, name, text, group_id, ctx)
    elif cat == "order_feed":
        n_order(staff, "사료", text)
        n_log(f"사료 주문: {text}", "완료", 비고=name)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"사료 주문 감지\n{name}\n{text[:60]}",
                reply_markup=make_kb("order", {"staff": staff, "content": text[:60], "order_type": "사료", "group_id": group_id}))
    elif cat == "order_supply":
        n_order(staff, "소모품", text)
        n_log(f"소모품 주문: {text}", "완료", 비고=name)
        if ADMIN_ID:
            await ctx.bot.send_message(ADMIN_ID, f"소모품 주문 감지\n{name}\n{text[:60]}",
                reply_markup=make_kb("order", {"staff": staff, "content": text[:60], "order_type": "소모품", "group_id": group_id}))
    elif cat == "vacation":
        날짜 = data.get("날짜")
        if 날짜:
            pid = n_vacation_create(staff, 날짜)
            await msg.reply_text(f"휴무 신청 접수: {날짜}", reply_markup=MAIN_KEYBOARD)
            if ADMIN_ID:
                await ctx.bot.send_message(ADMIN_ID, f"휴무 승인 요청\n{staff} / {날짜}",
                    reply_markup=make_kb("vacation", {"staff": staff, "date": 날짜, "page_id": pid, "group_id": group_id}))
        else:
            ctx.user_data.update({"mode": "vacation", "group_id": group_id, "staff": staff})
            await msg.reply_text("희망 날짜를 입력해주세요\n예) 4/15", reply_markup=MAIN_KEYBOARD)
    elif cat == "done":
        n_log(f"완료: {text}", "완료", 비고=name)
    else:
        n_log(f"기타: {text}", "완료", 비고=name)

# ============================================================
# 사진 핸들러
# ============================================================
SHIPOUT_NOTE_PROMPT = """This image is a handwritten pig farm shipping instruction note (Samsung Notes drawing).
Extract ALL shipout information visible.

Return ONLY this JSON (no other text):
{
  "locations": [
    {"barn": "barn name or code (e.g. B4, A3, donggong)", "count": number of pigs}
  ],
  "total": total number of pigs,
  "time": "time if visible (e.g. 14:00)",
  "date": "date if visible (e.g. 3/30)",
  "notes": "any other notes",
  "confidence": "high or low"
}

Rules:
- Barn codes: Korean names like donggong/bicuk/jadonsа, or letters+numbers like B4, A3
- Count numbers next to arrows or barn names
- If unclear, use null
- Return valid JSON only"""

async def vision_read_shipout_note(image_bytes: bytes) -> dict:
    import base64, json, re as _re
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 500, "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": SHIPOUT_NOTE_PROMPT}
                ],
            }]},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()
        raw_clean = _re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(raw_clean)
    except Exception as e:
        return {"error": str(e)[:80]}

def n_shipout_note(result: dict, sender: str, date_str: str):
    if not NOTION_TOKEN or result.get("error"): return
    locations = result.get("locations", [])
    total     = result.get("total", 0)
    time_str  = result.get("time", "")
    notes     = result.get("notes", "")
    loc_text  = ", ".join(f"{l.get('barn','?')} {l.get('count','?')}두" for l in locations)
    try:
        n_shipout(total or 0, f"출하지시 사진 판독 ({sender}) {loc_text}")
        n_log(f"출하지시 사진판독: {loc_text} 총{total}두 {time_str}", "완료", 비고=sender)
    except Exception as e:
        logger.error(f"출하노션오류: {e}")

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.is_bot: return
    name     = msg.from_user.full_name
    caption  = msg.caption or ""
    mode     = ctx.user_data.get("mode", "")
    user_id  = msg.from_user.id
    today    = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 이유 현황판 판독 ──
    weaning_kw = ["이유", "현황판", "farmsco", "모돈", "분만사", "산차"]
    if any(k in caption.lower() for k in weaning_kw) or mode == "weaning_photo" or "weaning_session" in ctx.user_data:
        try:
            from weaning_vision import vision_read_card
            if "weaning_session" not in ctx.user_data:
                ctx.user_data["weaning_session"] = {"cards": [], "text_info": {}, "start_time": datetime.now()}
                await msg.reply_text("모돈관리현황판 사진 감지!\n모두 전송 후 판독완료 입력", reply_markup=MAIN_KEYBOARD)
            session = ctx.user_data["weaning_session"]
            idx = len(session["cards"]) + 1
            photo = msg.photo[-1]
            f = await ctx.bot.get_file(photo.file_id)
            img = bytes(await f.download_as_bytearray())
            card = vision_read_card(img)
            session["cards"].append(card)
            if card.get("error"):
                await msg.reply_text(f"{idx}번째 판독 실패", reply_markup=MAIN_KEYBOARD)
            else:
                await msg.reply_text(
                    f"{idx}번째 카드\n산차:{card.get('산차','?')} 일령:{card.get('이유일령','?')} 두수:{card.get('이유두수','?')}",
                    reply_markup=MAIN_KEYBOARD)
        except Exception as e:
            logger.error(f"이유 사진: {e}")
        return

    # ── 2. 대표님 출하지시 사진 판독 (삼성노트 그림) ──
    is_admin_photo = (user_id == ADMIN_ID)
    shipout_kw = ["출하", "ship", "이동", "돈공", "비육"]
    is_shipout_note = (
        is_admin_photo and (
            not caption or
            any(k in caption for k in shipout_kw) or
            mode == "shipout"
        )
    )

    if is_shipout_note:
        await msg.reply_text("출하지시 사진 판독 중...", reply_markup=MAIN_KEYBOARD)
        try:
            photo = msg.photo[-1]
            f = await ctx.bot.get_file(photo.file_id)
            img = bytes(await f.download_as_bytearray())
            result = await vision_read_shipout_note(img)

            if result.get("error"):
                await msg.reply_text(f"판독 실패: {result['error']}\n텍스트로 입력해주세요", reply_markup=MAIN_KEYBOARD)
                return

            locations = result.get("locations", [])
            total     = result.get("total", 0)
            time_str  = result.get("time", "")
            date_str  = result.get("date", today)
            notes     = result.get("notes", "")
            confidence = result.get("confidence", "?")

            loc_lines = "\n".join(f"  {l.get('barn','?')}: {l.get('count','?')}두" for l in locations)
            reply = (
                f"출하지시 판독 완료 ({confidence})\n"
                f"{loc_lines}\n"
                f"합계: {total}두\n"
            )
            if time_str: reply += f"시간: {time_str}\n"
            if notes:    reply += f"메모: {notes}\n"

            await msg.reply_text(reply, reply_markup=MAIN_KEYBOARD)

            # 노션 저장
            n_shipout_note(result, name, today)
            await msg.reply_text("노션 출하 기록 저장 완료!", reply_markup=MAIN_KEYBOARD)

        except Exception as e:
            logger.error(f"출하지시 사진 오류: {e}")
            await msg.reply_text(f"오류: {str(e)[:60]}", reply_markup=MAIN_KEYBOARD)
        return

    # ── 3. 일반 사진 ──
    n_log(f"사진: {caption or '캡션없음'}", "완료", 비고=name)
    if "폐사" in caption and ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID, f"폐사 사진\n{name}\n{caption}")

# ============================================================
# 실행
# ============================================================
async def run_bot():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN 없음")
        return
    logger.info("도방육종 봇 시작 v6.1")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    if ADMIN_ID and app.job_queue:
        import datetime as dt
        app.job_queue.run_daily(daily_report, time=dt.time(7, 0, 0))
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("봇 폴링 시작!")
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(run_bot())
