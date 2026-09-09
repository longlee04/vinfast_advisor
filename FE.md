# TÀI LIỆU TỔNG QUAN KIẾN TRÚC & TÍNH NĂNG PHÂN HỆ FRONTEND (FE)
> **Dự án:** VinFast AI Sales Advisor (P-150)  
> **Framework & Công nghệ:** Next.js 16 (App Router), React 19, TypeScript 6, Tailwind CSS v4, Lucide Icons, Leaflet / Supercluster, @google/model-viewer (3D Showroom).  
> **Vị trí mã nguồn:** `frontend/`  
> **Trạng thái:** Đầy đủ các phân hệ Khách hàng (`CUSTOMER`), Tư vấn viên (`ADVISOR`), và Quản trị viên (`ADMIN`), tích hợp Trung tâm Phân công Khách hàng (Admin Assignment Center), Hàng đợi duyệt & Thống kê động từ PostgreSQL, Đặt lịch lái thử Showroom liên kết Database thời gian thực.

---

## 1. TỔNG QUAN CÔNG NGHỆ & NGUYÊN TẮC THIẾT KẾ FRONTEND

Phân hệ Frontend được xây dựng theo kiến trúc **Modern Component-Driven Architecture**, tối ưu hóa cho trải nghiệm người dùng tương tác thời gian thực với Trợ lý AI và hệ thống điều hành bán hàng đa vai trò.

### 1.1. Công nghệ Lõi (Tech Stack)
* **Core Framework:** Next.js 16.3.0 (React Server Components + Client Components với App Router)
* **UI Library:** React 19.2.8, React DOM 19.2.8
* **Ngôn ngữ:** TypeScript 6.0.3 (Type-safe 100%, cấu hình `strict: true`, không dùng `any`)
* **Styling & Design System:** Tailwind CSS v4.3.3 kết hợp biến màu CSS thương hiệu VinFast
* **Iconography:** Lucide React (1.28.0)
* **Bản đồ Không gian Địa lý:** Leaflet (1.9.4), Supercluster (8.0.1) xử lý cụm điểm trạm sạc hiệu năng cao
* **Mô hình 3D Showroom:** `@google/model-viewer` (4.3.1) kết xuất 3D WebGL tương tác 360 độ
* **Testing Suite:** Vitest (4.1.10), Testing Library React (16.3.2), JSDOM (29.1.1)

### 1.2. Nguyên tắc Thiết kế & Bảo mật Client
1. **HttpOnly Cookie Authentication:** Không lưu JWT/Access Token trong `localStorage` hay `sessionStorage` để chống XSS. Toàn bộ xác thực sử dụng HttpOnly Cookie (`credentials: "include"`).
2. **CSRF Double-Submit Header:** Tự động đọc cookie CSRF và gửi kèm header `X-CSRF-Token` cho mọi mutation request (`POST`, `PUT`, `DELETE`, `PATCH`).
3. **Session Auto-Refresh & Retry:** Cơ chế `withSessionRetry` tự động bắt mã lỗi 401, gọi làm mới token (`/api/v1/auth/refresh`) và phát lại request ban đầu mà không làm gián đoạn người dùng.
4. **Reactive Real-time Streams:** Tích hợp cả **Server-Sent Events (SSE)** để nhận các phản hồi AI sau khi được duyệt từ hàng đợi HITL và **WebSockets** cho Live Chat thời gian thực 2 chiều giữa Khách hàng và Tư vấn viên.
5. **Dữ liệu Thời Gian Thực (No Hardcoded Data):** Toàn bộ dữ liệu nghiệp vụ (Phân công khách hàng, Thống kê hàng đợi, Lịch hẹn lái thử, Xe catalog, Showroom) đọc/ghi trực tiếp 100% từ Database PostgreSQL thông qua REST API.

---

## 2. SƠ ĐỒ ĐIỀU HƯỚNG & CÁC TUYẾN ĐƯỜNG (ROUTING MAP)

