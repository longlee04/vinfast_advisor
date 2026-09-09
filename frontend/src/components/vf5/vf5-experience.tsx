"use client";

import { ChevronLeft, ChevronRight, Mail, Menu, Phone, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf5-experience.module.css";

const featureSlides = [
  ["/media/vinfast/vf5/feature-01.webp", "VinFast VF 5 đồng hành hàng ngày"],
  ["/media/vinfast/vf5/feature-02.webp", "VinFast VF 5 Solar Ruby"],
  ["/media/vinfast/vf5/feature-03.webp", "Không gian gia đình trên VinFast VF 5"],
  ["/media/vinfast/vf5/feature-04.webp", "VinFast VF 5 nhìn từ trên cao"],
  ["/media/vinfast/vf5/feature-05.webp", "Khoang hành lý VinFast VF 5"],
  ["/media/vinfast/vf5/feature-06.webp", "Gia đình trên VinFast VF 5"],
  ["/media/vinfast/vf5/feature-07.webp", "VinFast VF 5 trên đường phố"],
  ["/media/vinfast/vf5/feature-08.webp", "VinFast VF 5 Solar Ruby nhìn từ trên cao"],
  ["/media/vinfast/vf5/feature-09.webp", "VinFast VF 5 và gia đình"],
] as const;

const colorFrames = [
  { name: "Zenith Grey", image: "/media/vinfast/vf5/color-zenith-grey.webp", paint: "#8b9295" },
  { name: "Infinity Blanc", image: "/media/vinfast/vf5/color-infinity-blanc.webp", paint: "#f5f5f2" },
  { name: "Solar Ruby", image: "/media/vinfast/vf5/color-solar-ruby.webp", paint: "#d8123d" },
  { name: "Summer Yellow Body - Jet Black Roof", image: "/media/vinfast/vf5/color-summer-yellow.webp", paint: "linear-gradient(145deg, #26272a 0 45%, #f3c91c 46%)" },
] as const;

const interiorSlides = [
  ["/media/vinfast/vf5/interior-01.webp", "Khoang lái VinFast VF 5"],
  ["/media/vinfast/vf5/interior-02.webp", "Vô lăng VinFast VF 5"],
  ["/media/vinfast/vf5/interior-03.webp", "Ghế trước VinFast VF 5"],
  ["/media/vinfast/vf5/interior-04.webp", "Núm chuyển số VinFast VF 5"],
  ["/media/vinfast/vf5/interior-05.webp", "Cổng kết nối VinFast VF 5"],
  ["/media/vinfast/vf5/interior-06.webp", "Khoang hành lý VinFast VF 5"],
] as const;

const specifications = [
  ["Dài x rộng x Cao (mm)", "3.967 x 1.723 x 1.579"],
  ["Dung lượng pin khả dụng", "37,23 Kwh"],
  ["Loại la-zăng", "Hợp kim 17 inch"],
  ["Mức tiêu thụ nhiên liệu công khai", "13 kWh/100 km"],
  ["Số ghế ngồi", "5 ghế"],
  ["Thời gian nạp pin nhanh nhất (10%-70%)", "33 phút"],
  ["Túi khí", "6 túi khí"],
] as const;

function VinFastMark({ footer = false }: Readonly<{ footer?: boolean }>) {
  return (
    <Link className={footer ? styles.footerBrand : styles.brand} href="/" aria-label="VinFast - Trang chủ">
      <Image
        alt="VinFast"
        height={58}
        priority={!footer}
        src="/media/vinfast/vf2-page/vinfast-logo.webp"
        style={{ width: "auto", height: "auto" }}
        width={290}
      />
    </Link>
  );
}

function GlobalHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className={styles.header}>
      <VinFastMark />
      <nav className={styles.mainNav} aria-label="Điều hướng chính">
        <a href="#gioi-thieu">Giới thiệu</a>
        <VehicleMegaMenu />
        <Link href="/motorbikes">Xe máy điện</Link>
        <a href="#ngoai-that">Phụ kiện xe</a>
        <a href="#gia-ban">Dịch vụ hậu mãi</a>
        <a href="#thong-so">Pin và trạm sạc</a>
        <a href="#thong-so">Lưu trữ năng lượng</a>
      </nav>
      <div className={styles.headerActions}>
        <Link className={styles.account} href="/account">TÀI KHOẢN</Link>
        <Link className={styles.testDrive} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        <button aria-expanded={menuOpen} aria-label={menuOpen ? "Đóng menu" : "Mở menu"} className={styles.menuButton} onClick={() => setMenuOpen((open) => !open)} type="button">
          {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </div>
      {menuOpen ? (
        <nav className={styles.mobileNav} aria-label="Điều hướng di động">
          <a href="#gioi-thieu" onClick={() => setMenuOpen(false)}>Giới thiệu</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#mau-sac" onClick={() => setMenuOpen(false)}>Màu sắc</a>
          <a href="#noi-that" onClick={() => setMenuOpen(false)}>Nội thất</a>
          <a href="#thong-so" onClick={() => setMenuOpen(false)}>Thông số</a>
        </nav>
      ) : null}
    </header>
  );
}

