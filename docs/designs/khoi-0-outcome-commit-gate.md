# Spec Khối 0: Outcome semantic và commit gate thống nhất

Ngày: 2026-09-01  
Repo: `/Users/phungdinhdat/Documents/git/P-150`  
Branch: `feature/sua-thu-tu-spec-qa`  
Trạng thái: DRAFT  
Phạm vi: production audit, bốn lỗi K0-1 đến K0-4

## 1. Quyết định cốt lõi

Chọn **Outcome + commit gate thống nhất**. Không vá bằng regex, substring hoặc thêm bảng từ khóa để đoán một số câu cụ thể. LLM phải hiểu intent, tham chiếu, câu trả lời pending và ngữ cảnh đa lượt qua structured output đã có schema; code deterministic giữ invariant về ownership, side effect, persisted truth và commit.

LLM được phép trả lời semantic facts đã có consumer trong policy sau:

- dialogue act/intent;
- vehicle references và choice reference;
- yêu cầu handoff, booking, retry hoặc thay đổi lựa chọn;
- confidence và trạng thái chưa rõ.

LLM không được quyết định:

- phiên thuộc AI hay HUMAN;
- external side effect đã thành công hay chưa;
- booking nào là booking persisted;
- có được commit state/result hay không;
- customer-facing success khi chưa có bằng chứng persisted.

Đây là spec để triển khai sau khi được duyệt. **Không triển khai code trong phase này.**

## 2. Problem statement và customer harm

Core v2 hiện tách decision, act, ownership setter và commit thành các bước không có một outcome contract chung:

1. `run_turn._project_ownership()` bắt lỗi lookup rồi coi phiên như AI. Nếu session đang `HANDED_OFF`, stage bị kéo về `CHOSEN`; bot có thể nói chồng lên tư vấn viên.
2. `_ask_province()` vượt `MAX_PROVINCE_ASKS` chỉ trả `state_patch={stage: HANDED_OFF}`. `_mark_handoff_pending()` chỉ chạy với `Handoff | EnqueueHitl`, nên ownership vẫn AI và lượt sau có thể tiếp tục trả lời.
3. Booking token bind session/customer nhưng chưa bind vehicle. Replay token cũ sau khi state đổi xe có thể trả booking persisted của xe cũ trong khi renderer lấy tên xe mới từ state hiện tại.
4. `act()` throw bị đổi thành fallback text, sau đó `run_turn` vẫn áp `decision.state_after`/patch và commit. State có thể nói side effect đã xong dù action chưa xong; retry mất pending context.

Hậu quả: mất niềm tin, tư vấn viên bị bypass, xác nhận đặt lịch sai dữ kiện, retry gây hành vi không dự đoán được và audit không thể phân biệt semantic failure với infrastructure failure.

## 3. Evidence và mức độ xác nhận

### Provenance

**VERIFIED_PROD_SNAPSHOT + VERIFIED_CURRENT_SOURCE:** K0-1: `src/agents/core/run_turn.py:357-383`, lookup exception tại khoảng `369-372` fail-open.

**VERIFIED_PROD_SNAPSHOT + VERIFIED_CURRENT_SOURCE:** K0-2: `src/agents/core/act.py:2185-2205`, nhánh vượt trần tại `2197` chỉ patch stage.

**VERIFIED_PROD_SNAPSHOT + VERIFIED_CURRENT_SOURCE:** K0-3: `src/agents/core/act.py:2280-2314`; `src/agents/services/slot_token.py`; `src/agents/services/test_drive.py:123-191`; `src/agents/adapters/repositories.py:849-864`.

**VERIFIED_PROD_SNAPSHOT + VERIFIED_CURRENT_SOURCE:** K0-4: `src/agents/core/run_turn.py:159-170`; `commit_core_turn` atomic cho write bên trong nhưng không bao trùm act/external side effect.

**VERIFIED_CURRENT_SOURCE:** Handoff setter mở transaction riêng: `src/agents/services/conversation.py:188-192`; caller ngoài commit tại `run_turn.py:491-523`. `commit_core_turn` ghi outcome, state và trace cùng transaction: `src/agents/services/conversation_memory.py:309-391`.

### USER_VERIFIED correction

- Booking duplicate không phải P0. `_existing_booking(customer, showroom, scheduled_at)` chống replay tuần tự; **không có DB uniqueness cho cùng khách + cùng operation và concurrent replay còn race**. Index `ix_test_drive_bookings_showroom_time` là index thường, không unique (`src/agents/models.py:546-553`). Bug thật user verify là vehicle mismatch khi replay token cũ.

### UNVERIFIED, không dùng làm fact của Khối 0

- `VF2 hay VF3?` bị phân loại CHOICE thay vì COMPARE.
- Pending confirm bị intent mới cắt ngang.
- `VF 99 + Hà Nội` nuốt tên xe lỗi rồi tiếp tục bằng xe cũ.
- Các claim về empty dataset, unknown expect key, 429, judge verdict, truthy string, strict zip và exit code của eval runners.

## 4. Invariants bắt buộc

