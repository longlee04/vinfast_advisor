"use client";

import { Mail, Phone } from "lucide-react";
import Link from "next/link";

import { useEmbedMode } from "@/lib/use-embed-mode";

const footerGroups = [
  { title: "Khám phá", links: [["Ô tô điện", "/vehicles"], ["Xe máy điện", "/vehicles"], ["So sánh xe", "/compare"]] },
  { title: "Dịch vụ", links: [["Đăng ký lái thử", "/test-drive"], ["Showroom & trạm sạc", "/locations"], ["Ước tính chi phí", "/tco"]] },
  { title: "Hỗ trợ", links: [["Tư vấn chọn xe", "/consultation"], ["Lịch sử tư vấn", "/history"], ["Tài khoản", "/account"]] },
] as const;

export function SiteFooter() {
  const embedded = useEmbedMode();
  if (embedded) return null; // trong cửa sổ hội thoại thì trang tự ẩn footer
  return (
    <footer className="vf-footer">
      <div className="vf-footer-main">
        <div className="vf-footer-brand"><strong>VINFAST</strong><p>Trợ lý tư vấn sản phẩm, đồng hành cùng bạn từ lựa chọn đầu tiên đến lịch trải nghiệm.</p><div><a href="tel:1900232389"><Phone size={16} />1900 23 23 89</a><a href="mailto:support.vn@vinfastauto.com"><Mail size={16} />support.vn@vinfastauto.com</a></div></div>
        {footerGroups.map((group) => <div className="vf-footer-group" key={group.title}><h2>{group.title}</h2>{group.links.map(([label, href]) => <Link href={href} key={label}>{label}</Link>)}</div>)}
      </div>
      <div className="vf-footer-bottom"><span>© 2026 VinFast AI Sales Advisor demo</span><div><a href="https://www.facebook.com/VinFastAuto.Official">Facebook</a><a href="https://www.instagram.com/vinfastofficial">Instagram</a></div></div>
    </footer>
  );
}