```
frontend/src/app/
├── (Customer Facing)
│   ├── page.tsx                      # Trang chủ (Hero Carousel, Sản phẩm nổi bật, CTA)
│   ├── consultation/                 # Tư vấn trực tuyến cùng Trợ lý AI VinFast
│   │   ├── page.tsx                  # Giao diện Chatbot thông minh chính
│   │   └── pending/page.tsx          # Màn hình chờ duyệt phản hồi nhạy cảm (HITL)
│   ├── compare/page.tsx              # So sánh đối đầu 2-3 mẫu xe đa chiều
│   ├── locations/page.tsx            # Bản đồ tìm kiếm trạm sạc & Showroom toàn quốc
│   ├── tco/page.tsx                  # Công cụ tính tổng chi phí sở hữu 5 năm (TCO)
│   ├── vehicles/                     # Danh mục xe Ô tô điện
│   │   ├── page.tsx                  # Danh sách toàn bộ ô tô điện VinFast
│   │   └── [slug]/page.tsx           # Chi tiết xe ô tô (Showcase VF 7, VF 8,...)
│   ├── motorbikes/                   # Danh mục Xe máy điện
│   │   └── [slug]/page.tsx           # Chi tiết xe máy điện (Klara, Feliz, Evo,...)
│   ├── test-drive/                   # [CẬP NHẬT] Đăng ký lái thử xe (Liên kết PostgreSQL)
│   │   ├── page.tsx                  # Form đăng ký lái thử tại showroom (API DB)
│   │   └── success/page.tsx          # Trang thông báo đăng ký thành công
│   ├── history/page.tsx              # Lịch sử các phiên tư vấn cũ của khách
│   ├── account/page.tsx              # Quản lý tài khoản & hồ sơ nhu cầu cá nhân
│   ├── login/page.tsx                # Đăng nhập tài khoản khách hàng
│   └── register/page.tsx             # Đăng ký tài khoản khách hàng mới
│
├── (Advisor Portal - /advisor/*)
│   ├── layout.tsx                    # Shell điều hành riêng cho Tư vấn viên
│   ├── page.tsx                      # Dashboard tổng quan & Hàng đợi duyệt (HITL Queue)
│   ├── recommendations/[id]/page.tsx # Chi tiết duyệt bản nháp AI (Claim, Edit, Approve, Reject)
│   ├── conversations/                # Quản lý hội thoại Live Chat
│   │   └── [id]/page.tsx             # Tiếp quản chat trực tiếp 1-1 với khách qua WebSocket
│   ├── customers/page.tsx            # Danh sách khách hàng thực tế được phân công (Kết nối API)
│   ├── test-drives/page.tsx          # Quản lý & xử lý các lịch hẹn lái thử (Kết nối API)
│   └── notices/page.tsx              # Bảng tin thông báo nghiệp vụ nội bộ
│
├── (Admin Portal - /admin/*)
│   ├── layout.tsx                    # Shell quản trị cấp cao cho Admin
│   ├── page.tsx                      # Dashboard giám sát hệ thống & Live AI Metrics (Kết nối API)
│   ├── assignments/page.tsx          # [MỚI] Trung tâm Phân công Khách hàng (Assignment Center)
│   ├── chat-sessions/                # AI Observability & Transcript Inspector
│   │   ├── page.tsx                  # Danh sách toàn bộ phiên chat trong hệ thống
│   │   └── [id]/page.tsx             # AI Trace Timeline chi tiết (Model nodes, latency, token, cost)
│   ├── conversations/[id]/page.tsx   # Kiểm tra & quản lý xóa phiên hội thoại
│   ├── users/page.tsx                # Quản lý người dùng: Kích hoạt pending, Khóa/Mở tài khoản
│   ├── vehicles/page.tsx             # Quản trị danh mục xe catalog
│   └── notices/page.tsx              # Soạn thảo & phát hành thông báo nội bộ
│
└── staff-login/page.tsx              # Cổng đăng nhập dành riêng cho Staff (Advisor / Admin)
```

---

## 3. CHI TIẾT TỪNG PHÂN HỆ VÀ COMPONENT ĐÃ XÂY DỰNG

