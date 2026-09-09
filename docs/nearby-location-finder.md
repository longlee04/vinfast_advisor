# FIND_NEARBY_LOCATION — Tìm địa điểm gần nhất

Khách hỏi "gần đây có trạm sạc nào không" hay "showroom xe máy gần nhất" →
chatbot trả về danh sách địa điểm gần nhất kèm khoảng cách, mỗi địa điểm một nút
**Chỉ đường** mở Google Maps.

**Năm loại địa điểm**, một luồng chung:

| `LocationKind` | nhãn | `locations.location_type` | số bản ghi |
| --- | --- | --- | --- |
| `SHOWROOM_CAR` | Showroom Ô tô | `showroom_car` | 328 |
| `SHOWROOM_MOTORBIKE` | Showroom Xe máy điện | `showroom_escooter` | 753 |
| `CHARGING_STATION_CAR` | Trạm sạc Ô tô điện | `car_charging_station` | 22.898 |
| `CHARGING_STATION_MOTORBIKE` | Trạm sạc Xe máy điện | `bike_charging_station` | 558 |
| `BATTERY_SWAP_CABINET` | Tủ đổi pin | `battery_swap_station` | 36.142 |
| `SERVICE_WORKSHOP_CAR` | Xưởng dịch vụ Ô tô | `service_car` + `service_car_partner` | 157 |
| `SERVICE_WORKSHOP_MOTORBIKE` | Xưởng dịch vụ Xe máy điện | `service_escooter` | 8 |

> `[KHÁC BIỆT]` Hai loại **xưởng dịch vụ** nằm ngoài năm loại đặc tả liệt kê.
> Thêm vào vì khách gõ "gara ô tô" và bảng `locations` **có** dữ liệu cho nó.
> Đặc tả cho hai hướng xử lý "gara" — (a) map vào `SHOWROOM_CAR`, (b) trả lời
> "chưa hỗ trợ" — nhưng điều kiện của cả hai đều không đúng: (a) sai vì dữ liệu
> phân biệt rõ nơi bán xe với nơi sửa xe, và chỉ đường cho khách cần sửa xe tới
> showroom là một câu trả lời sai; (b) sai vì hệ thống **có** dữ liệu, nên từ
> chối là nói dối về chính năng lực của mình. Hai loại này **không** có mặt trong
> năm nút bấm chọn loại (`PRIMARY_KINDS`) — chúng chỉ xuất hiện khi khách gõ
> "gara"/"bảo dưỡng". Gỡ hai thành viên khỏi `LocationKind` là cách hoàn nguyên.

> Bản đầu của tính năng chỉ biết trạm sạc (`FIND_CHARGING_STATION`). Phần đo
> khoảng cách, lấy vị trí khách và dựng deep link **không đổi một dòng nào** khi
> mở rộng — chỉ có bộ dò loại địa điểm và bộ lọc truy vấn là mới.

Tài liệu này ghi lại các quyết định thiết kế và những điểm mà bản triển khai
**khác** đặc tả gốc, kèm lý do. Mọi mục `[KHÁC BIỆT]` và `[GIẢ ĐỊNH]` rải trong
code đều trỏ về đây.

---

## 1. Luồng một lượt

