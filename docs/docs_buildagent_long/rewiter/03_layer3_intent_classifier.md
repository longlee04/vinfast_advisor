# Lớp 3 — Intent classifier có căn cứ

**Module:** `src/agents/domain/nlu_confidence.py` (`classify_intent`).
**Không gọi LLM.**

## 1. "Có căn cứ" nghĩa là gì

Bộ phân loại này **không đọc câu chữ tự do**. Nó chỉ cộng điểm từ những entity mà
Lớp 2 đã trích được, và **mỗi kết luận đều mang theo danh sách entity đã dẫn tới
nó** (`NluClassification.evidence`).

Nhờ vậy một nhãn sai luôn truy được về đúng entity gây ra nó, thay vì phải đoán
mô hình đã "nghĩ" gì. Đây là cùng nguyên tắc với `domain/quote_risk.py` của
A7-4: quyết định quan trọng phải rule-based và giải thích được.

## 2. Input / Output

### Input
```python
classify_intent(
    entities: Sequence[EntityMatch],   # Lớp 2
    rewrite_trust: float = 1.0,        # Lớp 1 — 1.0 nếu câu vốn sạch
    pending_slot: str | None = None,   # A7-10
    pending_intent: str | None = None,
) -> NluClassification
```

Câu gốc và câu rewrite **không** được truyền trực tiếp vào đây: chúng đã được
Lớp 2 tiêu thụ, và mọi thứ Lớp 3 cần biết về chúng đã nằm trong `entities`
(kể cả `matched_on`) và `rewrite_trust`. Truyền lại nguyên văn sẽ mở cửa cho
việc lén thêm logic đọc chuỗi vào một lớp cố ý không đọc chuỗi.

### Output
```python
@dataclass(frozen=True, slots=True)
class NluClassification:
    intent_hint: str | None                  # GỢI Ý — xem §5
    confidence: float                        # [0, 1]
    candidates: tuple[IntentCandidate, ...]  # (intent, score) đã sắp giảm dần
    evidence: tuple[EntityMatch, ...]        # bằng chứng
    resolved_via_pending_slot: bool
    pending_slot: str | None

    @property vehicle_names -> tuple[str, ...]   # tên xe đã nhận ra
    @property attributes    -> tuple[str, ...]   # VehicleAttribute đã nhận ra
```

## 3. Intent hỗ trợ

Đúng ba giá trị của `domain/values.Intent` hiện có — **không tạo tập nhãn mới**:

| Intent | Khách đưa vào | Bằng chứng chính |
|---|---|---|
| `CATALOG_LOOKUP` | TÊN MỘT MẪU XE | `EntityCategory.VEHICLE` |
| `CATALOG_BROWSE` | TÊN MỘT LOẠI XE | `INTENT_KEYWORD` → `CATALOG_BROWSE` |
| `ADVISORY` | TIÊU CHÍ CÁ NHÂN | `INTENT_KEYWORD` → `ADVISORY` |

## 4. Công thức điểm

### 4.1 Điểm từng intent

```
CATALOG_LOOKUP += 0.60 × (điểm xe / 100)                    nếu có tên mẫu xe
CATALOG_LOOKUP += 0.25 × (điểm thuộc tính / 100)            CHỈ khi đã có tên xe
<intent của từ khoá> += 0.40 × (điểm từ khoá / 100)
CATALOG_BROWSE  ×= (1 − 0.50)                               nếu câu CÓ tên mẫu xe
```

Hai luật đáng chú ý:

- **Thuộc tính chỉ cộng khi đã biết hỏi về xe nào.** `"màu gì"` mà không có tên
  xe thì chưa biết hỏi màu của xe nào.
- **Tên MẪU xe hạ điểm tên LOẠI xe** — giữ đúng thứ tự ưu tiên A4-7 mà
  `nodes/route_intent:35` đang áp dụng: *"VF 5 với các ô tô khác thì sao"* phải
  trả bảng của VF 5.

### 4.2 Confidence tổng

```
evidence  = (điểm cao nhất trong các entity đã chấp nhận) / 100
support   = min(số entity, 2) / 2
trust     = rewrite_trust                    # 1.0 nếu câu vốn sạch

confidence = 0.50×evidence + 0.20×support + 0.30×trust
confidence ×= 0.90   nếu MỌI bằng chứng chỉ đến từ câu rewrite
```

Nhân tố phạt cuối cùng quan trọng: khi không entity nào khớp được trên câu gốc,
cả kết luận đang đứng trên **một suy đoán của mô hình**, không trên chữ khách đã
viết.

Không có entity nào được chấp nhận → `intent_hint = None`, `confidence = 0.0`.
Chỉ có ứng viên yếu (`is_weak`) → cũng `None`: chúng là chứng cứ phụ, không đủ
để kết luận.