### 3.1. Phân hệ Tư vấn Trợ lý AI Thông minh (`/consultation`)
Giao diện trung tâm cho phép người dùng trò chuyện tương tác trực tiếp với Agent thông qua chuỗi trạng thái LangGraph:

* **`ConsultationFlow` (`components/consultation/consultation-flow.tsx`):**
  * Điều phối toàn bộ luồng chat đa lượt, tự động cuộn (auto-scroll) mượt mà đến tin nhắn mới nhất.
  * Hỗ trợ nhận diện tin nhắn đầu vào từ URL prompt (`?prompt=...`).
  * Quản lý trạng thái nhập liệu (loading, sending, typing indicator).
  * Điều khiển hiển thị các thẻ đặc biệt theo ngữ cảnh: Thẻ xe đề xuất, Bảng so sánh, Thẻ địa điểm trạm sạc, Lời xin quyền vị trí, Quick Replies.
* **`VehiclePitchCard` & `VehiclePitchList` (`components/consultation/vehicle-pitch-card.tsx`):**
  * Hiển thị thẻ card xe đề xuất sang trọng, gồm: Ảnh thực tế chuẩn hóa, Tên thương mại, Giá niêm yết từ (VND), Đoạn phân tích cá nhân hóa (`pitch`), Chip tiêu chí nổi bật (`citations`), Nút hành động nhanh **"Đăng ký lái thử"** hoặc **"Xem chi tiết"**.
* **Tính năng Danh mục Thu gọn (Top 5 + Xem thêm):**
  * Khi duyệt danh mục ban đầu, FE hiển thị 5 mẫu xe tiêu biểu đầu tiên.
  * Tự động hiển thị nút tương tác **`Xem thêm (còn N mẫu xe khác)`** kèm icon `ChevronDown`. Khi bấm vào sẽ bung toàn bộ danh mục và cho phép **`Thu gọn danh sách`** bất kỳ lúc nào để tránh làm tràn màn hình chat.
* **`AgentComparison` (`components/consultation/agent-comparison.tsx`):**
  * Hiển thị bảng so sánh trực quan đối đầu giữa 2–3 mẫu xe ngay trong luồng chat.
* **`NearbyLocationList` (`components/consultation/nearby-location-list.tsx`):**
  * Hiển thị danh sách trạm sạc, showroom, tủ đổi pin gần nhất.
  * Mỗi card hiển thị: Tên địa điểm, địa chỉ, khoảng cách nổi bật (ví dụ: `📍 Cách khoảng 120 m`), giờ mở cửa, số hotline gọi nhanh (`tel:...`), và nút **"Chỉ đường Google Maps"** mở ứng dụng bản đồ dẫn đường trực tiếp.
* **`LocationRequest` (`components/consultation/location-request.tsx`):**
  * Khối giao diện xin vị trí thông minh khi khách cần tìm trạm sạc/showroom.
  * Cung cấp nút bấm một chạm **"📍 Chia sẻ vị trí của bạn"** (lấy GPS trực tiếp từ trình duyệt) và ô nhập văn bản vị trí tùy chỉnh.
* **`QuickReplies` (`components/consultation/quick-replies.tsx`):**
  * Render các nút bấm gợi ý câu trả lời nhanh giúp người dùng tương tác một chạm.
* **`PendingApproval` & `DeliveredAnswer` (`components/consultation/pending-approval.tsx`, `delivered-answer.tsx`):**
  * Hiển thị trạng thái chờ duyệt và tự động cập nhật câu trả lời đã được Tư vấn viên phê duyệt vào dòng chat qua SSE.
* **`NeedsSummarySheet` (`components/consultation/needs-summary-sheet.tsx`):**
  * Slide-over drawer bên phải hiển thị bảng tóm tắt các tiêu chí nhu cầu đã thu thập được của khách hàng.

---

---

### 3.2. Phân hệ Đặt lịch Lái thử Khách hàng (`/test-drive`, `components/booking/booking-form.tsx`) — *[CẬP NHẬT MỚI]*

