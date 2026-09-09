# VinFast AI Sales Advisor — UI Demo Specification

## 1. Purpose

This document describes the clickable frontend demo for three roles:

- Customer
- Advisor
- Admin preview

The demo uses local mock data only.

No backend, database, API, authentication server, RAG, or LangGraph implementation is required.

## 2. Customer journey

```text
Home
→ Guided consultation
→ Pending advisor approval
→ Approved recommendations
→ Vehicle comparison
→ TCO estimation
→ Test-drive booking
→ Confirmation
```

Important rule:

The recommendation must not appear immediately after generation. It first enters a simulated advisor-review state, then returns to the same local customer session after approval.

## 3. Customer screens

### 3.1 Home

Purpose:
- explain the product quickly;
- make the VinFast vehicle the main visual focus;
- move the customer into consultation.

Required:
- compact top navigation;
- large VinFast vehicle image or authorized 3D viewer;
- heading: `Tìm mẫu xe phù hợp với bạn`;
- primary CTA: `Bắt đầu tư vấn`;
- secondary CTA: `Khám phá các dòng xe`;
- three value points:
  - `Tư vấn theo nhu cầu`;
  - `Thông tin có căn cứ`;
  - `Tư vấn viên kiểm tra trước khi gửi`.

### 3.2 Guided consultation

Do not use a permanent two-column dashboard.

Layout:
- compact header;
- horizontal progress;
- centered conversation;
- quick replies;
- collapsed need summary;
- message composer.

First question:

```text
Bạn đang tìm ô tô hay xe máy điện?
```

For cars, ask:
- passenger count;
- travel distance;
- charging access;
- budget;
- primary use;
- additional priorities.

For electric motorbikes, ask:
- purpose: commuting, delivery, or personal;
- travel distance;
- charging access;
- budget;
- additional priorities.

Rules:
- one question per step;
- prior answers can be edited;
- summary opens temporarily;
- progress remains visible;
- no permanent need-profile sidebar.

Required states:
- initial;
- partial;
- typing/loading;
- completed;
- connection error.

### 3.3 Pending approval

Required:
- title: `Đề xuất đang được tư vấn viên kiểm tra`;
- need-profile summary;
- subtle loading state;
- `Tiếp tục trò chuyện`;
- `Gặp tư vấn viên`;
- demo-only action: `Mô phỏng tư vấn viên đã duyệt`.

Do not show a fake exact waiting time.

### 3.4 Recommendations

Display 1–3 ranked VinFast recommendations.

Each card:
- image;
- model and variant;
- rank;
- price;
- 2–4 personalized reasons;
- one trade-off;
- source labels;
- advisor-reviewed badge;
- select-for-comparison action.

Required states:
- default;
- loading;
- insufficient information;
- no match;
- rejected;
- error.

Actions:
- `So sánh xe`;
- `Ước tính chi phí`;
- `Đặt lịch lái thử`.

### 3.5 Comparison

Compare 2–3 vehicles of the same type.

Show:
- price;
- range;
- seats for cars;
- relevant motorbike attributes;
- charging;
- warranty;
- strongest advantage;
- trade-off;
- `Phù hợp với ai`.

Block cross-type comparison:

```text
Chỉ có thể so sánh các phương tiện cùng loại.
```

### 3.6 TCO demo

Local deterministic calculation only.

Inputs:
- selected vehicle;
- monthly distance;
- ownership duration;
- region;
- charging assumption.

Outputs:
- vehicle price;
- estimated registration cost;
- charging cost;
- maintenance;
- total initial cost;
- estimated total ownership cost.

Always show:

```text
Kết quả chỉ mang tính ước tính, không phải báo giá cuối cùng.
```

### 3.7 Test-drive booking

Fields:
- vehicle;
- showroom;
- date;
- time slot;
- full name;
- phone.

States:
- idle;
- submitting;
- success;
- slot conflict;
- error.

Always disclose:

```text
Bản demo giao diện — chưa kết nối hệ thống showroom.
```

## 4. Advisor journey

```text
Queue
→ Review customer profile
→ Review AI recommendation and sources
→ Approve / Edit / Reject
→ Send result to customer
```

### 4.1 Queue

Required:
- tabs: `Chờ duyệt`, `Đã duyệt`, `Đã từ chối`;
- customer;
- proposed models;
- submitted time;
- status;
- `Xem & duyệt`;
- loading, empty, and error states.

### 4.2 Review detail

Two-column operational layout is allowed.

Left:
- customer needs;
- recommendation;
- reasons;
- trade-offs;
- source labels;
- generated time.

Right:
- `Duyệt nguyên trạng`;
- `Chỉnh sửa nội dung`;
- `Từ chối`.

Edit mode:
- prefilled text;
- source labels remain visible;
- save and cancel.

Reject mode:
- mock reason;
- optional `Chuyển tư vấn trực tiếp`.

After action:
- local state changes;
- item leaves pending queue;
- customer session can reveal approved or edited content.

## 5. Admin preview

Visual prototype only.

### Dashboard
- conversations;
- completed profiles;
- approved recommendations;
- test-drive requests;
- conversion funnel.

### Catalog
- vehicle type;
- model;
- variant;
- price;
- status;
- updated date;
- mock `Xem`, `Sửa`, and `Thêm xe` dialogs.

### Internal notices
- title;
- priority;
- date;
- read-state preview;
- mock create-notice dialog.

No real persistence or CRUD backend.

## 6. Demo navigation

Provide a role switcher:

```text
Khách hàng | Tư vấn viên | Admin
```

This is not authentication.

Provide:

```text
Đặt lại demo
```

## 7. Required routes

Suggested:

```text
/
/consultation
/consultation/pending
/recommendations
/compare
/tco
/test-drive
/test-drive/success

/advisor
/advisor/recommendations/[id]
/advisor/test-drives

/admin
/admin/vehicles
/admin/notices
```

## 8. Mock data

Use typed local mock data.

Suggested files:

```text
frontend/src/mocks/
  vehicles.ts
  conversations.ts
  recommendations.ts
  advisor-queue.ts
  showrooms.ts
  bookings.ts
  admin.ts
```

## 9. Acceptance criteria

The demo is complete when:

- it runs without backend or database;
- all interactions use local frontend state;
- customer pages have no permanent sidebar;
- the full customer journey is clickable;
- advisor approval can be simulated;
- approved content returns to the customer session;
- comparison works for 2–3 same-type vehicles;
- TCO recalculates locally;
- booking success and conflict can be simulated;
- advisor screens are present;
- lightweight admin preview is present;
- the visual style is simple, modern, premium, and VinFast-oriented;
- an authorized VinFast 3D asset or explicit VinFast poster fallback is used;
- no generic car is presented as VinFast;
- desktop and mobile layouts are usable.
