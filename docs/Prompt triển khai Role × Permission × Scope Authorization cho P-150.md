# TASK: Hoàn thiện Authorization theo mô hình Role × Permission × Scope cho VinFast AI Sales Advisor (P-150)

## 1. Context

Đây là backend của dự án **VinFast AI Sales Advisor (P-150)**.

Hệ thống hiện tại đã có 3 role chính:

- `CUSTOMER`
- `ADVISOR`
- `ADMIN`

Các phân hệ chính:

- Customer: AI consultation, conversation history, booking, profile, live chat, locations
- Advisor: HITL review queue, live chat takeover, bookings, customers/leads, notices, funnel analytics
- Admin: user management, AI observability, chat sessions, catalog, locations, documents/RAG, notices

Hệ thống hiện tại đã có authentication và RBAC cơ bản. Không được phá vỡ các API và business flow đang hoạt động.

Mục tiêu của task này là **hoàn thiện authorization thành mô hình:**

```text
Role
  +
Permission
  +
Scope / Ownership
  +
Business State
  =
Authorization Decision
```

Không thay đổi 3 role chính. Không over-engineer thành nhiều role mới.

---

# 2. Mục tiêu chính

Triển khai authorization theo 3 lớp:

### Layer 1 — Role

```text
CUSTOMER
ADVISOR
ADMIN
```

### Layer 2 — Permission

Ví dụ:

```text
CHAT_CREATE
CHAT_VIEW_OWN
CHAT_VIEW_ASSIGNED

BOOKING_CREATE
BOOKING_VIEW_OWN
BOOKING_VIEW_ASSIGNED
BOOKING_UPDATE_ASSIGNED

HITL_VIEW
HITL_CLAIM
HITL_RESOLVE

CUSTOMER_VIEW_OWN
CUSTOMER_VIEW_ASSIGNED

AI_TRACE_VIEW
AI_COST_VIEW

USER_VIEW
USER_ACTIVATE
USER_DISABLE

CATALOG_VIEW
CATALOG_MANAGE

DOCUMENT_VIEW
DOCUMENT_MANAGE

NOTICE_VIEW
NOTICE_MANAGE
```

Không nhất thiết phải sử dụng đúng toàn bộ danh sách trên nếu codebase hiện tại đã có naming convention khác. Hãy audit code trước và reuse convention hiện có.

### Layer 3 — Scope

Hỗ trợ tối thiểu:

```text
OWN
ASSIGNED
GLOBAL
CLAIMED
PUBLIC
```

Ý nghĩa:

- `OWN`: resource thuộc chính current user
- `ASSIGNED`: resource được phân công cho current advisor
- `GLOBAL`: admin có quyền trên toàn hệ thống
- `CLAIMED`: resource đang được current advisor claim/lease
- `PUBLIC`: endpoint/resource không yêu cầu authentication

---

# 3. NGUYÊN TẮC QUAN TRỌNG

## 3.1 Không chỉ kiểm tra Role

Không chấp nhận authorization kiểu:

```python
if current_user.role == "CUSTOMER":
    allow()
```

nếu resource có ownership.

Phải kiểm tra:

```text
Role
+
Permission
+
Resource ownership/scope
+
Business state
```

Ví dụ:

```text
CUSTOMER
+
CHAT_VIEW_OWN
+
session.customer_id == current_user.id
```

mới được phép xem conversation.

---

# 4. Customer Ownership

Đây là yêu cầu bắt buộc.

Customer chỉ được phép truy cập resource thuộc chính mình.

## 4.1 Conversation

Các API như:

```text
GET /api/v1/conversations/{session_id}
GET /api/v1/agent/history/{session_id}
GET /api/v1/agent/conversation/state
GET /api/v1/agent/conversation/slots
POST /api/v1/agent/conversation/restart
```

phải đảm bảo:

```text
current_user.role == CUSTOMER
AND
conversation.customer_id == current_user.id
```

Nếu customer A cố truy cập conversation của customer B:

```text
HTTP 403
```

hoặc `404` nếu architecture hiện tại dùng resource hiding để tránh information disclosure.

Không được leak:

- conversation tồn tại hay không
- customer B là ai
- message history
- slots
- internal state
- agent trace

---

## 4.2 Booking

Customer chỉ được:

```text
CREATE booking
VIEW own booking
UPDATE/cancel own booking nếu business rule cho phép
```

Không được:

```text
VIEW booking của customer khác
UPDATE booking của customer khác
```

Authorization phải dựa trên:

```text
booking.customer_id == current_user.id
```

---

## 4.3 Profile

Customer chỉ được:

```text
GET own profile
UPDATE own profile
```

Không được dùng `user_id` arbitrary để đọc/sửa profile customer khác.

---

## 4.4 Live Chat

Customer chỉ được join/send message vào conversation/session mà mình sở hữu hoặc session được hệ thống bind với mình.

Không được:

```text
Customer A
→ connect tới live chat của Customer B
```

WebSocket cũng phải enforce authorization, không chỉ REST API.

---

# 5. Advisor Assignment Scope

Advisor không mặc định có toàn quyền trên mọi customer/resource.

Audit codebase để tìm cơ chế assignment hiện tại.

Có thể là:

```text
advisor_id
assigned_advisor_id
assigned_to
showroom_id
region_id
```

hoặc tên tương đương.

Không được tự tạo field mới nếu codebase đã có field phù hợp.

## 5.1 Customer

Advisor chỉ được xem customer:

```text
customer.assigned_advisor_id == current_user.id
```

nếu hệ thống hiện tại sử dụng direct advisor assignment.

Nếu assignment hiện tại theo showroom:

```text
customer.showroom_id IN current_user.assigned_showrooms
```

thì sử dụng showroom scope.

Không tự ý thay đổi business model.

---

## 5.2 Booking

Advisor chỉ được:

```text
VIEW assigned bookings
UPDATE assigned bookings
```

theo assignment rule thực tế của codebase.

Không cho Advisor A sửa booking thuộc Advisor B.

---

## 5.3 Conversation

Advisor chỉ được xem conversation nếu conversation thuộc customer/resource mà advisor được phép xử lý.

Ví dụ:

```text
conversation.customer.assigned_advisor_id == current_user.id
```

hoặc assignment scope tương ứng.

---

## 5.4 Live Chat

Advisor chỉ được `TAKE_OVER` session phù hợp với assignment/business rule.

Sau khi takeover:

```text
conversation.mode = LIVE_CHAT
conversation.assigned_advisor_id = current_user.id
```

Agent AI phải không tiếp tục trả lời nếu business state yêu cầu Advisor takeover.

---

# 6. HITL Claim Lease

Đây là phần quan trọng nhất.

Hệ thống hiện tại có:

```text
WAITING_REVIEW
```

và Advisor có thể:

```text
CLAIM
APPROVE
EDIT & APPROVE
REJECT
```

Claim phải hoạt động như một **atomic lease**.

## 6.1 State

Audit implementation hiện tại và chuẩn hóa về logic tương đương:

```text
WAITING_REVIEW
CLAIMED
RESOLVED
REJECTED
```

Không nhất thiết đổi enum nếu codebase hiện tại đã có enum tương đương.

---

## 6.2 Claim

Khi Advisor claim:

```text
ticket.status = CLAIMED
ticket.claimed_by = current_user.id
ticket.claimed_at = now()
ticket.lease_expires_at = now() + 15 minutes
```

TTL:

```text
15 minutes
```

Phải đảm bảo operation atomic.

Hai Advisor đồng thời claim cùng ticket:

```text
Advisor A → SUCCESS
Advisor B → FAIL
```

Không được xảy ra:

```text
Advisor A → claimed
Advisor B → also claimed
```

---

## 6.3 Resolve

Advisor chỉ được:

```text
APPROVE
EDIT
REJECT
```

nếu:

```text
ticket.claimed_by == current_user.id
AND
lease chưa hết hạn
AND
ticket.status == CLAIMED
```

Ví dụ:

```text
Advisor A claim ticket
        ↓
15 phút chưa hết
        ↓
Advisor A resolve → ALLOW

Advisor B resolve → DENY
```