function ModelNavigation() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const updateVisibility = () => setVisible(window.scrollY > 90);
    updateVisibility();
    window.addEventListener("scroll", updateVisibility, { passive: true });
    return () => window.removeEventListener("scroll", updateVisibility);
  }, []);

  if (!visible) return null;

  return (
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 5">
      <a className={styles.modelLogo} href="#dau-trang" aria-label="Về đầu trang VF 5"><Image alt="VF 5" height={29} src="/media/vinfast/vf5/vf5-logo.svg" width={109} /></a>
      <div className={styles.modelLinks}>
        <a href="#gioi-thieu">GIỚI THIỆU</a>
        <a href="#mau-sac">MÀU SẮC</a>
        <a href="#ngoai-that">NGOẠI THẤT</a>
        <a href="#noi-that">NỘI THẤT</a>
        <a href="#thong-so">THÔNG SỐ</a>
        <a href="#gia-ban">GIÁ BÁN</a>
      </div>
      <Link className={styles.consultButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function FeatureCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);
  const previous = (activeIndex - 1 + featureSlides.length) % featureSlides.length;
  const next = (activeIndex + 1) % featureSlides.length;

  return (
    <section className={styles.features} id="gioi-thieu">
      <h2>Cá nhân vượt trội</h2>
      <p>Đồng hành hàng ngày</p>
      <div className={styles.featureTrack}>
        {[previous, activeIndex, next].map((slideIndex, position) => (
          <button className={position === 1 ? styles.featureActive : styles.featureSide} key={`${slideIndex}-${position}`} onClick={() => setActiveIndex(slideIndex)} type="button">
            <Image alt={featureSlides[slideIndex][1]} fill sizes="(max-width: 720px) 78vw, 34vw" src={featureSlides[slideIndex][0]} />
          </button>
        ))}
      </div>
      <div className={styles.dots} aria-label="Chọn ảnh giới thiệu">
        {featureSlides.map((slide, index) => <button aria-label={`Xem ảnh ${index + 1}`} aria-pressed={index === activeIndex} className={index === activeIndex ? styles.dotActive : undefined} key={slide[0]} onClick={() => setActiveIndex(index)} type="button" />)}
      </div>
    </section>
  );
}

function ColorShowcase() {
  const [colorIndex, setColorIndex] = useState(0);
  const activeColor = colorFrames[colorIndex];

  return (
    <section className={styles.colorSection} id="mau-sac">
      <div className={styles.colorPanel} id="ngoai-that">
        <span className={styles.watermark}>VF5</span>
        <div className={styles.colorVehicle}>
          <Image alt={`VinFast VF 5 màu ${activeColor.name}`} fill key={activeColor.image} priority sizes="(max-width: 720px) 100vw, 54vw" src={activeColor.image} />
          <strong aria-live="polite">{activeColor.name}</strong>
        </div>
        <div className={styles.colorCopy}>
          <h2>Ngoại thất ấn tượng</h2>
          <p>Phong cách trẻ trung, năng động, cá tính.</p>
          <div className={styles.colorControls} aria-label="Bảng màu VinFast VF 5">
            {colorFrames.map((color, index) => (
              <button aria-label={`Xem màu ${color.name}`} aria-pressed={index === colorIndex} className={index === colorIndex ? styles.colorActive : undefined} key={color.name} onClick={() => setColorIndex(index)} style={{ "--paint": color.paint } as CSSProperties} type="button" />
            ))}
            <span>Chọn màu chi tiết tại đây</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function InteriorCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + interiorSlides.length) % interiorSlides.length);
  }

  return (
    <section className={styles.interior} id="noi-that">
      <div className={styles.sectionHeading}>
        <h2>Nội thất tinh tế</h2>
        <p>Không gian rộng rãi, phối màu sành điệu, cuốn hút với các đường viền bắt mắt.</p>
      </div>
      <div className={styles.interiorStage}>
        <Image alt={interiorSlides[activeIndex][1]} fill key={interiorSlides[activeIndex][0]} sizes="100vw" src={interiorSlides[activeIndex][0]} />
        <button aria-label="Ảnh nội thất trước" className={styles.sliderPrevious} onClick={() => move(-1)} type="button"><ChevronLeft /></button>
        <button aria-label="Ảnh nội thất tiếp theo" className={styles.sliderNext} onClick={() => move(1)} type="button"><ChevronRight /></button>
        <div className={styles.interiorDots}>{interiorSlides.map((slide, index) => <button aria-label={`Xem nội thất ${index + 1}`} aria-pressed={index === activeIndex} className={index === activeIndex ? styles.dotActive : undefined} key={slide[0]} onClick={() => setActiveIndex(index)} type="button" />)}</div>
      </div>
    </section>
  );
}

