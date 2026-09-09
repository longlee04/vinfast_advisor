# Ghi chép workshop CERTUS — và cách áp dụng vào P-150

> Nguồn: repo `certus-workshop` (backend FastAPI + React, `docs/research-notes/01-confidence-intervals.md`,
> `docs/research-notes/02-tot-grid-coverage.md`, `kb/`, `src/backend/app/`).
> Tài liệu này viết lại phần lý thuyết theo cách dễ hiểu, rồi ánh xạ từng bài học
> vào `eval/` của P-150 kèm số liệu tính trên bộ dữ liệu thật.

---

## Phần 0 — CERTUS giải quyết vấn đề gì

CERTUS là trợ lý QA phân tích độ phủ kiểm thử. Điểm khác biệt của nó không nằm ở
chỗ chạy test giỏi hơn, mà ở chỗ nó **đổi câu hỏi**:

| | Câu hỏi | Mẫu số |
|---|---|---|
| Coverage truyền thống | "Code đã chạy bao nhiêu?" | cấu trúc code (dòng, nhánh) |
| Mutation testing | "Test có bắt được lỗi giả lập không?" | dòng code mà test đã chạm |
| **CERTUS** | **"Vùng rủi ro nào đã có bằng chứng đủ mạnh?"** | **không gian rủi ro** |

Luận điểm trung tâm, trích `README.md` của repo đó:

> Bộ kiểm của bạn chạy 6 tình huống. Kiểm thử đột biến gài lỗi vào mã, chạy 6 bài
> đó, báo **"92% — tốt lắm"**. Con số 92% đó **đúng**, và **vô nghĩa**: nó là 92%
> của 6 tình huống, không phải của 24. Mười tám tình huống kia không nằm trong
> mẫu số.

Toàn bộ workshop xoay quanh một ý: **một con số không tự chứng minh được nó có ý
nghĩa gì.** Muốn tin một con số thì phải biết mẫu số của nó, độ bất định của nó,
và nó được sinh ra bằng quy trình nào.

---

## Phần I — Chín bài học

### Bài 1. Mọi tỉ lệ phải đi kèm khoảng tin cậy

`3/3 pass` và `300/300 pass` cùng cho tỉ lệ 100%, nhưng một cái đảm bảo tỉ lệ
thật ≥ 43,9%, cái kia ≥ 98,9%. Con số trần không phân biệt được hai tình huống đó.

Công thức dùng là **Wilson score interval** (không dùng Wald — Wald tràn ra ngoài
`[0,1]` hoặc sụp thành một điểm khi n nhỏ):

```python
from statistics import NormalDist
import math

def wilson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Khoảng Wilson cho tỉ lệ k/n. n = 0 trả (0.0, 1.0) — không raise, không chia 0."""
    if n == 0:
        return (0.0, 1.0)
    z = NormalDist().inv_cdf(1 - (1 - conf) / 2)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))
```

Ba điều dễ hiểu sai:

- **`center ≠ p̂`.** Tử số cộng thêm `z²/(2n)` nên tâm bị kéo về phía 0.5.
  `10/10` cho `p̂ = 1.00` nhưng tâm là `0.8612`.
- **"Wilson 95%" không phải đúng 95%.** Độ phủ thật ở `n=10, p=0.30` là `0.9244`.
  Nên đọc "Wilson95" là "khoảng 92–95%". Tăng n **không** cứu được điều này.
- **Đọc theo nghĩa Bayes là sai.** Nói *"95% xác suất giá trị thật nằm trong
  khoảng này"* là sai. Đúng phải là: *"quy trình này, nếu lặp lại, sinh ra khoảng
  chứa giá trị thật 95% số lần."*

Bảng tra nhanh cho trường hợp toàn-pass (`k = n`), Wilson 95%:

```
 1/1  → ≥ 20,7%  (gần như vô nghĩa)     50/50  → ≥ 92,9%
 3/3  → ≥ 43,9%                         73/73  → ≥ 95,0%
 5/5  → ≥ 56,6%                        100/100 → ≥ 96,3%
10/10 → ≥ 72,2%                        200/200 → ≥ 98,1%
20/20 → ≥ 83,9%                        381/381 → ≥ 99,0%
30/30 → ≥ 88,6%                        500/500 → ≥ 99,2%
```

### Bài 2. Số đem so với ngưỡng là **biên**, không phải điểm ước lượng