---

## 6.4 Expired Lease

Nếu:

```text
now() > lease_expires_at
```

thì ticket không còn thuộc Advisor đó.

Ticket phải có khả năng quay về:

```text
WAITING_REVIEW
```

hoặc state tương đương.

Không nhất thiết cần background worker nếu architecture hiện tại có thể kiểm tra lazy expiration tại mỗi mutation.

Ví dụ:

```python
if ticket.lease_expires_at < now:
    release_claim()
```

Nhưng nếu codebase đã có scheduler/worker thì có thể dùng worker.

---

## 6.5 Race Condition

Claim phải sử dụng transaction/row-level locking hoặc cơ chế atomic phù hợp với database hiện tại.

Không triển khai:

```python
if ticket.status == WAITING_REVIEW:
    ticket.claimed_by = user.id
    save()
```

một cách non-atomic.

Phải đảm bảo concurrency safety.

Có thể dùng:

```text
SELECT ... FOR UPDATE
```

hoặc equivalent phù hợp ORM/database đang sử dụng.

---

# 7. Admin Global Scope

Admin có:

```text
GLOBAL
```

trong phạm vi business permissions được cấp.

Ví dụ:

```text
USER_VIEW
USER_ACTIVATE
USER_DISABLE
CHAT_AUDIT
AI_TRACE_VIEW
CATALOG_MANAGE
DOCUMENT_MANAGE
NOTICE_MANAGE
HITL_MANAGE
```

Admin không cần ownership check giống Customer/Advisor.

Tuy nhiên không được biến:

```text
ADMIN
```

thành bypass tất cả business validation.

Ví dụ Admin approve HITL có thể không cần `claimed_by == admin.id` nếu business rule cho phép Admin override.

Nhưng phải thể hiện rõ đây là:

```text
ADMIN OVERRIDE
```

và tạo audit log.

---

# 8. Permission Matrix

Tạo một centralized authorization matrix.

Ví dụ:

```text
CUSTOMER

CHAT_CREATE              PUBLIC/CUSTOMER
CHAT_VIEW_OWN            CUSTOMER + OWN

BOOKING_CREATE           CUSTOMER
BOOKING_VIEW_OWN         CUSTOMER + OWN
BOOKING_UPDATE_OWN       CUSTOMER + OWN

PROFILE_VIEW_OWN         CUSTOMER + OWN
PROFILE_UPDATE_OWN       CUSTOMER + OWN

LIVE_CHAT_JOIN_OWN       CUSTOMER + OWN


ADVISOR

CHAT_VIEW_ASSIGNED       ADVISOR + ASSIGNED

CUSTOMER_VIEW_ASSIGNED   ADVISOR + ASSIGNED

BOOKING_VIEW_ASSIGNED    ADVISOR + ASSIGNED
BOOKING_UPDATE_ASSIGNED  ADVISOR + ASSIGNED

HITL_VIEW                ADVISOR
HITL_CLAIM               ADVISOR
HITL_RESOLVE             ADVISOR + CLAIMED

LIVE_CHAT_VIEW_ASSIGNED  ADVISOR + ASSIGNED
LIVE_CHAT_TAKEOVER       ADVISOR + ASSIGNED

NOTICE_VIEW              ADVISOR
FUNNEL_ANALYTICS_VIEW    ADVISOR


ADMIN

USER_VIEW                ADMIN + GLOBAL
USER_ACTIVATE            ADMIN + GLOBAL
USER_DISABLE             ADMIN + GLOBAL

CHAT_AUDIT               ADMIN + GLOBAL
AI_TRACE_VIEW            ADMIN + GLOBAL
AI_COST_VIEW             ADMIN + GLOBAL

CATALOG_MANAGE           ADMIN + GLOBAL
LOCATION_MANAGE          ADMIN + GLOBAL

DOCUMENT_MANAGE          ADMIN + GLOBAL
RAG_MANAGE               ADMIN + GLOBAL

NOTICE_MANAGE            ADMIN + GLOBAL

HITL_MANAGE              ADMIN + GLOBAL
```

Đây chỉ là baseline.

