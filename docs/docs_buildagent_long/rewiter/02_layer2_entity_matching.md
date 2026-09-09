# Lớp 2 — Fuzzy entity matching

**Module:** `src/agents/domain/entity_catalog.py` (danh mục),
`src/agents/domain/fuzzy_match.py` (thuật toán),
`src/agents/domain/text_normalization.py` (chuẩn hoá tiếng Việt).

**Không gọi LLM.** Toàn bộ lớp này là rule-based + `rapidfuzz`.

## 1. Khoảng trống đang lấp

Bộ khớp hiện có — `adapters/catalog_reader.resolve_vehicle_names:141` — là khớp
**CHÍNH XÁC** sau khi bỏ khoảng trắng. Comment trong chính file đó tự nhận:
*"vẫn là khớp CHÍNH XÁC, không phải khớp mờ"*. Nên `"vf5"` ra `VF 5`, nhưng gõ
sai một ký tự thì không ra gì.

Lớp 2 lấp đúng khoảng đó, và **chỉ** khoảng đó: nó trả về ứng viên kèm điểm,
không tự quyết định danh tính xe. Cam kết "không suy đoán danh tính xe" của A4-1
giữ nguyên.

## 2. Ba danh mục thực thể

| Danh mục | Alias | Giá trị chuẩn | Nguồn |
|---|---:|---:|---|
| `VEHICLE` | 52 | 30 | Seed tĩnh trong `entity_catalog.py` |
| `ATTRIBUTE` | 81 | 16 | **Sinh từ `FIELD_KEYWORDS`** của `domain/vehicle_overview.py` |
| `INTENT_KEYWORD` | 24 | 3 | Bảng curated trong `entity_catalog.py` |
| **Tổng** | **157** | | |

### 2.1 Xe — seed tĩnh, không phải nguồn sự thật

Ô tô: `VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 9, VF Wild, VF e34`.
Xe máy điện: 21 mẫu, **chép nguyên từ `prompts/scope_prompts.py`** — nơi cùng
một danh mục đã được liệt kê cho bộ phân loại phạm vi (A6-2). Chép từ đó thay vì
gõ lại theo trí nhớ để hai chỗ không nói hai danh mục khác nhau.

`VF e34` **không còn** trong catalog hiện hành nhưng vẫn nhận diện được — **cố
ý**: khách hỏi một xe đã ngừng bán thì câu trả lời đúng là "mẫu này không còn
trong danh mục" (nhánh `unmatched_mentions` của A4-1 đã làm sẵn), chứ không phải
im lặng coi như khách chưa nêu tên xe nào.

`default_catalog(vehicle_names=...)` nhận sẵn tham số để nối DB thật về sau —
**[GIẢ ĐỊNH]** hiện chỉ dùng seed, xem `06_assumptions_and_risks.md`.

### 2.2 Thuộc tính — sinh từ nguồn sự thật, không chép tay

```python
for attribute, keywords in FIELD_KEYWORDS:   # domain/vehicle_overview.py
    for keyword in keywords:
        yield EntityAlias.build(keyword, attribute.value, ATTRIBUTE)
```

Chép tay là dựng nguồn sự thật thứ hai: thêm một từ khoá cho
`VehicleAttribute.COLOR` ở đó mà quên chép sang đây thì hai lớp hiểu khác nhau
về cùng một câu, và **không test nào bắt được**.

`VehicleAttribute.UNKNOWN` tự nhiên vắng mặt (nó không có từ khoá nào trong bảng
gốc) — đúng, vì nó nghĩa là "khách không nhắm thuộc tính nào", tức trạng thái
KHÔNG khớp.

### 2.3 Từ khoá intent — bảng riêng, cố ý tách khỏi `intent_reconciliation`

Ánh xạ sang đúng `Intent` enum hiện có (`ADVISORY`, `CATALOG_LOOKUP`,
`CATALOG_BROWSE`) — không tạo tập nhãn thứ hai.

