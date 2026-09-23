# BÁO CÁO THỰC THI — plan `docs/PLAN_AGENT_MIGRATION.md`

**Ngày:** 2026-09-22 → 2026-09-23 · **Nhánh:** `feature/agent-migration` (tạo từ `main` @ `12bc394`)
**Trạng thái:** 9/10 bước DONE về code. Bước 10 (canary) và phần **chạy thật** của Bước 9 chưa thực hiện được — cần môi trường chạy (API + OpenAI key thật), xem §5.

> Cờ `agent_fallback` **đang TẮT**. Không một lượt khách nào đi qua agent cho tới khi có người bật cờ theo `docs/runbooks/agent-fallback-canary.md`.

---

## 1. Trạng thái từng bước

| Bước | Trạng thái | Commit | Ghi chú |
|---|---|---|---|
| 1 — Vá 3 lỗi đã định vị | **DONE** | `c73a1cf`, `b1bdcba`, `eeb28d7` | 3 commit, 3 fix, +17 test |
| 2 — Cắm lại `quote_gate` | **DONE** | `25cb497`, `e860257` | +7 test |
| 3 — Feature flag | **DONE** | `a35231d`, `d3d9b4a`, `0bcd7f1`, `5dd7f6d` | migration `agent_0036`, +11 unit +4 integration |
| 4 — Tool registry | **DONE** | `b234fb0` | 6 tool chỉ-đọc, +7 test |
| 5 — Agent loop adapter | **DONE** | `c70765b`, `ff22790`, `c0820de` | +15 test loop, +4 test budget |
| 6 — `OpenQuestion` + Móc 1 | **DONE** | `89c7596`, `abbe97e`, `fba684f`, `18acb70` | +19 test handler, +2 test suggest/run_turn |
| 7 — Móc 2 (`_recommend`) | **DONE** | `962e2db`, `7ac06c2` | +9 test |
| 8 — Quan sát | **DONE** | `6840345`, `912dc6a` | 5 khoá `agent_*` trong trace, +5 test trace, +2 test metrics |
| 9 — Bộ đánh giá | **DONE (code)** / **BLOCKED (chạy)** | `9a394ad` | dataset 30 câu + `scripts/agent_eval.py`, +5 test. Chưa chạy thật — §5 |
| 10 — Canary | **CHƯA BẮT ĐẦU** | — (không có commit code) | Runbook: `docs/runbooks/agent-fallback-canary.md`. Điều kiện tiên quyết là Bước 9 chạy thật |

**Tổng: 22 commit** (plan dự trù tối thiểu 21 cho Bước 1-9; Bước 7 tách thêm một commit test).

---

## 2. Test: baseline so với sau khi làm

### 2.1 Unit (`tests/agents/unit`)

| Mốc | Kết quả |
|---|---|
| Baseline trước Bước 1 (2026-09-22) | `1 failed, 5123 passed` |
| Sau Bước 9 | `1 failed, 5224 passed` |

**+101 test mới, 0 test cũ chuyển từ pass sang fail.**

Lỗi duy nhất còn lại là **test bom hẹn giờ đã biết từ trước**, không liên quan plan:
`tests/agents/unit/services/test_test_drive_availability.py::test_hoi_mot_ngay_thi_chi_nhan_o_cua_ngay_do`
— test khoá cứng `NOW = datetime(2026, 8, 28)` trong khi service đọc `now_in_vietnam()`.

### 2.2 Integration (`tests/agents/integration`, có Postgres)

| Mốc | Kết quả |
|---|---|
| Baseline sau Bước 2 (lần đầu chạy được với DB) | `33 failed, 362 passed` |
| Sau Bước 9 | `33 failed, 366 passed` |

**Đúng 33 lỗi cũ, không thêm lỗi nào; +4 test mới đều pass** (`test_migration_0036`, 3 test `test_agent_flag_repository`).

33 lỗi có sẵn thuộc ba nhóm, tất cả đã hỏng TRƯỚC plan này: lõi v1 LangGraph đã xoá (`graph=None` → `.ainvoke`), pipeline NLU v1 (`KeyError: budget_max_vnd`), và schema drift trong `test_migrations.py` (`EXPECTED_AGENT_TABLES` thiếu `conversation_core_state`/`turn_traces`; `FLOAT` vs `DOUBLE PRECISION`). Danh sách đầy đủ: `eval/results/agent-fallback/baseline-integration.txt`.

