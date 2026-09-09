"use client";

import type { SpecGroup, VehicleDetails } from "@/types/agent";

/**
 * Thẻ chi tiết xe khách vừa chốt.
 *
 * Trước thẻ này, câu trả lời về dưới dạng văn xuôi trong `answer` và `RichText`
 * render nó — nên khách nhận một bảng thông số dạng markdown. Đo trên prod
 * 2026-08-28: *"1. **Thông số kỹ thuật**: * **Động cơ & Vận hành**: công suất
 * 100 kW..."* — đúng một trang tài liệu, không phải một lời tư vấn.
 *
 * **Chỉ nguồn ĐÃ XÁC MINH.** Ba khối cũ (điểm nổi bật / tính năng / an toàn) đã
 * bị gỡ ở vòng rà soát #4: chúng chở trích đoạn RAG thô, lọc duy nhất bằng
 * trạng thái `ACTIVE` của TÀI LIỆU — không phải dấu duyệt cho từng câu. Còn lại
 * là các nhóm thông số đọc thẳng từ danh mục.
 *
 * **Thiếu dữ liệu là BỎ BỚT.** Không ô rỗng, không chữ giữ chỗ, không `UNKNOWN`.
 * Một nhóm trống còn tệ hơn không có nhóm: khách đọc một tiêu đề rồi không thấy
 * gì bên dưới và tưởng trang lỗi.
 *
 * Mỗi khối là một `region` có nhãn: người dùng trình đọc màn hình nhảy được
 * thẳng tới "An toàn" thay vì nghe hết cả thẻ.
 */
export function VehicleDetailsCard({ details }: { details: VehicleDetails | null | undefined }) {
  if (!details) return null;

  const groups = details.spec_groups.filter((group) => group.rows.length > 0);
  if (groups.length === 0) return null;

  return (
    <section aria-label={`Chi tiết ${details.vehicle_name}`} className="vehicle-details-card">
      <p className="vehicle-details-card__title">{details.vehicle_name}</p>
      {groups.map((group) => (
        <SpecBlock group={group} key={group.title} />
      ))}
    </section>
  );
}

function SpecBlock({ group }: { group: SpecGroup }) {
  return (
    <section aria-label={group.title} className="vehicle-details-card__block">
      <h4>{group.title}</h4>
      <dl>
        {group.rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
