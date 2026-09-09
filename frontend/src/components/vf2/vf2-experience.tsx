"use client";

import { ChevronLeft, ChevronRight, Mail, Menu, Phone, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf2-experience.module.css";

const featureSlides = [
  ["/media/vinfast/vf2-page/slider-1.webp", "VinFast VF 2 - Ấn tượng ngay từ ánh nhìn đầu tiên"],
  ["/media/vinfast/vf2-page/slider-2.webp", "VinFast VF 2 màu Rose Pink"],
  ["/media/vinfast/vf2-page/slider-3.webp", "VinFast VF 2 - Nhỏ gọn để chinh phục phố thị"],
] as const;

const colorFrames = [
  { name: "Pebble Beige", image: "/media/vinfast/vf2/color-pebble-beige.webp", paint: "#d1b68e" },
  { name: "Infinity Blanc", image: "/media/vinfast/vf2/color-infinity-blanc.webp", paint: "#f7f7f7" },
  { name: "Urban Mint", image: "/media/vinfast/vf2/color-urban-mint.webp", paint: "#91a088" },
  { name: "Rose Pink", image: "/media/vinfast/vf2/color-rose-pink.webp", paint: "#d89aad" },
  { name: "Sky Blue", image: "/media/vinfast/vf2/color-sky-blue.webp", paint: "#19c7bd" },
  { name: "Solar Ruby", image: "/media/vinfast/vf2/color-solar-ruby.webp", paint: "#c91428" },
  { name: "Summer Yellow", image: "/media/vinfast/vf2/color-summer-yellow.webp", paint: "#f1d211" },
  { name: "Desat Silver", image: "/media/vinfast/vf2/color-desat-silver.webp", paint: "#b6bab7" },
] as const;

const INITIAL_COLOR_INDEX = colorFrames.findIndex((color) => color.name === "Solar Ruby");

const specifications = [
  ["Động cơ", "01 Motor"],
  ["Công suất tối đa (kW)", "30"],
  ["Mô men xoắn cực đại (Nm)", "65"],
  ["Quãng đường chạy một lần sạc đầy (km) (NEDC)", "210"],
  ["Thời gian nạp pin nhanh nhất", "34 phút (10% - 70%)"],
  ["Dẫn động", "RWD/Cầu sau"],
] as const;

function VinFastMark({ footer = false }: { footer?: boolean }) {
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

function Vf2Header() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className={styles.header}>
      <VinFastMark />
      <nav className={styles.mainNav} aria-label="Điều hướng chính">
        <a href="#gioi-thieu">Giới thiệu</a>
        <VehicleMegaMenu />
        <a href="#noi-that">Xe máy điện</a>
        <a href="#thong-so">Phụ kiện xe</a>
        <a href="#tram-sac">Dịch vụ hậu mãi</a>
        <a href="#tram-sac">Pin và trạm sạc</a>
        <a href="#tram-sac">Lưu trữ năng lượng</a>
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
          {menuOpen ? <X aria-hidden="true" size={25} /> : <Menu aria-hidden="true" size={25} />}
        </button>
      </div>
      {menuOpen ? (
        <nav className={styles.mobileNav} aria-label="Điều hướng di động">
          <a href="#gioi-thieu" onClick={() => setMenuOpen(false)}>Giới thiệu</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#noi-that" onClick={() => setMenuOpen(false)}>Nội thất</a>
          <a href="#thong-so" onClick={() => setMenuOpen(false)}>Thông số kỹ thuật</a>
          <a href="#tram-sac" onClick={() => setMenuOpen(false)}>Pin và trạm sạc</a>
        </nav>
      ) : null}
    </header>
  );
}

