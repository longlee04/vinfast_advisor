import Image from "next/image";
import Link from "next/link";

import styles from "@/components/home/home-shell.module.css";

export function HomeFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerMain}>
        <div className={styles.footerCompany}>
          <Image alt="VinFast" height={31} src="/media/vinfast/home/footer-logo.webp" width={154} />
          <h2>Công ty TNHH Kinh doanh Thương mại và Dịch vụ VinFast</h2>
          <p><strong>MST/MSDN:</strong> 0108926276 do Sở KHĐT TP Hà Nội cấp lần đầu ngày 01/10/2019 và các lần thay đổi tiếp theo.</p>
          <p><strong>Địa chỉ trụ sở chính:</strong> Số 7, Đường Bằng Lăng 1, Khu đô thị Vinhomes Riverside, Phường Phúc Lợi, Thành phố Hà Nội, Việt Nam.</p>
          <p><strong>Người đại diện theo pháp luật:</strong> Nguyễn Mai Hoa. <strong>Chức vụ:</strong> Chủ tịch Hội đồng thành viên.</p>
        </div>

        <div className={styles.footerLinks}>
          <Link href="/#green-future">VỀ VINFAST</Link>
          <a href="https://vingroup.net/">VỀ VINGROUP</a>
          <Link href="/consultation">TIN TỨC</Link>
          <Link href="/vehicles">Công ty</Link>
          <Link href="/vehicles">Ô tô điện</Link>
          <Link href="/motorbikes">Xe máy điện</Link>
          <Link href="/locations">SHOWROOM &amp; ĐẠI LÝ</Link>
          <strong>ĐIỀU KHOẢN CHÍNH SÁCH</strong>
          <Link href="/account">Chính sách bảo vệ dữ liệu cá nhân</Link>
          <Link href="/account">Chính sách vận chuyển</Link>
          <Link href="/account">Chính sách đổi trả</Link>
          <Link href="/account">Miễn trừ trách nhiệm</Link>
        </div>

        <div className={styles.footerContact}>
          <h2>DỊCH VỤ KHÁCH HÀNG</h2>
          <a href="tel:1900232389">1900 23 23 89 - Nhánh 1</a>
          <a href="mailto:support.vn@vinfastauto.com">support.vn@vinfastauto.com</a>
          <h2>SPEAK-UP HOTLINE</h2>
          <a href="https://vinfast.ethicspoint.com/">vinfast.ethicspoint.com</a>
          <a href="mailto:v.speakup@vinfast.vn">v.speakup@vinfast.vn</a>
          <h2>Kết nối với VinFast</h2>
          <div className={styles.socialLinks}>
            <a href="https://www.facebook.com/VinFastAuto.Official">Facebook</a>
            <a href="https://www.youtube.com/@VinFastOfficial">YouTube</a>
            <a href="https://www.instagram.com/vinfastofficial">Instagram</a>
          </div>
        </div>
      </div>

      <div className={styles.footerBottom}>
        <div><strong>Hệ sinh thái</strong><a href="https://vinhomes.vn/">Vinhomes</a><a href="https://www.vinmec.com/">Vinmec</a><a href="https://vinpearl.com/">Vinpearl</a></div>
        <span>VinFast. All rights reserved. © Copyright 2025</span>
      </div>
    </footer>
  );
}