### 4.3 Số thật đo được

| Câu | evidence | support | trust | confidence | tier |
|---|---:|---:|---:|---:|---|
| `vf5 gia bao nhieu` | 1.0 | 1.0 | 1.0 | **1.000** | AUTO |
| `tho ti x vf năm` (rewrite 0.95) | 1.0 | 1.0 | 0.95 | **0.985** | AUTO |
| `e can tv x cho gd 5 ng` (rewrite 0.9) | 1.0 | 1.0 | 0.90 | **0.873** | AUTO |
| `vf nam` (1 entity, câu sạch) | 1.0 | 0.5 | 1.0 | **0.900** | AUTO |
| `zxcv qwer asdf` | — | — | — | **0.000** | CLARIFY |

## 5. `intent_hint` là GỢI Ý, không phải nhãn cuối cùng

> **Nguồn sự thật duy nhất của `state["intents"]` vẫn là
> `domain/intent_reconciliation.reconcile_intents`,** chạy sau `extract_slots`.

`intent_hint` chỉ dùng để:
1. quyết định tier ở Lớp 4;
2. dựng câu xác nhận ở nhánh CONFIRM;
3. ghi log/audit.

Nó **không** ghi vào `state["intents"]`. Hai bộ cùng ghi một field là cách chắc
chắn nhất để chúng lệch nhau âm thầm ở các câu lai (A4-6) — và không test nào
bắt được.

Có test khoá điều này: `test_intent_hint_never_invents_a_label_outside_the_existing_enum`.

## 6. Tương thích ngược với pending-slot (A7-10)

### 6.1 Trong `classify_intent` — ưu tiên tuyệt đối

```python
if pending_slot is not None:
    return NluClassification(
        intent_hint=pending_intent,
        confidence=1.0,
        resolved_via_pending_slot=True,
        ...
    )
```

Lượt đang trả lời một câu hỏi slot **không được phân loại lại như tin nhắn mới**.
`confidence=1.0` + `resolved_via_pending_slot=True` khiến Lớp 4 trả `AUTO` ngay,
tức không lớp nào được chen câu hỏi xác nhận vào giữa.

### 6.2 Điểm nối THẬT — `PendingSlotServiceImpl.fallback_extractors`

> Đây là chỗ dễ hiểu nhầm nhất của cả thiết kế.

`chain._resume_pending_slot` (`src/agents/chain.py:110`) chạy **TRƯỚC**
`graph.ainvoke` và **kết thúc lượt ngay** khi giải được. Nên node
`recognize_intent` **không bao giờ** nhìn thấy một lượt đang trả lời câu hỏi
slot — nhánh `pending_slot` ở §6.1 gần như không bao giờ chạy trong graph.

Vì vậy tầng nhận diện có **điểm nối thứ hai**, cắm thẳng vào A7-10:

```python
# services/pending_slot.py
def _extract(self, slot_name, user_message):
    value = self.extractors.get(slot_name)(...)        # bộ CHÍNH: khớp chính xác
    if value is not None:
        return value
    return self.fallback_extractors.get(slot_name)(...)  # bộ MỜ, chỉ khi bộ chính bó tay
```

**Thứ tự này là điều kiện an toàn, không phải tối ưu.** Bộ chính
(`detect_province`) khớp chính xác và không bao giờ đoán. Đảo thứ tự thì một câu
khách viết đúng vẫn có thể bị bộ mờ đọc lệch — đánh đổi độ chính xác để lấy đúng
những ca không cần.

Bộ mờ dùng ngưỡng **riêng, cao hơn** Lớp 2 (`SLOT_MATCH_THRESHOLD = 88` so với
85/80): đã biết đang chờ slot nào thì không gian đáp án hẹp lại còn vài chục giá
trị, và **đoán sai tỉnh nghĩa là báo sai phí trước bạ hàng chục triệu đồng**.

Kết quả đo được:

| Câu khách | `detect_province` (cũ) | `fuzzy_detect_province` (mới) |
|---|---|---|
| `hà nội` | `HN` | `HN` |
| `hà nôi` (sai một dấu) | **`None`** | **`HN`** ← cứu được |
| `ha nol` (sai một chữ cái) | `None` | `None` ← **cố ý không cứu** |
| `hn` | `HN` | `HN` |
| `hm` | `None` | `None` |

**[GIẢ ĐỊNH]** `FUZZY_FALLBACK_EXTRACTORS` hiện chỉ có `province`, vì
`DEFAULT_EXTRACTORS` của A7-10 cũng chỉ có `province` — không slot nào khác từng
được dựng thành pending. Thêm slot mới vào pending thì thêm một dòng ở đây.