function FeatureStory() {
  const [slideIndex, setSlideIndex] = useState(0);

  function showSlide(nextIndex: number) {
    setSlideIndex((nextIndex + featureSlides.length) % featureSlides.length);
  }

  return (
    <section className={styles.featureStory} id="ngoai-that">
      <p className={styles.storyKicker}>Lên đời bốn bánh, lên cấp trải nghiệm</p>
      <div className={styles.featureGrid}>
        <div className={styles.tallFeature}>
          <Image alt="VinFast VF 2 nhìn từ phía sau" fill sizes="(max-width: 800px) 100vw, 40vw" src="/media/vinfast/vf2-page/feature-row1-left.webp" />
        </div>
        <div className={styles.sliderFeature}>
          <Image alt={featureSlides[slideIndex][1]} fill sizes="(max-width: 800px) 100vw, 58vw" src={featureSlides[slideIndex][0]} />
          <div className={styles.sliderControls}>
            <button aria-label="Ảnh trước" onClick={() => showSlide(slideIndex - 1)} type="button"><ChevronLeft /></button>
            <span>{featureSlides.map((slide, index) => <i className={index === slideIndex ? styles.activeDot : undefined} key={slide[0]} />)}</span>
            <button aria-label="Ảnh tiếp theo" onClick={() => showSlide(slideIndex + 1)} type="button"><ChevronRight /></button>
          </div>
        </div>
        <div className={styles.wideFeature}>
          <Image alt="Không gian bốn chỗ của VinFast VF 2" fill sizes="(max-width: 800px) 100vw, 58vw" src="/media/vinfast/vf2-page/feature-row2-left.webp" />
          <div className={styles.featureCaption}>
            <h3>Nhỏ gọn để chinh phục phố thị</h3>
            <p>Thiết kế tối ưu giúp VF 2 dễ dàng luồn lách trên những tuyến phố đông, quay đầu linh hoạt và đỗ xe gọn gàng ngay cả trong không gian hẹp. Dù là người mới cầm lái hay đã có kinh nghiệm, mỗi hành trình đều trở nên nhẹ nhàng và tự tin hơn.</p>
          </div>
        </div>
        <div className={styles.squareFeature}>
          <Image alt="Khoang lái VinFast VF 2" fill sizes="(max-width: 800px) 100vw, 40vw" src="/media/vinfast/vf2-page/feature-row2-right.webp" />
        </div>
      </div>
    </section>
  );
}

function ColorShowcase() {
  const [colorIndex, setColorIndex] = useState(INITIAL_COLOR_INDEX);
  const activeColor = colorFrames[colorIndex];
  const visibleColors = [-2, -1, 0, 1, 2].map((offset) => {
    const index = (colorIndex + offset + colorFrames.length) % colorFrames.length;
    return { color: colorFrames[index], index };
  });

  function moveColor(direction: -1 | 1): void {
    setColorIndex((current) => (current + direction + colorFrames.length) % colorFrames.length);
  }

  return (
    <section className={styles.colorShowcase} aria-label="Bảng màu VinFast VF 2">
      <picture className={styles.colorBackdrop}>
        <source media="(max-width: 700px)" srcSet="/media/vinfast/vf2-page/color-bg-mobile.webp" />
        <Image alt="" fill sizes="100vw" src="/media/vinfast/vf2-page/color-bg.webp" />
      </picture>
      <div className={styles.colorVehicle}>
        <Image
          alt={`VinFast VF 2 màu ${activeColor.name}`}
          fill
          key={activeColor.image}
          priority
          sizes="(max-width: 700px) 92vw, 64vw"
          src={activeColor.image}
        />
      </div>
      <div className={styles.colorPicker}>
        <button aria-label="Màu trước" className={styles.colorArrow} onClick={() => moveColor(-1)} type="button"><ChevronLeft /></button>
        {visibleColors.map(({ color, index }) => (
          <button
            aria-label={`Xem màu ${color.name}`}
            aria-pressed={index === colorIndex}
            className={index === colorIndex ? styles.hotspotActive : undefined}
            key={color.name}
            onClick={() => setColorIndex(index)}
            style={{ "--paint": color.paint } as React.CSSProperties}
            type="button"
          />
        ))}
        <button aria-label="Màu tiếp theo" className={styles.colorArrow} onClick={() => moveColor(1)} type="button"><ChevronRight /></button>
      </div>
      <strong className={styles.colorName} aria-live="polite">{activeColor.name}</strong>
    </section>
  );
}

