# Live probe benchmark — 2026-08-30T13:43:53+00:00

Server: `http://127.0.0.1:18000/api/v1` · bộ dữ liệu: `live_probe_v2.json`

| Chỉ số | Giá trị |
|---|---|
| Kịch bản đạt | **39/46** |
| Lượt đạt | **99/106** |
| Lỗi HTTP (500/429…) | 0 |
| Lượt chết (OUT_OF_SCOPE / UNAVAILABLE / CONTENT_BLOCKED / NO_CANDIDATE / EXPIRED) | 1 |
| Độ trễ p50 / p95 | 3.65s / 8.46s |

| Nguồn | Kịch bản đạt |
|---|---|
| v2-intake | 8/9 |
| v2-refine | 6/6 |
| v2-choice | 6/6 |
| v2-fit | 3/5 |
| v2-task | 9/11 |
| v2-guard | 7/9 |

## Từng kịch bản

| ID | Tên | Lượt đạt | Lượt đỏ (tiêu chí) |
|---|---|---|---|
| V2-01 | ✅ Một câu hỏi duy nhất rồi đề xuất — không hỏi từng slot | 3/3 | — |
| V2-02 | ✅ Biết loại xe từ đầu — bày dải sản phẩm, KHÔNG hỏi lại loại | 3/3 | — |
| V2-03 | ✅ Câu đầu đủ ý → đề xuất ngay lượt đầu | 1/1 | — |
| V2-04 | ✅ Không nói loại xe, 30 triệu → suy ra xe máy điện | 2/2 | — |
| V2-05 | ✅ SUÝT V2-04: 500 triệu không dấu → ô tô điện, không phải xe máy | 1/1 | — |
| V2-06 | ✅ Ranh giới 150 triệu — vẫn về nhánh xe máy điện | 1/1 | — |
| V2-07 | ❌ PHỦ ĐỊNH hỏi bù slot: thiếu ngân sách vẫn đề xuất, không hỏi thêm | 2/3 | t2 text_none[dự tính khoảng bao nhiêu cho chiếc xe này] |
| V2-08 | ✅ Hỏi lại chỉ khi KHÔNG HIỂU, quá 2 lần → tư vấn viên | 3/3 | — |
| V2-09 | ✅ SUÝT V2-08: không hiểu một lần rồi khách nói rõ → chạy tiếp | 3/3 | — |
| V2-10 | ✅ Vòng chỉnh: 'rẻ hơn' phải ra mẫu rẻ hơn, không lặp bản cũ | 3/3 | — |
| V2-11 | ✅ Vòng chỉnh theo thuộc tính: 'cốp rộng hơn' | 2/2 | — |
| V2-12 | ✅ PHỦ ĐỊNH lặp bài: hết mẫu rẻ hơn thì nói thật, vẫn giữ thẻ xe | 2/2 | — |
| V2-13 | ✅ 'thôi xe máy đi' đổi loại xe, đề xuất lại đúng loại | 4/4 | — |
| V2-14 | ✅ SUÝT V2-13: nhắc cả hai loại trong một câu là câu HỎI, không phải đổi ý | 2/2 | — |
| V2-15 | ✅ PHỦ ĐỊNH đổi loại: câu có tên MẪU thì mẫu đó mới là thứ khách trỏ tới | 2/2 | — |
| V2-16 | ✅ Chọn bằng số thứ tự '1' | 2/2 | — |
| V2-17 | ✅ Chọn bằng 'mẫu đầu tiên' | 2/2 | — |
| V2-18 | ✅ 'chốt VF3' là một lượt CHỌN, không phải lời xin chỉnh | 3/3 | — |
| V2-19 | ✅ 'ok lấy VF 5' — tên đầy đủ thắng bộ đề xuất đang bày | 3/3 | — |
| V2-20 | ✅ PHỦ ĐỊNH chọn: 'không chọn VF 5' KHÔNG được ghi thành lượt chốt | 2/2 | — |
| V2-21 | ✅ SUÝT chọn: động từ đứng SAU tên xe là câu hỏi, không phải lời chốt | 2/2 | — |
| V2-22 | ✅ 'có hợp không' được ĐÁNH GIÁ, không bị nuốt bởi vế chọn | 2/2 | — |
| V2-23 | ✅ '4 người đi xa' trên VF 2 → hợp một phần + mẫu thay thế | 2/2 | — |
| V2-24 | ✅ SUÝT V2-23: bổ sung nhu cầu sau khi chốt → đánh giá LẠI, không xác nhận trơ | 3/3 | — |
| V2-25 | ❌ So sánh có KẾT LUẬN theo nhu cầu, không lôi mẫu thứ ba vào | 1/2 | t2 no_raw_output[decimal:326.00] |
| V2-26 | ❌ SUÝT V2-25: so sánh trơn hai mẫu, không cần nhu cầu | 0/1 | t1 no_raw_output[decimal:215.00] |
| V2-27 | ✅ 'làm sao để chốt' trả BA bước, không đẩy về đầu phễu | 2/2 | — |
| V2-28 | ✅ PHỦ ĐỊNH thủ tục: 'ok tôi chốt VF 3' là lượt CHỌN, không phải câu hỏi quy trình | 2/2 | — |
| V2-29 | ✅ Câu NGOÀI PHẠM VI về xe đã chọn → nói thật kèm tầm chạy | 2/2 | — |
| V2-30 | ✅ PHỦ ĐỊNH ngoài phạm vi: 'hay đi du lịch cuối tuần' là lời KỂ nhu cầu | 1/1 | — |
| V2-31 | ✅ Hỏi thông số sau khi chọn → trả số, KHÔNG chào hàng lại | 4/4 | — |
| V2-32 | ❌ Chi phí sử dụng: tạm tính 30 km/ngày rồi tính lại theo số khách nêu | 3/4 | t4 text_any['60'] |
| V2-33 | ✅ SUÝT tính lại: 'ngày anh đi 30km' sau khi chốt xe vẫn giữ mạch, không đề xuất lại | 3/3 | — |
| V2-34 | ❌ Giá lăn bánh: hỏi tỉnh MỘT lần, 'Hà Nội' trả lời được, không mặc định An Giang | 2/3 | t1 asks |
| V2-35 | ✅ PHỦ ĐỊNH cướp lượt: câu tìm địa điểm THẬT vẫn đi đường tìm địa điểm | 1/1 | — |
| V2-36 | ✅ Lái thử: cho tỉnh là ra THẺ khung giờ có ít nhất một ô còn chỗ | 2/2 | — |
| V2-37 | ✅ Nút khung giờ hết hiệu lực thì nói rõ và gợi ý lại | 1/1 | — |
| V2-38 | ❌ Chen ngang giữa lúc lõi đang hỏi → giữ pending rồi quay lại | 2/3 | t2 no_raw_output[decimal:215.00] |
| V2-39 | ✅ Xã giao giữa chừng KHÔNG làm mất mạch | 3/3 | — |
| V2-40 | ✅ Injection vẫn bị chặn, lượt sau vẫn trả giá THẬT | 2/2 | — |
| V2-41 | ✅ Kiểm duyệt: câu tục + đòi giá 0 đồng không sinh ra con số nào | 2/2 | — |
| V2-42 | ✅ Câu chính sách không có nguồn → nói thật + mời tư vấn viên | 1/1 | — |
| V2-43 | ✅ Duyệt danh mục CHỈ khi khách hỏi 'có những xe nào' | 2/2 | — |
| V2-44 | ❌ PHỦ ĐỊNH duyệt danh mục: 'ô tô điện' khi đang có câu hỏi treo là câu TRẢ LỜI | 1/2 | t2 text_none[dải sản phẩm ô tô điện đa dạng],text_none[dòng ô tô điện đang bán] |
| V2-45 | ✅ Tên xe viết kiểu khách gõ đều tra ra đúng mẫu | 3/3 | — |
| V2-46 | ✅ Nút gợi ý có mặt ở mọi lượt của một phiên đầy đủ | 4/4 | — |