> Con số dùng **để quyết định** hầu như luôn là **biên**. Nó trả lời: *"trường
> hợp tệ nhất tệ đến đâu?"*

Chọn phía nào phụ thuộc chiều của ràng buộc:

| Ràng buộc | Phía bảo thủ |
|---|---|
| "tỉ lệ đúng phải **≥** ngưỡng" (sàn) | **biên dưới** |
| "tỉ lệ lỗi phải **≤** ngưỡng" (trần) | **biên trên** |

Ví dụ trong repo CERTUS: bản ghi `{killed: 2, survived: 0}` cho tỉ lệ chấm-sai
`0.0` và **đi lọt**, trong khi Wilson95 của `0/2` là `[0.0000, 0.6576]` — tỉ lệ
thật có thể tới 65,8%, hơn bốn lần trần cho phép. Điểm ước lượng cho PASS,
khoảng cho FAIL, và cái thứ hai đúng.

> **Lưu ý:** chính repo CERTUS đang sai chỗ này. `src/backend/app/gates/outcome.py`
> so `wilson_lower` với một ngưỡng **trần**, trong khi lập luận trong docstring của
> nó lại trích đúng con số biên **trên**. Bài học rút ra: nhớ chiều ràng buộc quan
> trọng hơn nhớ tên hàm.

### Bài 3. Không bao giờ gộp nhiều vùng về một con số

Hai con số của lưới, và luật là chúng **không bao giờ nhập làm một**:

```
RWC     = Σ w(c)·score(band(c)) / Σ w(c)      ← chỉ để xem xu hướng
gate(z) = min score trong zone z              ← đây mới là cổng thật
```

Lý do: một trung bình cho phép một vùng tốt che một vùng tệ ở chỗ hoàn toàn khác.
999 ô an toàn không có quyền che 1 ô tới hạn còn `unknown`.

Repo CERTUS thi hành luật này bằng cách **cố ý không cung cấp hàm thứ ba** gộp hai
số lại — và (theo tài liệu nền) có một bài kiểm liệt kê mọi hàm công khai của
module, làm đỏ build ngay khi ai đó thêm vào.

> **Lưu ý:** trong bản CERTUS này, `rollup.py:227` **có** hàm
> `overall_coverage_score = 0.7 * rwc + 0.3 * worst`, đi ngược docstring của chính
> module (dòng 1–14), và bài kiểm chặn nói trên **không tồn tại** trong
> `tests/test_rollup.py`. Hiện chỉ frontend dùng nó, chưa gate nào gọi — nhưng đây
> đúng là hình dạng mà module tự cấm.

Thang điểm band phải là **dữ liệu trong config**, không phải hằng số trong code:

```yaml
- {band: high,    score: 1.0}
- {band: med,     score: 0.6}
- {band: low,     score: 0.2}
- {band: stub,    score: 0.0}
- {band: unknown, score: 0.0}
# N/A CỐ Ý không có entry
```

### Bài 4. Mẫu số phải là không gian rủi ro, không phải danh sách test đã viết

Cấu trúc lưới gồm ba khái niệm:

- **Axis** — một chiều rủi ro. Bắt buộc có `ref` trỏ tới enum/config **có thật
  trong code**, phải có ≥2 giá trị chạm tới được, và phải trực giao với các axis
  khác (loại nếu tương quan cao). Mọi lần từ chối đều được ghi log kèm lý do.
- **Cell** — một tổ hợp giá trị cụ thể trên t axis. Id chuẩn hoá cứng:
  `cell:<axis>=<value>|<axis>=<value>`, đúng chuỗi đó là id trong sổ, id trong
  lưới và hàng trong báo cáo — không có dạng nào khác.
- **Zone** — nhóm ô có ý nghĩa rủi ro chung, mang trọng số `w`, khớp theo luật
  **first-match-wins**. Đổi thứ tự hai luật cùng khớp một ô là **thật sự đổi zone
  của ô đó**.

Dùng `t=2` (pairwise) thay vì tích Descartes đầy đủ, và chỉ nâng lên `t=3` ở các
zone nóng.

Một guard chống lách đáng học: lệnh biên dịch zone **từ chối chạy** nếu không luật
nào chạm ngưỡng `blocking_w` — *"bên bị chấm điểm không được phép làm rỗng tập
chặn."*

### Bài 5. `N/A` không phải điểm 0, và phải đi qua đúng một cửa

