# Nhật ký triển khai Khối 3 — A5 và A6

Tài liệu này ghi lại phần đã làm, phần còn thiếu và điểm tích hợp cần từ các khối khác.
Kết quả kiểm thử được cập nhật sau từng task; không dùng tài liệu này thay cho kết quả CI.

## A5-1 — Migration `agent_0003`

### Đã làm

- Xác minh migration hiện có tạo đủ `agent_runs`, `run_snapshots`, `run_candidates`,
  `run_evidence`, `scoring_result`, `tco_estimates`, các index, foreign key và check constraint.
- Bổ sung acceptance test chạy Alembic thật: upgrade từ `agent_0002` lên `agent_0003` tạo đủ
  sáu bảng; downgrade về `agent_0002` chỉ xóa bảng của run và giữ bảng hội thoại.
- Bổ sung kiểm thử constraint cho trạng thái run, rank, layer, TCO total và số reasons.

### Kiểm thử

- A5-1 cùng integration bất biến A5-2: `3 passed` trên PostgreSQL thật.
- Các migration/constraint cũng nằm trong bộ toàn Agent `149 passed`.

### Còn thiếu / cần khối khác

- Không còn thiếu DDL trong phạm vi A5-1. Các repository ghi/đọc những bảng này và việc
  chuyển state run trong luồng thật thuộc persistence/composition của A4 và A7.

## A5-2 — Snapshot bất biến

### Đã làm

- Tạo payload versioned, Pydantic frozen cho candidate facts và feature assertions; chặn
  candidate trùng, fact code trùng, assertion trỏ ra ngoài candidate set.
- `DefaultSnapshottingService` chụp dữ liệu tại một thời điểm, lưu bản copy tách khỏi
  catalog và đổi run sang `SNAPSHOT_READY` trong cùng transaction.
- Integration test sửa giá catalog sau khi snapshot và chứng minh kết quả run vẫn giữ giá
  cũ, không đọc lại dữ liệu sống.

### Kiểm thử

- Unit A5-2: `8 passed`; integration bất biến PostgreSQL nằm trong nhóm `3 passed` với A5-1.

### Còn thiếu / cần khối khác

- Cần Khối Catalog/persistence cung cấp `CatalogSnapshotSource` production cho toàn bộ fact
  code, không chỉ nguồn SQL tối thiểu dùng trong integration test.
- Cần A4 tạo `run_id` và gọi snapshot node/service ở đúng vị trí graph.

## A5-3 — Chấm điểm và xếp hạng

### Đã làm

- Xếp hạng deterministic tối đa ba mẫu, thứ tự ổn định, mỗi mẫu có ít nhất hai lý do có
  trace về slot đã xác nhận.
- Chỉ feature assertion nguồn `FLAG` được tác động điểm; `DOCUMENT` không đổi thứ hạng.
- Xe vượt ngân sách không có nhãn bị loại; xe được phép vượt có phần trăm và lý do rõ ràng.
- Service chỉ đọc snapshot A5-2; `ScoreNode` đã thay stub và gọi contract recommendation.

### Kiểm thử

- Domain + service + node A5-3: `16 passed`.

### Còn thiếu / cần khối khác

- Cần production `RecommendationDataSource` đọc snapshot và slot của cùng run, đồng thời
  persistence lưu `scoring_result`/rank vào DB.
- Cần A4 đưa `run_id` vào state chính thức; node hiện chỉ có đường đọc tương thích runtime.

## A5-4 — Bảng so sánh

### Đã làm

- So sánh đúng hai hoặc ba xe cùng loại; từ chối bảng trộn ô tô và xe máy điện.
- Dùng bộ tiêu chí cấu trúc riêng theo loại xe, đánh dấu giá trị tốt hơn theo quy tắc
  `lower/higher is better`, giữ evidence cho từng ô.
- Assertion nguồn tài liệu luôn mang nhãn “theo tài liệu, chưa xác minh”; nguồn `FLAG`
  không bị gắn nhãn này.
- So sánh và tra cứu một fact đi qua cùng snapshot path, tránh mỗi màn hình một nguồn số.

### Kiểm thử

- Domain + service A5-4: `13 passed`.

### Còn thiếu / cần khối khác

- Cần adapter nguồn snapshot production và A4/API gọi method `compare`/`lookup_fact`.
- Phần hiển thị bảng ở frontend không thuộc Khối 3 backend.

