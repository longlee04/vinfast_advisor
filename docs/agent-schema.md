# Agent Schema

Tài liệu này đặc tả DDL cho toàn bộ bảng module `agent` — phần mà `docs/vinfast-agent-mvp.md` chỉ liệt kê tên bảng theo migration (mục 5), chưa có cột cụ thể. Cùng vai trò với `docs/vehicle-catalog-schema.md` nhưng cho module `agent`.

Module `agent` **không** sở hữu bảng nào của `product`/`document` — chỉ đọc qua repository. Toàn bộ FK sang `vehicles`/`feature_definitions` ở đây là tham chiếu liên module trong cùng database vật lý (giống cách `vehicle_documents` tham chiếu `vehicles`), không phải dấu hiệu module `agent` sở hữu các bảng đó.

Sáu migration, chain tuyến tính (mục 5 `docs/vinfast-agent-mvp.md`):

| Migration | Bảng |
|---|---|
| `agent_0002` | `conversation_sessions`, `conversation_slots`, `pending_feature_mentions`, `customer_profiles`, `out_of_scope_log` |
| `agent_0003` | `agent_runs`, `run_snapshots`, `run_candidates`, `run_evidence`, `scoring_result`, `tco_estimates` |
| `agent_0004` | `review_queue` |
| `agent_0005` | `test_drive_bookings`, `internal_notices`, `notice_reads` |
| `agent_0006` | `VIEW funnel_metrics` |

Quy ước ID giống `vehicle-catalog-schema.md` §3.1: ID thực thể agent (`session_id`, `run_id`...) là `UUID`; ID người dùng tham chiếu module auth (`advisor_id`, `claimed_by`, `created_by`...) là `VARCHAR(64)`, tham chiếu mềm — không FK, vì `agent` không phụ thuộc cứng vào schema `auth` (cùng lý do nêu ở mục §5.2 quy tắc auth trong `docs/erd.md`).

---

## agent_0002 — Hội thoại và hồ sơ nhu cầu

### `conversation_sessions`

Một phiên hội thoại, gắn khách hàng và (khi có) tư vấn viên phụ trách.

```sql
CREATE TABLE conversation_sessions (
    session_id UUID PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    assigned_advisor_id VARCHAR(64),
    vehicle_type_hint VARCHAR(32),
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    started_at TIMESTAMPTZ NOT NULL,
    last_activity_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_conversation_sessions_status CHECK (
        status IN ('ACTIVE', 'COMPLETED', 'ABANDONED')
    ),
    CONSTRAINT ck_conversation_sessions_vehicle_type CHECK (
        vehicle_type_hint IS NULL OR vehicle_type_hint IN ('CAR', 'ELECTRIC_MOTORBIKE')
    )
);

CREATE INDEX ix_conversation_sessions_customer
    ON conversation_sessions (customer_id, started_at DESC);

CREATE INDEX ix_conversation_sessions_advisor
    ON conversation_sessions (assigned_advisor_id, status);
```

| Field | Kiểu | Dùng để |
|---|---|---|
| `session_id` | UUID | Khoá chính, đầu mối join mọi bảng agent còn lại. |
| `customer_id` | VARCHAR(64) | Khách hàng sở hữu phiên (`auth_users.id`), bắt buộc — MVP không hỗ trợ chat ẩn danh vì A8-3 yêu cầu khách xem lại lịch sử của chính mình. |
| `assigned_advisor_id` | VARCHAR(64) nullable | Tư vấn viên phụ trách phiên này. Gán khi có HITL đầu tiên hoặc Admin phân công thủ công; null nghĩa là chưa ai phụ trách. |
| `vehicle_type_hint` | VARCHAR(32) nullable | Cache slot đầu tiên (loại xe) để UI/dashboard không phải join `conversation_slots` chỉ để biết CAR hay ELECTRIC_MOTORBIKE. |
| `status` | VARCHAR | Vòng đời phiên, phục vụ `funnel_metrics`. |
| `started_at`/`last_activity_at`/`ended_at` | TIMESTAMPTZ | Đo funnel và phát hiện phiên bỏ dở. |

### `conversation_slots`

