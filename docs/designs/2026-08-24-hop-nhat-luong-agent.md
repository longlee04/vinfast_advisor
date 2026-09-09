# Hợp nhất ba nhánh agent thành một luồng

Ngày chốt: 2026-08-24 · Nhánh chính: `feature/build-agent` · Mốc: `7e201cf`

Tài liệu này ghi lại **quyết định** và **lý do**, không mô tả code. Ai đọc lại code sau
này mà thấy lạ thì tra ở đây trước.

---

## 1. Bối cảnh

Năm nhánh phát triển song song đã đụng nhau ở tầng hiểu ý khách.

| Nhánh | Mốc | Trạng thái |
|---|---|---|
| `feature/build-agent` | `7e201cf` | **Nhánh chính.** Đã hút trọn hai nhánh dưới. |
| `feature/tong-hop-uu-dai` | `7e201cf` | Trùng khít nhánh chính. Nút thắt hội thoại, ưu đãi, hàng đợi duyệt. |
| `feature/agent-integration` | `edf9a27` | Trả về nguyên trạng theo yêu cầu. Công đã bê sang nhánh chính. |
| `dev/ngoc` | `bc61656` | Chưa gộp. Tầng hiểu ý mới, chốt leo thang, phản ứng có căn cứ. |
| `feature/build-agent-long` | `cf2c854` | Chưa gộp. 90% đã có sẵn; phần mới chỉ là bốn cải tiến tìm địa điểm. |

---

## 2. Đánh giá: bản nào tự nhiên, bản nào khó phá

Hai câu hỏi cho hai câu trả lời khác nhau — đó chính là lý do phải **ghép**, không chọn một.

| Tiêu chí | `build-agent` | `dev/ngoc` | Thắng |
|---|---|---|---|
| Lượt **chủ động** (bot hỏi) | LLM diễn đạt lại câu hỏi slot; hỏi gộp ngân sách + mục đích; có câu recap; câu đóng khi khách mơ hồ | Không đụng tới | `build-agent` |
| Lượt **bị động** (khách phản ứng) | Khách chê "đắt quá" thì chạy lại cả pipeline tra cứu, đáp như chưa nghe | Nhận ra đó là phản ứng với câu vừa nói; tách hành vi hội thoại khỏi nhiệm vụ; có thang mức khẩn | `dev/ngoc` |
| Giọng nói | Lẫn lộn "Quý khách" / "anh/chị" / "bạn" tuỳ chỗ | Một chốt chuẩn hoá duy nhất ở cửa ra | `dev/ngoc` |
| Nền phòng thủ | 9 lớp (xem dưới) | Giữ nguyên toàn bộ 9 lớp | `build-agent` |
| Chốt tất định | Chỉ có "xin gặp người" | Thêm sự cố an toàn, thiếu dữ liệu thẩm quyền, guardrail hỏng → người | `dev/ngoc` |

**Chín lớp phòng thủ của `build-agent`:** chặn nội dung độc → phân loại phạm vi → cổng
rủi ro báo giá → chặn chữ số → chính sách claim → kiểm chứng ngữ nghĩa → guardrail
hậu sinh → cổng nháp → dọn đầu ra.

Quan trọng nhất là **chặn chữ số + claim placeholder**: mô hình không bao giờ được phép
tự viết ra một con số hay một lời hứa. Kể cả khi prompt injection dụ được model viết bậy,
guardrail vẫn chặn ở cửa. Đây là tài sản của `build-agent`, **không đụng vào**.

---

## 3. Các quyết định

### QĐ-01 — Xưng hô: "Quý khách"

- **Chọn:** "Quý khách", áp một lượt cho toàn hệ thống qua một chốt chuẩn hoá ở cửa ra.
- **Bỏ:** "anh/chị" của `dev/ngoc`, "bạn" của bản cũ.

Giọng hiện rải rác khắp nơi nên mỗi lần merge lại lệch một chỗ. Đặt chốt ở **cửa ra cuối
cùng**, sau guardrail, để không đường nào lách qua.

### QĐ-02 — Chốt tất định đứng trước mọi bước dùng LLM

- **Chọn:** ba ca cưỡng bức đẩy người — khách xin gặp người · sự cố nguy hiểm trên xe của
  chính khách · thiếu dữ liệu thẩm quyền cho câu hỏi chính sách hoặc TCO.
- **Bỏ:** để mô hình tự quyết có nên chuyển người hay không.

Khách kêu cứu thì không được để mô hình cân nhắc.

