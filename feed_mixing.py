"""
🌾 도방육종 사료배합지시 자동 생성 모듈
주문 승인 → 입고 확인 → 배합지시 텔레그램 전송
"""
from datetime import datetime

# 배합지시 = 주문 내용과 동일한 형식
# (사료 + 약품이 같이 들어가야 하므로)


def generate_mixing_instruction(order_text: str) -> str:
    """
    주문서 텍스트를 배합지시 문자로 변환

    입력: 승인된 주문서 원문
    출력: 배합지시 문자 (업무 텔레그램 전송용)

    배합지시 = 주문서와 동일 형식
    (사료 입고 후 해당 빈에 약품을 섞어야 하므로 동일 정보 필요)
    """
    lines = order_text.strip().split('\n')
    header = f"🌾 사료배합지시\n{'='*20}\n"
    footer = f"\n{'='*20}\n⚠️ 약품 정확히 계량 후 투입\n📋 배합 완료 후 '배합완료' 보고"

    return header + order_text + footer


class FeedOrderSession:
    """
    사료주문 세션 관리
    주문 생성 → 승인 대기 → 승인/수정/취소 → 입고확인 → 배합지시 전송
    """

    def __init__(self):
        # 대기중인 주문: {admin_msg_id: order_data}
        self.pending_orders = {}
        # 승인된 주문 (입고 대기): {order_id: order_data}
        self.approved_orders = {}

    def add_pending(self, msg_id: str, order_data: dict):
        """주문 대기 등록"""
        self.pending_orders[msg_id] = {
            **order_data,
            'created_at': datetime.now().isoformat(),
            'status': 'pending',
        }

    def approve(self, msg_id: str) -> dict:
        """주문 승인 → 입고 대기로 이동"""
        order = self.pending_orders.pop(msg_id, None)
        if not order:
            return None
        order['status'] = 'approved'
        order['approved_at'] = datetime.now().isoformat()
        order_id = f"FO-{datetime.now().strftime('%Y%m%d-%H%M')}"
        self.approved_orders[order_id] = order
        return {'order_id': order_id, **order}

    def reject(self, msg_id: str) -> dict:
        """주문 취소"""
        return self.pending_orders.pop(msg_id, None)

    def confirm_delivery(self, order_id: str = None) -> dict:
        """
        입고 확인 → 배합지시 생성
        order_id가 None이면 가장 최근 승인 주문
        """
        if order_id and order_id in self.approved_orders:
            order = self.approved_orders.pop(order_id)
        elif self.approved_orders:
            # 가장 최근 승인 주문
            order_id = list(self.approved_orders.keys())[-1]
            order = self.approved_orders.pop(order_id)
        else:
            return None

        order['status'] = 'delivered'
        order['delivered_at'] = datetime.now().isoformat()
        return {'order_id': order_id, **order}

    def get_pending_summary(self) -> str:
        """대기중인 주문 요약"""
        if not self.pending_orders:
            return "대기중인 주문 없음"
        lines = ["📋 대기중 주문:"]
        for mid, o in self.pending_orders.items():
            lines.append(f"  {o.get('summary','')[:50]}")
        return '\n'.join(lines)

    def get_approved_summary(self) -> str:
        """승인됨(입고 대기) 주문 요약"""
        if not self.approved_orders:
            return "입고 대기 주문 없음"
        lines = ["🚛 입고 대기 주문:"]
        for oid, o in self.approved_orders.items():
            lines.append(f"  [{oid}] {o.get('summary','')[:50]}")
        return '\n'.join(lines)


# 글로벌 세션
feed_session = FeedOrderSession()