1. **Handoff fail-closed:** lỗi/timeout/thiếu adapter khi đọc ownership không được biến thành ownership AI. Với session đang hoặc có dấu hiệu `PENDING_HANDOFF`, `HUMAN`, `HANDED_OFF`, hệ thống phải im lặng an toàn hoặc trả trạng thái chờ người; không chạy semantic decision để bot trả lời.
2. **Stage và ownership không mâu thuẫn:** `HANDED_OFF` chỉ hợp lệ khi ownership là `PENDING_HANDOFF` hoặc `HUMAN`; ownership AI không được project thành `HANDED_OFF`.
3. **Không báo handoff success giả:** customer-facing handoff success chỉ được render khi transition ownership thành công và đọc-back thấy `PENDING_HANDOFF/HUMAN`, hoặc hệ thống đã chuyển sang fail-closed state với thông báo không hứa transition đã hoàn tất.
4. **Outcome là nguồn commit duy nhất:** `run_turn` không tự suy side-effect success từ `Action`, state patch hoặc text. Mọi state patch phải đi qua typed outcome validation.
5. **Persisted truth thắng mutable state:** booking confirmation lấy vehicle/showroom/slot từ booking persisted/result trả bởi service, không lấy lại từ `CoreState` sau khi side effect chạy.
6. **Act failure không advance state giả:** nếu side effect chưa xác nhận thành công, không commit `booking_id`, clear pending, chuyển stage thành công hoặc handoff success.
7. **Retry an toàn:** lỗi trước external commit giữ/reconstruct pending intent và idempotency key; retry không tạo duplicate. Nếu external commit đã thành công nhưng response/persistence thất bại, retry phải reconcile bằng key trước khi tạo mới.
8. **LLM không bypass invariant:** structured semantic output chỉ lái action intent; commit gate có quyền từ chối outcome không đủ bằng chứng.
9. **Một turn có một truth:** persisted outcome, core state, trace và customer-facing result phải mô tả cùng outcome; nếu commit transaction fail, không công bố result như đã hoàn tất.

## 5. Outcome contract đề xuất

Tên cụ thể có thể điều chỉnh khi implementation đọc type hiện tại, nhưng không được bỏ trường semantics dưới đây:

```text
ActOutcome
  response: RenderableResponse
  state_patch: ValidatedStatePatch
  side_effect: SideEffectOutcome
  ownership: OwnershipOutcome
  booking: PersistedBookingRef | None
  retry: RetryContext | None
  failure: ActFailure | None
  observability: OutcomeMetadata
```

Quy tắc:

- `failure != None` không đồng nghĩa có thể commit `state_patch`; gate phải lọc patch theo side-effect state.
- `side_effect` dùng trạng thái tối thiểu `NOT_ATTEMPTED`, `SUCCEEDED`, `FAILED`, `UNKNOWN`, không dùng bool mơ hồ.
- `UNKNOWN` là fail-closed cho customer-facing success; retry chạy reconcile trước create.
- `ownership` ghi `NOT_REQUESTED`, `PENDING_CONFIRMED`, `HUMAN_CONFIRMED`, `TRANSITION_FAILED`, `UNKNOWN`.
- `booking` phải chứa persisted `booking_id`, `vehicle_id`, `showroom`, `scheduled_at`, customer/session binding hoặc DTO tương đương. Renderer dùng object này.
- `retry` giữ operation kind, idempotency key, immutable request fingerprint và pending intent cần resume.
- `response` không được là bằng chứng side effect; text chỉ render sau gate.

### Durable booking operation contract

Khối 0 chốt một operation ledger durable, không dùng in-memory retry:

```text
BookingOperation
  operation_id: UUID
  fingerprint: SHA-256 canonical payload, UNIQUE
  payload_hash: SHA-256 immutable request payload
  customer_id
  session_id
  vehicle_id
  showroom_normalized
  scheduled_at_utc
  status: REQUESTED | SUCCEEDED | FAILED | UNKNOWN
  booking_id: UUID | None
  error_code: safe enum | None
  created_at / updated_at / expires_at
```

Canonical fingerprint input là versioned JSON với stable key order: `v`, `customer_id`, `session_id`, lowercase canonical UUID `vehicle_id`, trimmed/collapsed-space showroom identifier, ISO-8601 UTC `scheduled_at`. Không gồm mutable display name hoặc current state. Same fingerprint + different payload hash là `BookingOperationConflict`, không reuse.

Service API mục tiêu:

```text
create_or_reconcile(request: BookingRequest, fingerprint: str)
  -> PersistedBookingDTO
```

`PersistedBookingDTO` gồm `booking_id`, `customer_id`, `session_id`, `vehicle_id`, `showroom`, `scheduled_at`, `operation_id`, `replayed`. Transaction booking phải atomically claim unique fingerprint, create booking + notice, rồi mark operation `SUCCEEDED` với booking ID. Concurrent same fingerprint: một creator, caller còn lại đọc cùng persisted DTO. Same slot nhưng khác fingerprint vẫn là operation độc lập theo capacity policy hiện tại. Crash sau booking insert trước operation success rollback cả booking + operation vì cùng booking UoW transaction. `UNKNOWN` chỉ dành cho adapter ngoài transaction; current local DB path không được tạo UNKNOWN cho lỗi transaction rõ.