> **Lưu ý môi trường:** `tests/agents/integration/conftest.py` chỉ đọc `AGENT_DATABASE_URL` từ biến môi trường (mặc định cổng 5432), còn Postgres của dự án chạy cổng **5433**. Không export biến này thì ~486 test **skip im lặng** và báo cáo trông "sạch" một cách giả tạo.

### 2.3 `ruff check src/ tests/`

| Mốc | Kết quả |
|---|---|
| Baseline | 5 lỗi |
| Sau Bước 9 | 5 lỗi (đúng 5 lỗi cũ) |

`[LỆCH PLAN]` Plan ghi cổng commit là "ruff sạch", nhưng repo **chưa từng sạch**: 3 × `I001` (import chưa sắp xếp trong `conversation_routes.py`, `act.py`, `render.py`) và 2 × `F821 Undefined name 'Final'` (`policy.py:643`, `render.py:241`) đã có từ commit gốc. Cổng thực tế áp dụng là **"không tệ hơn baseline"**, và điều đó được giữ ở mọi commit. Không sửa 5 lỗi này vì chúng nằm ngoài phạm vi plan (`AGENTS.md`: "treat unrelated modified paths as out of scope").

---

## 3. Đánh giá workflow (cờ OFF) vs agent (cờ ON)

### 3.1 Những gì đã CHỨNG MINH ĐƯỢC bằng test tự động

| Chỉ số / bất biến | Cách đo | Kết quả |
|---|---|---|
| Cờ OFF: 0 call LLM thêm | `test_co_tat_thi_khong_goi_llm`, `test_khong_cam_agent_flag_thi_khong_goi_llm` | **Đạt** — loop không bị gọi lần nào |
| Cờ OFF: chữ giống hệt hôm nay | `test_co_tat_thi_ra_dung_chu_cu` (so từng ký tự với `Reply(TEMPLATE_CLARIFY)`), `test_co_tat_thi_ra_dung_{no_better,same_pick,nearest_by_price}_cu` | **Đạt** |
| Mọi nhánh hỏng → đúng chữ tất định | `test_agent_hong_thi_ve_same_pick`, `test_verify_tu_choi_thi_fallback`, `test_quote_gate_chan_thi_fallback`, `test_render_error_thi_fallback`, `test_exception_la_thi_fallback_khong_thoat_len_act` | **Đạt** |
| Agent không ghi state | `test_state_patch_rong`, `test_khong_dat_hitl_request`, `test_ngo_cut_3_agent_tra_loi_van_giu_danh_sach_xe` | **Đạt** |
| HITL: TVV cầm phiên thì agent câm | `test_handed_off_khong_goi_agent` | **Đạt** |
| Không chen lượt chờ xác nhận | `test_pending_confirm_khong_goi_agent` | **Đạt** |
| Registry không có tool ghi | `test_khong_co_tool_ghi`, `test_executor_chi_chay_tool_chi_doc` | **Đạt** |
| Trần bước / timeout / budget / chống lặp | 15 test `test_agent_loop_llm.py` | **Đạt** |
| Vệt không chứa chữ khách | `test_steps_khong_chua_gia_tri_args`, `test_trace_khong_co_chu_khach_trong_agent_steps` | **Đạt** |
| 5 cột vô hướng `turn_traces` không đổi | `test_5_cot_vo_huong_khong_doi` | **Đạt** |
| Contract HTTP / `_CARD_FIELDS` | `test_build_result_voi_open_question` | **Đạt** |

### 3.2 Những gì CHƯA đo được (cần chạy thật)

| Chỉ số plan §5.3 | Trạng thái |
|---|---|
| Tỷ lệ trả lời đúng/đủ trên bộ 30 câu (A3 ≥ 70%) | **Chưa đo** — cần API + OpenAI key |
| "Bot chịu thua" + "tự tin sai" giảm ≥ 40% (A4) | **Chưa đo** — baseline 8.7%/8.2% của plan vẫn là số ước |
| Số lần gọi tool / lượt agent | **Chưa đo** — script đã sẵn (`core_v2_metrics`, bảng "Chi so agent") |
| Latency p50/p95 tách theo `agent_used` (A5, A6) | **Chưa đo** |
| Token / câu | **Chưa đo** |
| Tỷ lệ fallback theo lý do (A7, A8) | **Chưa đo** — `agent_error` đã ghi sẵn vào trace |