## A5-5 — TCO structured tool

### Đã làm

- `vinfast_tco_v1` giữ contract/horizon Agent nhưng đã trở thành adapter gọi calculator chuẩn
  `src/products/domain/tco.py`; không còn một công thức tiền thứ hai trong Khối 3.
- Giá dùng `BATTERY_INCLUDED`/`BATTERY_INCLUDED_PRICE`, nếu thiếu mới dùng `STARTING_PRICE`;
  promotion và chính sách thuê/mua pin lịch sử không đi vào estimate catalog ổn định.
- Phí trước bạ, biển số, đăng kiểm theo số mốc, bảo hiểm, đường bộ, điện và bảo dưỡng được
  tính bởi calculator Products; bảo dưỡng làm tròn lên thay vì làm tròn xuống.
- Assumption Products nâng lên version 3 bằng migration kế tiếp, không sửa lịch sử migration:
  chu kỳ xe con mới là 36/24/12 tháng. Đúng 7 năm vẫn dùng chu kỳ 24 tháng; vì vậy horizon
  10 năm có 5 mốc 36, 60, 84, 108 và 120, không có mốc 96 tháng.
- `source_note` phân biệt căn cứ pháp lý với giả định: 3.150 VND/kWh, chi phí bảo dưỡng cố
  định và mức bảo hiểm gom theo loại xe không được trình bày như giá chính thức. Giá biển
  14 triệu chỉ là giả định khu vực I. Xe máy có chi phí kiểm định khí thải chưa được model,
  không được diễn giải thành miễn kiểm định vĩnh viễn.
- Xe máy điện ưu tiên mức tiêu thụ Admin, nếu thiếu thì suy từ dung lượng pin và tầm hoạt động;
  không đủ dữ liệu trả `TCO_UNAVAILABLE` kèm tên field, không đoán.
- Đổi quãng đường/ngày làm đổi đúng quãng đường tháng và năng lượng; output có giả định,
  thời điểm tính và cảnh báo đây không phải báo giá cuối cùng. `TcoNode` đã thay stub.

### Kiểm thử

- Có golden vector ô tô/xe máy điện, vector biên chu kỳ đăng kiểm và test Agent trả cùng tổng
  với calculator Products. Bộ unit/API không cần database sau cập nhật: `170 passed`.

### Còn thiếu / cần khối khác

- Cần `TcoDataSource` production đọc giá và đúng một assumption ACTIVE theo loại xe/vùng;
  cần persistence lưu `tco_estimates`.
- Bảo hiểm thân vỏ tự nguyện, lãi vay, bãi đỗ/cầu đường phát sinh, lốp/sửa chữa bất thường,
  lắp bộ sạc tại nhà và khấu hao chưa có trong công thức/schema MVP hiện tại. Muốn thêm phải
  được Product/Catalog duyệt giả định và contract, không nên tự gán số.

## A5-6 — Synthesis bằng placeholder

### Đã làm

- Tạo persona tập trung tại `src/agents/prompts/synthesis_prompts.py`: giọng tư vấn thân thiện,
  xưng hô nhất quán, diễn đạt lý do phù hợp và không chào hàng.
- Tạo `DefaultSynthesisService`; LLM chỉ nhận lý do đã chuyển thành câu tự nhiên và danh
  sách placeholder, không nhận số liệu thật, UUID hay token trace thô.
- Khóa allowlist đúng schema mục 7.5; placeholder ngoài allowlist hoặc không có trong
  snapshot bị từ chối trước khi render.
- Mỗi placeholder được thay bằng đúng `value_text`, đơn vị và
  `[evidence_id:<UUID>]`; TCO phải khớp `TcoResult` được truyền vào.
- Chặn chữ số ngoài placeholder, cú pháp placeholder lỗi, token structured thô và dữ liệu
  nguồn trùng/khác xe đang đề xuất.
- Thay stub `SynthesizeNode` bằng node gọi service qua hợp đồng đóng băng.

### Kiểm thử

- Red trước implementation: test không collect được vì chưa có module synthesis.
- Test riêng A5-6: `11 passed`.
- Toàn bộ Agent: `115 passed`.
- `ruff check src/agents tests/agents`: đạt.
- `mypy src/agents`: đạt, 40 source files.

### Còn thiếu / cần khối khác

