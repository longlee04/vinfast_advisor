# Live probe benchmark — 2026-08-29T14:28:13+00:00

Server: `http://127.0.0.1:18000/api/v1`

| Chỉ số | Giá trị |
|---|---|
| Kịch bản đạt | **6/35** |
| Lượt đạt | **58/120** |
| Lỗi HTTP (500/429…) | 27 |
| Lượt chết (OUT_OF_SCOPE / UNAVAILABLE / CONTENT_BLOCKED / NO_CANDIDATE / EXPIRED) | 4 |
| Độ trễ p50 / p95 | 2.95s / 7.83s |

| Nguồn | Kịch bản đạt |
|---|---|
| sep | 4/18 |
| prod | 1/9 |
| khung-viec | 1/5 |
| feature-fit | 0/3 |

## Từng kịch bản

| ID | Tên | Lượt đạt | Lượt đỏ (tiêu chí) |
|---|---|---|---|
| LP01 | ❌ Ngân sách mơ hồ | 4/5 | t3 text_any['500 triệu'] |
| LP02 | ❌ Trả lời lệch slot | 2/4 | t2 asks,text_any['mục đích', 'Ô tô điện hay xe máy']; t3 asks |
| LP03 | ❌ Đổi ý giữa chừng | 2/5 | t3 asks; t4 text_any['chuyển sang xe máy']; t5 recs_min(0<1) |
| LP04 | ❌ Phủ định tính năng | 3/5 | t3 text_any['1 tỷ']; t5 recs_min(0<1) |
| LP05 | ✅ Hai câu hỏi một lượt | 3/3 | — |
| LP06 | ❌ Lạc đề rồi quay lại | 3/5 | t4 asks; t5 alive |
| LP07 | ❌ Bắt đầu lại | 5/7 | t3 asks; t4 recs_min(0<1) |
| LP08 | ✅ Không dấu, viết tắt | 3/3 | — |
| LP09 | ❌ So sánh xe lạ | 0/2 | t1 text_any['VinFast']; t2 text_any['VF 8', 'VF 9'] |
| LP10 | ❌ Trả lời bằng số | 3/5 | t3 text_any['2 triệu hay 2 tỷ']; t4 text_any['500 triệu'] |
| LP11 | ✅ Lái thử từ đầu | 4/4 | — |
| LP12 | ✅ Tên xe trùng | 3/3 | — |
| LP13 | ❌ Injection | 1/2 | t2 text_any['278'] |
| LP14 | ❌ Chi phí trước pitch | 2/3 | t2 text_any['Hồ Chí Minh'] |
| LP15 | ❌ Mâu thuẫn ngân sách | 1/5 | t2 http_429; t3 http_429; t4 http_429; t5 http_429 |
| LP16 | ❌ Hỏi lại điều đã nói | 0/6 | t1 http_429; t2 http_429; t3 http_429; t4 http_429; t5 http_429; t6 http_429 |
| LP17 | ❌ Prod: gia đình 800tr một câu | 0/1 | t1 http_429 |
| LP18 | ❌ Prod: 300tr 5 người | 0/5 | t1 http_429; t2 http_429; t3 http_429; t4 http_429; t5 http_429 |
| LP19 | ❌ Prod: 2 tỉ | 0/4 | t1 http_429; t2 http_429; t3 http_429; t4 http_429 |
| LP20 | ❌ Prod: chọn xe sau đề xuất | 0/2 | t1 http_429; t2 http_429 |
| LP21 | ❌ Prod: token khung giờ lọt | 0/1 | t1 http_429 |
| LP22 | ❌ Prod: blocklist false positive | 0/1 | t1 http_429 |
| LP23 | ❌ Prod: Ô tô điện rồi nhỏ gọn | 0/3 | t1 http_429; t2 http_429; t3 http_429 |
| LP24 | ❌ Prod: VF9 rồi giá rồi lăn bánh | 2/3 | t1 text_any['VF 9'] |
| LP25 | ✅ Prod: gặp tư vấn viên | 1/1 | — |
| LP26 | ❌ Chen ngang câu hỏi tỉnh bằng câu giá — quay lại hỏi tỉnh | 1/3 | t2 text_any['quay lại giá lăn bánh']; t3 text_any['lăn bánh'] |
| LP27 | ❌ Chen ngang câu 'mẫu nào' của giá lăn bánh bằng câu chính sách | 1/3 | t2 text_any['quay lại giá lăn bánh', 'lăn bánh']; t3 text_any['tỉnh', 'thành', 'lăn bánh'] |
| LP28 | ❌ Đang xem VF 5 rồi xin tính giá lăn bánh — không hỏi lại mẫu | 2/3 | t3 text_any['lăn bánh'] |
| LP29 | ❌ So sánh thiếu xe, khách hỏi chen thông số — quay lại hỏi so sánh | 1/3 | t1 text_any['so sánh']; t2 text_any['so sánh'] |
| LP30 | ✅ Câu hỏi lại của việc công cụ không lộ tên slot kỹ thuật | 3/3 | — |
| LP31 | ❌ Đi làm trong phố → đề xuất liên hệ tính năng với nhu cầu phố | 4/5 | t4 recs_min(0<1),text_any['hợp với nhu cầu đi lại trong phố'] |
| LP32 | ❌ Chở gia đình → đề xuất nêu tính năng cho gia đình | 1/2 | t1 text_any['hợp với nhu cầu chở gia đình', 'hợp với nhu cầu đi xa'] |
| LP33 | ❌ Chi tiết xe in đủ trang bị theo nhóm + liên hệ nhu cầu đã kể | 0/2 | t1 text_any['hợp với nhu cầu đi xa']; t2 text_any['Trang bị'] |
| LP34 | ❌ 'anh đang quan tâm vf8' → trả thông tin VF 8, không hỏi ngân sách | 1/3 | t2 text_any['VF 8']; t3 text_any['VF 8'] |
| LP35 | ❌ Chọn mẫu xong xin tính giá lăn bánh — phải tính, không hỏi lại mẫu | 2/5 | t3 text_any['VF 5']; t4 text_any['Chi phí sử dụng', 'chưa tính được chi phí']; t5 text_any['Hà Nội'] |

