# Live probe benchmark — 2026-08-30T10:02:50+00:00

Server: `http://127.0.0.1:18000/api/v1`

| Chỉ số | Giá trị |
|---|---|
| Kịch bản đạt | **14/35** |
| Lượt đạt | **86/120** |
| Lỗi HTTP (500/429…) | 0 |
| Lượt chết (OUT_OF_SCOPE / UNAVAILABLE / CONTENT_BLOCKED / NO_CANDIDATE / EXPIRED) | 3 |
| Độ trễ p50 / p95 | 4.0s / 8.08s |

| Nguồn | Kịch bản đạt |
|---|---|
| sep | 5/18 |
| prod | 8/9 |
| khung-viec | 1/5 |
| feature-fit | 0/3 |

## Từng kịch bản

| ID | Tên | Lượt đạt | Lượt đỏ (tiêu chí) |
|---|---|---|---|
| LP01 | ❌ Ngân sách mơ hồ | 4/5 | t3 text_any['500 triệu'] |
| LP02 | ❌ Trả lời lệch slot | 2/4 | t2 asks; t3 asks |
| LP03 | ❌ Đổi ý giữa chừng | 3/5 | t3 asks; t5 recs_min(0<1) |
| LP04 | ❌ Phủ định tính năng | 4/5 | t3 text_any['1 tỷ'] |
| LP05 | ✅ Hai câu hỏi một lượt | 3/3 | — |
| LP06 | ❌ Lạc đề rồi quay lại | 3/5 | t4 asks; t5 alive |
| LP07 | ❌ Bắt đầu lại | 6/7 | t3 asks |
| LP08 | ✅ Không dấu, viết tắt | 3/3 | — |
| LP09 | ❌ So sánh xe lạ | 1/2 | t1 text_any['VinFast'] |
| LP10 | ❌ Trả lời bằng số | 3/5 | t3 text_any['2 triệu hay 2 tỷ']; t4 text_any['500 triệu'] |
| LP11 | ✅ Lái thử từ đầu | 4/4 | — |
| LP12 | ✅ Tên xe trùng | 3/3 | — |
| LP13 | ❌ Injection | 1/2 | t2 text_any['278'] |
| LP14 | ❌ Chi phí trước pitch | 2/3 | t2 text_any['Hồ Chí Minh'] |
| LP15 | ❌ Mâu thuẫn ngân sách | 3/5 | t3 asks; t5 text_any['cao hơn ngân sách'] |
| LP16 | ❌ Hỏi lại điều đã nói | 3/6 | t3 asks; t5 text_any['700 triệu']; t6 text_any['ô tô điện'] |
| LP17 | ✅ Prod: gia đình 800tr một câu | 1/1 | — |
| LP18 | ✅ Prod: 300tr 5 người | 5/5 | — |
| LP19 | ❌ Prod: 2 tỉ | 3/4 | t3 text_any['2 tỷ'] |
| LP20 | ✅ Prod: chọn xe sau đề xuất | 2/2 | — |
| LP21 | ✅ Prod: token khung giờ lọt | 1/1 | — |
| LP22 | ✅ Prod: blocklist false positive | 1/1 | — |
| LP23 | ✅ Prod: Ô tô điện rồi nhỏ gọn | 3/3 | — |
| LP24 | ✅ Prod: VF9 rồi giá rồi lăn bánh | 3/3 | — |
| LP25 | ✅ Prod: gặp tư vấn viên | 1/1 | — |
| LP26 | ❌ Chen ngang câu hỏi tỉnh bằng câu giá — quay lại hỏi tỉnh | 1/3 | t2 text_any['quay lại giá lăn bánh']; t3 text_any['lăn bánh'] |
| LP27 | ❌ Chen ngang câu 'mẫu nào' của giá lăn bánh bằng câu chính sách | 2/3 | t2 text_any['quay lại giá lăn bánh', 'lăn bánh'] |
| LP28 | ❌ Đang xem VF 5 rồi xin tính giá lăn bánh — không hỏi lại mẫu | 1/3 | t2 text_any['VF 5']; t3 text_any['lăn bánh'] |
| LP29 | ❌ So sánh thiếu xe, khách hỏi chen thông số — quay lại hỏi so sánh | 1/3 | t1 text_any['so sánh']; t2 text_any['so sánh'] |
| LP30 | ✅ Câu hỏi lại của việc công cụ không lộ tên slot kỹ thuật | 3/3 | — |
| LP31 | ❌ Đi làm trong phố → đề xuất liên hệ tính năng với nhu cầu phố | 4/5 | t4 text_any['hợp với nhu cầu đi lại trong phố'] |
| LP32 | ❌ Chở gia đình → đề xuất nêu tính năng cho gia đình | 1/2 | t1 text_any['hợp với nhu cầu chở gia đình', 'hợp với nhu cầu đi xa'] |
| LP33 | ❌ Chi tiết xe in đủ trang bị theo nhóm + liên hệ nhu cầu đã kể | 0/2 | t1 text_any['hợp với nhu cầu đi xa']; t2 text_any['Trang bị'] |
| LP34 | ✅ 'anh đang quan tâm vf8' → trả thông tin VF 8, không hỏi ngân sách | 3/3 | — |
| LP35 | ❌ Chọn mẫu xong xin tính giá lăn bánh — phải tính, không hỏi lại mẫu | 2/5 | t3 text_any['VF 5']; t4 text_any['Chi phí sử dụng', 'chưa tính được chi phí']; t5 text_any['Hà Nội'] |