```sql
CREATE TABLE conversation_slots (
    session_id UUID NOT NULL REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
    slot_name VARCHAR(64) NOT NULL,
    slot_value_text TEXT,
    slot_value_number NUMERIC(14, 3),
    confirmed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, slot_name)
);
```

Khoá chính là `(session_id, slot_name)` — không dùng `id` rời — vì A2-2 yêu cầu "sửa slot là UPDATE, không append": khoá chính tổng hợp làm điều đó thành bất biến ở tầng database thay vì chỉ ở application, `INSERT` trùng khoá tự thất bại thay vì âm thầm tạo hàng thứ hai.

| Field | Kiểu | Dùng để |
|---|---|---|
| `slot_name` | VARCHAR(64) | Tên slot theo cây A3-1, ví dụ `vehicle_type`, `passenger_count`, `daily_distance_km`, `home_charging`, `budget_max_vnd`, `usage_purpose`, `delivery_use`, `additional_preference`. |
| `slot_value_text`/`slot_value_number` | TEXT/NUMERIC | Đúng một trong hai có giá trị tuỳ slot là chuỗi hay số; validate ở application theo kiểu slot khai trong `domain/slot_tree.py` (A3-1), không validate bằng CHECK vì tập slot còn mở rộng theo nhánh xe. |
| `confirmed_at` | TIMESTAMPTZ | Thời điểm slot được khách xác nhận — dùng để đo tốc độ hoàn thành hồ sơ nhu cầu cho `funnel_metrics`. |

### `pending_feature_mentions`

```sql
CREATE TABLE pending_feature_mentions (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
    raw_mention TEXT NOT NULL,
    feature_code VARCHAR(100),
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_pending_feature_mentions_session
    ON pending_feature_mentions (session_id, applied_at);
```

| Field | Kiểu | Dùng để |
|---|---|---|
| `raw_mention` | TEXT | Nguyên văn khách nói, ví dụ "xe có cửa sổ trời không". Giữ lại kể cả sau khi resolve, để review được NLU đoán sai chỗ nào. |
| `feature_code` | VARCHAR(100) nullable | Mã đã khớp với `feature_definitions.feature_code` (module product). Null nếu chưa resolve được hoặc feature không tồn tại trong danh mục. |
| `applied_at` | TIMESTAMPTZ nullable | Thời điểm A4-4 áp mention này vào Lớp 2. Null nghĩa là chưa áp — phân biệt với "đã áp nhưng không match feature nào". |

### `customer_profiles`

```sql
CREATE TABLE customer_profiles (
    customer_id VARCHAR(64) PRIMARY KEY,
    display_name VARCHAR(150),
    phone VARCHAR(20),
    email VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
```

**Cố ý không có cột "sở thích đã học" (preferred features, lịch sử tìm kiếm tổng hợp...).** PRD 6.2 xếp "memory dài hạn" ngoài phạm vi MVP (mục 2.2 `vinfast-agent-mvp.md`). Bảng này chỉ giữ thông tin liên hệ hiển thị cho tư vấn viên khi xử lý HITL/booking, tra theo `customer_id` — không tích luỹ hành vi qua các phiên. Nếu sau này cần cá nhân hoá theo lịch sử, đó là bảng mới ở PRD 6.2, không phải mở rộng bảng này.

### `out_of_scope_log`

```sql
CREATE TABLE out_of_scope_log (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
    utterance TEXT NOT NULL,
    classification VARCHAR(24) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_out_of_scope_log_classification CHECK (
        classification IN ('IN_SCOPE', 'MISSING_DATA', 'OUT_OF_SCOPE')
    )
);

CREATE INDEX ix_out_of_scope_log_classification
    ON out_of_scope_log (classification, created_at DESC);
```

Ba nhãn khớp đúng A6-2. `IN_SCOPE` cũng được ghi (không chỉ hai nhãn từ chối) để đếm được tỷ lệ phân loại đúng/sai khi review thủ công.

---

## agent_0003 — Lượt chạy, snapshot bằng chứng, chấm điểm, TCO

### `agent_runs`