Retention: giữ operation cùng vòng đời booking; không xóa operation đang `REQUESTED/UNKNOWN`; terminal operation chỉ purge sau booking retention policy và không sớm hơn token expiry + replay window. Retry owner là request path theo `client_turn_id`; background reconciliation chỉ cần nếu adapter ngoài transaction được thêm sau này, ngoài Khối 0.


`understand` tiếp tục là cổng LLM structured hiện hữu với `intent`, `dialogue_act`, `vehicle_ids`, `choice_ref`, `confidence`. Khối 0 **không mở rộng semantic schema nếu không có consumer và acceptance test trực tiếp**. Cấm thêm transcript-specific regex/substring branch để phân loại ý định cho vài câu lỗi. Regex/protocol parsing vẫn hợp lệ cho HMAC token framing, validation, normalization và format tất định. Khi LLM hỏng/sai schema, dùng `UNCLEAR`; ownership gate chạy trước nên `UNCLEAR` không kéo phiên handoff về AI.

## 6. Transaction boundary

### Boundary logic

```text
load user + state + ownership
  → ownership gate (fail-closed)
  → LLM semantic understanding
  → deterministic policy/action
  → act: external side effect, immutable request fingerprint
  → normalize ActOutcome
  → commit gate validates outcome + ownership + persisted truth
  → one persistence transaction: message/result + core state + outcome + trace + review row
  → return persisted result
```

`commit_core_turn` hiện atomic cho memory/outcome/core state/trace/review. Khối 0 chốt exact API:

```text
begin_core_turn(session_id, customer_id, client_turn_id) -> TurnClaim
commit_core_turn(
  claim: TurnClaim,
  user_message: str,
  result: TurnResult,
  core_state: CoreState,
  trace: TurnTrace,
  ownership_transition: OwnershipTransition | None,
  retry_context: RetryContext | None,
) -> PersistedTurnResult
```

`begin_core_turn` chỉ claim `IN_PROGRESS`, không append content. `commit_core_turn` mở transaction theo thứ tự: validate claim owner/lease → append USER → apply ownership transition + read-back → append ASSISTANT → finalize outcome → save core state/retry context → record trace/review → mark claim `COMPLETED`. Lỗi bất kỳ rollback toàn bộ và không trả result. Handoff transition lỗi rollback trước; orchestration mở fallback transaction riêng để persist câu `HANDOFF_UNAVAILABLE` **và durable `handoff_retry_required` marker trong cột riêng** của `conversation_core_state`, không handoff success/stage patch. Ownership gate đọc marker trước LLM; chỉ xóa marker sau transition confirmed hoặc terminal cancellation. Replay key `(session_id, client_turn_id)` trả persisted result khi `COMPLETED`.

Marker encoding versioned, không đi qua `slot_codec.coerce_slots`: thêm cột nullable riêng, ví dụ `handoff_retry JSONB`, vào `conversation_core_state`; `pending` giữ câu pending bình thường và `slots` chỉ chứa `SlotName` hợp lệ. Shape cột là `{version: 1, status: REQUIRED|EXPIRED, created_at, expires_at, attempt_count, last_error_code}`. Mọi set/retry/expiry/delete chạy trong transaction với row lock/CAS trên `conversation_core_state.session_id`; stale writer không được ghi đè marker mới. Đây là schema migration có chủ đích, không sửa `coerce_slots`, không miễn trừ prefix và marker không thể lọt vào prompt `understand._slots_line`.

Nếu fallback transaction cũng lỗi, không nuốt lỗi rồi trả câu tĩnh không marker: trả retryable application error cho transport, ghi structured error log/metric, coi turn chưa hoàn tất; client retry cùng `client_turn_id` sau khi hạ tầng hồi phục.

`_conversation_transaction` tại `src/agents/composition.py:263-277` dựng `sessions`, `core_state`, `outcomes`, `messages`, `turn_traces`, `review_queue` trên cùng `AsyncSession`; `ConversationMemoryService` và `ConversationService` nhận cùng typed UoW. Vì vậy ownership transition + core commit **đủ điều kiện chạy chung một DB transaction**. `ConversationTransaction` thêm `sessions.request_handoff/get_ownership` và expose transaction identity; `run_turn` bỏ `_mark_handoff_pending()` ngoài commit. Acceptance assert ownership update và core writes dùng cùng SQLAlchemy `AsyncSession`/transaction identity, không chỉ assert end state. Booking ledger dùng `BookingUnitOfWork` riêng, nhưng booking + operation row atomic trong booking UoW; core commit chỉ nhận DTO đã persisted.

Nhánh `NO APPROVAL/saga` không kích hoạt. Không chọn transition-after-commit/best-effort setter.



