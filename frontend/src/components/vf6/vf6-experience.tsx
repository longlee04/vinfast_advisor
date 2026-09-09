"use client";

import { ChevronDown, ChevronLeft, ChevronRight, Mail, Menu, Phone, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf6-experience.module.css";

type Slide = Readonly<{
  alt: string;
  image: string;
}>;

const exteriorSlides: readonly Slide[] = [
  { image: "/media/vinfast/vf6/exterior-1.webp", alt: "Ngoại thất VinFast VF 6 nhìn từ phía trước" },
  { image: "/media/vinfast/vf6/exterior-2.webp", alt: "Ngoại thất VinFast VF 6 nhìn từ phía sau" },
  { image: "/media/vinfast/vf6/exterior-3.webp", alt: "Đèn và đường nét ngoại thất VinFast VF 6" },
];

const interiorSlides: readonly Slide[] = [
  { image: "/media/vinfast/vf6/interior-1.webp", alt: "Khoang lái VinFast VF 6" },
  { image: "/media/vinfast/vf6/interior-2.webp", alt: "Hàng ghế VinFast VF 6" },
];

const technologySlides: readonly Slide[] = [
  { image: "/media/vinfast/vf6/technology-1.webp", alt: "Màn hình giải trí VinFast VF 6" },
  { image: "/media/vinfast/vf6/technology-2.webp", alt: "Tiện nghi công nghệ VinFast VF 6" },
];

const gallerySlides: readonly Slide[] = [
  { image: "/media/vinfast/vf6/gallery-1.webp", alt: "VinFast VF 6 trên cung đường ven núi" },
  { image: "/media/vinfast/vf6/gallery-2.webp", alt: "VinFast VF 6 giữa thiên nhiên" },
  { image: "/media/vinfast/vf6/gallery-3.webp", alt: "VinFast VF 6 đồng hành cùng gia đình" },
  { image: "/media/vinfast/vf6/gallery-4.webp", alt: "VinFast VF 6 trên hành trình mới" },
];

const specificationRows = [
  ["Dài x Rộng x Cao", "4.241 x 1.834 x 1.580 mm", "4.241 x 1.834 x 1.580 mm"],
  ["Chiều dài cơ sở", "2.730 mm", "2.730 mm"],
  ["Quãng đường di chuyển (NEDC)", "485 km", "460 km"],
  ["Công suất tối đa", "130 kW / 174 hp", "150 kW / 201 hp"],
  ["Mô-men xoắn cực đại", "250 Nm", "310 Nm"],
  ["Dung lượng pin khả dụng", "59,6 kWh", "59,6 kWh"],
  ["Hệ dẫn động", "FWD / Cầu trước", "FWD / Cầu trước"],
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
        <a href="#thiet-ke">Phụ kiện xe</a>
        <a href="#gia-ban">Dịch vụ hậu mãi</a>
        <a href="#thong-so">Pin và trạm sạc</a>
        <a href="#thong-so">Lưu trữ năng lượng</a>
      </nav>
      <div className={styles.headerActions}>
        <Link className={styles.account} href="/account">TÀI KHOẢN</Link>
        <Link className={styles.testDrive} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        <button
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Đóng menu" : "Mở menu"}
          className={styles.menuButton}
          onClick={() => setMenuOpen((open) => !open)}
          type="button"
        >
          {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </div>
      {menuOpen ? (
        <nav className={styles.mobileNav} aria-label="Điều hướng di động">
          <a href="#gioi-thieu" onClick={() => setMenuOpen(false)}>Giới thiệu</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#gia-ban" onClick={() => setMenuOpen(false)}>Giá bán</a>
          <a href="#thiet-ke" onClick={() => setMenuOpen(false)}>Thiết kế</a>
          <a href="#thong-so" onClick={() => setMenuOpen(false)}>Thông số</a>
          <a href="#hinh-anh" onClick={() => setMenuOpen(false)}>Hình ảnh</a>
        </nav>
      ) : null}
    </header>
  );
}

function ModelNavigation() {
  return (
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 6">
      <a className={styles.modelLogo} href="#dau-trang" aria-label="Về đầu trang VF 6">
        <Image alt="VF 6" height={24} priority src="/media/vinfast/vf6/logo.webp" width={128} />
      </a>
      <div className={styles.modelLinks}>
        <a href="#gia-ban">GIÁ BÁN</a>
        <a href="#thiet-ke">THIẾT KẾ</a>
        <a href="#thong-so">THÔNG SỐ</a>
        <a href="#hinh-anh">HÌNH ẢNH</a>
      </div>
      <Link className={styles.modelAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function Highlights() {
  return (
    <section className={styles.highlights} aria-label="Thông số nổi bật của VF 6">
      <div><strong>59,6 kW</strong><span>Dung lượng pin</span></div>
      <div><strong>485 km/lần sạc</strong><span>Quãng đường di chuyển (NEDC)</span></div>
      <div><strong>150 kW/201 hp</strong><span>Công suất tối đa (VF 6 Plus)</span></div>
      <div><strong>310 Nm</strong><span>Mô-men xoắn cực đại (VF 6 Plus)</span></div>
      <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </section>
  );
}

function PriceSection() {
  return (
    <section className={styles.priceSection} id="gia-ban">
      <picture className={styles.pricePicture}>
        <source media="(max-width: 620px)" srcSet="/media/vinfast/vf6/price-mobile.webp" />
        <Image alt="Khoang nội thất VinFast VF 6" fill sizes="100vw" src="/media/vinfast/vf6/price.webp" />
      </picture>
      <div className={styles.priceCard}>
        <p>Giá niêm yết</p>
        <div className={styles.priceVersions}>
          <article>
            <h2>VF 6 Eco</h2>
            <strong>613.700.000 VNĐ*</strong>
            <del>646.000.000 VNĐ</del>
          </article>
          <article>
            <h2>VF 6 Plus</h2>
            <strong>664.050.000 VNĐ*</strong>
            <del>699.000.000 VNĐ</del>
          </article>
        </div>
        <small>
          (*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản
          và điều kiện tại từng thời điểm.
        </small>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      </div>
    </section>
  );
}

function ImageCarousel({
  controlName,
  slides,
}: Readonly<{
  controlName: string;
  slides: readonly Slide[];
}>) {
  const [activeIndex, setActiveIndex] = useState(0);

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + slides.length) % slides.length);
  }

  const activeSlide = slides[activeIndex];

  return (
    <div className={styles.overviewCarousel}>
      <Image
        alt={activeSlide.alt}
        fill
        key={activeSlide.image}
        sizes="(max-width: 900px) 100vw, 58vw"
        src={activeSlide.image}
      />
      <button
        aria-label={`${controlName} trước`}
        className={styles.previous}
        onClick={() => move(-1)}
        type="button"
      >
        <ChevronLeft aria-hidden="true" />
      </button>
      <button
        aria-label={`${controlName} tiếp theo`}
        className={styles.next}
        onClick={() => move(1)}
        type="button"
      >
        <ChevronRight aria-hidden="true" />
      </button>
      <div className={styles.imageDots} aria-label={`Chọn ảnh ${controlName.toLowerCase()}`}>
        {slides.map((slide, index) => (
          <button
            aria-label={`${controlName} ${index + 1}`}
            aria-pressed={index === activeIndex}
            className={index === activeIndex ? styles.dotActive : undefined}
            key={slide.image}
            onClick={() => setActiveIndex(index)}
            type="button"
          />
        ))}
      </div>
    </div>
  );
}

function DesignOverview() {
  return (
    <section className={styles.design} id="thiet-ke">
      <div className={styles.sectionIntro}>
        <span>THIẾT KẾ</span>
        <h2>Triết lý thiết kế “Cặp đối lập tự nhiên”</h2>
        <p>
          VF 6 được chấp bút bởi Torino Design, lấy cảm hứng từ sự tương phản giữa những
          đường nét mềm mại và các mảng khối mạnh mẽ, tạo nên một diện mạo khác biệt đầy cuốn hút.
        </p>
      </div>

      <article className={`${styles.designRow} ${styles.exteriorRow}`}>
        <ImageCarousel controlName="Ngoại thất" slides={exteriorSlides} />
        <div className={styles.designCopy}>
          <span>01</span>
          <h3>Ngoại thất</h3>
          <p>
            Dải đèn LED hình cánh chim đặc trưng, thân xe khỏe khoắn cùng những đường cong
            liền mạch giúp VF 6 nổi bật trên mọi cung đường.
          </p>
        </div>
      </article>

      <article className={`${styles.designRow} ${styles.reverseRow}`}>
        <ImageCarousel controlName="Nội thất" slides={interiorSlides} />
        <div className={styles.designCopy}>
          <span>02</span>
          <h3>Nội thất</h3>
          <p>
            Khoang nội thất rộng rãi, tối ưu công thái học và được hoàn thiện với những chi tiết
            tinh tế để mỗi hành trình luôn thoải mái.
          </p>
        </div>
      </article>

      <article className={styles.designRow}>
        <ImageCarousel controlName="Công nghệ" slides={technologySlides} />
        <div className={styles.designCopy}>
          <span>03</span>
          <h3>Công nghệ</h3>
          <p>
            Màn hình trung tâm 12,9 inch cùng hệ thống hỗ trợ lái thông minh mang đến trải nghiệm
            kết nối trực quan, tiện nghi và an tâm.
          </p>
        </div>
      </article>
    </section>
  );
}

function Specifications() {
  return (
    <section className={styles.specifications} id="thong-so">
      <div className={styles.specHeader}>
        <Image alt="VF 6" height={184} src="/media/vinfast/vf6/performance-logo.webp" width={685} />
        <div>
          <span>VẬN HÀNH</span>
          <h2>Khả năng vận hành vượt trội</h2>
          <p>
            VF 6 mang lại cảm giác lái mạnh mẽ, linh hoạt và êm ái trong đô thị với hai phiên bản
            Eco và Plus phù hợp cho từng nhu cầu sử dụng.
          </p>
        </div>
      </div>
      <div className={styles.specTableWrap}>
        <table>
          <thead>
            <tr><th>Thông số</th><th>VF 6 Eco</th><th>VF 6 Plus</th></tr>
          </thead>
          <tbody>
            {specificationRows.map(([name, eco, plus]) => (
              <tr key={name}><th>{name}</th><td>{eco}</td><td>{plus}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.specActions}>
        <a
          href="https://storage.googleapis.com/vinfast-data-01/brochure/14052026/VF%206_Brochure_Final_130526%20(12AM)_compressed.pdf"
          rel="noreferrer"
          target="_blank"
        >
          TẢI BROCHURE
        </a>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      </div>
    </section>
  );
}

const formatCurrency = new Intl.NumberFormat("vi-VN");

function FuelComparison() {
  const [consumption, setConsumption] = useState("7.5");
  const [distance, setDistance] = useState("1200");
  const [fuel, setFuel] = useState("petrol");
  const [calculation, setCalculation] = useState({ consumption: 7.5, distance: 1200, fuel: "petrol" });

  const fuelPrice = calculation.fuel === "diesel" ? 27130 : 22060;
  const monthlyCost = useMemo(
    () => Math.round((calculation.distance / 100) * calculation.consumption * fuelPrice),
    [calculation, fuelPrice],
  );

  function calculate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCalculation({
      consumption: Math.max(0, Number(consumption) || 0),
      distance: Math.max(0, Number(distance) || 0),
      fuel,
    });
  }

  return (
    <section className={styles.comparison}>
      <div className={styles.comparisonIntro}>
        <span>CHI PHÍ SỬ DỤNG</span>
        <h2>Tiết kiệm hơn mỗi ngày</h2>
        <p>
          Ước tính nhanh chi phí nhiên liệu của một mẫu xe xăng hoặc dầu có mức sử dụng tương đương.
        </p>
        <div className={styles.comparisonVisual}>
          <Image alt="Nhiên liệu hóa thạch" height={56} src="/media/vinfast/vf6/comparison-logo.webp" width={56} />
          <span>so với</span>
          <Image alt="VinFast VF 6" height={174} src="/media/vinfast/vf6/comparison-car.webp" width={318} />
        </div>
      </div>
      <form className={styles.comparisonForm} onSubmit={calculate}>
        <label>
          Loại nhiên liệu
          <span className={styles.selectWrap}>
            <select aria-label="Loại nhiên liệu" onChange={(event) => setFuel(event.target.value)} value={fuel}>
              <option value="petrol">Xăng RON 95</option>
              <option value="diesel">Dầu Diesel</option>
            </select>
            <ChevronDown aria-hidden="true" />
          </span>
        </label>
        <label>
          Mức tiêu thụ nhiên liệu
          <span className={styles.inputWithUnit}>
            <input
              aria-label="Mức tiêu thụ nhiên liệu"
              inputMode="decimal"
              min="0"
              onChange={(event) => setConsumption(event.target.value)}
              step="0.1"
              type="number"
              value={consumption}
            />
            <span>lít/100 km</span>
          </span>
        </label>
        <label>
          Quãng đường mỗi tháng
          <span className={styles.inputWithUnit}>
            <input
              aria-label="Quãng đường mỗi tháng"
              inputMode="numeric"
              min="0"
              onChange={(event) => setDistance(event.target.value)}
              step="1"
              type="number"
              value={distance}
            />
            <span>km</span>
          </span>
        </label>
        <button type="submit">TÍNH CHI PHÍ</button>
        <div className={styles.comparisonResult} aria-live="polite">
          <span>Chi phí nhiên liệu ước tính</span>
          <strong>{formatCurrency.format(monthlyCost)} VNĐ/tháng</strong>
          <small>{formatCurrency.format(monthlyCost * 12)} VNĐ/năm</small>
        </div>
      </form>
    </section>
  );
}

function Gallery() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = gallerySlides[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + gallerySlides.length) % gallerySlides.length);
  }

  return (
    <section className={styles.gallery} id="hinh-anh">
      <div className={styles.galleryHeading}>
        <span>KHÁM PHÁ VF 6</span>
        <h2>Cùng VF 6 ghi dấu từng khoảnh khắc,<br />khởi đầu mọi hành trình.</h2>
      </div>
      <div className={styles.galleryStage}>
        <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="100vw" src={activeSlide.image} />
        <button aria-label="Ảnh trước" className={styles.previous} onClick={() => move(-1)} type="button">
          <ChevronLeft aria-hidden="true" />
        </button>
        <button aria-label="Ảnh tiếp theo" className={styles.next} onClick={() => move(1)} type="button">
          <ChevronRight aria-hidden="true" />
        </button>
        <div className={styles.galleryCounter}><strong>0{activeIndex + 1}</strong><span>/ 0{gallerySlides.length}</span></div>
      </div>
      <div className={styles.galleryDots} aria-label="Chọn ảnh VF 6">
        {gallerySlides.map((slide, index) => (
          <button
            aria-label={`Xem ảnh VF 6 ${index + 1}`}
            aria-pressed={index === activeIndex}
            className={index === activeIndex ? styles.dotActive : undefined}
            key={slide.image}
            onClick={() => setActiveIndex(index)}
            type="button"
          />
        ))}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div>
        <VinFastMark footer />
        <p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p>
        <small>VinFast. All rights reserved.</small>
      </div>
      <nav aria-label="Thông tin VinFast">
        <a href="#gioi-thieu">VỀ VINFAST</a>
        <a href="#thong-so">SHOWROOM VÀ ĐẠI LÝ</a>
        <a href="#gia-ban">ĐIỀU KHOẢN CHÍNH SÁCH</a>
      </nav>
      <div>
        <a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a>
        <a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a>
      </div>
    </footer>
  );
}

export function Vf6Experience() {
  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <section className={styles.hero} id="gioi-thieu">
          <picture>
            <source media="(max-width: 620px)" srcSet="/media/vinfast/vf6/hero-mobile.webp" />
            <Image
              alt="VinFast VF 6 - Cùng bạn ghi dấu từng khoảnh khắc"
              fill
              priority
              sizes="100vw"
              src="/media/vinfast/vf6/hero.webp"
            />
          </picture>
        </section>
        <Highlights />
        <PriceSection />
        <section className={styles.lifestyle}>
          <div>
            <span>VF 6</span>
            <h2>Cùng VF 6 ghi dấu từng khoảnh khắc,<br />khởi đầu mọi hành trình.</h2>
          </div>
          <Image alt="VinFast VF 6 trên cung đường núi" fill sizes="100vw" src="/media/vinfast/vf6/lifestyle-00.webp" />
        </section>
        <DesignOverview />
        <Specifications />
        <FuelComparison />
        <Gallery />
        <VehicleSupportChoice anchorId="ho-tro-vf6" from="/vehicles/vf-6" model="VF 6" />
      </main>
      <Footer />
    </div>
  );
}