```
Khách: "trạm sạc gần đây"  /  "showroom xe máy gần nhất"  /  "tìm chỗ gần tôi"
  │
  ├─ domain/intent_reconciliation.reconcile_intents
  │    is_nearby_location_request() → [FIND_NEARBY_LOCATION]   (tất định, 0 lần gọi LLM)
  │
  ├─ chain.run_turn: nạp conversation_sessions.user_location → state["user_location"]
  │
  ├─ nodes/route_intent._nearby_locations
  │    services/nearby_location.NearbyLocationServiceImpl.answer(...)
  │
  ├── (1) CHƯA rõ LOẠI ───────────────────────────────────────────────────────
  │     detect_location_kinds() → ()
  │     answer   = câu hỏi làm rõ
  │     locations= { needs_location_kind: true }
  │     quick_replies = 5 nút  → đi qua state["nlu_quick_replies"] (kênh Lớp 4)
  │     pending  = PendingSlotRequest(FIND_NEARBY_LOCATION, "location_kind")
  │     → Khách bấm "Tủ đổi pin" → gửi như tin nhắn thường → A7-10 nối vào pending
  │
  ├── (2) ĐÃ rõ loại, CHƯA có vị trí ─────────────────────────────────────────
  │     answer   = lời mời chia sẻ vị trí (nêu đúng loại đã chốt)
  │     locations= { needs_location: true, location_types: [...] }
  │     pending  = PendingSlotRequest(..., "user_location", giữ location_kind)
  │     → Frontend hiện <LocationRequest/>
  │        ├─ Bấm "Chia sẻ vị trí"  → POST /api/v1/locations/nearest {lat,lng,location_type}
  │        │                            → ghi toạ độ vào phiên (session_id)
  │        └─ Gõ "Cầu Giấy"          → POST /api/v1/agent/turn  (A7-10 nối vào pending)
  │                                      → geocode → lưu session → danh sách
  │
  └── (3) ĐỦ cả hai ──────────────────────────────────────────────────────────
        NearbyLocationPort.nearest(location_types=[...], radius 5 → 15 → 50 km,
                                   dừng ở vòng đầu có kết quả)
        → NearbyLocationListView (đã sắp tăng dần, làm tròn 1 chữ số thập phân)
        → LLM viết câu dẫn từ CHÍNH danh sách đó
        → TurnResponse.nearby_locations → <NearbyLocationCards/>
```

**Hỏi LOẠI trước, VỊ TRÍ sau** là có chủ đích: chỉ MỘT bản ghi chờ tồn tại mỗi
phiên (`conversation_sessions.pending_slot_request`), nên hai câu hỏi bắt buộc
phải nối tiếp. Loại đi trước vì nó là một cú bấm nút, còn vị trí cần quyền trình
duyệt — hỏi thứ đắt trước rồi mới phát hiện còn thiếu thứ rẻ là bắt khách trả giá
hai lần.

Lượt thứ hai trong cùng phiên **không hỏi lại vị trí**: toạ độ đã nằm trong
`conversation_sessions.user_location`.

**Loại không rõ thì HỎI, không đoán.** "trạm sạc" trần vẫn là câu trả lời được
(cả hai loại trạm sạc — trả cả hai là đúng), nhưng "tìm chỗ gần tôi" thì không.
Đoán loại cho câu đó trả về một danh sách trông rất thuyết phục và sai loại, và
khách chỉ phát hiện khi đã tới nơi.

---

## 2. `[KHÁC BIỆT]` — không có bảng `charging_stations`, và không cần `service_locations`

Đặc tả (cả bản gốc lẫn bản mở rộng) giả định có một bảng `charging_stations` cần
tạo rồi migrate sang `service_locations`, và cần **thêm cột `location_type`**.
Thực tế đã kiểm trên database:

- **`charging_stations` không tồn tại** — `SELECT to_regclass('public.charging_stations')`
  trả `NULL`.
- Bảng `locations` (`migrations/locations/versions/b44e204613af`) **đã có sẵn cột
  `location_type`**, với đúng năm giá trị mà bản mở rộng yêu cầu, cùng 60.861 địa
  điểm VinFast, và `/api/v1/locations/nearby` đã truy vấn chúng bằng Haversine
  trên index btree.
- Dữ liệu **đã phân biệt ô tô/xe máy** sẵn (22.898 vs 558), nên `[GIẢ ĐỊNH]`
  "map mặc định sang `CHARGING_STATION_CAR` rồi rà lại" của bản mở rộng **không
  áp dụng** — không có bản ghi nào cần đoán.

**Quyết định: dùng lại `locations`, không đổi tên, không migrate dữ liệu.** Đổi
tên bảng nghĩa là sửa cả trang bản đồ `/locations`, `scripts/seed_locations_data.py`
và bốn endpoint đang chạy — để đạt đúng con số 0 thay đổi về hành vi. Hai bảng cho
cùng một loại dữ liệu thì tệ hơn nữa: bản đồ và chatbot sẽ lệch nhau ngay lần cập
nhật đầu tiên chỉ chạm một bảng.