## Lượt đỏ — chi tiết

### V2-07 t2 — `ô tô`
- tiêu chí đỏ: `['text_none[dự tính khoảng bao nhiêu cho chiếc xe này]']` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 7 dòng ô tô điện đang bán ạ:

* **VF 2**: Hatchback 4 chỗ, tầm chạy 210 km mỗi lần sạc. [Xem thêm](/vehicles/vf-2)
* **VF 3**: SUV 4 chỗ, tầm chạy 215 km mỗi lần sạc. [Xem thêm](/vehicles/vf-3)
* **VF 5*

### V2-25 t2 — `VF 5 với VF 6 thì cái nào hợp với nhu cầu của tôi hơn`
- tiêu chí đỏ: `['no_raw_output[decimal:326.00]']` · terminal: `None` · HTTP 200
- bot: Dạ, theo nhu cầu anh/chị đã kể thì VinFast VF 5 All New hợp hơn VinFast VF 6 Eco ạ: xe 5 chỗ, đủ cho 4 người nhà mình; tầm chạy ~326 km/lần sạc, đi xa vẫn thoải mái.

Bảng so sánh VinFast VF 5 All New và VinFast VF 6 Eco:

**VinFast VF 5 All New**:
* **Giá niêm yết**: 496.000.000 VND
* **Tầm hoạt độ