`N/A` bị loại khỏi **cả tử lẫn mẫu** — *"không áp dụng được"* không phải *"rủi ro
trung bình bằng không"*. Báo cáo phải in ra `cells_excluded_na` để người đọc
**thấy** phần bị loại thay vì bị nuốt im lặng.

Bốn lý do bị từ chối thẳng khi ai đó xin đánh dấu `N/A`:

`rare` · `hard_to_test` · `few_users` · `system_will_block`

> *"'Hiếm', 'khó test', 'ngách' và 'hệ thống sẽ chặn thôi' không phải là ràng
> buộc; chúng là **ô chưa test kèm một cái cớ**."*

Lỗi thật đã đo được: **một** `N/A` được duyệt trên ô duy nhất của zone nặng nhất
(w = 0,95) làm **cả zone biến mất khỏi báo cáo**, và lần chạy đó báo PASS mà không
dòng nào nói có một zone đã rời đi.

### Bài 6. Fail-closed — "tôi không đo được" khác hẳn "tôi đã đo và kết quả tệ"

```python
# Nguy hiểm: hệ thống xanh vì không có dữ liệu
if missing_artifact:
    pass

# An toàn: chưa đo thì không coi là sạch
if missing_artifact:
    block("unverified")
```

Bốn đẳng thức bị cấm: `missing artifact ≠ pass` · `zero denominator ≠ pass` ·
`unknown ≠ N/A` · `unverified ≠ success`.

Câu chuyện "con số rỗng" trong nhật ký nợ của repo: cùng một phép đo cho ba kết
quả rỗng liên tiếp — `1.0` (oracle đã nổ sẵn trên mã lành), `0.0` (một writer chạy
tuần tự nên không lỗi nào va chạm nổi), rồi `0.0` lần hai (module đã nạp vào
`sys.modules`, sửa file trên đĩa không đổi mã đang chạy).

> **Lần ba nguy hiểm nhất: `0.0` đọc y hệt "oracle mù hoàn toàn", trong khi sự
> thật là "lỗi cấy chưa từng chạy một dòng".**

### Bài 7. Thước LLM cũng phải được đo trước khi dùng

Đo pipeline bằng một thước chưa từng được hiệu chỉnh là cách kinh điển để một con
số sai đi qua mọi cổng mà vẫn mang nhãn "đã kiểm chứng".

Ba ngưỡng sàng lọc, chạy **trước** khi dùng judge:

| Kiểm tra | Ngưỡng | Không đạt thì |
|---|---|---|
| `J = sens + spec − 1` | ≥ 0,5 | **từ chối judge**, đừng hiệu chỉnh |
| `\|sens − spec\|` | ≤ 0,15 | judge thiên vị một phía |
| `n_calib` | ≥ 50 | chưa đủ để kết luận về judge |

Vì sao "từ chối, đừng hiệu chỉnh": `J < 0,5` nghĩa là hệ số khuếch đại lỗi
`1/J ≥ 2`, và khoảng sau hiệu chỉnh nở thành `[0, 1]` — vô thông tin.

**Bẫy thị giác nguy hiểm nhất:** judge tệ nhất bảng (0,70) lại cho khoảng **hẹp
nhất** sau khi clamp (0,1305), trong khi độ rộng thô là **6,68** — hẹp vì đã tràn
rồi bị cắt. Nhìn số đã clamp thì thước cong trông chắc chắn nhất. Bắt buộc phải
trả cả giá trị thô chưa clamp kèm cờ bão hoà.

Hai điều liên quan:

- Calibration set lấy ngẫu nhiên từ production thường có tỉ lệ pass ~95%, làm
  specificity gần như không đo được. Phải cân bằng khoảng 50/50.
- Hai judge cùng model **không phải** hai judge. *"Ở chỗ nào model sai, nó không
  tự bắt được chính nó."*

### Bài 8. Bốn bẫy quy trình — rẻ nhất để chặn, đắt nhất nếu bỏ qua

Tài liệu nền nói thẳng: bốn bẫy dưới đây nhân tỉ lệ claim sai lên **10 lần** và
thổi điểm lên **0,10**.

| Bẫy | Là gì | Mức thổi điểm |
|---|---|---|
| **Optional stopping** | Nhìn kết quả sau mỗi mẫu, dừng khi thấy đẹp | false claim 1,92% → **18,35%** |
| **Winner's curse** | Chọn phương án tốt nhất trên chính tập test đó | N=20 → **+0,1257** |
| **Golden set leakage** | Tinh chỉnh nhiều vòng trên cùng một bộ dữ liệu | 20 vòng → **+0,1284** |
| **Forking paths** | Chỉ báo cáo chiều nào ra kết quả đáng nói | 16 chiều → **+0,1028** |