* **Nạp Tùy chọn Xe & Showroom Thời Gian Thực (`fetchBookingOptions`):**
  * Gọi API `GET /api/v1/agent/bookings/options` nạp danh sách toàn bộ các dòng xe từ bảng `vehicles` (VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 9) và danh sách Showroom chính hãng từ bảng `locations`.
* **Ghi Nhận Đặt Lịch vào PostgreSQL (`createTestDriveBooking`):**
  * Khi khách hàng gửi yêu cầu, dữ liệu được truyền thẳng tới endpoint `POST /api/v1/agent/bookings`.
  * Tự động lưu bản ghi vào bảng `test_drive_bookings` với trạng thái `REQUESTED`.
  * Kích hoạt bản tin thông báo nội bộ khẩn cấp (`internal_notices`) thông báo tới các Tư vấn viên.

---

### 3.3. Phân hệ Tài khoản Khách hàng & Thống kê Hoạt động (`/account`, `components/customer/customer-history.tsx`) — *[CẬP NHẬT MỚI]*

* **Bộ đếm Thống kê Động Thời Gian Thực (`fetchCustomerSummary`):**
  * Gọi API `GET /api/v1/agent/customer/summary` để nạp dữ liệu thống kê trực tiếp từ PostgreSQL cho khách hàng đăng nhập:
    * **Phiên tư vấn**: Đếm số phiên hội thoại của khách hàng trong bảng `conversation_sessions`.
    * **Bảng so sánh**: Đếm số lượt so sánh/phiên có tương tác.
    * **Lịch lái thử**: Đếm số đơn đăng ký lái thử trong bảng `test_drive_bookings`.
  * Bổ sung nút **"Làm mới"** cập nhật số liệu và dòng thời gian hoạt động tức thì.
* **Dòng thời gian Hoạt động gần đây (Dynamic Activity Timeline):**
  * Tự động tổng hợp và sắp xếp theo thời gian các phiên tư vấn và đơn đặt lịch lái thử thực tế.
  * Hiển thị trạng thái chi tiết (*Chờ xác nhận*, *Đã xác nhận*, *Đã hoàn thành*, *Đang chờ duyệt*) kèm tone màu và biểu tượng trực quan.
  * Hỗ trợ cập nhật hồ sơ cá nhân và sở thích nhu cầu (loại xe, ngân sách, số chỗ, điều kiện sạc).

---

### 3.4. Phân hệ Khám phá Sản phẩm & Showroom 3D (`/vehicles`, `/motorbikes`, `/compare`, `/tco`)

* **Showroom Xe 3D Tương tác (`components/showroom/`):**
  * **`VinfastVehicleViewer` & `InteractiveVehicleModel`:** Tích hợp WebGL 3D Viewer cho phép xoay 360 độ, phóng to/thu nhỏ chi tiết xe.
  * **`VehicleControlTray`:** Thanh điều khiển tương tác chọn bảng màu sơn ngoại thất xe thực tế, đổi góc nhìn (Camera view angle).
  * **`VehiclePosterFallback`:** Hiển thị poster chất lượng cao trong thời gian tải dữ liệu 3D.
* **Chi tiết & Showcase Dòng Xe (`components/catalog/`):**
  * `VF7Showcase`, `VF8Showcase`: Trang giới thiệu đặc biệt cho các dòng xe chủ lực với câu chuyện sản phẩm, thông số ADAS và video/hình ảnh chính hãng.
* **Công cụ So sánh Xe Đa chiều (`/compare`, `components/comparison/vehicle-comparison.tsx`):**
  * Cho phép chọn 2 đến 3 mẫu xe bất kỳ để so sánh thông số chi tiết.
* **Bộ Tính toán Tổng Chi phí Sở hữu TCO 5 Năm (`/tco`, `components/tco/tco-calculator.tsx`):**
  * Công cụ tài chính trực quan mô phỏng chi phí sở hữu xe điện VinFast trong 60 tháng (Mua pin vs Thuê pin vs Xe xăng).

---

### 3.4. Phân hệ Bản đồ Mạng lưới Trạm sạc & Showroom (`/locations`)

