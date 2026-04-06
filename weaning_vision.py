"""
도방육종 모돈관리현황판 Vision 판독 모듈
Anthropic API를 직접 호출하여 카드 판독
"""
import os
import re
import json
import base64
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

VISION_PROMPT = """이 사진은 Farmsco 모돈관리현황판입니다.

판독 규칙:
1. 상단에 1산/2산/3산/4산 또는 5산/6산/7산/8산 열이 있습니다
2. 제일 오른쪽 열에서 데이터가 기록된 마지막 열을 찾으세요 (빈 열 제외)
3. 그 열에서 아래 값을 읽어주세요:
   - 열 상단 숫자 = 현재 산차 (예: 4, 7)
   - 분만 일 행의 날짜 (월.일 형식)
   - 이유 일 행의 날짜 (월.일 형식)
   - 이유 두수 행의 숫자

반드시 아래 JSON만 반환하세요. 다른 텍스트 없이:
{"산차": 숫자또는null, "분만일": "월.일또는null", "이유일": "월.일또는null", "이유두수": 숫자또는null, "신뢰도": "높음또는낮음"}

숫자가 불명확하면 null을 사용하세요."""


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def parse_date(date_str: str, weaning_year: int = None) -> str:
    """월.일 형식을 YYYY-MM-DD로 변환"""
    if not date_str or date_str == "null":
        return None
    year = weaning_year or datetime.now().year
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})", str(date_str))
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    if month > 12 or day > 31:
        return None
    return f"{year}-{month:02d}-{day:02d}"


def calc_age(birth_str: str, weaning_str: str) -> int:
    """이유일령 계산"""
    try:
        birth = datetime.strptime(birth_str, "%Y-%m-%d")
        wean  = datetime.strptime(weaning_str, "%Y-%m-%d")
        diff  = (wean - birth).days
        # 분만일이 이유일보다 미래면 전년도
        if diff < 0:
            birth = birth.replace(year=birth.year - 1)
            diff  = (wean - birth).days
        return diff if 0 < diff < 60 else None
    except:
        return None


def vision_read_card(image_bytes: bytes, weaning_year: int = None) -> dict:
    """
    단일 카드 판독
    Returns: {산차, 분만일, 이유일, 이유두수, 이유일령, 신뢰도, error}
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY 미설정"}

    b64 = image_to_base64(image_bytes)

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 300,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": VISION_PROMPT}
                    ],
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()

        # JSON 파싱
        raw_clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(raw_clean)

        year = weaning_year or datetime.now().year
        이유일_str  = parse_date(data.get("이유일"),  year)
        분만일_str  = parse_date(data.get("분만일"),  year)
        이유일령    = None

        if 이유일_str and 분만일_str:
            이유일령 = calc_age(분만일_str, 이유일_str)
            if 이유일령 is None:
                # 분만일 전년도로 재시도
                분만일_str = parse_date(data.get("분만일"), year - 1)
                이유일령 = calc_age(분만일_str, 이유일_str) if 분만일_str else None

        return {
            "산차":     data.get("산차"),
            "분만일":   분만일_str,
            "이유일":   이유일_str,
            "이유두수": data.get("이유두수"),
            "이유일령": 이유일령,
            "신뢰도":   data.get("신뢰도", "알수없음"),
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e} / raw: {raw[:100]}")
        return {"error": f"JSON파싱실패: {str(e)[:50]}"}
    except requests.HTTPError as e:
        logger.error(f"API HTTP 오류: {e}")
        return {"error": f"API오류: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Vision 판독 오류: {e}")
        return {"error": str(e)[:80]}


def aggregate_cards(card_results: list) -> dict:
    """여러 카드 집계"""
    valid = [c for c in card_results if not c.get("error") and c.get("산차")]

    산차_list  = [c["산차"]     for c in valid if c.get("산차") is not None]
    일령_list  = [c["이유일령"] for c in valid if c.get("이유일령") is not None]
    두수_list  = [c["이유두수"] for c in valid if c.get("이유두수") is not None]

    분포 = {}
    for s in 산차_list:
        key = f"{s}산"
        분포[key] = 분포.get(key, 0) + 1

    return {
        "판독성공":   len(valid),
        "총카드":     len(card_results),
        "평균산차":   round(sum(산차_list) / len(산차_list), 2) if 산차_list else None,
        "평균일령":   round(sum(일령_list) / len(일령_list), 1) if 일령_list else None,
        "총이유두수": sum(두수_list) if 두수_list else None,
        "산차분포":   분포,
        "실패목록":   [c for c in card_results if c.get("error")],
    }


def format_report(agg: dict, 군번호: str = "", 이유날짜: str = "") -> str:
    """집계 결과 보고 형식"""
    lines = [
        f"📊 이유 판독 완료 — {이유날짜}",
        f"군번호: {군번호}",
        f"",
        f"판독: {agg['판독성공']} / {agg['총카드']}장 성공",
        f"",
        f"🐷 모돈 데이터:",
    ]
    if agg["평균산차"]:
        lines.append(f"  평균 산차: {agg['평균산차']}산")
    if agg["산차분포"]:
        분포_str = " / ".join(
            [f"{k}:{v}두" for k, v in sorted(agg["산차분포"].items())])
        lines.append(f"  산차 분포: {분포_str}")
    lines.append(f"")
    lines.append(f"🐣 자돈 데이터:")
    if agg["평균일령"]:
        lines.append(f"  평균 이유일령: {agg['평균일령']}일")
    if agg["총이유두수"]:
        lines.append(f"  총 이유두수: {agg['총이유두수']}두")
    if agg["실패목록"]:
        lines.append(f"")
        lines.append(f"⚠️ 판독 실패 {len(agg['실패목록'])}장 — 추가 확인 필요")
    return "\n".join(lines)