Ba câu đáng nhớ:

> *Optional stopping là cái bẫy nguy hiểm nhất, vì nó mô tả đúng cách người ta làm
> việc một cách tự nhiên. Và mức nguy hiểm tăng theo độ gần ngưỡng — đúng lúc bạn
> muốn nhìn nhất.*

> *Wilson tính trên chính tập test đó **không** bắt được winner's curse.*

> *Forking paths làm điểm cao lên **trong khi ta cảm thấy hoàn toàn trung thực**.*

Cách chặn cả ba bẫy đầu, chi phí gần bằng 0 — **ba dòng metadata cho mỗi lần đo**:

```yaml
n_locked_before: 55      # chốt TRƯỚC khi chạy lệnh đầu tiên
candidates_tried: 3      # đã thử bao nhiêu phương án
tuning_rounds: 5         # đã tinh chỉnh bao nhiêu vòng trên bộ này
```

### Bài 9. Trích dẫn đúng nguồn không có nghĩa là nghĩa đúng

Phần này là bài học về hallucination, dựng bằng **lỗ hổng cài có chủ đích** trong
knowledge base của workshop:

1. **Khoảng trống chủ đích.** KB cố ý không chứa bất kỳ ngưỡng nào về một chỉ số
   nhất định. Câu hỏi mồi được thiết kế để chỉ có một đáp án đúng: *"KB hiện tại
   không có thông tin về việc này."* Bất kỳ câu trả lời nào kèm con số phần trăm
   đều là bịa. Kèm theo là **lệnh grep kiểm chứng khoảng trống còn nguyên**, để
   người đời sau "bổ sung cho đầy đủ" không vô tình xoá mất ca kiểm thử.

2. **Cắt ngữ cảnh làm lật nghĩa.** Một điều khoản chứa câu *"…thì tiêu chí đó được
   coi là **đã thoả mãn**"* được đặt **vắt qua mốc ký tự thứ 1200**, có đo đạc
   (câu bắt đầu ở 1096, cụm "đã thoả mãn" ở 1201). Phép cắt ngữ cảnh cứng ở 1200
   làm mất hẳn cụm đó, **nghĩa bị lật ngược**, trong khi trích dẫn vẫn trỏ đúng
   file, đúng dòng.

3. **Hai nguồn nói ngược nhau về cùng một thứ.** Một chuẩn coi im lặng là đã đạt;
   chuẩn kia coi im lặng là chưa đạt. Đây không phải lỗi soạn thảo — hai chuẩn trả
   lời hai câu hỏi khác nhau. Hệ quả: chính sách `N/A` phải **cấu hình theo từng
   nguồn**. Một công cụ chỉ có một luật `N/A` duy nhất sẽ sai với ít nhất một
   trong hai, và **sai một cách im lặng**.

### Phụ lục bài 9 — hai bài kiểm meta đáng học

**Đếm nơi gọi (chống code mồ côi).** Hàm viết ra phải có ≥1 nơi gọi thật ngoài
file định nghĩa và ngoài cây test. Ba điều làm khác cách quét ngây thơ:

- Chỉ đếm **cạnh gọi thật** (`ast.Call`). Một cái tên nằm trong dict đăng ký
  **không phải** một nơi gọi — hệ tham chiếu có `registerGate` với 0 handler thật
  mà bảng ánh xạ trông rất đầy đủ.
- Dùng **AST, không dùng regex**. Đã đo được ba lần: khảo sát bằng regex trên mã
  luôn trả tập **nhỏ hơn** thật.
- Có **đối chứng dương** và phát ra **mẫu số** `symbols_scanned`; `symbols_scanned
  == 0` là ĐỎ. Vì kết quả rỗng đọc y hệt nhau ở hai hoàn cảnh khác hẳn: "quét
  sạch, không có gì mồ côi" và "quét trượt, không bắt được gì".

**Trung thực về việc chạy bộ kiểm.** Nếu bộ kiểm của repo đích không chạy được thì
phải **nói ra**, không được đo tiếp. Hai lỗi cùng cho triệu chứng "63/63 ô chưa ai
canh" nhưng nghĩa khác hẳn nhau, và người đọc không có cách nào phân biệt. Cả hai
đều biến *"tôi không đo được"* thành *"tôi đã đo và kết quả tệ"*.