| Tình huống | State commit | Customer response | Retry |
|---|---|---|---|
| Chưa gọi side effect | Chỉ commit state không phụ thuộc side effect | clarify/retry | giữ pending |
| Side effect success + persistence success | commit success state | success từ persisted result | exact replay trả cùng result |
| Side effect fail rõ | không commit success patch | lỗi an toàn, không hứa thành công | retry cùng fingerprint |
| Side effect unknown | không commit success patch | pending/retry, không hứa | reconcile trước create |
| External success + local commit fail | không rollback external | không completed response; retryable application error | reconcile bằng idempotency key |
| Ownership transition fail/unknown | rollback ownership/core; fallback ghi safe outcome + marker cột riêng | câu `HANDOFF_UNAVAILABLE`, không success | marker chặn LLM; retry đến 24h, rồi expiry path |
| Fallback transaction fail | không có completed turn | retryable application error, không trả câu tĩnh | retry cùng `client_turn_id` sau hạ tầng hồi phục |

| Booking persisted + renderer fail | booking operation/row vẫn atomic success; core turn không success | không tự tạo booking lần nữa | next request reconcile fingerprint, render persisted DTO |
| Ownership confirmed + core commit fail | same-UoW rollback ownership về trước transaction | không completed response; retryable application error | retry same turn, read-back trước retry |
| Booking success + ownership fail | booking may remain valid; no handoff success | không trộn two outcomes | retry ownership; booking replay exact fingerprint |
| `failure != None` + safe non-side-effect patch | safe patch only | booking/stage success/clear retry | persist explicit failed outcome if contract permits |

### Commit-gate matrix

| Action/outcome | Allowed patch | Forbidden patch | Persist/render |
|---|---|---|---|
| Pure reply/ask, `NOT_ATTEMPTED` | semantic/pending fields | `booking_id`, handoff stage | commit normal response |
| Handoff, ownership confirmed | `stage=HANDED_OFF`, review/pending | `stage=CHOSEN` | atomic ownership + turn, then success |
| Handoff, failed/unknown | fail-closed/retry only | handoff success, `stage=CHOSEN` | safe text, no success |
| Booking, side effect success + persisted DTO | booking fields from DTO | mutable current vehicle | render persisted DTO |
| Booking, failed/unknown | preserve/reconstruct pending | `booking_id`, success stage, clear pending | retry response, no success |
| Any renderer/source exception | no success patch | all success markers | rollback or explicit failure outcome |

Gate rejects unknown patch keys, invalid stage transitions, missing DTO fields and success response without confirmed evidence.

### Ownership lookup matrix

Adapter phải trả typed `OwnershipSnapshot`: `AI`, `PENDING_HANDOFF`, `HUMAN`, `NOT_FOUND`; exception/timeout/missing adapter được normalize thành `ERROR`, `TIMEOUT`, `ADAPTER_MISSING`, không ép bool.

Transition protocol trong transaction: `sessions.request_handoff(session_id) -> OwnershipSnapshot`; repository update chỉ từ `AI` sang `PENDING_HANDOFF`, rồi `get_ownership` read-back trong cùng transaction. `PENDING_HANDOFF/HUMAN` được coi confirmed idempotent; race `PENDING_HANDOFF → HUMAN` vẫn success. `AI`, `NOT_FOUND`, exception hoặc bool `False` không confirmed và làm transaction rollback. Session `NOT_FOUND` không được tạo ngầm ở nhánh handoff; turn trả retryable session error.

| Snapshot | Persisted stage `HANDED_OFF` | Stage khác |
|---|---|---|
| `HUMAN/PENDING_HANDOFF` | bot silent, không gọi LLM | project `HANDED_OFF`, bot silent |
| `AI` | project `CHOSEN`, chạy LLM | giữ stage hợp lệ, chạy LLM |
| `NOT_FOUND` | fail-closed, không gọi LLM | reject turn/session error, không tự nhận AI |
| `ERROR/TIMEOUT/ADAPTER_MISSING` | fail-closed, không gọi LLM | fail-closed cho turn; safe unavailable response, không mutate ownership/stage |

Fail-closed không dùng text “đã chuyển tư vấn viên” nếu chưa có ownership truth. Câu customer-facing bắt buộc:

> “Hệ thống đang kết nối tư vấn viên, anh/chị vui lòng chờ trong giây lát rồi thử lại ạ.”

Text không khẳng định handoff đã hoàn tất; result dùng `terminal_reason=HANDOFF_UNAVAILABLE`, `turn_status=COMPLETED` chỉ sau khi câu an toàn + marker được persist. Persisted stage cũ không bị rewrite thành `CHOSEN`. Nếu session lookup không xác định được session hợp lệ, dùng cùng câu này, không tạo session ngầm. Marker là fail-closed durable state: lượt sau không gọi LLM/AI response. Trước `expires_at=created_at+24h`, mỗi lượt tăng `attempt_count` bằng CAS rồi retry transition. Sau expiry, reconciliation một lần; nếu vẫn fail, atomically đổi status thành `EXPIRED`, persist `terminal_reason=HANDOFF_RETRY_EXPIRED`, rồi cho phép policy tiếp tục AI với câu nói rõ handoff chưa thành công và hỏi khách có muốn thử lại. `EXPIRED` không chặn LLM; terminal cancellation xóa marker. Test set, retry increment, concurrent CAS, expiry transition và delete.

