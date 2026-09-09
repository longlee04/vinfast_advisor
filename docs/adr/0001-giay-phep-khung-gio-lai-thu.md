# ADR 0001 — Giấy phép khung giờ lái thử có chữ ký

**Ngày:** 2026-08-28 · **Trạng thái:** đã áp dụng · **Nhánh:** `feature/chong-crack-llm-judge`

## Bối cảnh

Khách chốt lịch lái thử bằng cách **bấm nút**, không gõ chữ tự do: sai một giờ là
hẹn khách tới lúc không ai đợi, sai showroom là họ đi nhầm thành phố. Mỗi nút
mang một mã, và mã ấy đi trong `QuickReply.value` như một tin nhắn bình thường.

Mã của bản đầu là **chữ thường**:

```
__lichlaithu__|2026-08-30T14:00:00+07:00|VinFast Long Biên
```

`decode_slot_choice` chỉ tách chuỗi, rồi `chain._book_test_drive` ghi thẳng vào
`test_drive_bookings`. Không có bước nào hỏi mã này từ đâu ra. Hệ quả: bất kỳ ai
cũng tự gõ được một mã hợp lệ với **showroom bịa**, **giờ đã qua**, **giờ ngoài
cửa sổ bảy ngày**, hoặc **showroom chưa từng được mời cho phiên đó**.

Endpoint availability (`GET /agent/test-drive/availability`) trả mã do server
sinh là đúng hướng — nhưng chừng nào mã còn giả được thì nó chưa phải giấy phép.

## Quyết định

Mã trở thành **giấy phép có chữ ký**, buộc vào phiên và khách.

```
__lichlaithu__|<base64url(payload)>|<base64url(HMAC-SHA256[:16])>

payload = v1 ⟨0x1f⟩ session_id ⟨0x1f⟩ customer_id ⟨0x1f⟩
          scheduled_at(ISO) ⟨0x1f⟩ issued_at(ISO) ⟨0x1f⟩ showroom
```

| Điểm | Giá trị | Vì sao |
|---|---|---|
| Thuật toán | HMAC-SHA256, cắt 16 byte | đoán mò là vô vọng; mã vẫn ngắn |
| So chữ ký | `hmac.compare_digest` | so chuỗi thường rò rỉ thời gian |
| Dấu ngăn trường | `0x1f` (US), **không phải `\|`** | tên showroom chứa `\|` được; dùng `\|` thì chen thêm trường mà chữ ký vẫn đúng |
| TTL | 2 giờ **kể từ lúc CẤP** | đủ dài cho một cuộc trò chuyện, đủ ngắn để mã lọt ra ngoài không sống lâu |
| Lệch đồng hồ | ±2 phút (`CLOCK_SKEW`) | hai máy lệch vài giây là chuyện thường, không phải tấn công |
| Cửa hạn | `-CLOCK_SKEW ≤ now − issued_at ≤ TTL` | chặn **cả hai đầu** |

### TTL phải chặn hai đầu

Bản đầu chỉ hỏi `now - issued_at > TTL`. Hiệu số thành **âm** khi `issued_at` nằm
ở tương lai, nên một mã ghi ngày mai vẫn qua cửa — và nó sống dài hơn TTL thật
đúng bằng khoảng lệch đó.

### KHÔNG buộc `vehicle_id`

Endpoint availability không biết xe nào (nó trả khung giờ của showroom). Xe được
đọc từ **chặng sau đề xuất ở phía server**, client không chọn được — nên buộc
thêm `vehicle_id` không mua thêm an toàn mà làm hỏng endpoint.

### Nơi cấp

Ký ở **tầng service** (`services/test_drive._issuer`), không ở chỗ gọi. Chỗ gọi
tự ghép chuỗi chính là cách lỗ hổng cũ sống sót: `TestDriveSlotOption` và
`TestDriveOptionView` mang sẵn `value`, `chain` và route chỉ đọc.

## Khoá ký

`TEST_DRIVE_SLOT_SECRET`, rơi về `AUTH_JWT_SIGNING_KEY` nếu không khai.

**Tách mục đích:** khoá không dùng thẳng mà dẫn xuất
`HMAC(khoá_gốc, b"p150/test-drive-slot/v1")`. Một khoá ký hai loại giấy khác
nhau là mở đường cho việc lấy chữ ký của loại này ghép sang loại kia.

**`APP_ENV=production` mà thiếu cả hai khoá ⇒ `RuntimeError` ngay khi khởi
động.** Bản đầu chỉ ghi cảnh báo rồi sinh khoá ngẫu nhiên cho tiến trình. Trên
máy chạy nhiều worker, mã do worker A cấp bị worker B từ chối vì hai khoá khác
nhau — khách bấm đúng nút mình vừa nhận và nghe *"khung giờ này không đặt
được"*, lúc có lúc không tuỳ request rơi vào worker nào, và gần như không lần ra
được từ log. Chết sớm đọc được hơn nhiều.

Dev và bộ test (một tiến trình) vẫn rơi về khoá ngẫu nhiên kèm cảnh báo.

### Xoay khoá

Khoá dẫn xuất tất định từ biến môi trường, **không lưu ở đâu khác**. Xoay khoá:

