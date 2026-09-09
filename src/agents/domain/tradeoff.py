"""Câu trade-off — chỉ nói khi có SỐ của cả hai xe trên CÙNG một chiều.

*"VF 5 có thể không thoải mái bằng VF 6"* là một khẳng định về chiếc xe KHÁC.
Sinh nó từ template trống, hay từ nhãn phân khúc chung chung, là đúng loại claim
mà `claim_policy` sinh ra để chặn — chỉ khác ở chỗ lần này ta tự bịa thay vì để
LLM bịa.

Nên module này KHÔNG sinh chữ. Nó chỉ trả lời một câu hỏi: *có đủ bằng chứng để
nói một câu trade-off không, và chênh bao nhiêu*. Việc dựng câu thuộc tầng
prompt/claim, và nó chỉ được chạy khi hàm này trả về khác `None`.

Thiếu bằng chứng thì **bỏ hẳn** câu trade-off — ô thứ tư trong bản dựng tay dành
cho một thông số đã xác minh. Viết một câu chung chung cho đủ cấu trúc là tự mở
lại đúng cái cửa vừa đóng.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ComparisonFact:
    """Một số ĐÃ XÁC MINH của một xe, trên một chiều so sánh."""

    fact_code: str
    vehicle_name: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class TradeoffPlan:
    """Đủ căn cứ để nói một câu trade-off, và chênh lệch đo được."""

    fact_code: str
    subject_name: str
    alternative_name: str
    subject_value: Decimal
    alternative_value: Decimal
    difference: Decimal


def plan_tradeoff(
    *,
    subject: str,
    subject_fact: ComparisonFact | None,
    alternative_fact: ComparisonFact | None,
) -> TradeoffPlan | None:
    """`TradeoffPlan` khi nói được, `None` khi phải im.

    Bốn cửa, cửa nào trượt cũng là `None`:

    1. **Thiếu số một bên** — không biết "hơn" ở đâu.
    2. **Khác chiều** — so khoang hành lý với tầm chạy là so hai thứ không cùng
       đơn vị, và câu đó nghe vẫn xuôi nên rất khó bắt về sau.
    3. **Cùng một xe** — so nó với chính nó không nói lên điều gì.
    4. **Xe đối chiếu không hơn** — bằng hoặc kém mà vẫn mời khách xem sang là
       đẩy họ đi vô cớ.
    """

    if subject_fact is None or alternative_fact is None:
        return None
    if subject_fact.fact_code != alternative_fact.fact_code:
        return None
    if subject_fact.vehicle_name == alternative_fact.vehicle_name:
        return None
    if alternative_fact.value <= subject_fact.value:
        return None
    return TradeoffPlan(
        fact_code=subject_fact.fact_code,
        subject_name=subject,
        alternative_name=alternative_fact.vehicle_name,
        subject_value=subject_fact.value,
        alternative_value=alternative_fact.value,
        difference=alternative_fact.value - subject_fact.value,
    )