### Commit failure delivery semantics

- Không trả success object trước khi `commit_core_turn` hoàn tất.
- Nếu core commit fail trước HTTP response, raise retryable application error; transport trả lỗi chuẩn hiện hữu. Không trả ephemeral “pending” như completed turn. Chỉ handoff transition failure đã rollback mới được fallback transaction ghi câu `HANDOFF_UNAVAILABLE`.
- `client_turn_id` replay phải kiểm durable turn outcome; nếu chưa có outcome nhưng operation fingerprint đã success, reconcile rồi commit same persisted truth.
- Chốt đưa user-message append vào cùng core transaction với outcome/state/trace. `TurnClaim` có `claim_token`, `claimed_at`, `lease_expires_at`; lease 60 giây, act timeout phải ngắn hơn lease. Concurrent caller khác token nhận `TurnInProgressError`; sau lease, caller mới atomic takeover nếu vẫn `IN_PROGRESS`; token cũ bị reject khi commit. Crash trước commit không append content; retry cùng ID reclaim sau rollback/lease. `FAILED` chỉ cho terminal validation failure và trả failure rõ. Không chọn append-before-act + flag rời.
- “Customer saw response” chỉ đúng khi response được trả sau persisted commit; logs không được đánh success cho response chưa persisted.

## 7. State diagrams

### Normal handoff

```text
AI + action Handoff/EnqueueHitl
  → request ownership PENDING_HANDOFF
  → read-back PENDING_HANDOFF/HUMAN
  → outcome ownership confirmed
  → persist turn + review + state atomically
  → customer sees handoff success; next turn bot silent
```

### Handoff failure

```text
AI + handoff action
  → setter timeout/error/unknown
  → no HANDED_OFF success patch
  → fail-closed state
  → customer sees safe pending/error text, never false success
  → retry/reconciliation can complete transition
```

### Booking normal/replay

```text
signed token(bind session, customer, vehicle, showroom, slot)
  → validate signature/expiry/fingerprint
  → booking lookup by exact immutable tuple
  → create-or-return persisted booking
  → outcome.booking is persisted DTO
  → confirmation renders outcome.booking.vehicle_id
```

### Booking mismatch

```text
old token(VF5) + current state(VF7)
  → token vehicle VF5 != current mutable state VF7
  → no silent reuse as VF7
  → conflict/restart response (recommended)
  → exact old tuple replay may return old booking and say VF5
```

### Act failure/retry

```text
policy state_after + action
  → act external call
  → fail or UNKNOWN
  → commit gate rejects success patch
  → preserve pending + retry context
  → next turn semantic LLM sees pending intent
  → reconcile idempotency key
  → success commits only after persisted truth
```

## 8. Exact files/directories dự kiến

### Product source

- `src/agents/core/actions.py`: mở rộng typed outcome-related contracts nếu đặt cạnh action contracts là phù hợp.
- `src/agents/core/act.py`: side-effecting actions trả outcome đầy đủ; pure actions normalize từ `ActResult` mà không đổi semantics. Bỏ handoff province chỉ patch stage; booking trả persisted booking DTO.
- `src/agents/core/run_turn.py`: ownership gate fail-closed; commit gate; không catch act rồi áp state success giả; orchestration retry/reconcile.
- `src/agents/core/state.py`: encode/decode marker từ cột riêng; `slots` chỉ nhận `SlotName`; không đổi stage semantics âm thầm.
- `src/agents/models.py`: khai `ConversationCoreStateRow.handoff_retry` nullable JSONB cạnh các field core state hiện hữu.
- `src/agents/core/repository.py`: map `handoff_retry` hai chiều khi save/load `CoreState`; không đưa qua slot codec.
- `src/agents/services/test_drive.py`: canonical booking fingerprint, atomic `create_or_reconcile`, persisted booking DTO.
- `src/agents/services/slot_token.py` và `src/agents/domain/test_drive_booking.py`: token payload bind vehicle ID và versioned decode/expiry semantics.
- `src/agents/services/conversation.py`: typed ownership snapshot; transaction-aware transition/read-back.
- `src/agents/services/conversation_memory.py`: ownership transition + retry/outcome metadata trong cùng transaction; không coi ephemeral response là persisted success.
- `src/agents/adapters/repositories.py`: exact booking lookup/read và ownership atomic/read-back adapter.
- `src/agents/ports.py`, `src/agents/contracts.py`: cập nhật protocol/DTO, giữ backward compatibility có chủ đích trong cùng implementation.
- `migrations/agents/versions/agent_0035_handoff_retry_marker.py`: cột nullable `handoff_retry JSONB` cho K0-1/K0-2; revision nối head hiện hành sau migration preflight.
- `migrations/agents/versions/agent_0036_booking_operation_ledger.py`: ledger + unique fingerprint cho K0-3; số revision chỉ là target sequence, phải kiểm tra Alembic head sau PR2 trước khi tạo file.

