# Runbook nguồn chính sách chính thức và Policy RAG (`develop`)

Tài liệu này dành cho Admin/QA mới làm quen dự án. Mục tiêu là nạp chính sách thành bản nháp, review, rồi mới cho Agent sử dụng. Không có bước nào được `TRUNCATE` hoặc tự xóa corpus cũ.

## 1. Nguyên tắc an toàn

- Chỉ dùng nguồn HTTPS thuộc `vinfastauto.com`, `www.vinfastauto.com` hoặc `static-cms-prod.vinfastauto.com`.
- Crawl/import không chạy khi build image, migrate, khởi động container hoặc xử lý một lượt chat.
- Cùng URL và SHA-256 không tạo bản mới. Hash đổi thì tạo Document DRAFT mới và giữ liên kết tới revision cũ.
- File, scope và chunk luôn ở DRAFT cho đến khi Admin publish.
- Bản cũ không bị xóa khi bản mới được chọn làm mặc định; khách thuộc cohort cũ vẫn tra được bản cũ.
- `POLICY_RAG_ENABLED=false` là trạng thái deploy mặc định. Chỉ bật sau canary.

## 2. Kiểm tra inventory và tải thử, chưa ghi DB

```powershell
python scripts/crawl_vinfast_policies.py status
python scripts/crawl_vinfast_policies.py fetch --source-key motorbike_lfp_5y
python scripts/crawl_vinfast_policies.py fetch --source-key vf5_warranty_v2_2
python scripts/crawl_vinfast_policies.py discover --source-key warranty_index
```

`fetch` chỉ tải, kiểm MIME/magic bytes và tính SHA-256. `discover` chỉ liệt kê link allowlist. Nếu trang HTML bị Cloudflare chặn, kết quả là `FETCH_FAILED_REVIEW_REQUIRED`; không dùng cách lách bảo vệ. Admin có thể tải snapshot/file chính thức bằng trình duyệt và upload thủ công kèm đúng URL nguồn.

### Inventory P1 đã xác minh ngày 01/09/2026

Manifest đã đăng ký ở trạng thái `DISCOVERED` các Sổ bảo hành đang được trang bảo hành chính thức liên kết: VF 3, VF 5, VF 6, VF 8, VF 9, Lạc Hồng 900 LX, Minio Green, Nerio Green, Herio Green, Limo Green, EC Van, Ebus 6B/8B/10B và MPV 7. Các model chỉ có nội dung trên HTML như VF 7, VF 8 The All New và VF e34 tiếp tục dùng snapshot section của `warranty_index`; không gán PDF của model gần giống.

Manifest cũng đăng ký chính sách giá/bán hàng xe máy điện tháng 07/2026 và hợp đồng pin MAX tháng 03/2026, không đổi pin/đổi pin tháng 08/2026. Tất cả chỉ là inventory: merge/deploy không tải file, không tạo embedding và không đổi trạng thái thành `ACTIVE`.

Khi VinFast đổi link, chạy `discover` và đối chiếu lại HTML chính thức trước khi sửa manifest. Không suy luận “mới nhất” từ tên file; hash, nội dung và quyết định của Admin mới xác định revision được publish.

## 3. Import vào môi trường dev/test

Trước hết bật Docker test và dùng đúng DB/MinIO tạm theo [integration-test-safety.md](integration-test-safety.md). Kiểm tra `DOCUMENT_DATABASE_URL` tuyệt đối không trỏ tới DB đang deploy.

Dry-run:

```powershell
python scripts/crawl_vinfast_policies.py import --source-key motorbike_lfp_5y --target-env test
```

Ghi bản DRAFT sau khi đã kiểm tra output:

```powershell
python scripts/crawl_vinfast_policies.py import --source-key motorbike_lfp_5y --target-env test --apply
```

CLI cố ý từ chối import production. Production phải đi qua quy trình Admin đã xác thực và có backup PostgreSQL + inventory MinIO.

## 4. Review trên Admin UI

