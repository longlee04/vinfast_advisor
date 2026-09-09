# VinFast AI Sales Advisor — UI demo

Prototype giao diện frontend-only cho ba vai trò: Khách hàng, Tư vấn viên và Quản trị viên. Dữ liệu và trạng thái đều chạy cục bộ trong trình duyệt; ứng dụng không gọi API, cơ sở dữ liệu hay dịch vụ bên ngoài.

## Chạy local

Yêu cầu Node.js 20.9 trở lên.

```powershell
cd D:\P-150\frontend
npm install
npm run dev
```

Mở `http://localhost:3000`. Dùng bộ chuyển vai trò trên thanh đầu trang để đi nhanh giữa ba khu vực demo.

## Kiểm tra chất lượng

```powershell
npm run lint
npm run typecheck
npm run build
```

## Lưu ý về hình ảnh xe

Repository hiện chưa có poster hoặc model 3D VinFast được cấp quyền sử dụng. Vùng trưng bày vì vậy dùng placeholder thương hiệu và hiển thị rõ trạng thái `Asset pending`; không dùng ảnh xe chung rồi gắn nhãn VinFast. Khi có asset chính thức, thay URL tương ứng trong `src/data/vinfast-models.ts`.