### V2-26 t1 — `so sánh VF 3 với VF 5 giúp anh`
- tiêu chí đỏ: `['no_raw_output[decimal:215.00]']` · terminal: `None` · HTTP 200
- bot: Bảng so sánh VinFast VF 3 All New và VinFast VF 5 All New:

**VinFast VF 3 All New**:
* **Giá niêm yết**: 278.000.000 VND
* **Tầm hoạt động (km)**: 215.00
* **Dung lượng pin (kWh)**: 18.640
* **Công suất (kW)**: 30.000
* **Mô-men xoắn (Nm)**: 110.000
* **Số chỗ ngồi**: 4
* **Tốc độ tối đa (km/h)**: 

### V2-32 t4 — `ngày anh đi 60km cơ`
- tiêu chí đỏ: `["text_any['60']"]` · terminal: `None` · HTTP 200
- bot: Chi phí sử dụng 5 năm của VinFast VF 5 All New khoảng 565 triệu ạ. Anh/chị muốn em tính lại với số km khác không ạ?

### V2-34 t1 — `tính giá lăn bánh VF 5 giúp anh`
- tiêu chí đỏ: `['asks']` · terminal: `None` · HTTP 200
- bot: Anh/chị đăng ký xe ở tỉnh/thành nào để em tính đúng phí lăn bánh ạ?

### V2-38 t2 — `khoan, so sánh VF 3 với VF 5 cái đã`
- tiêu chí đỏ: `['no_raw_output[decimal:215.00]']` · terminal: `None` · HTTP 200
- bot: Bảng so sánh VinFast VF 3 All New và VinFast VF 5 All New:

**VinFast VF 3 All New**:
* **Giá niêm yết**: 278.000.000 VND
* **Tầm hoạt động (km)**: 215.00
* **Dung lượng pin (kWh)**: 18.640
* **Công suất (kW)**: 30.000
* **Mô-men xoắn (Nm)**: 110.000
* **Số chỗ ngồi**: 4
* **Tốc độ tối đa (km/h)**: 

### V2-44 t2 — `Ô tô điện`
- tiêu chí đỏ: `['text_none[dải sản phẩm ô tô điện đa dạng]', 'text_none[dòng ô tô điện đang bán]']` · terminal: `None` · HTTP 200
- bot: Dạ, VinFast hiện có dải sản phẩm ô tô điện đa dạng, phục vụ nhiều nhu cầu khác nhau. Dưới đây là 7 dòng ô tô điện đang bán ạ:

* **VF 2**: Hatchback 4 chỗ, tầm chạy 210 km mỗi lần sạc. [Xem thêm](/vehicles/vf-2)
* **VF 3**: SUV 4 chỗ, tầm chạy 215 km mỗi lần sạc. [Xem thêm](/vehicles/vf-3)
* **VF 5*