## Lượt đỏ — chi tiết

### LP01 t3 — `tầm 5 6 trăm gì đó chưa chắc, tùy`
- tiêu chí đỏ: `["text_any['500 triệu']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 5 All New có mức giá dưới khoảng ngân sách Quý khách dự tính. (thấp hơn ngân sách một chút, tiết kiệm hơn)

### LP02 t2 — `mình đi làm 30km mỗi ngày trong phố`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Với nhu cầu đi làm, VinFast VF 8 Plus Extended Range hợp vì thuộc đúng dòng xe Quý khách đang tìm.
VinFast VF 8 Plus Extended Range có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có tầm vận hành thoải mái cho quãng đường mỗi ngày và hợp với mục đích sử dụng Quý khách chia sẻ.

Với

### LP02 t3 — `ô tô`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 8 Plus Extended Range hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP03 t3 — `700 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em gợi ý anh/chị mấy mẫu sau ạ:
1. VinFast VF 6 Plus — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
2. VinFast VF 6 Eco — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
3. VinFast VF 5 All New — hợp vì thuộc đú

### LP03 t5 — `tầm 30 triệu`
- tiêu chí đỏ: `['recs_min(0<1)']` · terminal: `None` · HTTP 200
- bot: Em gợi ý anh/chị mấy mẫu sau ạ:
1. VinFast Evo Max Kèm Pin — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
2. VinFast Feliz II Kèm Pin — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
3. VinFast Feliz Lite Stand

### LP04 t3 — `1 tỷ`
- tiêu chí đỏ: `["text_any['1 tỷ']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 8 All New có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính.

**VinFast VF 8 Eco Extended Range** đi được xa nhất trong nhóm em vừa chọn, thuộc đúng dòng xe Quý khách đang tìm và có giá nằm trong ngân sách Quý khách dự tính. Ngo

### LP06 t4 — `ok tiếp đi`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em chưa hỗ trợ được ý này của anh/chị. Em đã chuyển sang tư vấn viên hỗ trợ trực tiếp ạ.

### LP06 t5 — `800 triệu`
- tiêu chí đỏ: `['alive']` · terminal: `UNAVAILABLE` · HTTP 200
- bot: (rỗng)

### LP07 t3 — `700 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em gợi ý anh/chị mấy mẫu sau ạ:
1. VinFast VF 6 Plus — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
2. VinFast VF 6 Eco — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
3. VinFast VF 5 All New — hợp vì thuộc đú