`_is_slot_conflict` và nhánh `except IntegrityError` tại `src/agents/services/test_drive.py:138-159` hiện dựa trên unique slot index đã bị bỏ ở `agent_0034`; current source không còn constraint tương ứng. Trong PR K0-3 phải chọn có ý thức:

- xóa dead branch/comment sai nếu preflight schema xác nhận không còn constraint nào phát signal đó; hoặc
- giữ nhưng đổi thành guard cho constraint cụ thể còn tồn tại, với test chứng minh.

Không để nguyên comment “chỉ index UNIQUE mới đóng được” khi index hiện là non-unique.

### Tests, test-first

Viết failing regression test trước source implementation:

- `tests/agents/unit/core/test_run_turn.py`: act throw không commit success state; ownership lookup failure fail-closed.
- `tests/agents/unit/core/test_run_turn_handoff.py`: ownership `HUMAN/PENDING`, stage `HANDED_OFF`, timeout/adapter failure, escalation multi-turn.
- `tests/agents/unit/core/test_act.py`: province cap trả formal handoff outcome; booking confirmation lấy persisted vehicle; no success on unknown.
- `tests/agents/unit/services/test_test_drive_*.py`: token vehicle binding, exact replay, vehicle mismatch, no duplicate.
- `tests/agents/unit/services/test_commit_core_turn_atomicity.py`: commit gate/rollback và retry metadata.
- `tests/agents/integration/test_booking.py`: replay exact tuple, old token after vehicle change, persisted confirmation.
- `tests/agents/integration/test_post_pitch_test_drive_e2e.py`: vượt `MAX_PROVINCE_ASKS`, handoff, lượt sau bot không trả lời như AI.

Không xóa/đổi test hiện hữu chỉ để làm test mới pass. Mỗi behavior change phải có test failure path và success path.

### Action inventory và allowed transitions

| Nhóm | Current actions | Allowed transition | Side-effect rule |
|---|---|---|---|
| Pure | `Reply`, `Ask`, `Lookup`, `Compare`, `Nearby`, `VehicleQa`, `FitCheck`, `NextSteps`, `ScopeNote`, `Recommend`, `Tco`, `OnRoadPrice`, `NotInCatalog` | policy-approved pending/ask-count fields only | normalize `ActResult`; no booking/handoff success |
| Booking side effect | `Book`, `ShowroomOptions` when it creates no booking | `Book`: booking fields only after DTO; options may set location/pending | operation ledger required for `Book` |
| Ownership side effect | `Handoff`, `EnqueueHitl`, province-cap escalation | `HANDED_OFF` only after ownership confirmed; review fields only after queue outcome | same DB UoW as core commit |
| Silent | `Silent` | no stage mutation | no LLM call, persist terminal handoff result as defined |

Gate validates transition enum and patch schema, not action-name strings alone. Pure action may not clear booking pending or set `booking_id`.

## 9. Dependency order

1. **K0 foundation:** chốt typed `ActOutcome`, status enums, immutable request fingerprint và commit-gate validator. Viết tests contract trước.
2. **K0-1:** ownership lookup fail-closed và invariant projection. Đây là blocker vì mọi turn sau handoff phụ thuộc nó.
3. **K0-2:** province escalation phát ra formal handoff outcome, transition ownership trong cùng gate; test chuỗi đa lượt.
4. **K0-4:** act failure/unknown semantics, pending reconstruction, reconcile hook; cần outcome contract và commit gate từ bước 1.
5. **K0-3:** token vehicle binding, exact booking idempotency, persisted DTO render. Có thể code song song sau foundation, nhưng rollout sau K0-4 để dùng cùng retry semantics.
6. Integration, observability, feature flag, canary và rollback rehearsal.

### PR slicing và ước lượng

Mỗi PR rebase `develop`, một commit squash, test độc lập; không merge develop vào feature.

| PR | Scope | Phụ thuộc | Ước lượng người | Ước lượng agent |
|---|---|---|---:|---:|
| PR1 Foundation | typed outcome, commit gate, TurnClaim lease/reclaim, atomic core commit API | none | 2-3 ngày | 4-6 giờ |
| PR2 K0-1 | typed ownership snapshot, fail-closed lookup/projection, exact safe text, marker column migration + upgrade/downgrade/preflight tests | PR1 | 1.5-2 ngày | 3-5 giờ |
| PR3 K0-2 | province escalation formal handoff, same-UoW transition/read-back, multi-turn tests | PR1-2 | 1-2 ngày | 3-4 giờ |
| PR4 K0-4 | act failure matrix, pending reconstruction, crash/retry tests | PR1-3 | 2 ngày | 4-6 giờ |
| PR5 K0-3 | token v2 vehicle binding, ledger, migration kế tiếp sau marker, preflight, persisted DTO, concurrency tests, dead branch cleanup | PR1 + PR2; rollout sau PR4 | 3-4 ngày | 6-10 giờ |