---

## Phần II — Áp dụng vào P-150

### Hiện trạng `eval/` (tính ngày 2026-08-10)

| Thành phần | Trạng thái |
|---|---|
| `eval/kpi.py` | Có KPI-1 / KPI-2 / KPI-4, trả `float \| None` |
| `eval/judge/` | Có `ports.py` / `runner.py` / `scoring.py`, mặc định tắt |
| `eval/datasets/kpi_questions.yaml` | **55 câu** |
| `eval/results/report.md` | Toàn `—`, chưa có số thật |
| Đã chạy lần nào chưa | **Chưa** |

Phân bố 55 câu:

```
intent:        ADVISORY 31 · CATALOG_LOOKUP 19 · OUT_OF_SCOPE  5
vehicle_type:  CAR      31 · ELECTRIC_MOTORBIKE 24
```

### Áp dụng 1 — Wilson cho `eval/kpi.py` (bài 1 + bài 2)

Hiện `factual_accuracy()` trả một `float` trần. Với `n = 55`, con số đó nghĩa là gì:

| Kết quả | Điểm | Wilson 95% | Biên dưới |
|---|---|---|---|
| 55/55 | 1,0000 | `[0,9347 – 1,0000]` | **93,5%** |
| 53/55 | 0,9636 | `[0,8768 – 0,9900]` | **87,7%** |
| 50/55 | 0,9091 | `[0,8042 – 0,9605]` | **80,4%** |
| 47/55 | 0,8545 | `[0,7384 – 0,9244]` | **73,8%** |

Đọc bảng này: **KPI-1 đạt 90,9% mà chỉ dám kết luận "thật sự ≥ 80,4%".** Ai đọc
`0.909` trần sẽ tưởng đã vượt ngưỡng 90%.

Điều này giải luôn chỗ `CHƯA CHỐT` về ngưỡng KPI trong
`docs/docs_buildagent_long/nghiemthu/A9-3.md`. Số câu tối thiểu để **biên dưới**
chạm ngưỡng, giả định toàn-pass:

| Ngưỡng muốn chứng minh | Số câu tối thiểu |
|---|---|
| ≥ 70% | 9 |
| ≥ 80% | 16 |
| ≥ 85% | 22 |
| **≥ 90%** | **35** |
| ≥ 95% | 73 |

Và số câu được phép sai mà vẫn giữ biên dưới ≥ 0,80:

```
n=55  → tối đa  5 câu sai        n=100 → tối đa 12 câu sai
n=80  → tối đa  8 câu sai        n=200 → tối đa 28 câu sai
```

**Kết luận cho P-150:** với 55 câu, ngưỡng hợp lý để chốt là **KPI-1 ≥ 80% theo
biên dưới Wilson 95%**. Muốn công bố "≥ 90%" thì phải toàn-pass và cần tối thiểu
35 câu — bộ hiện tại đủ số lượng, nhưng chỉ khi không sai câu nào.

Chú ý chiều ràng buộc, theo bài 2:

| KPI | Chiều | Dùng biên |
|---|---|---|
| KPI-1 Factual Accuracy | càng cao càng tốt (sàn) | **dưới** |
| KPI-4 Required-Slot Completion | càng cao càng tốt (sàn) | **dưới** |
| **KPI-2 Unwarned Over-Budget Rate** | **càng thấp càng tốt (trần)** | **trên** |

KPI-2 là chỗ dễ sai nhất, vì mẫu số của nó rất nhỏ — chỉ những lượt **có đề xuất
vượt ngân sách**:

```
0/3 vượt-ngân-sách không cảnh báo → [0,0000 – 0,5615]   trần thật có thể tới 56,2%
0/5                               → [0,0000 – 0,4345]
0/8                               → [0,0000 – 0,3244]
1/8                               → [0,0224 – 0,4709]
```

Nghĩa là **"0 ca vi phạm" trên 3 mẫu không chứng minh được gì.** Cần chủ động
thêm câu hỏi sinh ra tình huống vượt ngân sách để mẫu số KPI-2 đủ lớn.

Việc cần làm:

```
eval/stats/__init__.py
eval/stats/intervals.py      # hàm wilson() ở bài 1
```