**[GIẢ ĐỊNH]** Tách hai bảng là có chủ đích: `intent_reconciliation` là bộ
**hoà giải nhãn cuối cùng**, chạy trên câu đã sạch và vẫn là nguồn sự thật duy
nhất của `state["intents"]`. Bảng ở đây chỉ đo "câu này trông giống ý định nào"
trên câu **còn nhiễu**, phục vụ tính confidence. Gộp lại sẽ buộc regex hoà giải
phải chịu được cả input rác.

### 2.4 Alias số đếm tiếng Việt — phần đắt giá nhất

```
VF 5  →  {"vf 5", "vf5", "vf nam", "vf lam"}
```

Sinh từ chiều ngược của `VIETNAMESE_DIGIT_WORDS`, **không viết tay từng dòng**:
thêm mẫu xe mới vào catalog thì alias có ngay.

Đây là thứ bắt được đúng ca lỗi gốc `"tho ti x vf năm"` **mà không cần một lần
gọi LLM nào** — nên Lớp 2 vẫn nhận ra xe kể cả khi Lớp 1 bị tắt hoặc lỗi.

## 3. Chuẩn hoá tiếng Việt

`domain/text_normalization.normalize()`: `NFC` → bỏ dấu qua `NFD` + lọc dấu tổ
hợp → `casefold` → chỉ giữ chữ và số → squash khoảng trắng.

Hai điểm bắt buộc:

- **Bỏ dấu phải đi qua NFD, không dùng bảng ánh xạ tay.** Chữ `"ế"` có hai cách
  mã hoá Unicode (một code point, hoặc `e` + hai dấu tổ hợp), mà bàn phím tiếng
  Việt sinh ra cả hai. Bảng tay chỉ bắt được một dạng → hai khách gõ cùng một
  câu nhận hai kết quả nhận diện khác nhau.
- **`đ`/`Đ` xử lý riêng.** Nó là một **chữ cái độc lập** trong bảng chữ cái tiếng
  Việt, không phải `d` kèm dấu, nên NFD không tách nó ra.

Đây là lý do bắt buộc chuẩn hoá **trước** khi đưa vào `rapidfuzz`: `"hà nội"` và
`"ha noi"` có edit-distance lớn trên chuỗi thô — thư viện đo đúng khoảng cách ký
tự nhưng trả lời sai câu hỏi ta đang hỏi.

## 4. Thuật toán và ngưỡng

Khớp theo **CỬA SỔ TOKEN** (1–5 từ), không theo chuỗi con. So chuỗi con sẽ cho
`"o to"` khớp vào `"cho toi"` — đúng con bug mà `domain/catalog_browse._mentions`
đã phải xử lý bằng ranh giới từ.

Scorer: `rapidfuzz.fuzz.ratio` trên dạng đã chuẩn hoá.

| Ngưỡng | Giá trị | Biến môi trường |
|---|---:|---|
| Alias 1 token | **85** / 100 | `NLU_FUZZY_SINGLE_TOKEN_SCORE` |
| Alias nhiều token | **80** / 100 | `NLU_FUZZY_MULTI_TOKEN_SCORE` |
| Sàn "ứng viên yếu" | **70** / 100 | `NLU_FUZZY_WEAK_FLOOR` |

"Ứng viên yếu" (`is_weak=True`) **không** được coi là đã khớp — chỉ làm chứng cứ
phụ để Lớp 3 hạ confidence thay vì im lặng bỏ qua.

### Hai luật an toàn — cả hai giữ cam kết A4-1

**Luật 1 — alias < 4 ký tự chỉ khớp TUYỆT ĐỐI.**
Với chuỗi ba ký tự, một thao tác sửa đã là một phần ba chuỗi, nên mọi ngưỡng
phần trăm đều vô nghĩa: `"mua"` sẽ khớp `"màu"`, `"chi"` sẽ khớp `"cho"`. Đây là
nhóm alias đông nhất trong bảng thuộc tính.

Hệ quả: `"vf"` một mình **không bao giờ** ra `VF 5` (chỉ được 80 điểm, dưới 85).

