"""
🌾 도방육종 사료주문 자동 생성 모듈
카카오톡 1년치 데이터 패턴 분석 기반
"""
import re
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 벌크빈 표준 매핑 (노션 사료주문 표준 매뉴얼 기반)
# ══════════════════════════════════════════════════════════
BIN_MAP = {
    # 젖돈(자돈이유후) — 기본 5톤, 상황에 따라 3톤
    '3-1': {'종류': '젖돈', '기본톤수': 5, '대체톤수': 3},
    '4-1': {'종류': '젖돈', '기본톤수': 5, '대체톤수': 3},
    '4-2': {'종류': '젖돈', '기본톤수': 3, '대체톤수': 5},
    '5':   {'종류': '젖돈', '기본톤수': 3, '대체톤수': 5},
    # 육돈(비육) — 기본 5톤, 상황에 따라 3톤
    '7-2': {'종류': '육돈', '기본톤수': 5, '대체톤수': 3},
    '7-3': {'종류': '육돈', '기본톤수': 5, '대체톤수': 3},
    '8-1': {'종류': '육돈', '기본톤수': 5, '대체톤수': 3},
    '8-2': {'종류': '육돈', '기본톤수': 5, '대체톤수': 3},
    # 임신 — 고정 2톤
    '11': {'종류': '임신', '기본톤수': 2},
    '12': {'종류': '임신', '기본톤수': 2},
    '13': {'종류': '임신', '기본톤수': 2},
    '14': {'종류': '임신', '기본톤수': 2},
    # 포유 — 15번=2톤, 16번=1톤
    '15': {'종류': '포유', '기본톤수': 2},
    '16': {'종류': '포유', '기본톤수': 1},
    # 소규모
    '2-2': {'종류': '2호', '기본톤수': 1},
    '3-2': {'종류': '3호', '기본톤수': 1, '대체톤수': 2},
}

# 차량 적재 조합
TRUCK_LARGE = [5, 3, 2, 3, 2]   # 대형 5칸 최대 15톤
TRUCK_MEDIUM = [5, 3, 2]        # 중형 3칸 최대 10톤

# 현재 약품 처방 패턴 (2026년 3~4월 기준, 빈도순)
CURRENT_PRESCRIPTION = {
    '젖돈': [
        ('진프로', '2kg'),
        ('골든펜다', '1kg'),
    ],
    '육돈': [
        ('진프로', '2kg'),
        ('유한타이로신200산', '500g'),
    ],
    '임신': [
        ('진프로', '2kg'),
    ],
    '포유': [
        ('진프로', '2kg'),
        ('티아싸이클린', '2kg'),
    ],
    '3호': [
        ('진프로', '2kg'),
    ],
}

DOW_NAMES = ['월', '화', '수', '목', '금', '토', '일']


def parse_feed_request(message: str) -> list:
    """
    농장장/직원 메시지에서 사료 요청 파싱

    입력 예시:
    - "젖돈 3-1 비었어요"
    - "내일 육돈 7-2, 임신 13번 주문해주세요"
    - "3-1번 4-1번 사료없어요"
    - "포유 16번 1톤"

    반환: [{'빈번호': '3-1', '종류': '젖돈', '톤수': 5}, ...]
    """
    items = []
    text = message.strip()

    # 패턴 1: "빈번호" 직접 언급 (3-1번, 7-2, 13번 등)
    bin_matches = re.findall(r'(\d+(?:-\d+)?)\s*번?', text)
    for bin_no in bin_matches:
        if bin_no in BIN_MAP:
            info = BIN_MAP[bin_no]
            # 톤수 명시 확인
            ton_m = re.search(rf'{re.escape(bin_no)}\s*번?\s*(\d+)\s*톤', text)
            톤수 = int(ton_m.group(1)) if ton_m else info['기본톤수']
            items.append({
                '빈번호': bin_no + '번',
                '종류': info['종류'],
                '톤수': 톤수,
            })

    # 패턴 2: "종류" 언급 시 빈번호가 없으면 기본빈 추천
    if not items:
        if re.search(r'젖돈|자돈사료', text):
            items.append({'빈번호': '', '종류': '젖돈', '톤수': 5, '빈미정': True})
        if re.search(r'육돈|비육사료', text):
            items.append({'빈번호': '', '종류': '육돈', '톤수': 5, '빈미정': True})
        if re.search(r'임신', text):
            items.append({'빈번호': '', '종류': '임신', '톤수': 2, '빈미정': True})
        if re.search(r'포유', text):
            items.append({'빈번호': '', '종류': '포유', '톤수': 2, '빈미정': True})

    # 패턴 3: 1호 (포대)
    if re.search(r'1호', text):
        포수_m = re.search(r'1호\s*(\d+)\s*포', text)
        포수 = int(포수_m.group(1)) if 포수_m else 10
        items.append({'빈번호': '', '종류': '1호', '톤수': 0, '포수': 포수})

    return items