* **`LocationMap` (`components/locations/location-map.tsx`):**
  * Bản đồ Leaflet tích hợp thuật toán gom cụm **Supercluster** hiển thị mượt mà hơn 60.000 điểm sạc trên toàn quốc.
  * Tùy biến icon marker theo từng loại địa điểm: Trạm sạc Ô tô (xanh dương), Trạm sạc Xe máy (xanh ngọc), Tủ đổi pin (vàng), Showroom (đỏ VinFast), Xưởng dịch vụ (xám).
* **`LocationFinder` (`components/locations/location-finder.tsx`):**
  * Thanh tìm kiếm địa danh kết hợp bộ lọc danh mục và tự động định vị GPS.

---

### 3.5. Phân hệ Không gian Làm việc Tư vấn viên (`/advisor/*`) — *[CẬP NHẬT MỚI]*

* **Hàng đợi Phê duyệt AI & Bộ đếm Số liệu Động (`/advisor`, `components/advisor/advisor-queue-table.tsx`):**
  * **Bộ đếm thời gian thực từ Database (`GET /api/v1/agent/review/stats`):**
    * **Chờ duyệt:** Đếm chính xác số lượng yêu cầu đang chờ trong bảng `review_queue`, kèm cảnh báo số mục ưu tiên cao / khẩn cấp (`PRIORITY: HIGH/URGENT`).
    * **Yêu cầu tư vấn (Lead):** Đếm số lượng ticket khách hàng yêu cầu người thật hỗ trợ trực tiếp (`LEAD_REASON`).
    * **Đang giữ xử lý:** Đếm số lượng ticket đang được TVV giữ lease.
    * **Đã giải quyết:** Đếm tổng số yêu cầu đã duyệt (`APPROVED`, `EDITED`) hoặc từ chối (`REJECTED`) từ PostgreSQL.
  * Nút **Làm mới (Refresh)** đồng bộ dữ liệu tức thì.
  * Bảng danh sách các câu trả lời đang chờ duyệt kèm đếm ngược lease 15 phút.
* **Bảng Xử lý Chi tiết Duyệt (`/advisor/recommendations/[id]`, `components/advisor/advisor-review-panel.tsx`):**
  * Approve, Edit & Approve (có validate bảo vệ số liệu catalog), Reject.
* **Tiếp quản Cuộc trò chuyện & Live Chat 1-1 (`/advisor/conversations/[id]`, `components/advisor/advisor-live-chat.tsx`):**
  * Kênh WebSocket thời gian thực (`/ws/advisor/conversations/{id}`), AI Summary, Transcript, Handoff.
* **Quản lý Khách hàng Được Phân Công (`/advisor/customers`, `components/advisor/advisor-customers.tsx`):**
  * **Kết nối API thật 100% (`GET /api/v1/advisor/customers`)**: Tải danh sách khách hàng do Admin chỉ định cho Advisor từ bảng `customer_advisor_assignments`.
  * Hỗ trợ tìm kiếm, chuyển đổi nhanh danh tính TVV kiểm thử và xem hồ sơ nhu cầu khách hàng.
* **Quản lý Yêu cầu Lái thử Showroom (`/advisor/test-drives`, `app/advisor/test-drives/page.tsx`):**
  * **Đã xóa bỏ hoàn toàn mock hardcode (`bk-1`, `bk-2`)**.
  * Kết nối trực tiếp `GET /api/v1/agent/bookings` đọc từ bảng `test_drive_bookings` trong PostgreSQL.
  * 4 Thẻ thống kê động: *Tổng yêu cầu*, *Chờ xác nhận*, *Đã xác nhận*, *Đã hủy*.
  * Bộ lọc trạng thái và các nút hành động trực tiếp:
    * **"Xác nhận lịch"**: gọi API `POST /api/v1/agent/bookings/{booking_id}/confirm` -> chuyển trạng thái thành `CONFIRMED` và gán TVV phụ trách.
    * **"Hủy"**: gọi API `POST /api/v1/agent/bookings/{booking_id}/cancel` -> chuyển trạng thái thành `CANCELLED`.