Ranh giới quan trọng: phải **đủ hai vế** — xe của chính khách *và* nguy hiểm đang xảy ra.
"Xe điện có bốc cháy không ạ" là câu hỏi kiến thức, không phải sự cố. Bắt nhầm nó thì mỗi
câu hỏi vu vơ lại đánh thức một tư vấn viên.

### QĐ-03 — Hợp hai nguồn tín hiệu leo thang, không lấy giao

- **Chọn:** khớp danh sách chuỗi **hoặc** nhãn LLM — một nguồn báo là đủ kích hoạt.
- **Bỏ:** chỉ dùng keyword (bản gốc `dev/ngoc`), hoặc bắt cả hai cùng khớp.

Hai nguồn hỏng theo hai kiểu khác nhau: danh sách chuỗi trượt câu diễn đạt lạ, LLM trượt
khi bị đánh lạc hướng hoặc câu quá ngắn. Lấy hợp thì một nguồn trượt vẫn còn nguồn kia;
lấy giao thì hai điểm mù cộng lại.

**Đánh đổi đã cân nhắc:** hợp hai nguồn làm tăng báo động giả. Nhưng báo động giả ở đây
chỉ là một tư vấn viên đọc thừa một tin — rẻ hơn nhiều so với bỏ sót một khách đang báo
cháy xe.

### QĐ-04 — Guardrail cạn lượt thử → chuyển người, không kết thúc lượt

- **Chọn:** rẽ sang hàng đợi duyệt, giữ nguyên bản nháp để tư vấn viên còn thứ để đọc và sửa.
- **Bỏ:** kết thúc lượt với `terminal_reason`, khách nhận câu xin lỗi rồi thôi.

Hết lượt thử không phải hết cách. Bản nháp chưa kiểm chứng được thì đúng người cần đọc nó
là tư vấn viên.

**Bẫy khi cài:** không được đặt `terminal_reason` và không được xoá `draft_answer`. Bộ
định tuyến đọc `terminal_reason` trước nên đặt nó sẽ rẽ về đúng nhánh chết vừa muốn tránh;
còn xoá bản nháp thì hàng đợi nhận một mục rỗng.

### QĐ-05 — Thay tầng hiểu ý bằng bản tách bốn chiều

- **Chọn:** tách rạch ròi *hành vi hội thoại* · *nhiệm vụ* · *chủ đề* · *mức khẩn* — bốn
  trục độc lập.
- **Bỏ:** gộp tất cả vào một bảng 7 nhãn ý định như hiện tại.

Không tách thì vĩnh viễn không xử được câu "vừa chê vừa hỏi" — mà đó là dạng câu khách nói
nhiều nhất. Một lượt vừa phàn nàn vừa hỏi thông tin thì **hành vi vẫn là phàn nàn**, nhiệm
vụ đi theo câu hỏi chính.

Đây là bước tốn nhất: mọi test hiện có về ý định sẽ phải viết lại.

### QĐ-06 — Không merge cả nhánh, bê từng tính năng

- **Chọn:** bê từng ý tưởng sang, tự viết test, commit riêng từng bước.
- **Bỏ:** merge `dev/ngoc` và `feature/build-agent-long` nguyên si.

`dev/ngoc` mang theo **1.300 file rác** — thư mục kết quả eval, và nguyên một bản sao của
cả repo kèm file nén. Merge nguyên si là nhét đống đó vào lịch sử vĩnh viễn.

`feature/build-agent-long` thì ngược lại: bản `nearby_location` của nó **cũ hơn** bản đang
chạy, merge vào sẽ đè lùi.


### QĐ-07 — Ngân sách LLM dùng hai hạn mức tách rời

- **Chọn:** `REQUIRED = 4` (1 trích slot + 1 lượt thử synthesis + 2 retry A6-1) và
  `OPTIONAL = 1` nằm **ngoài** bốn slot kia.
- **Bỏ:** một trần chung 4 cho tất cả.

`detect_bottleneck` nằm ngay trên đường tới `synthesize`, nên một lượt cần
`1 + 1 + 3 = 5`. Với trần chung đã giữ chỗ 4/4 thì phần "chưa giữ chỗ" luôn bằng 0 —
tức cấm vĩnh viễn mọi việc tuỳ chọn, kể cả câu dẫn tìm địa điểm và diễn đạt lại câu hỏi
đang chạy tốt. Tách hạn mức biến điều khoản *"việc tuỳ chọn không cướp slot bắt buộc"*
thành **bất biến của cấu trúc dữ liệu**, không còn là con số phải chỉnh lại mỗi khi
thêm một việc tuỳ chọn.