**Kết luận đánh giá:** phần **an toàn** của plan đã đạt và chứng minh được bằng test
(cờ OFF = hành vi cũ nguyên vẹn; mọi nhánh hỏng rơi về đúng kết quả tất định; không
guardrail nào giao cho LLM). Phần **chất lượng** (agent có trả lời tốt hơn workflow
không) **chưa có số** — không thể kết luận bật cho khách thật. Ngưỡng A1-A11 của plan
chưa được đối chiếu vì thiếu dữ liệu chạy.

---

## 4. Danh sách `[GIẢ ĐỊNH]` / `[LỆCH PLAN]` / `[BLOCKED]`

### 4.1 `[GIẢ ĐỊNH]` — điểm tự quyết, cần duyệt

| # | Giả định | Ở đâu | Ảnh hưởng nếu sai |
|---|---|---|---|
| GĐ-1 | **Prompt CẤM agent viết bất kỳ chữ số nào.** `verification.verify` đòi mọi chữ số phải đi kèm citation `[evidence_id:<uuid>]` khớp `run_evidence`, mà LLM không sinh được marker đó. Nên hoặc agent viết không số (qua cửa), hoặc viết số (bị chặn, rơi fallback). Chọn cấm số để agent trả lời được **đúng chủ đề** thay vì luôn bị chặn | `act.AGENT_SYSTEM_PROMPT` | Agent không nói được giá/thông số; giá trị của nó giới hạn ở câu định tính. Nới được bằng cách đưa citation vào payload tool — việc của một bước riêng |
| GĐ-2 | `max_steps=3`, `step_timeout=4s`, `total_timeout=10s`, `AGENT_CALLS_PER_TURN=4` | `act.py`, `agent_loop_llm.py`, `call_budget.py` | Đúng theo plan §2.2; hiệu chỉnh sau khi có số |
| GĐ-3 | Model loop = `gpt-4o` | `agent_loop_llm.AGENT_LOOP_MODEL` | Theo plan; chưa A/B |
| GĐ-4 | Cờ mặc định OFF, allowlist rỗng, `rollout_percent=0` | migration `agent_0036` | Chiều an toàn |
| GĐ-5 | Móc 1 và móc 2 **dùng chung một cờ** | `act._open_question` | Không tắt riêng được một móc. Thêm cột `hook_dead_end` nếu Bước 10 cần |
| GĐ-6 | Bước quá hạn (`step_timeout`) vẫn **đếm là một bước và một call** | `agent_loop_llm._run` | Nếu không đếm, provider chậm kéo loop tới hết `total_timeout` |
| GĐ-7 | `_commercial_guard` đọc `quote_gate.config.standard_promotions` bằng `getattr`, không có thì dùng mặc định | `act._commercial_guard` | Cổng vẫn default-deny; chỉ mất phần allowlist |
| GĐ-8 | Chấp nhận snapshot mồ côi trong `agent_runs` khi loop hỏng | `act._open_question` | Bảng phình; theo dõi từ nấc 25% |

### 4.2 `[LỆCH PLAN]`

| # | Plan nói | Thực tế | Xử lý |
|---|---|---|---|
| L-1 | "Cổng commit: `ruff check src/ tests/` sạch" | Repo có sẵn 5 lỗi ruff từ commit gốc | Đổi cổng thành "không tệ hơn baseline"; giữ đúng 5 lỗi cũ |
| L-2 | Luật 6a thêm `and not u.question.strip()` | Điều kiện đó làm hỏng `test_sau_khi_chon_xe_co_panel_buoc_tiep_theo`: lượt `SLOT_ANSWER` mà LLM quên rút slot cũng mang `question` | Siết lại thành `not (u.dialogue_act is REQUEST and u.question.strip())` — chỉ chừa lời xin đổi xe |
| L-3 | Prompt agent có transcript 6 tin nhắn | `act()` không nhận transcript; thêm tham số là đổi chữ ký mà `run_turn` + hàng trăm test đang gọi | Prompt dùng `CoreState` (slot, chặng, xe đã chốt, bộ đề xuất) + câu khách + danh mục. Nối transcript là việc của bước riêng nếu đo thấy thiếu |
| L-4 | Bước 2 gọi `services.quote_gate` → `classify_delivery` | `QuoteGateServiceImpl.evaluate` cần `canonical`/`session_id`, ép HITL theo ý định khách (TCO, xin gặp người) và ghi audit — không phải việc của `act` | Thêm hàm thuần `quote_risk.classify_draft_delivery(draft, …)` đọc 4 cờ rủi ro trên **bản nháp**, gỡ cụm so sánh "rẻ hơn/giá thấp" trước khi dò (trong bài đề xuất đó là so sánh số thật, không phải lời trả giá — R12) |
| L-5 | Hai test policy cũ (`test_unclear_o_recommended_hoi_mau_nao`, `test_khong_hieu_that_o_chang_de_xuat_van_duoc_hoi_lai`) không nằm trong danh sách phải sửa | Móc 1 đổi Action của nhánh cuối `_unclear` từ `Reply` sang `OpenQuestion` | Hai test đổi sang khẳng định Action mới; **chữ tới khách không đổi**, có test riêng so từng ký tự |
| L-6 | `test_migrations.py::EXPECTED_AGENT_TABLES` | Test này đã đỏ sẵn (thiếu `conversation_core_state`, `turn_traces`) | Chỉ thêm `agent_feature_flags` — bảng của plan này; hai bảng thiếu kia để nguyên, ngoài phạm vi |