Phải map lại chính xác theo endpoint và domain model thực tế.

---

# 9. Central Authorization Layer

Không viết authorization rải rác trong từng controller.

Tìm architecture hiện tại và đưa authorization vào layer phù hợp.

Có thể sử dụng pattern tương đương:

```python
authorize(
    user=current_user,
    permission=Permission.CHAT_VIEW,
    resource=conversation,
)
```

hoặc:

```python
authorize_customer_ownership(...)
authorize_advisor_assignment(...)
authorize_hitl_claim(...)
```

Nếu project đang dùng Clean Architecture:

```text
domain/
    authorization/
        permissions.py
        roles.py
        scopes.py
        policies.py

application/
    authorization/
        authorization_service.py

adapters/
    ...
```

Không bắt buộc dùng đúng structure trên nếu repository đã có structure tương đương.

Ưu tiên **reuse architecture hiện tại**.

---

# 10. FastAPI Integration

Audit tất cả route hiện tại.

Không tạo một hệ thống auth mới nếu đã có:

```text
get_current_user
require_role
auth dependency
JWT dependency
```

Hãy mở rộng implementation hiện tại.

Mục tiêu:

```text
HTTP Request
    ↓
Authentication
    ↓
Current User
    ↓
Permission
    ↓
Resource Scope
    ↓
Business State
    ↓
Handler / Use Case
```

---

# 11. WebSocket Authorization

Đây là bắt buộc.

Không được chỉ authenticate WebSocket bằng JWT rồi cho phép user join bất kỳ session nào.

Flow:

```text
WS connect
    ↓
Authenticate JWT
    ↓
Resolve current_user
    ↓
Resolve conversation/session
    ↓
Check ownership/assignment
    ↓
Accept connection
```

Customer:

```text
session.customer_id == current_user.id
```

Advisor:

```text
session.assigned_advisor_id == current_user.id
```

Admin:

```text
GLOBAL access nếu business rule cho phép
```

---

# 12. Audit Logging

Authorization failure quan trọng phải được log.

Ví dụ:

```text
AUTHORIZATION_DENIED
```

metadata:

```text
user_id
role
permission
resource_type
resource_id
scope
endpoint
reason
timestamp
ip/user-agent nếu hệ thống đã có security logging
```

Đặc biệt log:

```text
Customer truy cập resource người khác
Advisor truy cập resource ngoài assignment
Advisor resolve HITL ticket không phải của mình
Expired lease mutation
Admin override
```

Không log password, JWT, refresh token hoặc dữ liệu bí mật.

---

# 13. Không leak information

Khi Customer/Advisor không có quyền:

Không trả về:

```text
resource owner
advisor owner
internal notes
AI trace
HITL decision
internal rejection reason
```

Không expose stack trace/database error.

Response phải thống nhất theo error handling convention hiện tại.

---

# 14. Tests bắt buộc

Không coi task hoàn thành nếu chưa có authorization tests.

## Customer

Test:

```text
Customer A → own conversation → 200
Customer A → Customer B conversation → 403/404
Customer A → own booking → 200
Customer A → other booking → 403/404
Customer A → other profile → 403/404
```

## Advisor

Test:

```text
Advisor A → assigned customer → 200
Advisor A → unassigned customer → 403
Advisor A → assigned booking → 200
Advisor A → unassigned booking → 403
Advisor A → assigned conversation → 200
Advisor A → unassigned conversation → 403
```

## HITL

Test concurrency/state:

```text
Advisor A claim WAITING_REVIEW → success
Advisor B claim same ticket → fail

Advisor A resolve claimed ticket → success
Advisor B resolve A's ticket → fail

Advisor A resolve after lease expiry → fail

Expired claim → ticket becomes/reverts WAITING_REVIEW

Admin override → success if business rule allows
```

## Admin

Test:

```text
Admin → global resources → allowed
Admin → user management → allowed
Admin → AI trace → allowed
```

## WebSocket

Test:

```text
Customer A → own session → allowed
Customer A → other session → rejected
Advisor A → assigned session → allowed
Advisor A → unassigned session → rejected
```

---

# 15. Backward Compatibility

