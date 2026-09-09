# Vehicle media assets

Đặt poster hoặc model 3D VinFast đã được cấp quyền sử dụng trong thư mục này. Không dùng ảnh xe chung rồi gắn tên một model VinFast cụ thể.

## Poster

Ví dụ:

```text
public/vehicles/vf6-plus/poster.webp
public/vehicles/vf7-base/poster.webp
```

Sau đó khai báo trong `src/mocks/vehicles.ts`:

```ts
posterPath: "/vehicles/vf6-plus/poster.webp",
assetStatus: "authorized",
```

Catalog đã có sẵn nhánh render poster. Nếu không có `posterPath`, UI tiếp tục hiển thị `Asset pending`.

## Model 3D

Định dạng đề xuất là GLB đã tối ưu cho web, kèm poster tĩnh để hiển thị trong lúc tải:

```text
public/models/vinfast/vf-6/model.glb
public/models/vinfast/vf-6/poster.webp
```

Khai báo đường dẫn và chuyển trạng thái trong `src/data/vinfast-models.ts`:

```ts
{
  id: "vf-6", // phải khớp id trong menu
  name: "VF 6",
  variant: "Plus",
  assetStatus: "authorized",
  modelPath: "/models/vinfast/vf-6/model.glb",
  posterPath: "/models/vinfast/vf-6/poster.webp",
  availableColors: [
    {
      id: "blue",
      name: "Urban Blue",
      hex: "#315f89",
      materialName: "CarPaint",
    },
  ],
}
```

`materialName` phải khớp đúng tên material sơn trong GLB. Nếu GLB dùng `KHR_materials_variants`, khai báo `variantName` cho từng màu thay cho `materialName`. Viewer chỉ bật khi đồng thời có `assetStatus: "authorized"` và `modelPath`; nếu thiếu hoặc tải lỗi, trang chi tiết tự dùng poster/ảnh menu mà không hiển thị model sai.