- Cần adapter đọc `run_snapshots` và bản ghi evidence thật từ khối Catalog/persistence;
  hiện service dùng port và test fake để không phụ thuộc DB/LLM thật.
- Cần khối A4 đưa `run_id` chính thức vào state và composition root nối LLM adapter,
  synthesis data source vào `AgentServices`.
- Placeholder hiện có tên theo fact code và không mang chỉ số xe; implementation an toàn
  chỉ render số của mẫu đứng đầu. Nếu sản phẩm muốn nêu số của nhiều xe trong cùng câu,
  nhóm cần duyệt mở rộng contract placeholder trước khi sửa.

## A5-7 — Giới thiệu feature theo nhu cầu, không chào hàng

### Đã làm

- Suy ra need tag từ tập đóng và slot đã xác nhận; không dùng text tự do để tự gắn nhu cầu.
- Chỉ chọn feature `YES` + `APPROVED` + `ACTIVE`, có evidence và gắn need tag phù hợp.
- Loại feature khách đã hỏi và feature mà mọi xe trong danh sách đều có; giới hạn mặc định
  hai giới thiệu, sắp xếp deterministic theo rank/relevance/display order.
- Không có feature đủ điều kiện thì trả rỗng, tuyệt đối không sinh lời khen/chào hàng fallback.
- Method `introduce_features` được nối vào recommendation service mà không sửa contract đóng băng.

### Kiểm thử

- Domain + service A5-7: `17 passed`.

### Còn thiếu / cần khối khác

- Cần Catalog/persistence implement join source từ `feature_need_tags`,
  `vehicle_feature_flags`, `feature_definitions` và danh sách feature khách đã hỏi.
- Cần A4/A5-6 đưa các introduction đã chọn vào nội dung synthesis; contract synthesis hiện
  chưa có tham số riêng cho feature introduction nên nhóm phải thống nhất cách truyền.

## A6-1 — Guardrail hậu-synthesis

### Đã làm

- Tạo `DefaultVerificationService` đọc evidence theo `run_id`, trích mọi số trong câu và
  chỉ chấp nhận khi số khớp nguyên văn với `value_text` của đúng `evidence_id`.
- Chặn số sai, số không citation, citation sai bản ghi, citation đứng tách khỏi số, citation
  thừa và trường hợp một câu còn bất kỳ số nào chưa được kiểm chứng.
- Thay stub `GuardrailNode` bằng fail-closed node; thiếu service/run/draft cũng không được
  đi tiếp.
- Vòng graph cho phép bản nháp ban đầu và tối đa hai lần sinh lại. Sai lần thứ ba đặt
  `terminal_reason=GUARDRAIL_FAILED_ADVISOR_HANDOFF`, xóa cả draft/answer và rẽ `END`.
- Thêm test graph với spy chứng minh synthesis được gọi đúng ba lần và `enqueue_hitl`
  không được gọi lần nào khi cả ba bản nháp đều sai.

### Kiểm thử

- Red trước implementation: test không collect được vì chưa có module verification.
- Test tập trung A6-1: `17 passed`, gồm edge case dạng số khoa học.
- Toàn bộ unit Agent sau A6-1: `101 passed`.
- Toàn bộ Agent gồm migration/integration: `129 passed`.
- `ruff check src/agents tests/agents`: đạt.
- `mypy src/agents`: đạt, 41 source files.

### Còn thiếu / cần khối khác

- Cần persistence adapter tải `run_evidence` thật theo `run_id`.
- Khi guardrail hết retry, state đã fail và không thể vào HITL; khối A4/persistence cần ghi
  đồng thời `agent_runs.state=FAILED` và `terminal_reason` xuống DB.
- `AgentState` đóng băng hiện chưa khai báo `run_id`; LangGraph loại field lạ. A4 cần đưa
  run identifier vào contract state được nhóm duyệt thì node thật mới chạy end-to-end.

## A6-2 — Phân loại ngoài phạm vi

### Đã làm

- Tạo domain `ScopeDecision` cho đúng ba nhãn `IN_SCOPE`, `MISSING_DATA`,
  `OUT_OF_SCOPE`.
- Hai nhãn từ chối bắt buộc có cả câu nêu giới hạn và lối thoát; domain không cho tạo
  decision bị từ chối mà thiếu một trong hai phần.
- Tạo prompt phân loại đóng: câu hỏi về/so sánh đối thủ luôn là `OUT_OF_SCOPE`; output
  chỉ được là một trong ba nhãn.