rồi đổi ba hàm trong `eval/kpi.py` trả về dataclass thay vì `float`:

```python
@dataclass(frozen=True)
class Rate:
    """Một tỉ lệ kèm mẫu số và khoảng — không bao giờ là float trần."""
    k: int
    n: int
    point: float | None
    lower: float
    upper: float
    conf: float
```

> Phần `None` khi không đủ dữ liệu thì `eval/kpi.py` **đã làm đúng** rồi —
> docstring ghi rõ *"không đủ dữ liệu thì trả None, không trả 0 hay 1"*. Đây đúng
> tinh thần bài 6. Chỉ cần đẩy xa thêm một bước: trả kèm `k` và `n` để người đọc
> thấy mẫu số.

### Áp dụng 2 — Ba dòng metadata mỗi lần chạy (bài 8)

Rẻ nhất, chặn được nhiều nhất, làm trong 15 phút. Ghi vào
`eval/results/baseline.json` mỗi lần chạy:

```json
{
  "run_id": "2026-08-10T09:00:00Z",
  "n_locked_before": 55,
  "candidates_tried": 1,
  "tuning_rounds": 0,
  "dataset_sha256": "…",
  "prompt_sha256": "…"
}
```

Vì sao P-150 cần đúng cái này: ngay khi bắt đầu tinh chỉnh prompt agent theo
`kpi_questions.yaml`, dự án rơi thẳng vào **golden set leakage** — 20 vòng tinh
chỉnh thổi điểm lên +0,1284. Không ghi `tuning_rounds` thì sau ba tuần không ai
biết con số đã bị thổi bao nhiêu.

`eval/judge/scoring.py` đã có `regressions()` so điểm với lần chạy trước, nhưng
hiện chưa có file `previous` nào để so. Lưu `baseline.json` vào git giải quyết
luôn cả hai việc.

### Áp dụng 3 — Sàng lọc judge trước khi tin điểm (bài 7)

`eval/judge/runner.py` gọi LLM chấm 3 tiêu chí (`on_topic`, `advisor_voice`,
`complete`) nhưng **chưa có bước nào đo chính judge**. Ở trạng thái đó, mọi điểm
judge chấm chỉ là ý kiến chưa kiểm chứng, không phải bằng chứng.

Cần thêm `eval/judge/screen.py`:

```python
def judge_screen(sens: float, spec: float, n_calib: int) -> tuple[bool, list[str]]:
    """Sàng judge TRƯỚC khi dùng. Trả (đạt, danh sách lý do từ chối)."""
    reasons = []
    if sens + spec - 1 < 0.5:
        reasons.append(f"J={sens + spec - 1:.4f} < 0.5 — từ chối, không hiệu chỉnh")
    if abs(sens - spec) > 0.15:
        reasons.append(f"|sens-spec|={abs(sens - spec):.4f} > 0.15 — judge thiên vị")
    if n_calib < 50:
        reasons.append(f"n_calib={n_calib} < 50 — chưa đủ để kết luận về judge")
    return (not reasons, reasons)
```

Bộ calibration cần khoảng 50 cặp (câu hỏi, câu trả lời) đã có nhãn người, **cân
bằng ~50/50 đạt/không đạt** — không lấy ngẫu nhiên từ log thật, vì log thật lệch
về phía đạt và làm specificity gần như không đo được.

Judge trượt sàng thì **đổi cách dùng, không vứt**: judge đạt → dùng làm thước;
judge trượt → dùng làm chuông báo gọi người xem lại.

### Áp dụng 4 — Grid coverage cho không gian tư vấn (bài 4)

Đây là câu trả lời cho câu hỏi "55 câu là nhiều hay ít": nhiều hay ít **so với
cái gì**. Grid chính là cái mẫu số đó.

Đề xuất 5 axis cho agent P-150, mỗi axis phải trỏ tới enum có thật trong
`src/agents/domain/`:

| Axis | Giá trị | Neo vào code |
|---|---|---|
| `vehicle_type` | CAR · ELECTRIC_MOTORBIKE | enum loại xe |
| `intent` | ADVISORY · CATALOG_LOOKUP · OUT_OF_SCOPE | enum intent |
| `budget_band` | dưới catalog · trong catalog · vượt catalog | ngưỡng giá catalog |
| `slot_state` | đủ · thiếu 1 · thiếu nhiều | `slot_policy` |
| `turn` | lượt đầu · nhiều lượt | trạng thái hội thoại |