function InteriorSection() {
  return (
    <section className={styles.interiorSection} id="noi-that">
      <h2>Chi tiết nội thất</h2>
      <div className={styles.interiorGrid}>
        <div className={styles.interiorMain}><Image alt="VinFast VF 2 - Nội thất bảng điều khiển" fill sizes="(max-width: 800px) 100vw, 50vw" src="/media/vinfast/vf2-page/interior-1.webp" /></div>
        <div className={styles.interiorTop}><Image alt="Sơ đồ bốn chỗ ngồi VinFast VF 2" fill sizes="(max-width: 800px) 100vw, 25vw" src="/media/vinfast/vf2-page/interior-2-1.webp" /></div>
        <div className={styles.interiorRear}><Image alt="Ghế sau VinFast VF 2" fill sizes="(max-width: 800px) 100vw, 25vw" src="/media/vinfast/vf2-page/interior-3.webp" /></div>
      </div>
      <div className={styles.interiorCopy}>
        <div>
          <h3>Tiện nghi vừa đủ cho mọi chuyến đi</h3>
          <p>Không gian được bố trí hợp lý với 4 chỗ ngồi thoải mái cùng khoang lái trực quan, dễ sử dụng. Từ đi học, đi làm đến đưa đón người thân hay vi vu cuối tuần, VF 2 luôn đáp ứng trọn vẹn nhu cầu di chuyển hằng ngày.</p>
        </div>
        <div className={styles.inlineActions}><a className={styles.outlineButton} href="#dang-ky">NHẬN TƯ VẤN</a><Link className={styles.primaryButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link></div>
      </div>
    </section>
  );
}

function FuelComparison() {
  const [distance, setDistance] = useState("3000");
  const [consumption, setConsumption] = useState("8");
  const [fuelType, setFuelType] = useState<"gasoline" | "diesel">("diesel");
  const [freeCharging, setFreeCharging] = useState(false);
  const [result, setResult] = useState<number | null>(null);

  function compareFuelCost() {
    const monthlyDistance = Number(distance.replace(",", "."));
    const fuelConsumption = Number(consumption.replace(",", "."));
    const fuelPrice = fuelType === "gasoline" ? 22_110 : 21_997.5;
    const combustionCost = monthlyDistance / 100 * fuelConsumption * fuelPrice;
    const vf2Cost = freeCharging ? 0 : 0;
    setResult(Math.max(0, Math.round(combustionCost - vf2Cost)));
  }

  return (
    <section className={styles.comparison} id="so-sanh">
      <h2>So sánh giữa xe VinFast VF 2 và xe động cơ đốt trong</h2>
      <div className={styles.comparisonGrid}>
        <form className={styles.calculator} onSubmit={(event) => { event.preventDefault(); compareFuelCost(); }}>
          <label className={styles.switchRow}><input checked={freeCharging} onChange={(event) => setFreeCharging(event.target.checked)} type="checkbox" /><span />Ưu đãi miễn phí sạc xe VinFast từ ngày 10/02/2026(*)</label>
          <label className={styles.fieldRow}><span>Quãng đường di chuyển/tháng (*)</span><span className={styles.inputSuffix}><input aria-label="Quãng đường di chuyển mỗi tháng" inputMode="decimal" onChange={(event) => setDistance(event.target.value)} value={distance} /><b>km</b></span></label>
          <p>Vui lòng nhập thông tin xe động cơ đốt trong cần so sánh:</p>
          <div className={styles.fieldRow}>
            <span>Loại nhiên liệu sử dụng</span>
            <span className={styles.segmented}><button className={fuelType === "gasoline" ? styles.segmentActive : undefined} onClick={() => setFuelType("gasoline")} type="button">Xăng</button><button className={fuelType === "diesel" ? styles.segmentActive : undefined} onClick={() => setFuelType("diesel")} type="button">Dầu</button></span>
          </div>
          <label className={styles.fieldRow}><span>Mức tiêu thụ nhiên liệu/100km (**)</span><span className={styles.inputSuffix}><input aria-label="Mức tiêu thụ nhiên liệu" inputMode="decimal" onChange={(event) => setConsumption(event.target.value)} value={consumption} /><b>lít</b></span></label>
          <small>(*) Thời điểm thay đổi chính sách miễn phí sạc pin của VinFast.<br />(**) Nhập số (phân cách bằng dấu phẩy &quot;,&quot;). Ví dụ: 6,5 lít</small>
          <button className={styles.compareButton} type="submit">SO SÁNH</button>
        </form>
        <div>
          <div className={styles.resultCard}>
            <Image alt="VinFast VF 2" height={150} src="/media/vinfast/vf2-page/comparison-car.png" width={250} />
            <h3>Lợi thế chi phí nhiên liệu của VF 2</h3>
            {result === null ? <p>(*) Chưa có dữ liệu so sánh. Vui lòng nhập thông tin!</p> : <div className={styles.resultValue}><span>Chi phí nhiên liệu tiết kiệm/tháng</span><strong>{new Intl.NumberFormat("vi-VN").format(result)} VNĐ</strong></div>}
          </div>
          <div className={styles.calculatorNote}><p>(*) Lưu ý: Các thông số, đơn giá và giả định sử dụng để tính chi phí nhiên liệu có thể thay đổi. Công cụ trên dựa vào một số thông tin cập nhật sau:</p><ul><li>Giá Xăng E10 RON 95-III Vùng I cập nhật gần nhất: 22.110 VNĐ/lít</li><li>Giá Dầu diesel 0,001S-V Vùng 1 cập nhật gần nhất: 21.997,5 VNĐ/lít</li></ul></div>
        </div>
      </div>
    </section>
  );
}

export function Vf2Experience() {
  return (
    <div className={styles.page}>
      <Vf2Header />
      <main>
        <section className={styles.hero} id="gioi-thieu"><picture><source media="(max-width: 700px)" srcSet="/media/vinfast/vf2-page/hero-bg-mobile.webp" /><Image alt="VinFast VF 2 - Ô tô đầu đời, ước mơ trong tầm với" fill priority sizes="100vw" src="/media/vinfast/vf2-page/hero-bg.webp" /></picture></section>
        <section className={styles.introduction}><div className={styles.introImage}><Image alt="VinFast VF 2 trên phố" fill sizes="30vw" src="/media/vinfast/vf2-page/scroll-highlight.webp" /></div><p><strong>Chiếc ô tô đầu đời,</strong> vừa đủ cho mọi ước mơ.<br />Không cần một chiếc xe quá lớn hay quá đắt tiền<br />để bắt đầu hành trình bốn bánh.</p></section>
        <section className={styles.dreamStatement}><Image alt="VinFast VF 2 trên đường phố" fill sizes="100vw" src="/media/vinfast/vf2-page/section2-city.webp" /><div><span>Ô TÔ ĐẦU ĐỜI</span><strong>ƯỚC MƠ TRONG TẦM VỚI</strong></div></section>
        <FeatureStory />
        <ColorShowcase />
        <section className={styles.priceStory}>
          <h2>Đa sắc màu<br />Đậm cá tính</h2>
          <p>Từ thanh lịch, tối giản đến nổi bật, trẻ trung, bảng màu đa dạng của VF 2 giúp mỗi chủ nhân dễ dàng lựa chọn chiếc xe phù hợp với phong cách của mình. Một chiếc ô tô không chỉ để di chuyển mà còn để thể hiện cá tính.</p>
          <div className={styles.priceBlock}><span>Giá xe kèm pin từ</span><p><strong>178.600.000</strong> VNĐ*</p><del>188.000.000 VNĐ</del><small>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.</small><a className={styles.outlineButton} href="#so-sanh">DỰ TOÁN CHI PHÍ LĂN BÁNH</a><Link className={styles.primaryButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link></div>
        </section>
        <InteriorSection />
        <section className={styles.specifications} id="thong-so"><h2>Thông số kỹ thuật</h2><dl>{specifications.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}</dl><div className={styles.specActions}><a className={styles.outlineButton} href="https://static-cms-prod.vinfastauto.com/" rel="noreferrer" target="_blank">TẢI BROCHURE</a><Link className={styles.primaryButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link></div></section>
        <FuelComparison />
        <section className={styles.charging} id="tram-sac">
          <div><h2>3,5 km - Khoảng cách nhỏ cho mục tiêu lớn</h2><p>Định hình tiên phong thúc đẩy ngành công nghiệp xe điện, hướng tới một tương lai Xanh và Thông Minh, VinFast đã đầu tư hàng trăm triệu USD phát triển hạ tầng, từng bước &quot;phủ rộng&quot; trạm sạc xe điện:</p><ul><li>Hệ thống trạm sạc xe điện VinFast trải dài 34 tỉnh và thành phố.</li><li>106 tuyến quốc lộ quan trọng đều có trạm sạc.</li><li>Khoảng cách ngắn 3,5 km giữa 2 trạm sạc trong thành phố.</li></ul><blockquote>VinFast cam kết nỗ lực mang đến nhiều tiện ích, giúp hành trình lái xe điện của người Việt thật dễ dàng!</blockquote></div>
          <picture><source media="(max-width: 700px)" srcSet="/media/vinfast/vf2-page/charging-mobile.webp" /><Image alt="VinFast VF 2 tại trạm sạc điện" height={540} sizes="(max-width: 800px) 100vw, 48vw" src="/media/vinfast/vf2-page/charging.webp" width={900} /></picture>
        </section>
        <VehicleSupportChoice anchorId="dang-ky" from="/vehicles/vf-2" model="VF 2" />
      </main>
      <footer className={styles.footer}>
        <div className={styles.companyInfo}><VinFastMark footer /><h2>Công ty TNHH Kinh doanh Thương mại và Dịch vụ VinFast</h2><p><strong>MST/MSDN:</strong> 0108926276 do Sở KHĐT TP Hà Nội cấp lần đầu ngày 01/10/2019 và các lần thay đổi tiếp theo.</p><p><strong>Địa chỉ trụ sở chính:</strong> Số 7, Đường Bằng Lăng 1, Khu đô thị Vinhomes Riverside, Phường Phúc Lợi, Thành phố Hà Nội, Việt Nam.</p><p><strong>Người đại diện theo pháp luật:</strong> Nguyễn Mai Hoa.</p><p><strong>Chức vụ:</strong> Chủ tịch Hội đồng thành viên.</p><div className={styles.ecosystem}><strong>Hệ sinh thái</strong><span>Vinhomes</span><span>Vinmec</span><span>Vinpearl</span></div><small>VinFast. All rights reserved.<br />© Copyright 2025</small></div>
        <nav aria-label="Thông tin VinFast"><a href="#gioi-thieu">VỀ VINFAST</a><a href="#gioi-thieu">VỀ VINGROUP</a><a href="#gioi-thieu">TIN TỨC⌄</a><a href="#gioi-thieu">SHOWROOM &amp; ĐẠI LÝ</a><a href="#gioi-thieu">ĐIỀU KHOẢN CHÍNH SÁCH⌄</a></nav>
        <div className={styles.customerService}><h2>DỊCH VỤ KHÁCH HÀNG</h2><a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a><a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a><h2>SPEAK-UP HOTLINE</h2><a href="https://vinfast.ethicspoint.com/"><Phone aria-hidden="true" />https://vinfast.ethicspoint.com/</a><a href="mailto:v.speakup@vinfast.vn"><Mail aria-hidden="true" />v.speakup@vinfast.vn</a><p>Kết nối với VinFast</p></div>
      </footer>
    </div>
  );
}