### LP09 t1 — `so sánh VF 8 với Tesla Model Y`
- tiêu chí đỏ: `["text_any['VinFast']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP10 t3 — `2`
- tiêu chí đỏ: `["text_any['2 triệu hay 2 tỷ']"]` · terminal: `None` · HTTP 200
- bot: Em chưa hỗ trợ được ý này của anh/chị. Em đã chuyển sang tư vấn viên hỗ trợ trực tiếp ạ.

### LP10 t4 — `500`
- tiêu chí đỏ: `["text_any['500 triệu']"]` · terminal: `UNAVAILABLE` · HTTP 200
- bot: (rỗng)

### LP13 t2 — `vậy giá thật VF 3 là bao nhiêu`
- tiêu chí đỏ: `["text_any['278']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị đăng ký xe ở tỉnh/thành nào để em tính đúng phí lăn bánh ạ?

### LP14 t2 — `còn ở Hồ Chí Minh`
- tiêu chí đỏ: `["text_any['Hồ Chí Minh']"]` · terminal: `None` · HTTP 200
- bot: Thông tin này của VinFast VF 3 All New em chưa có trong dữ liệu đã kiểm chứng ạ. Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?

### LP15 t3 — `300 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em gợi ý anh/chị mấy mẫu sau ạ:
1. VinFast VF 3 All New — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
2. VinFast VF 2 All New — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính

### LP15 t5 — `tôi thích VF 9 hơn, tư vấn VF 9 đi`
- tiêu chí đỏ: `["text_any['cao hơn ngân sách']"]` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 3 All New hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP16 t3 — `700 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em gợi ý anh/chị mấy mẫu sau ạ:
1. VinFast VF 6 Plus — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
2. VinFast VF 6 Eco — hợp vì thuộc đúng dòng xe Quý khách đang tìm; có giá nằm trong ngân sách Quý khách dự tính
3. VinFast VF 5 All New — hợp vì thuộc đú

### LP16 t5 — `à mà ngân sách tôi là bao nhiêu nhỉ`
- tiêu chí đỏ: `["text_any['700 triệu']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem kỹ mẫu nào trong các mẫu em vừa gợi ý ạ?

### LP16 t6 — `tôi vừa nói loại xe gì`
- tiêu chí đỏ: `["text_any['ô tô điện']"]` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 6 Plus hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP19 t3 — `2 tỉ`
- tiêu chí đỏ: `["text_any['2 tỷ']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 9 All New đi được xa nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính.

VinFast VF 8 Plus Extended Range có giá nằm trong ngân sách Quý khách dự tính.

**VinFast VF 8 All New** sạc nhanh nhất trong nhóm em vừa chọn, thuộc đúng dòng xe Quý khách đang tì

### LP26 t2 — `VF 3 giá bao nhiêu`
- tiêu chí đỏ: `["text_any['quay lại giá lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm xe máy điện và ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 27 dòng xe máy điện và 7 dòng ô tô điện đang bán ạ:

1. **Xe máy điện — 27 dòng đang bán**:
* **Amio**: Tầm chạy tới 65 km, tốc độ tối đa 25–30 km/h, không cần giấy phép lái xe, có 2 phiên

### LP26 t3 — `Hà Nội`
- tiêu chí đỏ: `["text_any['lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Thông tin này của VinFast VF 5 All New em chưa có trong dữ liệu đã kiểm chứng ạ. Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?

### LP27 t2 — `chính sách bảo hành pin thế nào`
- tiêu chí đỏ: `["text_any['quay lại giá lăn bánh', 'lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Chính sách này em chưa có tài liệu chính thức để trả lời chính xác ạ. Em nhờ tư vấn viên xác nhận lại cho anh/chị nhé?

Quay lại câu lúc nãy: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP28 t2 — `tính giá lăn bánh`
- tiêu chí đỏ: `["text_any['VF 5']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị đăng ký xe ở tỉnh/thành nào để em tính đúng phí lăn bánh ạ?

### LP28 t3 — `Đà Nẵng`
- tiêu chí đỏ: `["text_any['lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Thông tin này của VinFast VF 5 All New em chưa có trong dữ liệu đã kiểm chứng ạ. Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?

### LP29 t1 — `so sánh giúp tôi`
- tiêu chí đỏ: `["text_any['so sánh']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP29 t2 — `VF 6 chạy được bao xa`
- tiêu chí đỏ: `["text_any['so sánh']"]` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast VF 6 là mẫu xe thuần điện của VinFast.

1. **Thông số kỹ thuật**:
* **Động cơ & Vận hành**: công suất 100 kW, mô-men xoắn 135 Nm, dung lượng pin 59.6 kWh, quãng đường mỗi lần sạc 315 km (WLTP), tốc độ tối đa 175 km/h, sạc nhanh 24 phút (10–70%)

2. **Trang bị**:
* **An toàn**: móc gắn gh

### LP31 t4 — `đi làm trong phố, hay kẹt xe`
- tiêu chí đỏ: `["text_any['hợp với nhu cầu đi lại trong phố']"]` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 5 All New hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP32 t1 — `tư vấn ô tô điện cho gia đình 5 người, ngân sách 1 tỷ, hay đi chơi xa cuối tuần`
- tiêu chí đỏ: `["text_any['hợp với nhu cầu chở gia đình', 'hợp với nhu cầu đi xa']"]` · terminal: `None` · HTTP 200
- bot: Với nhu cầu hay đi chơi xa cuối tuần cho 5 người, VinFast VF 8 All New hợp vì thuộc đúng dòng xe Quý khách đang tìm.
VinFast VF 8 All New có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính và đủ chỗ cho số người Quý khách thường chở.

Với n

### LP33 t1 — `tôi hay đi tỉnh về quê, chi tiết VF 8 giúp tôi`
- tiêu chí đỏ: `["text_any['hợp với nhu cầu đi xa']"]` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm xe máy điện và ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 27 dòng xe máy điện và 7 dòng ô tô điện đang bán ạ:

1. **Xe máy điện — 27 dòng đang bán**:
* **Amio**: Tầm chạy tới 65 km, tốc độ tối đa 25–30 km/h, không cần giấy phép lái xe, có 2 phiên

### LP33 t2 — `chi tiết VF 8`
- tiêu chí đỏ: `["text_any['Trang bị']"]` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm xe máy điện và ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 27 dòng xe máy điện và 7 dòng ô tô điện đang bán ạ:

1. **Xe máy điện — 27 dòng đang bán**:
* **Amio**: Tầm chạy tới 65 km, tốc độ tối đa 25–30 km/h, không cần giấy phép lái xe, có 2 phiên

### LP35 t3 — `Tôi chọn VinFast VF 5 All New`
- tiêu chí đỏ: `["text_any['VF 5']"]` · terminal: `None` · HTTP 200
- bot: Với nhu cầu phục vụ gia đình, VinFast VF 3 All New hợp vì thuộc đúng dòng xe Quý khách đang tìm.
**VinFast VF 3 All New** đi được xa nhất trong nhóm em vừa chọn, hợp với mục đích sử dụng Quý khách chia sẻ và có mức giá dưới khoảng ngân sách Quý khách dự tính. Ngoài ra xe còn được trang bị kết nối Ap

### LP35 t4 — `tính giá lăn bánh`
- tiêu chí đỏ: `["text_any['Chi phí sử dụng', 'chưa tính được chi phí']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem kỹ mẫu nào ạ?
1. VinFast VF 3 All New
2. VinFast VF 2 All New

### LP35 t5 — `Hà Nội`
- tiêu chí đỏ: `["text_any['Hà Nội']"]` · terminal: `None` · HTTP 200
- bot: Dạ Quý khách muốn tìm loại địa điểm nào ạ? Em hỗ trợ tìm Showroom Ô tô, Showroom Xe máy điện, Trạm sạc Ô tô điện, Trạm sạc Xe máy điện và Tủ đổi pin.

Quay lại câu lúc nãy: Anh/chị muốn xem kỹ mẫu nào ạ?
1. VinFast VF 3 All New
2. VinFast VF 2 All New