function Specifications() {
  return (
    <section className={styles.specifications} id="thong-so">
      <div className={styles.container}>
        <h2>Thông số kỹ thuật</h2>
        <dl>{specifications.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}</dl>
        <div className={styles.specCopy}>
          <p>VF 5 Plus sở hữu thiết kế hiện đại, trẻ trung, cá tính và nổi bật với các lựa chọn phối màu nội ngoại thất, đảm bảo cá nhân hóa theo phong cách sống, cá tính và sở thích của mỗi khách hàng.</p>
          <div><p>VinFast VF 5 Plus được trang bị đầy đủ những công nghệ tiên tiến bậc nhất:</p><ul><li>Giám sát hành trình cơ bản</li><li>Cảnh báo giao thông phía sau</li><li>Cảnh báo điểm mù</li><li>Hỗ trợ đỗ xe phía sau</li><li>Hỗ trợ phanh khẩn cấp</li></ul></div>
          <div><p>Tích hợp các ứng dụng, tiện ích thông minh như:</p><ul><li>Trợ lý ảo điều khiển bằng giọng nói</li><li>Mua sắm trực tuyến trên xe</li><li>Điều khiển các thiết bị smart home</li></ul><p>Giúp nâng tầm trải nghiệm và kiến tạo một phong cách sống đẳng cấp, văn minh, hiện đại.</p></div>
        </div>
        <div className={styles.specActions}><a href="https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwf5eb40b2/Document/VF5_Brochure_T82025.pdf" rel="noreferrer" target="_blank">TẢI BROCHURE</a><Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link></div>
      </div>
    </section>
  );
}

function PriceSection({ onConsult }: Readonly<{ onConsult: () => void }>) {
  return (
    <section className={styles.priceSection} id="gia-ban">
      <div className={styles.priceCards}>
        <article><h2>Giá bán VF 5</h2><strong>471.200.000 VNĐ*</strong><del>496.000.000 VNĐ</del><small>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.</small></article>
        <article><h3>Bảo hành bảo dưỡng</h3><a href="#thong-so">CHÍNH SÁCH BẢO HÀNH</a><p>Bảo hành xe mới: 7 năm/160.000 km. Pin cao áp (Mua lần đầu theo xe mới): 8 năm/160.000 km.</p></article>
        <button aria-label="Nhận báo giá và ưu đãi" onClick={onConsult} type="button">NHẬN BÁO GIÁ VÀ ƯU ĐÃI</button>
      </div>
    </section>
  );
}

function ConsultationDialog({ onClose }: Readonly<{ onClose: () => void }>) {
  return (
    <div className={styles.dialogBackdrop}>
      <section aria-labelledby="vf5-dialog-title" aria-modal="true" className={styles.dialog} role="dialog">
        <button aria-label="Đóng biểu mẫu tư vấn" className={styles.dialogClose} onClick={onClose} type="button"><X /></button>
        <h2 id="vf5-dialog-title">NHẬN BÁO GIÁ &amp; ƯU ĐÃI MỚI NHẤT</h2>
        <p>Đăng ký ngay, VinFast sẽ liên hệ tư vấn trong thời gian sớm nhất</p>
        <form><input aria-label="Họ và tên trong hộp tư vấn" placeholder="Họ và tên *" /><input aria-label="Số điện thoại trong hộp tư vấn" placeholder="Số điện thoại *" type="tel" /><input aria-label="Email trong hộp tư vấn" placeholder="Email *" type="email" /><select aria-label="Thời gian dự kiến mua xe" defaultValue=""><option disabled value="">Thời gian dự kiến mua xe</option><option>Trong 1 tháng</option><option>Trong 3 tháng</option></select><textarea aria-label="Nội dung cần hỗ trợ" placeholder="Quý khách cần hỗ trợ thêm thông tin gì?" /><label><input defaultChecked type="checkbox" /> Tôi đồng ý cho phép VinFast xử lý dữ liệu cá nhân.</label><button type="submit">ĐĂNG KÝ</button></form>
      </section>
    </div>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div><VinFastMark footer /><p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p><small>VinFast. All rights reserved.</small></div>
      <nav aria-label="Thông tin VinFast"><a href="#gioi-thieu">VỀ VINFAST</a><a href="#thong-so">SHOWROOM VÀ ĐẠI LÝ</a><a href="#gia-ban">ĐIỀU KHOẢN CHÍNH SÁCH</a></nav>
      <div><a href="tel:1900232389"><Phone />1900 23 23 89 - Nhánh 1</a><a href="mailto:support.vn@vinfastauto.com"><Mail />support.vn@vinfastauto.com</a></div>
    </footer>
  );
}

export function Vf5Experience() {
  const [consultOpen, setConsultOpen] = useState(false);

  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <section className={styles.hero}><picture><source media="(max-width: 620px)" srcSet="/media/vinfast/vf5/campaign-hero-mobile.webp" /><Image alt="VinFast VF 5 - Cá nhân vượt trội" fill priority sizes="100vw" src="/media/vinfast/vf5/campaign-hero.webp" /></picture></section>
        <FeatureCarousel />
        <ColorShowcase />
        <InteriorCarousel />
        <Specifications />
        <PriceSection onConsult={() => setConsultOpen(true)} />
        <VehicleSupportChoice anchorId="ho-tro-vf5" from="/vehicles/vf-5" model="VF 5" />
      </main>
      <Footer />
      {consultOpen ? <ConsultationDialog onClose={() => setConsultOpen(false)} /> : null}
    </div>
  );
}