Kích thước không gian:

```
Cartesian đầy đủ  = 108 ô     (không thực tế)
t = 2 (pairwise)  =  67 ô     ← mẫu số nên dùng
t = 3             = 171 ô     (chỉ nâng ở zone nóng)
```

Bộ 55 câu hiện tại **chỉ gắn nhãn 2 trong 5 axis**, nên chỉ đo được trên hình
chiếu `vehicle_type × intent` (6 ô):

| | ADVISORY | CATALOG_LOOKUP | OUT_OF_SCOPE |
|---|---|---|---|
| **CAR** | 16 | 11 | 4 |
| **ELECTRIC_MOTORBIKE** | 15 | 8 | **1** |

Phủ 6/6 ô — nhưng ô `ELECTRIC_MOTORBIKE × OUT_OF_SCOPE` chỉ có **1 câu**, và
`1/1` toàn-pass chỉ đảm bảo ≥ 20,7%. Đó là một ô **gần như chưa được nhìn**, mà
bảng đếm thô không cho thấy điều đó.

Việc cần làm, theo thứ tự:

1. Thêm 3 trường `budget_band`, `slot_state`, `turn` vào từng câu trong
   `kpi_questions.yaml`. Chỉ là gắn nhãn, không cần viết câu mới.
2. Viết `eval/grid.py` đếm ô pairwise đã phủ / 67.
3. In ra con số đó trong `report.md` — *"bộ kiểm phủ X/67 ô"* là câu nói được
   nhiều hơn *"bộ kiểm có 55 câu"* rất nhiều.

### Áp dụng 5 — Zone chặn và luật không-gộp (bài 3 + bài 5)

Hai zone chặn của P-150, đặt `w` cao:

| Zone | Định nghĩa | Vì sao chặn |
|---|---|---|
| `budget_safety` | mọi ô có `budget_band = vượt catalog` | KPI-2 — đề xuất vượt ngân sách không cảnh báo là sai nghiệp vụ trực tiếp |
| `factual_grounding` | mọi ô có `intent = CATALOG_LOOKUP` | KPI-1 — bịa số liệu xe là lỗi mất niềm tin nặng nhất |

Luật báo cáo, áp thẳng từ bài 3:

- `report.md` in **điểm tệ nhất của từng zone**, giữ nguyên dạng per-zone.
- KPI trung bình toàn bộ chỉ để xem xu hướng, **không** được dùng làm cổng.
- Không viết hàm nào gộp các zone về một con số duy nhất.

Và luật `N/A` từ bài 5: câu hỏi nào bị đánh dấu không áp dụng thì phải ghi lý do
cụ thể, loại khỏi cả tử lẫn mẫu, và **in ra số câu bị loại**. Bốn lý do bị từ chối
thẳng: `hiếm gặp` · `khó test` · `ít người dùng` · `hệ thống sẽ chặn thôi`.

### Áp dụng 6 — Bộ adversarial dựng theo phương pháp (bài 9)

Lượt trước đã đề xuất bộ adversarial ~20 câu. Bài 9 cho **phương pháp** dựng nó,
thay vì nghĩ câu hỏi tuỳ hứng. Ba nhóm, mỗi nhóm kèm phép kiểm chứng để ca test
không bị vô hiệu về sau:

**Nhóm A — khoảng trống chủ đích (chống bịa số).**
Chọn một thông số **cố ý không có** trong catalog (ví dụ dung lượng pin của một
mẫu chưa nhập liệu). Đáp án đúng duy nhất là *"dữ liệu hiện chưa có thông tin
này"*. Kèm lệnh kiểm chứng khoảng trống còn nguyên, để người sau seed thêm dữ liệu
không âm thầm phá ca test:

```bash
# phải trả về 0 dòng
grep -rn "<mã xe>.*<thông số>" data-p150/
```

**Nhóm B — biên chunk làm lật nghĩa.**
P-150 dùng pgvector RAG (`tests/agents/unit/test_retrieval.py`,
`tests/agents/integration/test_retrieval_integration.py`). Chèn vào tài liệu một
câu **phủ định** — *"mẫu này **không** hỗ trợ sạc nhanh"* — đặt sao cho chữ
"không" vắt qua biên chunk. Nếu bot trả lời ngược lại mà trích dẫn vẫn đúng
file, đó là bug thật, thuộc loại khó phát hiện nhất.