* **Bảng Tin Thông báo Nội bộ (`/advisor/notices`):**
  * Tiếp nhận các thông báo khẩn cấp từ Ban Quản trị và hệ thống đặt lịch lái thử.

---

### 3.6. Phân hệ Trung tâm Quản trị Admin (`/admin/*`)

* **Trung tâm Phân công Khách hàng (Admin Assignment Center - `/admin/assignments`, `components/admin/assignment-center.tsx`):**
  * **Phân công mới & Chuyển giao:** Modal phân công khách hàng cho bất kỳ Tư vấn viên nào kèm lý do điều chuyển.
  * **Lịch sử Phân công (Audit Trail):** Modal xem toàn bộ dòng thời gian chuyển giao của từng khách hàng từ bảng `customer_advisor_assignments`.
  * **Bộ lọc Trạng thái:** Lọc theo `ACTIVE` (Đang phụ trách), `TRANSFERRED` (Đã chuyển giao), `UNASSIGNED` (Đã hủy gán).
* **Live Analytics Dashboard (`/admin`, `components/admin/admin-dashboard.tsx`):**
  * **Kết nối API thật 100% (`GET /api/v1/admin/analytics/dashboard`)**:
    * 4 Thẻ KPI tổng hợp trực tiếp từ DB (Tổng số hội thoại, Hồ sơ khách hàng hoàn tất, Đề xuất đã duyệt, Đơn lái thử).
    * Phễu chuyển đổi 5 bước tính toán tự động từ view `funnel_metrics`.
    * Tỷ lệ chất lượng duyệt HITL (Duyệt nguyên trạng vs Chỉnh sửa vs Từ chối).
* **Trung tâm AI Observability & Quản lý Phiên Chat (`/admin/chat-sessions`):**
  * Danh sách toàn bộ các phiên hội thoại và AI Trace Timeline chi tiết từng lượt.
* **Quản lý Người dùng & Kích hoạt Tài khoản (`/admin/users`, `components/admin/user-management-preview.tsx`):**
  * Kích hoạt tài khoản pending, vô hiệu hóa/mở khóa tài khoản, tạo tài khoản staff.
* **Quản lý Danh mục Phương tiện (`/admin/vehicles`, `components/admin/catalog-preview.tsx`):**
  * Quản lý xe và trạng thái kinh doanh trong Catalog DB thật.

---

## 4. TỔNG HỢP CẤU TRÚC THƯ MỤC MÃ NGUỒN FRONTEND

```
frontend/src/
├── app/                        # Next.js App Router Pages & Layouts
│   ├── admin/                  # Admin routes (/admin, /admin/assignments, /admin/users,...)
│   ├── advisor/                # Advisor routes (/advisor, /advisor/customers, /advisor/test-drives,...)
│   └── ...                     # Customer routes (/consultation, /test-drive, /locations,...)
├── components/                 # React UI Components phân chia theo module
│   ├── admin/                  # Dashboard, AssignmentCenter, AI Trace, UserManagement
│   ├── advisor/                # Dynamic Queue Table, Review Panel, Live Chat, AdvisorCustomers
│   ├── booking/                # Biểu mẫu đăng ký lái thử xe (PostgreSQL API)
│   ├── catalog/                # Chi tiết xe, showcase VF7, VF8, Motorbikes
│   ├── comparison/             # So sánh xe toàn trang
│   ├── consultation/           # Chatbot flow, Pitch cards, Nearby cards, Quick replies
│   ├── customer/               # Agent dock, Lịch sử hội thoại sidebar
│   ├── locations/              # Leaflet Map, Location Finder, Cluster pins
│   ├── shared/                 # Header, Mega menu, OperationalShell, Status badges, MetricCard
│   ├── showroom/               # WebGL 3D Model Viewer, Color selector
│   └── tco/                    # Công cụ tính toán chi phí sở hữu 5 năm
├── lib/                        # Thư viện tiện ích, API clients, formatters
│   ├── api/                    # API wrappers: agent.ts, assignments.ts, auth.ts, locations.ts, vehicles.ts, session.ts
│   ├── format.ts               # Định dạng tiền tệ VND, khoảng cách km/m, ngày tháng
│   └── vehicle-media.ts        # Helper xử lý ảnh xe & fallback
├── mocks/                      # Mock data phục vụ unit test và offline demo
├── store/                      # React Context Stores: auth-store, agent-session, demo-store
└── types/                      # TypeScript type definitions (agent.ts, location.ts, chat-observability.ts)
```

