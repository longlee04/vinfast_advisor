"use client";

import { AlertCircle, CarFront, LoaderCircle, MessageCircleMore, SearchX } from "lucide-react";
import Link from "next/link";

import { ProfileChips } from "@/components/recommendations/profile-chips";
import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { recommendations } from "@/mocks/recommendations";
import { useDemoStore } from "@/store/demo-store";

export function RecommendationsView() {
  const { state, setRecommendationPreview } = useDemoStore();
  const preview = state.recommendationPreview;

  if (preview === "loading") return <div className="state-panel"><LoaderCircle className="spin" size={38} /><h1>Đang tải đề xuất đã duyệt</h1><p>Vui lòng chờ trong giây lát.</p><button className="secondary-button" onClick={() => setRecommendationPreview("default")} type="button">Trở lại</button></div>;
  if (preview === "error") return <div className="state-panel"><AlertCircle size={38} /><h1>Không thể hiển thị đề xuất</h1><p>Đã xảy ra lỗi khi tải thông tin. Vui lòng thử lại.</p><button className="primary-button" onClick={() => setRecommendationPreview("default")} type="button">Thử lại</button></div>;
  if (preview === "empty") return <div className="state-panel"><SearchX size={38} /><h1>Chưa tìm thấy lựa chọn phù hợp</h1><p>Hãy điều chỉnh ngân sách hoặc ưu tiên để mở rộng danh sách ứng viên.</p><Link className="primary-button" href="/consultation">Cập nhật nhu cầu</Link></div>;
  if (state.recommendationStatus === "rejected") return <div className="state-panel"><MessageCircleMore size={38} /><h1>Tư vấn viên cần trao đổi thêm</h1><p>Đề xuất tự động chưa đủ căn cứ để gửi. Một tư vấn viên sẽ hỗ trợ bạn trực tiếp.</p><Link className="primary-button" href="/consultation">Tiếp tục trò chuyện</Link></div>;
  if (!(["approved", "edited"] as const).includes(state.recommendationStatus as "approved" | "edited")) return <div className="state-panel"><CarFront size={38} /><h1>Bạn chưa có đề xuất được duyệt</h1><p>Hoàn thành hồ sơ nhu cầu và chờ tư vấn viên kiểm tra trước khi xem kết quả.</p><div><Link className="secondary-button" href="/consultation">Bắt đầu tư vấn</Link></div></div>;

  return (
    <>
      <div className="recommendation-hero"><span className="eyebrow">Đã được tư vấn viên kiểm tra</span><h1>Đề xuất dành cho bạn</h1><p>Ba lựa chọn được xếp hạng theo ngân sách, nhu cầu gia đình và điều kiện sạc.</p><ProfileChips profile={state.needProfile} /></div>
      {state.recommendationStatus === "edited" ? <div className="advisor-edit-note"><strong>Ghi chú của tư vấn viên</strong><p>{state.editedRecommendationText}</p></div> : null}
      <div className="recommendation-list">{recommendations.map((recommendation) => <RecommendationCard key={recommendation.id} recommendation={recommendation} />)}</div>
      <div className="sticky-customer-actions"><span>{state.selectedVehicleIds.length} xe đã chọn</span><div><Link className="secondary-button" href="/compare">So sánh xe</Link><Link className="secondary-button" href="/tco">Ước tính chi phí</Link><Link className="primary-button" href="/test-drive">Đặt lịch lái thử</Link></div></div>
    </>
  );
}