```sql
CREATE TABLE agent_runs (
    run_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
    state VARCHAR(24) NOT NULL DEFAULT 'CAPTURING',
    terminal_reason VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_agent_runs_state CHECK (
        state IN (
            'CAPTURING', 'SNAPSHOT_READY', 'PACKAGE_READY', 'PENDING_REVIEW',
            'APPROVED', 'DELIVERED', 'FAILED', 'REJECTED'
        )
    )
);

CREATE INDEX ix_agent_runs_session ON agent_runs (session_id, created_at DESC);
CREATE INDEX ix_agent_runs_state ON agent_runs (state);
```

`terminal_reason` khớp §6.6 `vinfast-agent-mvp.md` — enum domain, không phải chuỗi lỗi tự do; giá trị null nghĩa là run chưa kết thúc hoặc kết thúc bình thường.

### `run_snapshots`

```sql
CREATE TABLE run_snapshots (
    snapshot_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_run_snapshots_run ON run_snapshots (run_id);
```

`payload` là bản sao đóng băng của mọi số liệu structured đã đọc từ `product` tại `captured_at` (giá, specs, feature flags liên quan) — theo A5-2, mọi tính toán sau đó đọc từ đây, không query lại catalog. Không CHECK cấu trúc `payload` vì nó thay đổi theo loại xe (CAR/ELECTRIC_MOTORBIKE có field khác nhau); validate ở application bằng Pydantic model tương ứng.

### `run_candidates`

```sql
CREATE TABLE run_candidates (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL,
    layer_reached VARCHAR(16) NOT NULL,
    rank SMALLINT,
    over_budget_percent NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_run_candidates_layer CHECK (layer_reached IN ('L1', 'L2', 'L3')),
    CONSTRAINT ck_run_candidates_rank CHECK (rank IS NULL OR rank BETWEEN 1 AND 3)
);

CREATE INDEX ix_run_candidates_run ON run_candidates (run_id, rank);
```

`vehicle_id` không FK sang `vehicles` (module `products`) — cố ý. Candidate của một run đã kết thúc phải giữ nguyên dù xe sau này bị archive/xoá; ràng buộc cứng sẽ chặn vòng đời catalog thay đổi bình thường. `over_budget_percent` khác null chỉ khi xe được đề xuất dù vượt ngân sách, đúng quy tắc A5-3 "chỉ xuất hiện khi có nhãn vượt ngân sách X%".

### `run_evidence`

```sql
CREATE TABLE run_evidence (
    evidence_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    fact_code VARCHAR(60) NOT NULL,
    source_table VARCHAR(60) NOT NULL,
    source_id UUID,
    value_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_run_evidence_run ON run_evidence (run_id, fact_code);
```

Mỗi hàng là một con số đã được phép nói ra theo allowlist `fact_code` ở `vehicle-catalog-schema.md` §7.5. A5-6 gắn `evidence_id` vào mỗi placeholder khi render; A6-1 guardrail đối chiếu số trong câu trả lời với bảng này.

### `scoring_result`

```sql
CREATE TABLE scoring_result (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL,
    score NUMERIC(6, 3) NOT NULL,
    reasons JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_scoring_result_reasons_min CHECK (jsonb_array_length(reasons) >= 2)
);

CREATE INDEX ix_scoring_result_run ON scoring_result (run_id, score DESC);
```

`reasons` là mảng JSON, mỗi phần tử `{"slot_name": "...", "reason_text": "..."}`. `ck_scoring_result_reasons_min` ép trực tiếp ở DB yêu cầu "mỗi mẫu ≥ 2 lý do" của A5-3 — nếu code quên kiểm tra, insert thất bại thay vì lọt qua.

### `tco_estimates`

```sql
CREATE TABLE tco_estimates (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL,
    assumption_id UUID NOT NULL,
    monthly_distance_km NUMERIC(10, 2) NOT NULL,
    promoted_purchase_price_vnd BIGINT NOT NULL,
    rolling_fees_vnd BIGINT NOT NULL,
    energy_vnd BIGINT NOT NULL,
    battery_vnd BIGINT NOT NULL,
    scheduled_maintenance_vnd BIGINT NOT NULL,
    total_vnd BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_tco_estimates_total CHECK (
        total_vnd = promoted_purchase_price_vnd + rolling_fees_vnd
            + energy_vnd + battery_vnd + scheduled_maintenance_vnd
    )
);

CREATE INDEX ix_tco_estimates_run ON tco_estimates (run_id);
```