`LocationKind` (hợp đồng công khai, đúng năm mã enum đặc tả nêu) được ánh xạ sang
chuỗi kho lưu trữ ở `domain/nearby_location.LOCATION_TYPE_BY_KIND` — client thấy
`SHOWROOM_MOTORBIKE`, bảng lưu `showroom_escooter`, và không bên nào phải biết
cách gọi của bên kia.

## 2a. Bộ dò nhận diện — luật hiện hành

**Dấu hiệu tìm kiếm KHÔNG bắt buộc.** Đây từng là một bug thật: bản đầu đòi phải
có "gần"/"ở đâu"/"tìm" bên cạnh danh từ địa điểm, nên cách gõ phổ biến nhất —
một **cụm danh từ trần** — rơi hết xuống câu từ chối chung chung:

| khách gõ | trước | sau |
| --- | --- | --- |
| `tủ đổi pin` | OUT_OF_SCOPE | `FIND_NEARBY_LOCATION` |
| `showroom ô tô` | OUT_OF_SCOPE | `FIND_NEARBY_LOCATION` |
| `trụ đổi pin` | OUT_OF_SCOPE | `FIND_NEARBY_LOCATION` |

Một cụm danh từ chỉ tên một loại địa điểm thì không có nghĩa nào khác ngoài "cho
tôi xem cái này ở đâu". Nên luật hiện hành là: **có danh từ địa điểm** (hoặc động
từ sạc kèm dấu hiệu vị trí), và **không** rơi vào bốn nghĩa khác:

| # | loại trừ | ví dụ |
| --- | --- | --- |
| 1 | sạc TẠI NHÀ → `ADVISORY` (slot `home_charging`) | `nhà em không có chỗ sạc` |
| 2 | hỏi THÔNG SỐ sạc → hỏi một con số | `sạc ở trạm mất bao lâu` |
| 3 | XIN TƯ VẤN XE → `ADVISORY`, địa điểm chỉ là bối cảnh | `khu tôi trạm sạc hay xếp hàng, tư vấn giúp mẫu ô tô` |
| 4 | hỏi DANH MỤC → `CATALOG_BROWSE` | `cửa hàng có xe nào không` |

Loại trừ 3 và 4 đều **nhường lại** khi câu có dấu hiệu vị trí mạnh: `gần đây có
showroom xe máy điện nào không` là câu hỏi đường, không phải câu hỏi hàng.

**`chỗ` có dấu thì tính là danh từ địa điểm, `cho` không dấu thì không** — nó
trùng nguyên văn động từ "cho", và `ban quản lý không **cho** sạc dưới hầm` từng
bị đọc thành "chỗ sạc".

## 2b. Ranh giới với `CATALOG_BROWSE` — chỗ dễ vỡ nhất

"cửa hàng"/"showroom" mang **hai** nghĩa: một cái kho hàng và một cái địa chỉ.
Câu `"cửa hàng có xe nào không"` là câu hỏi **danh mục**, và nó khớp trọn vẹn cả
danh từ địa điểm lẫn dấu hiệu "có … không".

Nên bộ dò phân biệt **độ mạnh của dấu hiệu**:

- Danh từ **mơ hồ** (showroom / cửa hàng / đại lý / "chỗ nào") đòi một dấu hiệu
  **mạnh** — câu phải nói thẳng về vị trí ("gần", "ở đâu", "địa chỉ", "chỉ đường").
- Danh từ **không mơ hồ** (trạm sạc, tủ đổi pin) thì một dấu hiệu yếu là đủ:
  không ai hỏi "có trạm sạc nào không" với ý hỏi danh mục xe.

| câu | kết quả |
| --- | --- |
| `cửa hàng có xe nào không` | `CATALOG_BROWSE` (không bị cướp) |
| `cửa hàng gần đây` | `FIND_NEARBY_LOCATION` |
| `có trạm sạc nào không` | `FIND_NEARBY_LOCATION` |
| `nhà em không có chỗ sạc, tư vấn xe giúp em` | `ADVISORY` |

## 2c. Cổng phạm vi không được giết một lượt đã nhận diện được