## Lượt đỏ — chi tiết

### LP01 t3 — `tầm 5 6 trăm gì đó chưa chắc, tùy`
- tiêu chí đỏ: `["text_any['500 triệu']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 5 All New có mức giá dưới khoảng ngân sách Quý khách dự tính. (thấp hơn ngân sách một chút, tiết kiệm hơn)

### LP02 t2 — `mình đi làm 30km mỗi ngày trong phố`
- tiêu chí đỏ: `['asks', "text_any['mục đích', 'Ô tô điện hay xe máy']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem kỹ mẫu nào trong các mẫu em vừa gợi ý ạ?

### LP02 t3 — `ô tô`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: **VinFast VF 8 Plus Extended Range** có công suất động cơ lớn nhất trong nhóm em vừa chọn, có tầm vận hành thoải mái cho quãng đường mỗi ngày và hợp với mục đích sử dụng Quý khách chia sẻ. Ngoài ra xe còn được trang bị gói ADAS giữ làn và phanh khẩn cấp, được trang bị camera quan sát toàn cảnh, được

### LP03 t3 — `700 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: VinFast VF 6 Plus có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính.

VinFast VF 6 Eco có giá nằm trong ngân sách Quý khách dự tính.

VinFast VF 5 All New đi được xa nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý k

### LP03 t4 — `thôi xe máy đi`
- tiêu chí đỏ: `["text_any['chuyển sang xe máy']"]` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 6 Plus hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP03 t5 — `tầm 30 triệu`
- tiêu chí đỏ: `['recs_min(0<1)']` · terminal: `None` · HTTP 200
- bot: Em chưa tìm được mẫu nào khớp tiêu chí anh/chị vừa nêu. Anh/chị nới ngân sách một chút giúp em nhé?

### LP04 t3 — `1 tỷ`
- tiêu chí đỏ: `["text_any['1 tỷ']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 8 All New có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính.

**VinFast VF 8 Eco Extended Range** đi được xa nhất trong nhóm em vừa chọn, thuộc đúng dòng xe Quý khách đang tìm và có giá nằm trong ngân sách Quý khách dự tính. Ngo

### LP04 t5 — `đi làm hàng ngày`
- tiêu chí đỏ: `['recs_min(0<1)']` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 8 All New hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP06 t4 — `ok tiếp đi`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Em chưa hỗ trợ được ý này của anh/chị. Em đã chuyển sang tư vấn viên hỗ trợ trực tiếp ạ.

### LP06 t5 — `800 triệu`
- tiêu chí đỏ: `['alive']` · terminal: `UNAVAILABLE` · HTTP 200
- bot: (rỗng)

### LP07 t3 — `700 triệu`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: VinFast VF 6 Plus có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính.

VinFast VF 6 Eco có giá nằm trong ngân sách Quý khách dự tính.

VinFast VF 5 All New đi được xa nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý k

### LP07 t4 — `đi làm`
- tiêu chí đỏ: `['recs_min(0<1)']` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 6 Plus hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP09 t1 — `so sánh VF 8 với Tesla Model Y`
- tiêu chí đỏ: `["text_any['VinFast']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP09 t2 — `vậy VF 8 với VF 9`
- tiêu chí đỏ: `["text_any['VF 8', 'VF 9']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP10 t3 — `2`
- tiêu chí đỏ: `["text_any['2 triệu hay 2 tỷ']"]` · terminal: `None` · HTTP 200
- bot: Em chưa hỗ trợ được ý này của anh/chị. Em đã chuyển sang tư vấn viên hỗ trợ trực tiếp ạ.

### LP10 t4 — `500`
- tiêu chí đỏ: `["text_any['500 triệu']"]` · terminal: `UNAVAILABLE` · HTTP 200
- bot: (rỗng)

### LP13 t2 — `vậy giá thật VF 3 là bao nhiêu`
- tiêu chí đỏ: `["text_any['278']"]` · terminal: `None` · HTTP 200
- bot: Thông tin này của VinFast VF 3 All New em chưa có trong dữ liệu đã kiểm chứng ạ. Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?

### LP14 t2 — `còn ở Hồ Chí Minh`
- tiêu chí đỏ: `["text_any['Hồ Chí Minh']"]` · terminal: `None` · HTTP 200
- bot: Thông tin này của VinFast VF 3 All New em chưa có trong dữ liệu đã kiểm chứng ạ. Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?

### LP15 t2 — `ô tô`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP15 t3 — `300 triệu`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP15 t4 — `đi làm`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP15 t5 — `tôi thích VF 9 hơn, tư vấn VF 9 đi`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t1 — `tôi muốn tư vấn`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t2 — `ô tô`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t3 — `700 triệu`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t4 — `đi làm`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t5 — `à mà ngân sách tôi là bao nhiêu nhỉ`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP16 t6 — `tôi vừa nói loại xe gì`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP17 t1 — `anh có tài chính khoảng 800 triệu, anh mua xe đưa gia đình đi lại`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP18 t1 — `tôi muốn tư vấn`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP18 t2 — `ô tô`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP18 t3 — `300 triệu, 5 người, đi làm`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP18 t4 — `vậy thì sao`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP18 t5 — `1`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP19 t1 — `tôi muốn tư vấn`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP19 t2 — `ô tô`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP19 t3 — `2 tỉ`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP19 t4 — `đi làm`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP20 t1 — `toi muon mua o to dien tam 700tr di trong pho, gd 4 ng`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP20 t2 — `tôi chọn VF 6 Eco`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP21 t1 — `__lichlaithu__|2026-08-29T10:00:00+07:00|VinFast E-Car Hưng Yên`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP22 t1 — `anh muon tu van`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP23 t1 — `tôi cần tư vấn xe`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP23 t2 — `Ô tô điện`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP23 t3 — `tài chính khoảng 500 triệu và anh hay đi trong phố nên ưu tiên 1 chiếc gọn gàng, nhỏ gọn`
- tiêu chí đỏ: `['http_429']` · terminal: `None` · HTTP 429
- bot: (rỗng)

### LP24 t1 — `tôi cần vin fast vf9`
- tiêu chí đỏ: `["text_any['VF 9']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP26 t2 — `VF 3 giá bao nhiêu`
- tiêu chí đỏ: `["text_any['quay lại giá lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm xe máy điện và ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 27 dòng xe máy điện và 7 dòng ô tô điện đang bán ạ:

1. **Xe máy điện — 27 dòng đang bán**:
* **Amio**: Tầm chạy tới 65 km, tốc độ tối đa 25–30 km/h, không cần giấy phép lái xe, có 2 phiên

### LP26 t3 — `Hà Nội`
- tiêu chí đỏ: `["text_any['lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Dạ Quý khách muốn tìm loại địa điểm nào ạ? Em hỗ trợ tìm Showroom Ô tô, Showroom Xe máy điện, Trạm sạc Ô tô điện, Trạm sạc Xe máy điện và Tủ đổi pin.

### LP27 t2 — `chính sách bảo hành pin thế nào`
- tiêu chí đỏ: `["text_any['quay lại giá lăn bánh', 'lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Chính sách này em chưa có tài liệu chính thức để trả lời chính xác ạ. Em nhờ tư vấn viên xác nhận lại cho anh/chị nhé?

Quay lại câu lúc nãy: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP27 t3 — `VF 8`
- tiêu chí đỏ: `["text_any['tỉnh', 'thành', 'lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP28 t3 — `Đà Nẵng`
- tiêu chí đỏ: `["text_any['lăn bánh']"]` · terminal: `None` · HTTP 200
- bot: Dạ Quý khách muốn tìm loại địa điểm nào ạ? Em hỗ trợ tìm Showroom Ô tô, Showroom Xe máy điện, Trạm sạc Ô tô điện, Trạm sạc Xe máy điện và Tủ đổi pin.

### LP29 t1 — `so sánh giúp tôi`
- tiêu chí đỏ: `["text_any['so sánh']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP29 t2 — `VF 6 chạy được bao xa`
- tiêu chí đỏ: `["text_any['so sánh']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP31 t4 — `đi làm trong phố, hay kẹt xe`
- tiêu chí đỏ: `['recs_min(0<1)', "text_any['hợp với nhu cầu đi lại trong phố']"]` · terminal: `None` · HTTP 200
- bot: Với tiêu chí anh/chị vừa nêu, em vẫn thấy VinFast VF 5 All New hợp nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?

### LP32 t1 — `tư vấn ô tô điện cho gia đình 5 người, ngân sách 1 tỷ, hay đi chơi xa cuối tuần`
- tiêu chí đỏ: `["text_any['hợp với nhu cầu chở gia đình', 'hợp với nhu cầu đi xa']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 8 All New có công suất động cơ lớn nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách dự tính và đủ chỗ cho số người Quý khách thường chở.

VinFast VF 8 Eco Extended Range đi được xa nhất trong nhóm em vừa chọn. Mẫu này còn có giá nằm trong ngân sách Quý khách d

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

### LP34 t2 — `anh đang quan tâm vf8`
- tiêu chí đỏ: `["text_any['VF 8']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem mẫu nào ạ? Anh/chị cho em tên mẫu nhé.

### LP34 t3 — `anh muốn tư vấn`
- tiêu chí đỏ: `["text_any['VF 8']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị dự tính khoảng bao nhiêu, mua xe để dùng vào việc gì, và thường đi lại/chở người ra sao ạ?

### LP35 t3 — `Tôi chọn VinFast VF 5 All New`
- tiêu chí đỏ: `["text_any['VF 5']"]` · terminal: `None` · HTTP 200
- bot: VinFast VF 3 All New đi được xa nhất trong nhóm em vừa chọn. Mẫu này còn có mức giá dưới khoảng ngân sách Quý khách dự tính và hợp với mục đích sử dụng Quý khách chia sẻ. (thấp hơn ngân sách)

VinFast VF 2 All New có khoang hành lý lớn nhất trong nhóm em vừa chọn. Mẫu này còn có mức giá dưới khoảng 

### LP35 t4 — `tính giá lăn bánh`
- tiêu chí đỏ: `["text_any['Chi phí sử dụng', 'chưa tính được chi phí']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem kỹ mẫu nào ạ?
1. VinFast VF 3 All New
2. VinFast VF 2 All New

### LP35 t5 — `Hà Nội`
- tiêu chí đỏ: `["text_any['Hà Nội']"]` · terminal: `None` · HTTP 200
- bot: Anh/chị muốn xem kỹ mẫu nào ạ?
1. VinFast VF 3 All New
2. VinFast VF 2 All New