1. Đổi `TEST_DRIVE_SLOT_SECRET` rồi khởi động lại toàn bộ worker.
2. Mọi giấy phép đang lưu hành **hết hiệu lực ngay**.
3. Ảnh hưởng tối đa là **2 giờ** (bằng TTL): khách đang mở thẻ chọn giờ sẽ nhận
   *"khung giờ này vừa có người đặt mất"* và phải bấm lại. Không mất lịch đã ghi.
4. Không xoay giữa giờ cao điểm; không xoay từng worker một — nửa đội dùng khoá
   cũ, nửa dùng khoá mới thì lỗi trông y hệt sự cố nhiều worker ở trên.

Không dựng cơ chế hai khoá (cũ + mới) song song: cửa sổ ảnh hưởng chỉ 2 giờ, và
một danh sách khoá là thêm một chỗ để quên xoá cái cũ đi.

## Quyền sở hữu phiên

`GET /agent/test-drive/availability` gác **trước** khi đọc bất cứ gì:

| Ca | Mã | Vì sao |
|---|---|---|
| phiên không tồn tại | **404** | không xác nhận cho người lạ biết `session_id` nào có thật |
| phiên của người khác | **404** | như trên |
| phiên **đã lưu trữ** | **404** | lượt chat đã chặn (`ensure_session` ném `ConversationArchivedError`); endpoint phải chặn giống hệt |
| chưa nối service | **503** | lỗi vận hành, không phải lỗi nghiệp vụ |
| phiên hợp lệ, thiếu loại xe | **409** `VEHICLE_TYPE_UNKNOWN` | không âm thầm dùng `CAR` — khách hỏi xe máy sẽ nhận showroom ô tô |
| phiên hợp lệ, chưa biết vị trí | **409** `LOCATION_UNKNOWN` | *"hết chỗ"* và *"chưa biết anh/chị ở đâu"* là hai chuyện khác nhau |
| ngày sai định dạng | **422** | |
| ngày ngoài cửa sổ 7 ngày | **200**, `options: []` | ngày đến từ nút trên trình duyệt; một ngày lạ phải dẫn tới "hôm đó không còn khung nào", không phải màn hình hỏng |

**Toạ độ đọc từ PHIÊN, không nhận từ client.** Cùng nguồn với lượt chat đã dựng
thẻ. Cho client gửi toạ độ là để bất kỳ ai có `session_id` cũng dò được lịch của
một showroom họ chưa từng được mời, rồi dựng mã nút từ đó. Tham số toạ độ gửi
kèm bị **bỏ qua** — có test riêng canh.

## Luồng đặt lịch chuẩn

```
lượt chat "đăng ký lái thử"
  └─ chain._advance_post_pitch  → AWAITING_SLOT (chỉ khi ĐÃ biết xe)
       └─ services.test_drive.answer(session_id, customer_id, …)
            └─ thẻ + nút, mỗi ô mang một GIẤY PHÉP đã ký

khách bấm sang ngày khác
  └─ GET /agent/test-drive/availability?session_id=…&date=…
       └─ gác quyền → loại xe từ phiên → toạ độ từ phiên → giấy phép mới

khách bấm một khung giờ
  └─ giá trị nút đi lên như MỘT TIN NHẮN bình thường
       └─ chain._slot_choice → read_slot_token(session, customer, now)
            └─ chain._book_test_drive → BookingSlotSource.book
```

Một chỗ đọc giấy phép duy nhất: `chain._slot_choice`. Mọi nhánh hỏi *"lượt này
có phải một lần chọn khung giờ không"* đều đi qua đó, nên không nhánh nào lỡ bỏ
quên phép kiểm chữ ký.

`POST /agent/bookings` (portal) là **đường khác**, không dùng giấy phép này —
xem `api/booking_routes.py`. Nó vẫn nhận `customer_id`/`phone` từ payload; đó là
nợ đã biết, **chưa** thuộc phạm vi ADR này.

## Hệ quả

- Client cũ đang giữ mã kiểu chữ thường sẽ bị từ chối. Chấp nhận: mã chỉ sống
  trong một lượt chat, và luồng cũ vốn đã hỏng ở đúng chỗ này.
- Prod **bắt buộc** có `TEST_DRIVE_SLOT_SECRET` hoặc `AUTH_JWT_SIGNING_KEY`.
- Nút không còn đọc được bằng mắt trong log. Đổi lại, không ai bị dụ "sửa tay
  cho nhanh" một chuỗi trông như dữ liệu.

## Bằng chứng

- `tests/agents/unit/domain/test_slot_token.py` — 15 ca: sửa một ký tự · gõ tay
  mã cũ · khoá khác · mã phiên khác · mã khách khác · quá hạn · **cấp ở tương
  lai** · lệch đồng hồ nhỏ · 5 loại rác · payload không lộ tên showroom
- `tests/agents/unit/services/test_slot_signing_key.py` — 5 ca khoá
- `tests/agents/unit/api/test_test_drive_availability_endpoint.py` — 11 ca cổng
- `tests/agents/integration/test_post_pitch_test_drive_e2e.py` — luồng thật