1. Mở Document Admin, kiểm URL nguồn, authority `OFFICIAL`, revision, SHA-256 và thời điểm lấy nguồn.
2. Analyze. Với PDF scan không có text, dừng ở `NEEDS_OCR`/422; không tạo evidence giả.
3. Kiểm từng scope: xe hay pin/phụ tùng, CAR/MOTORBIKE, LFP/non-LFP, mua/thuê/đổi, tiêu chuẩn/thương mại, mốc hóa đơn/kích hoạt và khoảng ngày.
4. Kiểm model resolve chính xác. Model thiếu hoặc một tên khớp nhiều variant thì không publish.
5. Kiểm evidence là câu chữ có thật trong file và embedding đã sẵn sàng.
6. Khi revision giao nhau, mặc định dừng với HTTP 409. Chỉ chọn:
   - `COEXIST_BY_COHORT` khi cohort thực sự không giao nhau;
   - `SUPERSEDE_DEFAULT` để bản mới thành mặc định nhưng giữ bản cũ cho cohort cũ;
   - không chọn gì/CANCEL để giữ toàn bộ ở DRAFT.

Publish là một transaction: notification, scopes và chunks cùng thành công hoặc cùng rollback.

## 5. Golden canary bắt buộc

Nạp/publish bản cũ trước, kiểm tra; sau đó nạp bản mới ở DRAFT và chứng minh câu trả lời chưa đổi. Chỉ publish bản mới sau review.

- LFP, hóa đơn 14/08/2025: bản cũ, xe/pin 5 năm.
- LFP, ngày 15/08/2025: fail closed cho tới khi reviewer chốt mâu thuẫn “sau” và “từ”.
- LFP, hóa đơn 16/08/2025: bản mới, xe 6 năm và pin 8 năm.
- Pin khác đã review: xe/pin 3 năm; tuyệt đối không lấy scope LFP.
- VF5 v2.1/v2.2: nhận ra thay đổi fact nhưng không tự suy cohort từ tên file.
- “VF5 chạy Grab”: chỉ dùng scope thương mại hoặc yêu cầu làm rõ; không dùng scope tiêu chuẩn.
- Promotion/sạc/đổi pin không được dùng làm evidence bảo hành.
- Follow-up “bảo hành pin thì sao?” phải dùng đúng `vehicle_id` đã chọn ở lượt trước.

Mỗi kết quả canary phải ghi `source_url`, `source_revision`, `scope_id` và evidence ID; không ghi API key/token.

## 6. Bật dần và rollback

Sau khi migration, Admin flow và canary đều xanh:

```dotenv
POLICY_RAG_ENABLED=true
```

Nếu có câu trả lời sai hoặc scope miss tăng:

1. đặt `POLICY_RAG_ENABLED=false` và restart Agent để ngừng retrieval ngay;
2. giữ nguyên Document/MinIO/chunks để điều tra, không xóa;
3. sửa cohort/default bằng một revision DRAFT mới hoặc thao tác Admin đã review;
4. chạy lại golden canary rồi mới bật lại.

Khi cần chọn lại một scope ACTIVE cũ làm mặc định, luôn dry-run trước và dùng đúng ID đã review:

```powershell
python scripts/set_policy_default.py --scope-id <UUID> --actor-id <ADMIN_ID> --target-env production
python scripts/set_policy_default.py --scope-id <UUID> --actor-id <ADMIN_ID> --target-env production --apply --confirm-scope-id <UUID>
```

Lệnh kiểm tra `APP_ENV`, khóa các scope liên quan trong transaction và chỉ đổi cờ mặc định. Nó không archive, không xóa chunk và không xóa object MinIO.

Rollback schema chỉ thực hiện trong cửa sổ bảo trì sau backup. Không downgrade nếu cột/scope mới đã có dữ liệu production mà chưa xuất backup.

## 7. QA trước merge/deploy

```powershell
ruff check src/ tests/
pytest tests/document/ -v --tb=short
pytest tests/agents/ -v --tb=short
pytest tests/ -v --tb=short
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Migration phải chạy trên DB tạm: upgrade head, downgrade một revision rồi upgrade lại. Không dùng DB dev để chạy integration test.