---

## 5. HỆ THỐNG KIỂM THỬ TỰ ĐỘNG FRONTEND (TESTING SUITE)

Frontend được bao phủ toàn diện bằng bộ kiểm thử tự động **Vitest + Testing Library**:

| Module Kiểm thử | File Test | Kịch bản Kiểm tra |
|:---|:---|:---|
| **Chat Flow** | `consultation-flow.test.tsx` | Khởi tạo phiên, gửi tin nhắn, nhận phản hồi, auto-scroll, render quick replies |
| **Thẻ Đề xuất Xe** | `vehicle-pitch-card.test.tsx` | Hiển thị ảnh catalog, giá niêm yết, pitch text, ẩn pitch khi TVV sửa |
| **Danh sách Đề xuất** | `vehicle-pitch-list.test.tsx` | Render lưới responsive thẻ xe, xử lý danh sách rỗng |
| **So sánh Xe** | `agent-comparison.test.tsx`, `vehicle-comparison.test.tsx` | Render bảng so sánh 2-3 xe, highlight khác biệt thông số |
| **Showcase Xe** | `vf7-showcase.test.tsx`, `vf8-showcase.test.tsx`, `car-showcase.test.tsx` | Render hình ảnh, thông số kỹ thuật ADAS, chuyển tab màu sơn |
| **Live Chat** | `advisor-live-chat.test.tsx`, `live-chat-session.test.ts` | Kết nối WebSocket, gửi nhận tin nhắn, chuyển giao quyền (handoff) |
| **AI Observability** | `chat-session-list.test.tsx` | Bảng danh sách phiên chat, lọc theo status, hiển thị latency và token cost |
| **Mega Menu** | `vehicle-mega-menu.test.tsx`, `motorbike-mega-menu.test.tsx` | Mở menu điều hướng danh mục xe ô tô và xe máy điện |
| **Lịch sử Khách** | `customer-history.test.tsx`, `agent-dock.test.tsx` | Bộ đếm động từ PostgreSQL (Phiên tư vấn, So sánh, Lái thử), dòng thời gian hoạt động thực tế, widget chat nổi |
| **Auth & Session** | `agent-session.test.tsx`, `session.test.ts`, `agent.test.ts` | Quản lý state reducer, cơ chế retry khi hết hạn session, CSRF echo header |

---

## 6. TỔNG KẾT

Phân hệ Frontend của dự án **VinFast AI Sales Advisor (P-150)** hiện đã hoàn thiện đầy đủ 100% các tính năng theo yêu cầu thiết kế:
* **Trung tâm Phân công Khách hàng (Admin Assignment Center)** cho phép Admin chỉ định, điều chuyển và xem toàn bộ lịch sử phân công của từng khách hàng.
* **Hàng đợi Duyệt & Bộ đếm Số liệu Advisor Thời Gian Thực** đọc trực tiếp từ PostgreSQL `review_queue`.
* **Quy trình Đặt lịch Lái thử Khách hàng & Quản lý Lịch hẹn Advisor** liên kết trực tiếp hai chiều với cơ sở dữ liệu `test_drive_bookings`, `vehicles`, `locations`, `customer_profiles`.
* **Trang Tài khoản Khách hàng (`/account`) & Hoạt động Thời Gian Thực** nạp số liệu thống kê và timeline hoạt động trực tiếp 100% từ cơ sở dữ liệu PostgreSQL.
* **Trợ lý AI Đa kênh Thông suốt** tương tác mượt mà qua các tùy chọn nhanh (CAR, BIKE, ngân sách, số chỗ) với cơ chế bảo vệ an toàn fail-open không gián đoạn.
* Giao diện hiện đại, chuẩn nhận diện thương hiệu VinFast, tương thích tốt trên mọi thiết bị.