`assumption_id` trỏ tới `tco_assumptions.assumption_id` (module `products`, không FK cứng cùng lý do với `run_candidates`) — giữ được truy vết "kết quả TCO này dùng bộ giả định phiên bản nào" ngay cả khi Admin cập nhật giả định mới sau đó. `monthly_distance_km` là kết quả đã quy đổi theo `DAYS_PER_MONTH = 30` (mục "Quy tắc bắt buộc để TCO deterministic" trong `vehicle-catalog-schema.md`), lưu tường minh để audit không phải tính lại. `ck_tco_estimates_total` là lưới an toàn cấp DB cho đúng công thức A5-5 — cộng sai ở code thì insert thất bại.

---

## agent_0004 — HITL

### `review_queue`

Bảng này là trọng tâm của gate A7 và là chỗ review trước phát hiện thiếu cột: A7-2 đã mô tả hành vi "claim với CAS và lease 15 phút", nhưng DDL trước đó chưa có cột nào chứa được `claim`, `lease` hay `version` — hành vi được đặc tả nhưng không có chỗ lưu.

```sql
CREATE TABLE review_queue (
    review_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    claimed_by VARCHAR(64),
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    advisor_id VARCHAR(64),
    processed_at TIMESTAMPTZ,
    edited_content TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_review_queue_status CHECK (
        status IN ('PENDING', 'APPROVED', 'EDITED', 'REJECTED')
    ),
    CONSTRAINT ck_review_queue_claim_pair CHECK (
        (claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL)
        OR (claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);

CREATE INDEX ix_review_queue_status_lease
    ON review_queue (status, lease_expires_at);

CREATE INDEX ix_review_queue_session
    ON review_queue (session_id, created_at DESC);
```

**Ba cột phục vụ CAS (compare-and-swap):**

| Field | Kiểu | Dùng để |
|---|---|---|
| `claimed_by` | VARCHAR(64) nullable | Tư vấn viên đang giữ mục này. Null nghĩa là chưa ai claim hoặc lease đã hết hạn và mục quay lại trạng thái nhận claim được. |
| `claimed_at` | TIMESTAMPTZ nullable | Thời điểm claim, dùng audit và tính thời gian xử lý trung bình. |
| `lease_expires_at` | TIMESTAMPTZ nullable | `claimed_at + 15 phút` (A7-2). Sau mốc này, tư vấn viên khác được phép claim lại dù `claimed_by` còn giá trị cũ — hết hạn không tự xoá `claimed_by`, mà điều kiện claim mới kiểm tra `lease_expires_at < now()`. |
| `version` | INTEGER | Optimistic concurrency. Mọi UPDATE claim/xử lý phải kèm `WHERE version = :expected_version` và `SET version = version + 1`; UPDATE trả về 0 dòng nghĩa là có tư vấn viên khác đã thắng, code phải đọc lại và báo "mục đã được người khác xử lý", không retry mù. |

**Câu lệnh claim mẫu (CAS đầy đủ):**

```sql
UPDATE review_queue
SET claimed_by = :advisor_id,
    claimed_at = now(),
    lease_expires_at = now() + INTERVAL '15 minutes',
    version = version + 1,
    updated_at = now()
WHERE review_id = :review_id
  AND status = 'PENDING'
  AND version = :expected_version
  AND (claimed_by IS NULL OR lease_expires_at < now());
```

Không cần `SELECT ... FOR UPDATE` trước — chính `UPDATE ... WHERE version = :expected_version` đã là CAS nguyên tử của Postgres. Ứng dụng đọc `version` hiện tại trước khi hiển thị nút "Nhận xử lý", gửi lại đúng `version` đó khi bấm; UPDATE trả 0 dòng thì hiển thị "đã có người nhận", không hiển thị lỗi chung chung.

**Phân công customer↔advisor:** không phải cột riêng trên `review_queue` — dùng `conversation_sessions.assigned_advisor_id`. Một khi tư vấn viên claim review đầu tiên của một phiên, application set `assigned_advisor_id` nếu đang null, để các lượt HITL/booking/lịch sử sau của cùng phiên ưu tiên gợi ý đúng người đó (không bắt buộc, Admin vẫn phân công lại được). `ck_review_queue_claim_pair` đảm bảo ba cột claim luôn cùng có hoặc cùng không — không có trạng thái nửa vời như có `claimed_by` mà thiếu `lease_expires_at`.