Kiểm kê thực tế tìm ra **7** nơi chạm provider, không phải 5:
`OpenAIBottleneckDetector` **tự dựng client OpenAI riêng**, né hoàn toàn `LLMPort`.

### QĐ-08 — Đếm theo LƯỢT THỬ synthesis, không gom lô

- **Chọn:** một lượt thử synthesis = một slot, bất kể bao nhiêu xe.
- **Bỏ:** đếm từng lần chạm provider + gom 20 xe vào một prompt.

Fan-out theo từng xe là **tính chất an toàn có chủ ý**, ghi trong docstring:
*"mỗi call LLM chỉ thấy facts và quotes của xe đó"*. Gộp lô cho mô hình nhìn thấy dữ
liệu cả cụm và mở đường gán nhầm thông số giữa các xe — đúng loại lỗi mà chín lớp
guardrail sinh ra để chặn. Gộp lô cũng làm mất `return_exceptions=True`: một xe hỏng
kéo sập cả cụm.

Thứ cần chặn là số **lượt thử**, không phải số xe — số xe được chặn ở QĐ-09.

### QĐ-09 — Trần LIỆT KÊ tách khỏi trần THUYẾT PHỤC

- **Chọn:** `MAX_RECOMMENDATIONS = 20` cho danh sách; `MAX_PITCHED_RECOMMENDATIONS = 3`
  cho đoạn văn thuyết phục. Xe ngoài top vẫn về đủ thẻ, dựng thuần từ snapshot.
- **Bỏ:** hạ `MAX_RECOMMENDATIONS` về 3.

`baa31ab` nới 3 → 20 để vá bug thật: khách hỏi "xe từ 200–900 triệu" có sáu mẫu thoả mà
chỉ ba mẫu được trả, nên hai câu hỏi khác nhau ra cùng một đáp án. Bản vá đúng, nhưng
`synthesize` gọi LLM một lần cho mỗi xe nên nó nới luôn chi phí lên `20 × 3 = 60` lần
gọi mỗi lượt chat.

Hai việc bị buộc chung một con số. Tách ra thì cả hai ý định cùng đúng: liệt kê không
tốn gì (tên, giá, ảnh đều từ snapshot), thuyết phục dừng ở nơi nó có tác dụng.

Chi phí ca xấu nhất: **60 → 9**.

---


### QĐ-10 — Tách QUOTA khỏi METRIC

- **Chọn:** quota tiêu ở **tầng điều phối** (một thao tác = một slot); lớp bọc provider
  chỉ **đo** số lần chạm thật.
- **Bỏ:** lớp bọc provider vừa đo vừa tiêu quota.

Trộn hai vai thì một thao tác nội bộ fan-out ba lần sẽ âm thầm tiêu ba slot, và tệ hơn:
lớp bọc có quyền **từ chối giữa chừng** — khách nhận nửa câu trả lời. Chặn phải xảy ra
TRƯỚC khi thao tác bắt đầu, ở nơi biết ranh giới thao tác.

Đổi lại ta có con số thứ hai: `provider_calls` nói *"lượt thử này tốn bao nhiêu lần
gọi"*, trong khi quota chỉ nói *"còn được làm thêm thao tác nào không"*. Không có metric
thì chi phí thật trôi đi mà quota vẫn báo xanh.

Ngoại lệ có chủ ý: phát hiện nút thắt tự xin slot, vì nó là một thao tác trọn vẹn không
có tầng điều phối nào khác đứng trước.

---

## 4. Luồng đích

Nguyên tắc xếp thứ tự: chốt tất định đứng trước mọi thứ dùng LLM; guardrail không ai được
đụng; chuẩn hoá giọng đặt cuối để không đường nào lách qua.

| # | Chặng | Nội dung | Nguồn |
|---|---|---|---|
| 1 | Chặn nội dung độc | Lọc trước khi tốn một lần gọi mô hình | giữ nguyên |
| 2 | **Chốt tất định** | Xin gặp người · sự cố an toàn. Khớp keyword hoặc nhãn LLM | mới, cao nhất |
| 3 | Hiểu lượt | Hành vi · nhiệm vụ · chủ đề · mức khẩn — bốn trục tách bạch | thay mới |
| 4 | Rẽ nhánh | Phản ứng có căn cứ · tư vấn · tra cứu/so sánh/TCO/trạm sạc · thiếu dữ liệu thẩm quyền thì đẩy người | bồi thêm |
| 5 | Sinh câu + guardrail | Chặn chữ số · claim placeholder · kiểm chứng ngữ nghĩa. Hỏng ba lần thì chuyển người | giữ nguyên |
| 6 | Cổng rủi ro báo giá | Mặc cả, ưu đãi, cam kết tài chính đều dừng chờ người | giữ nguyên |
| 7 | Chuẩn hoá giọng | Mọi câu ra ngoài đều xưng "em", gọi "Quý khách" | mới, chốt cuối |
| 8 | Dọn đầu ra | Xoá UUID và mọi dấu vết nội bộ | giữ nguyên |