Kèm phép đo vị trí ký tự y như cách workshop làm, để ca test không bị dịch mất
triệu chứng khi ai đó sửa tài liệu:

```python
text = open("data-p150/.../mo-ta-xe.md", encoding="utf-8").read()
S = "mẫu này không hỗ trợ sạc nhanh"
i = text.find(S)
assert i >= 0, "câu nguyên văn đã bị sửa"
assert i < CHUNK_SIZE < i + S.find("không"), "câu không còn vắt qua biên chunk"
```

**Nhóm C — hai nguồn mâu thuẫn.**
Cùng một thông số có hai giá trị khác nhau ở hai nguồn (catalog và tài liệu
marketing). Đáp án đạt: **nêu cả hai kèm nguồn**, không tự chọn một cái rồi im
lặng.

### Áp dụng 7 — Hai bài kiểm meta (phụ lục bài 9)

Cả hai đều hợp với P-150, nơi đã có sẵn nếp gate kiến trúc
(`tests/auth/integration/test_ci_gates.py`, `tests/agents/integration/test_layer_boundary.py`).

**`tests/test_no_orphans.py`** — quét `src/` bằng AST, khẳng định mọi hàm công
khai có ≥1 nơi gọi thật. Bắt buộc phát ra `symbols_scanned` và làm đỏ khi mẫu số
bằng 0. P-150 có 176 file Python, 19.580 dòng — dư sức có code mồ côi.

**`tests/agents/test_eval_honesty.py`** — nếu OpenAI API lỗi, quota hết, hoặc
dataset không parse được, thì KPI phải là `None` kèm lý do, **tuyệt đối không phải
0**. Nếu không, một sự cố hạ tầng sẽ đọc thành "agent trả lời sai hết".

---

## Lộ trình đề xuất

| # | Việc | Công sức | Chặn được gì |
|---|---|---|---|
| 1 | Wilson vào `eval/kpi.py` (áp dụng 1) | ~1 giờ | Công bố quá tự tin; chốt được ngưỡng KPI |
| 2 | 3 dòng metadata mỗi lần chạy (áp dụng 2) | ~15 phút | Optional stopping, winner's curse, golden set leakage |
| 3 | `judge_screen` + bộ calibration 50 cặp (áp dụng 3) | ~2 giờ + gán nhãn | Tin vào một cái thước cong |
| 4 | Test trung thực về eval (áp dụng 7, phần 2) | ~30 phút | Sự cố hạ tầng bị đọc thành lỗi agent |
| 5 | Gắn nhãn 3 axis + `eval/grid.py` (áp dụng 4) | ~1 ngày | Không biết bộ kiểm phủ bao nhiêu phần không gian |
| 6 | Zone chặn + luật per-zone trong report (áp dụng 5) | ~half ngày | Trung bình đẹp che vùng nguy hiểm |
| 7 | Bộ adversarial 3 nhóm (áp dụng 6) | ~1 ngày | Bịa số, lật nghĩa do chunk, mâu thuẫn nguồn |
| 8 | `test_no_orphans.py` (áp dụng 7, phần 1) | ~2 giờ | Code viết ra không ai gọi |

Bốn việc đầu làm xong trong một ngày và lấp đúng lỗ hổng lớn nhất hiện nay: **có
910 bài kiểm code, nhưng chưa có bằng chứng nào về chất lượng đầu ra của agent.**

---

## Một câu để nhớ

> Đừng để AI, một phần trăm coverage, hay một chỉ số tổng hợp tự biến mình thành
> bằng chứng. Hãy định nghĩa không gian rủi ro, thu bằng chứng chạy được cho từng
> phần, định lượng độ bất định, giữ dấu vết nguồn gốc, rồi để những cổng tất định
> quyết định phát hành.

Và cảnh báo cuối cùng của tài liệu nền — rủi ro cao nhất không phải sai công thức,
mà là **sùng bái công thức**:

> *Ai đó dán một khoảng tin cậy vào báo cáo, thấy một con số trông có vẻ khoa học,
> và không bao giờ đọc phần giải thích. Ta đổi một dạng tự tin mù quáng lấy một
> dạng khác — dạng này khó cãi hơn, vì nó có công thức.*

Phòng thủ duy nhất: công cụ phải **lên tiếng khi có gì sai**, không chỉ in số.
*Một con số im lặng thì dễ bỏ qua. Một dòng `WARNING: judge thiên về phía cho đạt`
thì không.*