Đây là yêu cầu rất quan trọng.

Trước khi sửa:

1. Audit tất cả authentication dependencies.
2. Audit tất cả role checks.
3. Audit tất cả endpoint.
4. Audit database schema/model.
5. Audit existing tests.

Không được:

- rewrite authentication
- đổi JWT format nếu không cần
- đổi role enum nếu không cần
- đổi API contract nếu không cần
- đổi response schema đang được frontend sử dụng
- phá WebSocket protocol
- phá HITL flow
- phá conversation state machine

Nếu cần migration database:

```text
1. migration
2. backfill data
3. code compatibility
4. tests
```

---

# 16. Deliverables

Sau khi implementation hoàn thành, trả về report:

## A. Current Authorization Audit

Liệt kê:

```text
Endpoint
Current protection
Role
Current scope
Missing protection
```

## B. Implemented Authorization Model

Mô tả:

```text
Role
Permission
Scope
Resource ownership
Assignment
HITL lease
```

## C. Endpoint Matrix

Tạo bảng:

```text
Method | Endpoint | Role | Permission | Scope | Resource Check
```

cho toàn bộ endpoint liên quan.

## D. Files Changed

Liệt kê chính xác:

```text
file path
what changed
why
```

## E. Database Changes

Nếu có migration:

```text
migration file
new columns
indexes
constraints
```

## F. Tests

Báo cáo:

```text
Existing tests
New authorization tests
Passed
Failed
Skipped
```

Không được báo "done" nếu authorization tests chưa pass.

---

# 17. Definition of Done

Task chỉ được coi là hoàn thành khi:

- [ ] Không thay đổi 3 role `CUSTOMER / ADVISOR / ADMIN`
- [ ] Permission được centralize hoặc reuse architecture hiện tại
- [ ] Customer ownership được enforce ở backend
- [ ] Advisor assignment được enforce ở backend
- [ ] HITL claim là atomic
- [ ] HITL lease 15 phút được enforce
- [ ] Advisor không thể resolve ticket của Advisor khác
- [ ] Expired lease không thể mutation
- [ ] WebSocket có authorization
- [ ] Admin có global scope theo permission
- [ ] Authorization failures được audit log
- [ ] Không leak resource information
- [ ] Existing tests không bị regression
- [ ] New authorization tests pass
- [ ] Frontend API contract không bị phá
- [ ] Không có authorization logic duplicate không cần thiết
- [ ] Không hard-code bypass kiểu `if admin: allow everything` ngoài các policy thực sự cần thiết
- [ ] Có endpoint matrix hoàn chỉnh
- [ ] Có migration nếu cần
- [ ] Có final implementation report

---

# 18. Cách làm việc

**Không code ngay.**

Thực hiện theo thứ tự:

### Phase 1 — Audit

Đọc:

```text
auth
users
roles
agent
conversation
booking
advisor
HITL/review
WebSocket
database models
repositories
API dependencies
tests
```

Tìm chính xác implementation hiện tại.

### Phase 2 — Authorization Design

Đề xuất:

```text
Role
Permission
Scope
Ownership
Assignment
HITL Lease
```

và map với code hiện tại.

### Phase 3 — Implementation

Chỉ sau khi hiểu architecture hiện tại mới bắt đầu sửa code.

### Phase 4 — Tests

Ưu tiên:

```text
ownership
assignment
HITL race condition
lease expiry
WebSocket authorization
```

### Phase 5 — Regression

Chạy toàn bộ test suite hiện tại.

Nếu có failure do authorization change:

```text
identify
explain
fix
rerun
```

Không được bỏ test hoặc disable test để làm cho suite PASS.

---

## Final instruction

Hãy coi đây là một task **security/authorization hardening**, không phải một task refactor thông thường.

Ưu tiên:

```text
Correctness
>
Security
>
Backward Compatibility
>
Testability
>
Clean Architecture
>
Code elegance
```

Không tự ý mở rộng scope sang các tính năng khác.

Trước khi thay đổi code, hãy báo cáo **Audit hiện trạng + Authorization Gap + Implementation Plan** dựa trên code thực tế của repository.