---

## agent_0005 — Lái thử, thông báo nội bộ

### `test_drive_bookings`

```sql
CREATE TABLE test_drive_bookings (
    booking_id UUID PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    vehicle_id UUID NOT NULL,
    advisor_id VARCHAR(64),
    run_id UUID REFERENCES agent_runs(run_id) ON DELETE SET NULL,
    showroom VARCHAR(255) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'REQUESTED',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_test_drive_bookings_status CHECK (
        status IN ('REQUESTED', 'CONFIRMED', 'CANCELLED')
    )
);

CREATE INDEX ix_test_drive_bookings_showroom_time
    ON test_drive_bookings (showroom, scheduled_at)
    WHERE status <> 'CANCELLED';

CREATE INDEX ix_test_drive_bookings_customer
    ON test_drive_bookings (customer_id, scheduled_at DESC);
```

`run_id` nullable, `ON DELETE SET NULL` — A8-2 yêu cầu đặt lịch phải xuất phát từ "đề xuất đã duyệt" (kiểm ở application: `run_id` phải trỏ tới run có `state = 'APPROVED'` hoặc `'DELIVERED'`), nhưng không FK cứng theo kiểu chặn xoá vì lịch sử đặt lịch phải giữ được kể cả khi run gốc dọn dẹp sau này.

### `internal_notices`

```sql
CREATE TABLE internal_notices (
    notice_id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    priority VARCHAR(16) NOT NULL DEFAULT 'NORMAL',
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_internal_notices_priority CHECK (priority IN ('NORMAL', 'URGENT'))
);

CREATE INDEX ix_internal_notices_created ON internal_notices (created_at DESC);
```

### `notice_reads`

```sql
CREATE TABLE notice_reads (
    notice_id UUID NOT NULL REFERENCES internal_notices(notice_id) ON DELETE CASCADE,
    advisor_id VARCHAR(64) NOT NULL,
    read_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (notice_id, advisor_id)
);
```

Khoá chính tổng hợp: mỗi tư vấn viên chỉ có một trạng thái đã-đọc cho một notice, khớp A8-4 "hai tư vấn viên đọc cùng notice → hai hàng độc lập".

---

## agent_0006 — Dashboard phễu

### `VIEW funnel_metrics`

```sql
CREATE VIEW funnel_metrics AS
SELECT
    date_trunc('day', cs.started_at) AS day,
    count(DISTINCT cs.session_id) AS sessions_started,
    count(DISTINCT cs.session_id) FILTER (
        WHERE EXISTS (
            SELECT 1 FROM conversation_slots slot
            WHERE slot.session_id = cs.session_id
        )
    ) AS sessions_with_profile,
    count(DISTINCT ar.session_id) FILTER (WHERE ar.state IN ('PENDING_REVIEW', 'APPROVED', 'DELIVERED'))
        AS sessions_with_recommendation,
    count(DISTINCT rq.session_id) FILTER (WHERE rq.status = 'APPROVED')
        AS sessions_approved,
    count(DISTINCT tdb.customer_id) FILTER (WHERE tdb.status <> 'CANCELLED')
        AS sessions_booked
FROM conversation_sessions cs
LEFT JOIN agent_runs ar ON ar.session_id = cs.session_id
LEFT JOIN review_queue rq ON rq.session_id = cs.session_id
LEFT JOIN test_drive_bookings tdb ON tdb.customer_id = cs.customer_id
GROUP BY date_trunc('day', cs.started_at);
```

View, không phải bảng — không có dữ liệu riêng, tính lại từ năm bảng nguồn mỗi lần query. `downgrade()` của `agent_0006` phải có `DROP VIEW funnel_metrics` (mục 6, nit 6e `vinfast-agent-mvp.md`). Bộ lọc 7 ngày/30 ngày/tuỳ chỉnh (A9-1) áp ở application bằng `WHERE day >= :from`, không hardcode trong view.