**Luật 2 — token ngắn TRONG alias nhiều từ phải khớp tuyệt đối, đúng vị trí.**

> Phát hiện khi chạy thật: `"các xe"` khớp mờ `"cần xe"` (ADVISORY) ở **83
> điểm** — đủ qua ngưỡng cụm nhiều từ. Điểm tính trên cả cụm che mất lỗi nằm
> trong một từ ngắn; đo trên đúng từ chứa nó thì `"cac"` và `"can"` là hai từ
> khác hẳn nhau.

Hệ quả có chủ đích: `"vf nem"` **không** còn khớp `"vf nam"`. Đó là chiều đúng —
một ký tự sai giữa "năm" với "nem" không đủ để khẳng định khách muốn VF 5. Ca đó
thuộc về Lớp 1: sửa chính tả xong thì `"VF 5"` khớp tuyệt đối.

## 5. Quét cả câu gốc VÀ câu rewrite

```python
match_entities(original_text=..., rewritten_text=..., catalog=..., thresholds=...)
```

Quét cả hai là **có chủ đích**, không phải quét thừa: rewrite có thể sửa đúng
(`"tho ti"` → `"thông tin"`) nhưng cũng có thể **làm hỏng** một tên xe mà câu gốc
viết đúng. Giữ điểm cao nhất giữa hai đường nghĩa là **Lớp 1 chỉ có thể GIÚP
Lớp 2, không bao giờ làm nó tệ đi**. Câu gốc được ưu tiên khi hoà điểm.

`EntityMatch.matched_on` ghi lại khớp đến từ đâu (`"original"` / `"rewritten"`) —
cần cho audit, và Lớp 3 dùng nó để phạt confidence khi **mọi** bằng chứng chỉ
xuất hiện sau rewrite.

## 6. Schema output

```python
@dataclass(frozen=True, slots=True)
class EntityMatch:
    category: EntityCategory       # VEHICLE | ATTRIBUTE | INTENT_KEYWORD
    canonical: str                 # "VF 5" | "PRICE" | "CATALOG_BROWSE"
    matched_alias: str             # alias đã khớp, dạng chuẩn hoá
    score: float                   # 0–100 (rapidfuzz)
    source_span: str               # cụm từ TRONG CÂU KHÁCH VIẾT — không bịa
    matched_on: "original" | "rewritten"
    is_weak: bool
```

`canonical` giữ **nguyên văn** cách catalog ghi — giá trị này được chuyển xuống
`IntentRoutingService.lookup_facts` để tra catalog, nên nó phải khớp đúng cách
catalog ghi, không phải cách module này nghĩ là đẹp.

## 7. Ví dụ thật (chạy trên code đã merge)

```
'tho ti x vf năm'            → VEHICLE:VF 5@100, ATTRIBUTE:OVERVIEW@100
'vf5 giá bao nhiêu'          → VEHICLE:VF 5@100, ATTRIBUTE:PRICE@100
'klaraa gia bao nhieu'       → VEHICLE:Klara@91,  ATTRIBUTE:PRICE@100   ← khớp mờ thật
'vf 8 có mấy chỗ ngồi'       → VEHICLE:VF 8@100, ATTRIBUTE:SEAT_COUNT@100
'cho tôi xem các xe máy điện'→ INTENT_KEYWORD:CATALOG_BROWSE@100
'cho tôi hỏi về vf'          → (không entity nào — A4-1 giữ nguyên)
'tôi muốn mua xe'            → (KHÔNG có COLOR: "mua" ≠ "màu")
```

## 8. Hiệu năng

Danh mục dựng **một lần** ở `composition.py` (`default_catalog()`), dùng lại cho
mọi lượt. Dựng lại ở mỗi tin nhắn sẽ cộng vài nghìn phép chuẩn hoá chuỗi vào
đúng đường chạy mà p95 ≤ 6s đang đo (PRD 8.5).

Cửa sổ token bị chặn trên ở `MAX_WINDOW_TOKENS = 5` để một tin nhắn dài bất
thường không biến bước này thành O(n²).