def parse_delivery_date(message: str) -> tuple:
    """
    메시지에서 배송 날짜/시간 추출
    반환: (날짜문자열, 시간문자열)
    """
    now = datetime.now()

    # 날짜
    if '내일' in message:
        target = now + timedelta(days=1)
    elif '모레' in message:
        target = now + timedelta(days=2)
    elif '오늘' in message or '당일' in message:
        target = now
    else:
        # 날짜 직접 지정
        m = re.search(r'(\d{1,2})[/월.](\d{1,2})', message)
        if m:
            target = now.replace(month=int(m.group(1)), day=int(m.group(2)))
        else:
            target = now + timedelta(days=1)  # 기본: 내일

    date_str = f"{target.month}월 {target.day}일 {DOW_NAMES[target.weekday()]}요일"

    # 시간
    time_m = re.search(r'(\d+)\s*시', message)
    time_str = f"{time_m.group(1)}시차" if time_m else "2시차"

    return date_str, time_str


def add_medicine(items: list, include_meds: bool = True) -> list:
    """
    각 사료 항목에 현재 처방 기준 약품 추가
    """
    if not include_meds:
        return items

    for item in items:
        종류 = item['종류']
        if 종류 in CURRENT_PRESCRIPTION:
            item['약품'] = CURRENT_PRESCRIPTION[종류]
        else:
            item['약품'] = []

    return items


def check_truck_capacity(items: list) -> dict:
    """
    차량 적재 가능 여부 체크
    반환: {'추천차량': '대형'|'중형', '총톤수': N, '칸수': N, '초과': bool}
    """
    총톤수 = sum(item.get('톤수', 0) for item in items)
    칸수 = len([i for i in items if i.get('톤수', 0) > 0])

    if 총톤수 <= 10 and 칸수 <= 3:
        return {'추천차량': '중형(3칸)', '총톤수': 총톤수, '칸수': 칸수, '초과': False}
    elif 총톤수 <= 15 and 칸수 <= 5:
        return {'추천차량': '대형(5칸)', '총톤수': 총톤수, '칸수': 칸수, '초과': False}
    else:
        return {'추천차량': '대형(5칸) — ⚠️ 2대 필요', '총톤수': 총톤수, '칸수': 칸수, '초과': True}


def generate_order_text(items: list, date_str: str, time_str: str) -> str:
    """
    주문서 텍스트 생성 (카카오톡 사료주문방에 올릴 형식)

    출력 예:
    4월 7일 월요일
    2시차
    젖돈 5톤 3-1번
    진프로 2kg
    골든펜다 1kg
    육돈 5톤 7-2번
    진프로 2kg
    유한타이로신200산 500g
    임신 2톤 13번
    진프로 2kg
    """
    lines = [date_str, time_str]

    for item in items:
        종류 = item['종류']
        톤수 = item.get('톤수', 0)
        빈번호 = item.get('빈번호', '')
        포수 = item.get('포수', 0)

        if 종류 == '1호':
            lines.append(f"1호 {포수}포")
        elif 빈번호:
            lines.append(f"{종류} {톤수}톤 {빈번호}")
        else:
            lines.append(f"{종류} {톤수}톤")

        # 약품 추가
        for med_name, med_dose in item.get('약품', []):
            lines.append(f"{med_name} {med_dose}")

    return '\n'.join(lines)


def generate_full_order(message: str, include_meds: bool = True) -> dict:
    """
    전체 주문 프로세스 실행

    입력: 농장장 메시지
    반환: {
        'order_text': 카톡 복사용 주문서,
        'summary': 요약,
        'truck': 차량 정보,
        'items': 파싱된 항목들,
        'has_unresolved': 빈번호 미정 여부,
    }
    """
    items = parse_feed_request(message)

    if not items:
        return {
            'order_text': '',
            'summary': '❌ 사료 요청을 인식하지 못했습니다',
            'items': [],
            'has_unresolved': False,
        }

    date_str, time_str = parse_delivery_date(message)
    items = add_medicine(items, include_meds)
    truck = check_truck_capacity(items)

    order_text = generate_order_text(items, date_str, time_str)

    # 빈번호 미정 체크
    has_unresolved = any(item.get('빈미정') for item in items)

    # 요약
    item_summary = ', '.join(
        f"{i['종류']} {i.get('톤수',0)}톤" if i['종류'] != '1호'
        else f"1호 {i.get('포수',10)}포"
        for i in items
    )
    summary = (
        f"📋 주문 요약\n"
        f"  {date_str} {time_str}\n"
        f"  {item_summary}\n"
        f"  🚛 {truck['추천차량']} (총 {truck['총톤수']}톤, {truck['칸수']}칸)"
    )

    if has_unresolved:
        summary += "\n  ⚠️ 빈번호 미정 항목 있음 — 확인 필요"

    return {
        'order_text': order_text,
        'summary': summary,
        'truck': truck,
        'items': items,
        'has_unresolved': has_unresolved,
    }