Nguyên nhân gốc **thứ hai** của cùng bug, và nó độc lập với bộ dò:

```
"tủ đổi pin" → bộ phân loại phạm vi (LLM) thấy cụm hai chữ, không nhắc VinFast
             → OUT_OF_SCOPE → classify_scope đặt terminal_reason
             → graph rẽ END TRƯỚC KHI route_intent chạy
```

Sửa bộ dò thôi thì chưa đủ: intent gắn đúng nhưng lượt vẫn chết ở cổng. Nên
`turn_understanding.reconcile_scope` có một cửa hậu **hẹp**: khi `intents` đã
mang `FIND_NEARBY_LOCATION` **và** `is_nearby_location_request()` đồng ý, scope
được ép về `IN_SCOPE` — bằng chứng tất định thắng một phỏng đoán của mô hình.

Cửa hậu đòi **cả hai** điều kiện, nên nó không nới cổng phạm vi cho lượt nào
khác: `mai Hà Nội có mưa không` vẫn `OUT_OF_SCOPE`.

Prompt phạm vi (`prompts/scope_prompts.py`) cũng được bổ sung luật + ví dụ cụm
danh từ trần — nhưng đó là lớp phòng thủ thứ hai, không phải chỗ dựa: không nên
tin vào việc chỉnh prompt để mô hình đọc đúng một cụm hai chữ.

## 3. `[KHÁC BIỆT]` — Haversine nằm trong SQL, không phải Python

Đặc tả mô tả một hàm Haversine viết bằng Python. Trong repo, phép tính là một
biểu thức SQL (`src/locations/infrastructure/repositories._haversine_km`) chạy
cùng câu lệnh với bộ lọc bounding box, đúng như đặc tả gợi ý cho tập > 5000 điểm
— chỉ khác là bộ lọc thô đó đã được cài sẵn ở tầng SQL thay vì tầng Python.

Hệ quả với test: bài kiểm khoảng cách nằm ở
`tests/locations/integration/test_nearby_location_distance.py` và cần Postgres
(tự SKIP khi thiếu DSN). Viết lại công thức bằng Python để có một unit test chạy
không cần hạ tầng là test một **bản sao** — bản sao đó vẫn xanh trong khi biểu
thức SQL thật bị sửa sai.

## 4. `[KHÁC BIỆT]` — không có Redis trong repo

Đặc tả nói lưu `user_location` vào Redis theo `session_id`, TTL theo session.
Repo **không có Redis**: không dependency trong `pyproject.toml`, không service
trong `docker-compose.yml`, không biến môi trường nào trong `.env.example`.

Bộ nhớ ngắn hạn của phiên trong hệ thống này vốn nằm ở `conversation_sessions` —
cùng chỗ với `pending_slot_request`, `active_task_state`, `last_quote_evaluation`.
Toạ độ đi cùng chúng, qua cột JSONB `user_location` (`agent_0021`). Vòng đời vẫn
gắn với **phiên**, đúng thứ đặc tả mô tả, chỉ khác chỗ cất.

`[GIẢ ĐỊNH]` giữ nguyên: **không** lưu toạ độ vào `customer_profiles`. Đây là dữ
liệu tạm của một lượt đi lại, không phải thông tin khách hàng dài hạn.

## 5. `[KHÁC BIỆT]` — `charger_type` mang loại TRẠM, không phải chuẩn AC/DC

Đặc tả yêu cầu `charger_type` enum `AC/DC/BOTH` và `num_ports`. Bộ dữ liệu thật
(`data-p150/locations/*.json`, 23.456 trạm sạc) **không có** hai trường đó. Các
trường thực sự có: `type_id` (hằng số theo nhóm — `2444` cho mọi trạm ô tô,
`2445` cho mọi trạm xe máy, nên không mang thông tin chuẩn sạc), `access_type`,
`charging_status`.

Sinh ra một giá trị `"DC"` cho đủ hợp đồng là đặt một **khẳng định kỹ thuật sai**
trước mặt khách — đúng thứ guardrail A6-1 tồn tại để chặn. `charger_type` vì vậy
mang thứ dữ liệu nói được:

| giá trị              | loại                              |
| -------------------- | --------------------------------- |
| `CAR_CHARGER`        | `CHARGING_STATION_CAR`            |
| `MOTORBIKE_CHARGER`  | `CHARGING_STATION_MOTORBIKE`      |
| `null`               | showroom và tủ đổi pin            |

`null` với ba loại còn lại là **đúng đặc tả bản mở rộng** ("chỉ áp dụng cho 2
loại trạm sạc, để nullable"): showroom và tủ đổi pin không có khái niệm cổng sạc
nào để nói, và một chuỗi rỗng ở đó sẽ bị client dựng thành một nhãn trống.

`scripts/import_charging_stations.py` vẫn **đọc** `charger_type`/`num_ports` khi
nguồn có, và ghép chúng vào cột `status` để không mất dữ liệu.

`[GIẢ ĐỊNH]` gốc ("không cần trạng thái real-time") được giữ, có điều chỉnh: dữ
liệu **có** `charging_status` (`ACTIVE`/`BUSY`/`INACTIVE`/…), nên nó được trả ra
ở trường `status` — kèm cảnh báo rằng đó là ảnh chụp lúc crawl, không phải trạng
thái thời gian thực. Prompt LLM cấm tường minh việc nói trạm đang trống hay bận.

## 6. `[KHÁC BIỆT]` — dedupe theo `external_id`, sinh từ `name+lat+lng` khi thiếu

Đặc tả chọn khoá dedupe `name + latitude + longitude`. Khoá duy nhất thật của
bảng là `external_id`. `scripts/import_charging_stations.py` tôn trọng cả hai:

- nguồn **có** `external_id` → dùng nguyên;
- nguồn **không có** → sinh `GEN-<16 hex đầu SHA-256(name|lat|lng)>`, toạ độ làm
  tròn 6 chữ số (đúng độ chính xác `Numeric(9,6)` lưu được).

Cùng ba giá trị đó luôn cho cùng một khoá → chạy lại không nhân đôi bản ghi,
đúng ngữ nghĩa đặc tả yêu cầu.

## 7. `[GIẢ ĐỊNH]` — Nominatim, không Google Geocoding

Đã soát: repo **không** có sẵn Google Maps API key nào (`.env.example`,
`src/config.py`). Nominatim miễn phí, không cần key. Điều kiện sử dụng của họ
được tôn trọng bằng `User-Agent` định danh, khoá tuần tự hoá lời gọi ra ngoài, và
bảng đệm `geocode_cache` (TTL 30 ngày, migration `c1f7a2d40b3e`) — kể cả kết quả
**rỗng** cũng được đệm, để một địa danh sai chính tả không sinh một lời gọi mới ở
mỗi lần khách gõ lại.

Nút "Chỉ đường" vẫn mở **Google Maps**, nhưng đó là deep link công khai
(`maps/dir/?api=1&origin=…&destination=…`) — URL scheme, không phải Directions
API: không key, không quota, không lời gọi mạng nào từ phía ta. `origin` luôn
được gắn để Google Maps không phải xin lại quyền vị trí trên máy khách.

## 8. `[GIẢ ĐỊNH]` — quét nới dần 5 → 15 → 50 km

Không bắn thẳng bán kính tối đa: ở nội thành một truy vấn 50 km trả về hàng nghìn
điểm và tính khoảng cách cho tất cả chỉ để vứt đi phần lớn. Vòng quét dừng ở bán
kính **đầu tiên** có kết quả.

50 km không phải con số tự chọn — nó là trần cứng của
`src/locations/domain/values.MAX_RADIUS_KM`. Hết 50 km mà không có trạm nào thì
câu trả lời **nói rõ đã quét bao xa**, thay vì trả một danh sách rỗng im lặng.

## 9. Rủi ro và HITL

Nhánh này **không qua HITL**, cùng nhóm với `CATALOG_BROWSE` và
`COMPARE_VEHICLES`: mọi dòng chép nguyên văn từ bảng `locations`, không cá nhân
hoá, không cam kết thương mại. Service cố ý **không** ghi `lookup_facts` — cổng
rủi ro báo giá (A7-4) đếm giá trong field đó, và một danh sách địa chỉ không mang
giá nào.

## 10. Ngân sách gọi LLM (A4-2)

| bước                | số lần gọi LLM |
| ------------------- | -------------- |
| nhận diện intent    | 0 (tất định)   |
| chốt vị trí         | 0 (rule-based + geocode HTTP) |
| đọc trạm            | 0 (SQL)        |
| viết câu dẫn        | 1              |

Hỏng hoặc chưa nối LLM → `_fallback_lead` viết một câu deterministic; danh sách
vẫn gửi được, chỉ thiếu phần văn xuôi.

---

## 11. Hai bề mặt HTTP

| endpoint | trạng thái | `location_type` | `action_type` |
| --- | --- | --- | --- |
| `POST /api/v1/locations/nearest` | hiện hành | **bắt buộc**, nhận nhiều giá trị | `NEARBY_LOCATION_LIST` |
| `POST /api/v1/charging-stations/nearest` | tương thích ngược | không có — mặc định hai loại trạm sạc | `CHARGING_STATION_LIST` |

Endpoint cũ giữ **nguyên** hình dạng request/response từ trước khi tổng quát hoá
(`charger_type` là `str` chứ không `str | None`, không có `location_type` trong
từng phần tử). Client đã dựng theo nó, và một endpoint biến mất là một màn hình
trắng chứ không phải một lỗi biên dịch. `tests/agents/unit/api/` khoá hợp đồng đó.

Nhãn intent cũ `FIND_CHARGING_STATION` cũng được giữ trong `Intent` — **không
nhánh nào phát ra nó nữa**, nhưng cột `pending_slot_request` của các phiên mở
trước lần tổng quát hoá đang chứa nguyên văn chuỗi ấy. Mọi phép so khớp đi qua
`domain/values.is_nearby_location_intent()` để nhận cả hai.

`[KHÁC BIỆT]` Prefix `/locations` **dùng chung** với router chỉ-đọc của module
Locations (`GET /locations`, `/locations/nearby`, `/locations/categories`,
`/locations/regions`). Không đường dẫn nào trùng nhau. Route mới nằm ở module
`agents` vì `reply_text` do LLM viết, và LLM chỉ được nối trong composition của
`agents`.

---

## 12. File liên quan

**Backend**

| file | vai trò |
| --- | --- |
| `src/agents/domain/nearby_location.py` | `LocationKind`, bộ dò intent + loại, deep link, `UserLocation` |
| `src/agents/services/nearby_location.py` | use case bốn bước (loại → vị trí → đọc → câu dẫn) |
| `src/agents/ports.py` | `NearbyLocationPort`, `GeocodePort`, `NearbyPlace`, `GeocodedPlace` |
| `src/agents/adapters/nearby_location_source.py` | bắc sang module Locations |
| `src/agents/nodes/route_intent.py` | nhánh trong graph |
| `src/agents/chain.py` | nạp/ghi vị trí phiên, resume hai slot chờ |
| `src/agents/api/nearby_location_routes.py` | hai router (hiện hành + tương thích ngược) |
| `src/agents/api/nearby_location_schemas.py` | hợp đồng HTTP dùng chung ba bề mặt |
| `src/locations/infrastructure/geocoding.py` | Nominatim + đệm Postgres |
| `scripts/import_service_locations.py` | nạp CSV/JSON 5 loại vào `locations` |

**Frontend**

| file | vai trò |
| --- | --- |
| `frontend/src/components/consultation/nearby-location-list.tsx` | card + icon theo loại + nút "Chỉ đường" |
| `frontend/src/components/consultation/location-request.tsx` | geolocation + ô gõ địa danh |
| `frontend/src/components/consultation/quick-replies.tsx` | 5 nút chọn loại (dùng chung với Lớp 4) |
| `frontend/src/lib/api/agent.ts` | `fetchNearestLocations` |

**Migration**

- `migrations/agents/versions/agent_0021_session_user_location.py`
- `migrations/locations/versions/c1f7a2d40b3e_tao_bang_geocode_cache.py`

Cả hai đã áp lên database dev; **bản mở rộng không cần migration mới** — cột
`location_type` đã có sẵn từ `b44e204613af`.