- Tạo `DefaultScopeClassifierService`, giữ nguyên chữ ký contract `classify`, đồng thời có
  `classify_with_guidance` để A4 lấy trọn câu trả lời an toàn.
- Mọi nhãn, kể cả `IN_SCOPE`, đều được ghi audit đúng thiết kế schema để có thể đánh giá
  độ chính xác classifier sau này.
- Tạo `SqlAlchemyScopeLogUnitOfWork`; log thật vào PostgreSQL trong transaction tập trung,
  không để repository tự mở session.
- Test integration xác nhận câu so sánh Tesla được gán `OUT_OF_SCOPE` và lưu đủ
  `session_id`, utterance, classification, reason, timestamp vào `out_of_scope_log`.

### Kiểm thử

- Red trước implementation: ba test module không collect được vì domain/service/adapter
  chưa tồn tại.
- Unit riêng A6-2: `19 passed`, trong đó danh sách parametrized phủ mọi nhóm câu bị từ chối.
- Integration log PostgreSQL: `1 passed`.
- Toàn bộ Agent gồm migration/integration: `149 passed`.
- `ruff check src/agents tests/agents`: đạt.
- `mypy src/agents`: đạt, 44 source files.

### Còn thiếu / cần khối khác

- A4 cần gọi scope classifier ở điểm routing phù hợp và dùng `user_response` của decision
  cho nhánh từ chối; graph hiện chưa có node/nhánh scope riêng.
- A4/composition cần bind `session_id` của request vào `ScopeSessionContext`, đồng thời nối
  classifier adapter thật. Kiểm thử hiện dùng classifier fake, không gọi dịch vụ trả phí.
- `LLMPort` đóng băng chưa có method phân loại scope dù tài liệu giao LLM làm việc này;
  implementation dùng narrow port riêng để không tự ý sửa contract. Nhóm cần thống nhất
  adapter hoặc duyệt thay đổi contract khi tích hợp.

## Tổng kết QA và phụ thuộc liên khối

### Trạng thái Khối 3

| Task | Lõi + test | Tích hợp production còn phụ thuộc |
|---|---|---|
| A5-1 | Hoàn tất | Repository/state transition của A4/A7 |
| A5-2 | Hoàn tất | Catalog snapshot source + A4 `run_id` |
| A5-3 | Hoàn tất | Recommendation source + persistence score |
| A5-4 | Hoàn tất | API/frontend bảng so sánh |
| A5-5 | Hoàn tất | TCO data source + persistence estimate |
| A5-6 | Hoàn tất | LLM/snapshot-evidence adapter + composition |
| A5-7 | Hoàn tất | Catalog feature join + đường truyền sang synthesis |
| A6-1 | Hoàn tất | Ghi run `FAILED` + `run_id` trong state |
| A6-2 | Hoàn tất | A4 routing/session context + classifier adapter |

### Gate cuối

- `pytest tests/agents -q`: `150 passed`.
- `ruff check src/agents tests/agents`: đạt.
- `mypy src/agents`: đạt, 44 source files.
- `pytest tests/ -v --tb=short`: thu thập 860 test; `849 passed`, `5 failed`, `6 errors`.
  Toàn bộ lỗi/error còn lại thuộc Document/Product và cùng quy về schema test thiếu bảng
  `vehicles`; không có test Agent thất bại.
- `ruff check src/ tests/`: còn 30 lỗi ở Product/Document và test của hai module đó; không
  có lỗi trong phạm vi Agent. Không sửa vì ngoài phạm vi Khối 3.

### Việc cần thống nhất trước khi chạy end-to-end production

1. A4 bổ sung `run_id` vào `AgentState` đóng băng và nối các service/adapters trong
   composition root.
2. A4 nối scope classifier vào routing, bind session context và dùng câu guidance cho mọi
   nhánh từ chối.
3. Catalog/persistence cung cấp nguồn production cho snapshot, scoring/comparison,
   TCO, synthesis evidence và feature introduction.
4. A4/A7 persist `FAILED` khi guardrail hết retry và bảo đảm chỉ bản pass mới vào HITL.
5. Nhóm duyệt cách truyền feature introduction vào synthesis và cách gọi scope classifier
   vì hai nhu cầu này chưa được biểu diễn đầy đủ trong các contract đang đóng băng.