---

## 5. Thứ tự triển khai

Kế hoạch thi hành chi tiết nằm ở `.omo/plans/hop-nhat-luong-agent.md` (13 todo).
Bảng dưới là bản rút gọn theo trạng thái.

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Audit dirty work, chốt baseline | ✅ baseline = 5 node đỏ có sẵn |
| 2 | Ngân sách gọi LLM — hai hạn mức tách rời | ✅ `89f78b7` |
| 2b | Tách trần liệt kê khỏi trần thuyết phục | ✅ `e11c7f0` |
| 3 | Hợp đồng leo thang tất định | ✅ `e9ea2f8` |
| 4 | Handoff giao dịch + chốt trước LLM | ⬜ |
| 5 | Guardrail cạn lượt → người, không rò bản nháp | ⬜ thừa kế 2 ca đỏ nền |
| 6 | Tách bốn trục hiểu lượt | ⬜ rủi ro cao |
| 7 | Chốt leo thang ngữ nghĩa sau trích xuất | ⬜ |
| 8 | Phản ứng có căn cứ | ⬜ |
| 9 | Chuẩn hoá giọng, số, dọn dấu vết nội bộ | ⬜ |
| 10 | Nghiệm lại tìm địa điểm + TCO hiện hữu | ⬜ chỉ regression |
| 11 | Eval bốn trục | ⬜ |
| 12 | Hợp đồng REST/SSE/WebSocket/HITL/replay | ⬜ |
| 13 | Migration, lint, bộ đầy đủ | ⬜ |

**Đính chính so với bản đầu:** *"bốn cải tiến tìm địa điểm"* từng được xếp là việc phải
làm. Sai — đo lại sau khi `build-agent` fast-forward lên `7e201cf` thì cả bốn **đã có
sẵn**; phần chênh còn lại với `feature/build-agent-long` chỉ là xuống dòng ruff. Todo 10
vì vậy chỉ còn là nghiệm lại, không port gì.

**Đã hoãn sang plan riêng:** policy Q&A / authority pipeline dựng từ `PolicySearchPort`
đang ngủ đông. Nó là làm tính năng mới, không phải hợp nhất.

---

## 6. Rủi ro đã biết

**Chốt leo thang dựa trên danh sách chuỗi cứng.** Khách viết khác đi — "cho tôi nói chuyện
với người", "xe em đang khét lẹt" — là trượt. Nhưng nó **trượt về phía an toàn**: không
khớp thì chạy luồng thường, vẫn còn moderation, cổng phạm vi và guardrail đỡ. Đây là độ
phủ thấp, không phải lỗ hổng. Bước 7 bù bằng nhãn LLM chạy song song.

**Mặt tấn công chưa vá.** Lớp sửa lỗi gõ viết lại câu khách trước khi phân loại. Kẻ tấn
công có thể soạn chuỗi mà bộ sửa lỗi "nắn" thành câu hợp lệ. Câu gốc vẫn được giữ song song
cho audit và guardrail — nhưng **cổng phạm vi lại chấm trên câu đã nắn**. Cần rà lại, chưa
nằm trong bảy bước trên.

---

## 7. Việc còn nợ, ngoài phạm vi hợp nhất

- `test_prd_acceptance_e2e` chập chờn theo thứ tự chạy — chạy riêng thì xanh, chạy cả bộ
  thì thỉnh thoảng đỏ. Có test nào đó phía trước làm bẩn trạng thái.
- `test_staff_identity_wiring` đỏ sẵn từ trước khi hợp nhất.
- Cơ sở dữ liệu agent trên máy dev kẹt: cột `profile_snapshot` tồn tại sẵn nên migration
  mới báo trùng cột. Muốn chạy ứng dụng local phải tạo lại `p150_agent`. Test không dính
  vì dùng cơ sở dữ liệu tạm.
- Dãy thẻ thống kê và thẻ Lead ở màn hàng đợi tư vấn viên đã bị bỏ khi chọn bản có tab.
  Đắp lại được bất cứ lúc nào.