Tổng: khoảng 9.5-13 ngày người hoặc 20-31 giờ agent, chưa tính CI/reviewer/rollout wait. PR2 và K0-3 có schema migration/preflight; K0-3 vẫn tách riêng vì ledger + data duplicate/concurrency risk lớn hơn.


## 10. Acceptance criteria

### K0-1, P0

- Lookup throw, timeout và adapter failure không chuyển `HANDED_OFF` về `CHOSEN`.
- Ownership `HUMAN` và `PENDING_HANDOFF` làm bot không chạy semantic answer như AI.
- Không lộ exception, token, customer content; log có session hash/id không nhạy cảm, error class và latency.
- `HANDED_OFF` không tồn tại trong persisted state nếu ownership không ở PENDING/HUMAN, trừ fail-closed marker được định nghĩa rõ.

### K0-2, P0

- Vượt `MAX_PROVINCE_ASKS` dùng formal handoff outcome/action, không chỉ patch stage.
- Ownership transition thành công được read-back trước customer-facing success.
- Transition fail/unknown không nói “đã chuyển tư vấn viên”; lượt sau bot không nói như AI.
- Chuỗi nhiều lượt được test từ hỏi tỉnh lần 1, lần 2, vượt trần, handoff, lượt tiếp theo.

### K0-3, P1

- Token chứa và xác thực vehicle ID, showroom, slot, customer, session, expiry và version.
- Exact tuple replay không tạo duplicate và trả đúng persisted booking.
- Token VF5 sau state đổi VF7 không xác nhận VF7; khuyến nghị trả conflict/restart. Nếu chọn trả booking cũ, text phải nói VF5.
- Render chỉ dùng persisted booking DTO/result; không đọc vehicle mutable state cho confirmation.
- Durable operation ledger có unique fingerprint là yêu cầu của K0-3. Production preflight quyết định backfill/duplicate cleanup và rollout index, không quyết định có cần guarantee hay không.

### K0-4, P1

- Booking service throw, handoff setter fail, renderer/source throw đều không commit state biểu thị success.
- Pending intent không mất sau failure; retry lượt sau không bắt khách bắt đầu lại vô cớ.
- External success nhưng local persistence fail không tạo duplicate khi retry; reconcile bằng fingerprint.
- Core turn, outcome, state, trace/review rollback đồng bộ khi transaction fail.

## 11. Automated QA scenarios

Mỗi scenario phải có test đỏ trước implementation và test xanh sau implementation.

1. `load_handoff_state` throw trên stage `HANDED_OFF` → no AI response, no CHOSEN projection.
2. Ownership adapter timeout → fail-closed, safe response, metric increment.
3. Ownership `PENDING_HANDOFF`/`HUMAN` → bot silent/pending behavior, no LLM semantic call.
4. Province ask count reaches cap → formal handoff outcome, setter called, read-back confirmed.
5. Province handoff setter returns false/throws → no success text, no AI next-turn response.
6. Exact booking token replay → one booking row, same booking DTO, same vehicle confirmation.
7. Old VF5 token after state VF7 → conflict/restart, never “đã đặt VF7”.
8. Booking service throws before persistence → no `booking_id`, pending retry preserved.
9. External booking succeeds then `commit_core_turn` throws → retry reconciles same booking, no duplicate.
10. Action renderer/source throws after policy transition → no success patch committed.
11. Commit trace/review failure → all transactional writes rollback, retry context remains as designed.
12. LLM malformed/unclear output → semantic fallback, no regex-specific branch, invariants remain enforced.
13. Ownership adapter missing, returns `False`, read-back `AI`, `NOT_FOUND`, `ERROR`, or `TIMEOUT` × persisted stages `CHOSEN/HANDED_OFF` → assert exact safe behavior and no AI response where required.
14. Sequential exact replay → same DTO; concurrent same fingerprint → one booking; concurrent same slot/different fingerprint → independent operations; same fingerprint/different payload → conflict. Real-DB asserts row counts and values.
15. Process restart after external booking success before local commit → reconcile returns original booking, no duplicate.
16. Token version/expiry/vehicle mismatch and persisted booking DTO vehicle differing from mutable state → assert explicit conflict or correct old vehicle text.
17. Commit gate receives illegal patch key or invalid transition → reject and persist no success state.
18. Crash after turn claim, before act; after act, before core commit; during core commit → retry same `client_turn_id`, one user message, one final outcome, no duplicate side effect.
19. Real PostgreSQL round-trip: persist full versioned `handoff_retry` marker through `CoreStateRepository`, open transaction mới, load state, assert marker shape/value unchanged; assert marker absent from slots/prompt projection. Test upgrade and downgrade of marker migration against real schema.

## 12. Observability

Structured logs/metrics, no raw customer message or token:

- `core_outcome_total{action,outcome_status}`;
- `core_commit_gate_rejected_total{reason}`;
- `handoff_ownership_lookup_failure_total{phase}`;
- `handoff_transition_total{result}`;
- `booking_replay_total{result=exact|conflict|expired|invalid}`;
- `booking_reconcile_total{result}`;
- `act_failure_total{action,error_class}`;
- latency for ownership lookup, external act, commit and reconciliation.