### 4.3 `[BLOCKED]`

| # | Việc | Lý do | Cần gì để gỡ |
|---|---|---|---|
| B-1 | **DoD "diff rỗng khi cờ OFF" bằng `scripts/core_v2_replay.py`** (Bước 2, 6, 7) | File nhãn `docs/handoff/loi-v2-34-phien.md` mà script đọc **không tồn tại trong repo** (`docs/handoff/` không có). Không có dữ liệu thì không chạy được | File nhãn 34 phiên, hoặc một bộ phiên tương đương. Thay thế hiện tại: test so **từng ký tự** giữa nhánh agent-OFF và chữ tất định (§3.1) |
| B-2 | **Chạy thật Bước 9** (bộ 30 câu, 2 chế độ) | Cần API đang chạy, tài khoản đăng nhập, `OPENAI_API_KEY` thật và ngân sách token | `scripts/agent_eval.py` đã sẵn sàng; lệnh chạy ở `eval/results/agent-fallback/README.md` |
| B-3 | **Bước 10 — canary** | Phụ thuộc B-2 và việc chốt 8 `[GIẢ ĐỊNH]` ở §4.1 | Runbook đã có: `docs/runbooks/agent-fallback-canary.md` |
| B-4 | Checklist "trước khi code": chốt 12 `[GIẢ ĐỊNH]` của plan với người quyết định; chốt số phận code mồ côi; cập nhật `ARCHITECTURE.md` | Là việc của người, không phải của code | Anh duyệt §4.1 |

---

## 5. Bật / tắt cờ và rollback

### Bật (không cần deploy, hiệu lực ≤ 60s)

```sql
UPDATE agent_feature_flags
   SET enabled = TRUE, rollout_percent = 0, customer_allowlist = 'cus-1,cus-2', updated_at = now()
 WHERE name = 'agent_fallback';
```

### Tắt — rollback thường dùng

```sql
UPDATE agent_feature_flags SET enabled = FALSE, updated_at = now() WHERE name = 'agent_fallback';
```

### Kill-switch (sự cố, thắng cả DB)

```
AGENT_FALLBACK_KILL_SWITCH=true    # .env, cần restart process
```

### Rollback toàn bộ

1. Tắt cờ (trên) — **luôn làm trước**.
2. Không vào được DB → kill-switch + restart.
3. Revert code (chỉ khi thật cần): `git revert 962e2db 7ac06c2` (móc 2), rồi
   `git revert 18acb70 fba684f abbe97e 89c7596` (móc 1). Bước 1-5, 8, 9 **không
   cần revert** — chúng không bật gì và Bước 1-2 là vá lỗi độc lập.
4. Gỡ bảng cờ (chỉ khi gỡ hẳn): `alembic -c alembic-agent.ini downgrade agent_0035`.

Chi tiết vận hành: `docs/runbooks/agent-fallback-canary.md`.

---

## 6. Việc anh cần duyệt

1. **8 `[GIẢ ĐỊNH]` ở §4.1** — quan trọng nhất là **GĐ-1** (agent không được viết chữ số).
   Đây là hệ quả trực tiếp của guardrail `verify` hiện có; nới nó ra là một quyết định
   sản phẩm, không phải một dòng code.
2. **6 `[LỆCH PLAN]` ở §4.2** — nhất là **L-2** (phạm vi vá luật 6a) và **L-4**
   (cách cắm lại `quote_gate`).
3. **B-1**: có file nhãn 34 phiên ở đâu không? Thiếu nó thì DoD "replay diff rỗng"
   của Bước 2/6/7 không có cách chạy.
4. **B-2/B-3**: cho phép chi token để chạy bộ 30 câu, và chốt ngưỡng A3/A4/A5/A7/A8/A9
   trước khi canary.