Log correlation bằng `session_hash`, `client_turn_id`, `operation_fingerprint_hash`; không log token raw, customer ID raw, message raw, exception message chứa dữ liệu nhạy cảm. Alert P0 khi ownership lookup/transition failure tăng hoặc có handoff success không kèm read-back confirmation.

## 13. Rollout và rollback

- Ship sau test contract/unit/integration; không chạy mutation probe trên production.
- Feature flag theo customer/session, bắt đầu sanitized clone/staging với prod image + sanitized DB.
- Canary read-only metrics trước; sau đó bật write path cho nhóm nhỏ.
- Giữ versioned token decoder để token cũ hết hạn tự nhiên hoặc trả lỗi có hướng dẫn; không silently reinterpret payload cũ.
- Rollback app phải giữ database compatibility. Không rollback schema migration nếu đã có dữ liệu mới; dùng expand/contract nếu migration được duyệt.
- Khi commit gate reject tăng bất thường: tắt flag, giữ handoff fail-closed, không quay lại fail-open behavior.
- Request-path reconciliation/runbook phải có trước rollout. Background job không cần cho local atomic booking UoW; chỉ thêm nếu sau này có external adapter.

## 14. Migration verdict

**Hai migration có chủ đích:** marker dùng migration kế tiếp sau head hiện tại (target `agent_0035_handoff_retry_marker.py`); booking ledger dùng migration kế tiếp sau marker (target `agent_0036_booking_operation_ledger.py`). Tên/revision phải kiểm tra lại sau mỗi PR. Current model xác nhận index `ix_test_drive_bookings_showroom_time` là index thường, không unique; lookup application hiện chỉ bind `customer_id + showroom + scheduled_at`, không bind vehicle và chạy transaction riêng trước create. Vì vậy sequential replay được chống, concurrent replay chưa có DB guarantee. Production preflight vẫn bắt buộc trước apply để đếm duplicate và chọn backfill.

Rule: K0-1/K0-2 cần Alembic migration nullable cho marker; K0-3 cần Alembic migration durable operation ledger + unique fingerprint. Trước từng migration: xác minh Alembic head. Trước ledger migration: query duplicate hiện hữu, quyết định canonical rows/backfill/conflict. Mỗi migration ghi lock/index strategy, upgrade/downgrade, duplicate handling và production preflight. Token vehicle binding không cần sửa booking row schema ngoài ledger nếu DTO/query đã có vehicle ID.

### Production preflight K0-3, read-only

Chạy trên production trước apply migration, lưu count + timestamp + image ID; không sửa dữ liệu:

```sql
SELECT customer_id, vehicle_id, showroom, scheduled_at, COUNT(*) AS duplicate_count
FROM test_drive_bookings
WHERE status <> 'CANCELLED'
GROUP BY customer_id, vehicle_id, showroom, scheduled_at
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

Đồng thời xác minh:

- Trước marker migration: Alembic production head phải là `agent_0034`; nếu khác, dừng và rebase migration chain.
- Trước ledger migration: Alembic production head phải là marker revision đã deploy (target `agent_0035`); nếu khác, dừng và rebase ledger revision.
- `ix_test_drive_bookings_showroom_time` thật sự non-unique trong `pg_indexes`/catalog.
- số booking active, số tuple duplicate, booking cũ thiếu session/run linkage cần backfill.
- migration dry-run trên sanitized snapshot; unique fingerprint index build và downgrade rehearsal.

Nếu có duplicate, không tự xóa. Xuất report canonical-candidate theo earliest `created_at`, trình duyệt data remediation trước migration.

## 15. Out of scope

- A1 budget semantics/widening.
- A2 tự đổi xe.
- A3 general post-recommendation conversation claims chưa user verify.
- A4 stale vehicle fallback.
- B1 natural-needs hard filter.
- B2 hardcoded scoring/LLM rerank architecture.
- Feature definition/need-tag cache invalidation.
- Rewrite benchmark runners hoặc chạy 50 blind cases trực tiếp production.
- Refactor toàn bộ UoW/graph/HTTP contract.
- Giao ownership, booking truth hoặc transaction decision cho LLM.

## 16. Open decisions trước implementation

1. Ownership UoW đã verify: `_conversation_transaction` (`composition.py:263-277`) gom `sessions`, `core_state`, `outcomes`, `messages`, `turn_traces`, `review_queue` trên cùng `AsyncSession`; `ConversationMemoryService` và `ConversationService` dùng cùng typed UoW. Implementation đi theo one-DB-UoW path, không cần saga spec.
2. Old token sau đổi xe chốt conflict/restart. Persisted old booking chỉ được hiển thị từ booking history, không reinterpret token theo xe mới.
3. Production preflight chốt backfill/duplicate cleanup cho operation ledger; unique fingerprint guarantee không mở lại.
4. Booking retry truth nằm trong operation ledger. Non-booking act failure giữ original `state_before.pending`; không thêm generic retry table nếu không có side effect durable.

## 17. Review status

Đã review đối kháng. Chưa phải approval triển khai cho đến khi SẾP duyệt tài liệu.
