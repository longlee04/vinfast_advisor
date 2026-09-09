"use client";

import {
  ChevronLeft,
  ChevronRight,
  Mail,
  Menu,
  Phone,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState, type CSSProperties, type FormEvent } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf8-experience.module.css";

const colors = [
  { name: "Jet Black", image: "/media/vinfast/vf8/color-jet-black.webp", paint: "#16191d" },
  { name: "Ivy Green", image: "/media/vinfast/vf8/color-ivy-green.webp", paint: "#294336" },
  { name: "Infinity Blanc", image: "/media/vinfast/vf8/color-infinity-blanc.webp", paint: "#f2f1ed" },
  { name: "Crimson Red", image: "/media/vinfast/vf8/color-crimson-red.webp", paint: "#be2534" },
] as const;

const interiorSlides = [
  { image: "/media/vinfast/vf8/interior-1.webp", alt: "Khoang nội thất VinFast VF 8" },
  { image: "/media/vinfast/vf8/interior-2.webp", alt: "Bảng điều khiển VinFast VF 8" },
  { image: "/media/vinfast/vf8/interior-3.webp", alt: "Hàng ghế VinFast VF 8" },
  { image: "/media/vinfast/vf8/interior-4.webp", alt: "Tiện nghi nội thất VinFast VF 8" },
  { image: "/media/vinfast/vf8/interior-5.webp", alt: "Không gian nội thất VinFast VF 8" },
] as const;

const technologyTabs = [
  {
    label: "Trợ lý ảo ViVi 2.0",
    image: "/media/vinfast/vf8/technology-assistant.webp",
    alt: "Trợ lý ảo VinFast VF 8",
    copy: "Trợ lý ảo ViVi 2.0 phản hồi mượt mà, dùng giọng nói để điều khiển thông minh và cá nhân hóa trải nghiệm.",
  },
  {
    label: "Cập nhật từ xa",
    image: "/media/vinfast/vf8/technology-hud.webp",
    alt: "Màn hình hiển thị kính lái VinFast VF 8",
    copy: "Phần mềm được cập nhật từ xa, giúp chiếc xe luôn được bổ sung và tối ưu những tính năng mới.",
  },
  {
    label: "Ứng dụng VinFast",
    image: "/media/vinfast/vf8/technology-app.webp",
    alt: "Ứng dụng VinFast trên VF 8",
    copy: "Ứng dụng VinFast kết nối chủ xe với hành trình, hỗ trợ theo dõi và điều khiển nhiều tính năng thuận tiện.",
  },
] as const;

const exteriorFeatures = [
  {
    image: "/media/vinfast/vf8/aerodynamics.webp",
    alt: "Thiết kế khí động học VinFast VF 8",
    title: "Thiết kế khí động học",
    copy: "Giảm lực cản không khí và tăng hiệu quả vận hành, đồng thời mang lại vẻ ngoài hiện đại và mạnh mẽ.",
  },
  {
    image: "/media/vinfast/vf8/mirror.webp",
    alt: "Gương chiếu hậu điện tử VinFast VF 8",
    title: "Gương chiếu hậu hiện đại",
    copy: "Tự động gập và điều chỉnh điện, tích hợp báo điểm mù và cảnh báo phương tiện cắt ngang.",
  },
  {
    image: "/media/vinfast/vf8/panorama.webp",
    alt: "Cửa sổ trời toàn cảnh VinFast VF 8",
    title: "Cửa sổ trời toàn cảnh",
    copy: "Tích hợp rèm điện, điều khiển đóng mở bằng giọng nói.",
  },
  {
    image: "/media/vinfast/vf8/camera.webp",
    alt: "Camera 360 độ VinFast VF 8",
    title: "Cảm biến và camera 360 độ",
    copy: "Giúp tài xế dễ dàng quan sát và điều khiển trong không gian hẹp hay khu vực đông đúc.",
  },
] as const;

const comparisonRows = [
  ["Màu sắc", "4 màu tiêu chuẩn và 4 màu nâng cao", "4 màu tiêu chuẩn và 4 màu nâng cao"],
  ["Công suất", "201 hp", "402 hp"],
  ["Quãng đường di chuyển", "562 km (theo NEDC)", "457 km (theo WLTP)"],
  ["Trợ lý ảo", "Trợ lý ảo ViVi", "Trợ lý ảo ViVi"],
] as const;

const currency = new Intl.NumberFormat("vi-VN");

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
        <a href="#tong-quan">Giới thiệu</a>
        <VehicleMegaMenu />
        <Link href="/motorbikes">Xe máy điện</Link>
        <a href="#thiet-ke">Phụ kiện xe</a>
        <a href="#ho-tro-vf8">Dịch vụ hậu mãi</a>
        <a href="#van-hanh">Pin và trạm sạc</a>
        <a href="#cong-nghe">Lưu trữ năng lượng</a>
      </nav>
      <div className={styles.headerActions}>
        <Link className={styles.account} href="/account">TÀI KHOẢN</Link>
        <Link className={styles.testDrive} href="/test-drive">ĐĂNG KÝ LÁI THỬ</Link>
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
          <a href="#tong-quan" onClick={() => setMenuOpen(false)}>Tổng quan</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#thiet-ke" onClick={() => setMenuOpen(false)}>Thiết kế</a>
          <a href="#noi-that" onClick={() => setMenuOpen(false)}>Nội thất</a>
          <a href="#cong-nghe" onClick={() => setMenuOpen(false)}>Công nghệ</a>
        </nav>
      ) : null}
    </header>
  );
}

function ModelNavigation() {
  return (
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 8">
      <a className={styles.modelLogo} href="#dau-trang">VF8</a>
      <div className={styles.modelLinks}>
        <a href="#tong-quan">Tổng quan</a>
        <a href="#thiet-ke">Thiết kế</a>
        <a href="#noi-that">Nội thất</a>
        <a href="#cong-nghe">Công nghệ</a>
        <a href="#van-hanh">Vận hành</a>
        <a href="#an-toan">An toàn</a>
        <a href="#phien-ban">Các phiên bản</a>
      </div>
      <Link className={styles.modelAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function PriceSection() {
  const variants = [
    { name: "VF 8 Eco", image: "/media/vinfast/vf8/price-eco.webp", price: "853.100.000 VNĐ*", oldPrice: "898.000.000 VNĐ" },
    { name: "VF 8 Plus", image: "/media/vinfast/vf8/price-plus.webp", price: "1.025.050.000 VNĐ*", oldPrice: "1.079.000.000 VNĐ" },
  ] as const;

  return (
    <section className={styles.prices} id="tong-quan">
      <div className={styles.priceGrid}>
        {variants.map((variant) => (
          <article key={variant.name}>
            <div className={styles.priceImage}><Image alt={variant.name} fill sizes="(max-width: 760px) 100vw, 50vw" src={variant.image} /></div>
            <div className={styles.priceCopy}>
              <h2>{variant.name}</h2>
              <span>Giá bán từ</span>
              <strong>{variant.price}</strong>
              <del>{variant.oldPrice}</del>
              <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
            </div>
          </article>
        ))}
      </div>
      <small>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.</small>
    </section>
  );
}

function ColorShowcase() {
  const [colorIndex, setColorIndex] = useState(0);
  const activeColor = colors[colorIndex];

  return (
    <section className={styles.design} id="thiet-ke">
      <div className={styles.sectionHeading}>
        <h2>Thiết kế cá nhân hoá</h2>
        <p>VF 8 Eco và VF 8 Plus đem đến đa dạng sự lựa chọn màu ngoại thất, phù hợp cho những chủ nhân yêu thích sự hiện đại, phong cách và sang trọng.</p>
      </div>
      <div className={styles.colorStage}>
        <Image alt={`VinFast VF 8 màu ${activeColor.name}`} fill key={activeColor.image} priority sizes="100vw" src={activeColor.image} />
      </div>
      <div className={styles.colorControls} aria-label="Bảng màu VinFast VF 8">
        {colors.map((color, index) => (
          <button
            aria-label={`Xem màu ${color.name}`}
            aria-pressed={index === colorIndex}
            className={index === colorIndex ? styles.colorActive : undefined}
            key={color.name}
            onClick={() => setColorIndex(index)}
            style={{ "--paint": color.paint } as CSSProperties}
            type="button"
          />
        ))}
      </div>
      <strong className={styles.colorName} aria-live="polite">{activeColor.name}</strong>
      <div className={styles.exteriorGrid}>
        {exteriorFeatures.map((feature) => (
          <article key={feature.title}>
            <div><Image alt={feature.alt} fill sizes="(max-width: 760px) 50vw, 25vw" src={feature.image} /></div>
            <h3>{feature.title}</h3>
            <p>{feature.copy}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function InteriorSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = interiorSlides[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + interiorSlides.length) % interiorSlides.length);
  }

  return (
    <section className={styles.interior} id="noi-that">
      <div className={styles.sectionHeading}>
        <h2>Thăng hạng đẳng cấp</h2>
        <p>VF 8 Eco và VF 8 Plus dành cho những người hiểu rõ giá trị sang trọng và đẳng cấp, mong muốn tận hưởng trọn vẹn những trải nghiệm cho bản thân và gia đình.</p>
      </div>
      <div className={styles.interiorStage}>
        <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="100vw" src={activeSlide.image} />
        <button aria-label="Nội thất trước" className={styles.previous} onClick={() => move(-1)} type="button"><ChevronLeft aria-hidden="true" /></button>
        <button aria-label="Nội thất tiếp theo" className={styles.next} onClick={() => move(1)} type="button"><ChevronRight aria-hidden="true" /></button>
      </div>
      <div className={styles.thumbnails} aria-label="Chọn ảnh nội thất VF 8">
        {interiorSlides.map((slide, index) => (
          <button aria-label={`Ảnh nội thất ${index + 1}`} aria-pressed={index === activeIndex} key={slide.image} onClick={() => setActiveIndex(index)} type="button">
            <Image alt="" fill sizes="90px" src={slide.image} />
          </button>
        ))}
      </div>
    </section>
  );
}

function TechnologySection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeTab = technologyTabs[activeIndex];

  return (
    <section className={styles.technology} id="cong-nghe">
      <div className={styles.sectionHeading}>
        <h2>Công nghệ tiên phong</h2>
        <p>VF 8 sở hữu hàng loạt tính năng thông minh, hỗ trợ người lái và kết nối liền mạch trên mọi hành trình.</p>
      </div>
      <div className={styles.technologyStage}>
        <Image alt={activeTab.alt} fill key={activeTab.image} sizes="(max-width: 800px) 100vw, 70vw" src={activeTab.image} />
      </div>
      <div className={styles.technologyTabs} role="tablist" aria-label="Công nghệ VinFast VF 8">
        {technologyTabs.map((tab, index) => (
          <button aria-selected={index === activeIndex} key={tab.label} onClick={() => setActiveIndex(index)} role="tab" type="button">{tab.label}</button>
        ))}
      </div>
      <p className={styles.technologyCopy}>{activeTab.copy}</p>
    </section>
  );
}

function JourneySection() {
  return (
    <section className={styles.journey} id="van-hanh">
      <div className={styles.journeyImage}><Image alt="VinFast VF 8 sẵn sàng cho mọi hành trình" fill sizes="(max-width: 760px) 100vw, 48vw" src="/media/vinfast/vf8/journey.webp" /></div>
      <div className={styles.journeyCopy}>
        <h2>Sẵn sàng cho mọi hành trình</h2>
        <p>Với quãng đường di chuyển mỗi lần sạc đầy lên tới 562 km, VF 8 sẵn sàng cùng bạn chinh phục mọi hành trình.</p>
        <dl>
          <div><dt>562 km</dt><dd>pin cao cấp từ CATL</dd></div>
          <div><dt>5,58 giây</dt><dd>0-100 km/h</dd></div>
          <div><dt>402 hp</dt><dd>sức mạnh tối đa</dd></div>
          <div><dt>31 phút</dt><dd>sạc nhanh từ 10-70%</dd></div>
        </dl>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      </div>
    </section>
  );
}

function SafetySection() {
  return (
    <section className={styles.safety} id="an-toan">
      <div className={styles.sectionHeading}>
        <h2>An toàn của gia đình bạn là ưu tiên trên hết của VinFast</h2>
        <p>Tất cả các xe VinFast tuân thủ các tiêu chuẩn an toàn nghiêm ngặt nhất và được trang bị những công nghệ hiện đại theo chuẩn quốc tế.</p>
      </div>
      <div className={styles.safetyGrid}>
        <article><Image alt="Hệ thống túi khí VinFast VF 8" fill sizes="(max-width: 760px) 100vw, 48vw" src="/media/vinfast/vf8/safety-airbags.webp" /><span>Hệ thống 11 túi khí</span></article>
        <article><Image alt="Hệ thống trợ lái VinFast VF 8" fill sizes="(max-width: 760px) 100vw, 48vw" src="/media/vinfast/vf8/safety-assistance.webp" /><span>Hệ thống hỗ trợ lái nâng cao</span></article>
      </div>
    </section>
  );
}

function VersionComparison() {
  return (
    <section className={styles.versions} id="phien-ban">
      <h2>Tổng quan sự khác biệt</h2>
      <div className={styles.versionTableWrap}>
        <table>
          <thead><tr><th>VF8</th><th>Eco</th><th>Plus</th></tr></thead>
          <tbody>{comparisonRows.map(([label, eco, plus]) => <tr key={label}><th>{label}</th><td>{eco}</td><td>{plus}</td></tr>)}</tbody>
        </table>
      </div>
      <div className={styles.versionActions}>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        <a href="https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dw4642b15e/Document/VF8_Brochure_T04.pdf" rel="noreferrer" target="_blank">THÔNG SỐ CHI TIẾT</a>
      </div>
    </section>
  );
}

function FuelComparison() {
  const [distance, setDistance] = useState("1200");
  const [consumption, setConsumption] = useState("8");
  const [fuelPrice, setFuelPrice] = useState("23000");
  const [values, setValues] = useState({ distance: 1200, consumption: 8, fuelPrice: 23000 });
  const saving = useMemo(() => Math.round(values.distance / 100 * values.consumption * values.fuelPrice), [values]);

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValues({
      distance: Math.max(0, Number(distance) || 0),
      consumption: Math.max(0, Number(consumption) || 0),
      fuelPrice: Math.max(0, Number(fuelPrice) || 0),
    });
  }

  return (
    <section className={styles.fuelComparison}>
      <h2>So sánh giữa xe VinFast VF 8 và xe động cơ đốt trong</h2>
      <div className={styles.fuelGrid}>
        <form onSubmit={calculate}>
          <label>Quãng đường di chuyển/tháng<span><input aria-label="Quãng đường VF 8 mỗi tháng" min="0" onChange={(event) => setDistance(event.target.value)} type="number" value={distance} /><small>km</small></span></label>
          <label>Mức tiêu thụ nhiên liệu/100km<span><input aria-label="Mức tiêu thụ nhiên liệu VF 8" min="0" onChange={(event) => setConsumption(event.target.value)} step="0.1" type="number" value={consumption} /><small>lít</small></span></label>
          <label>Giá nhiên liệu mỗi lít<span><input aria-label="Giá nhiên liệu so sánh VF 8" min="0" onChange={(event) => setFuelPrice(event.target.value)} type="number" value={fuelPrice} /><small>VNĐ</small></span></label>
          <button type="submit">SO SÁNH</button>
        </form>
        <article>
          <div><Image alt="Nhiên liệu hóa thạch" height={56} src="/media/vinfast/vf8/comparison-logo.webp" width={56} /><span>so với</span><Image alt="VinFast VF 8" height={128} src="/media/vinfast/vf8/comparison-car.webp" width={230} /></div>
          <p>Lợi thế chi phí nhiên liệu của VF 8 mỗi tháng</p>
          <strong>{currency.format(saving)} VNĐ</strong>
          <small>{currency.format(saving * 12)} VNĐ/năm</small>
        </article>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div><VinFastMark footer /><p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p></div>
      <nav aria-label="Thông tin VinFast"><a href="#tong-quan">VỀ VINFAST</a><a href="#phien-ban">ĐIỀU KHOẢN CHÍNH SÁCH</a></nav>
      <div><a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a><a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a></div>
    </footer>
  );
}

export function Vf8Experience() {
  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <section className={styles.hero}>
          <picture><source media="(max-width: 620px)" srcSet="/media/vinfast/vf8/hero-mobile.webp" /><Image alt="VinFast VF 8 trên đường phố" fill priority sizes="100vw" src="/media/vinfast/vf8/hero.webp" /></picture>
        </section>
        <PriceSection />
        <ColorShowcase />
        <InteriorSection />
        <TechnologySection />
        <JourneySection />
        <SafetySection />
        <VersionComparison />
        <FuelComparison />
        <VehicleSupportChoice anchorId="ho-tro-vf8" from="/vehicles/vf-8" model="VF 8" />
      </main>
      <Footer />
    </div>
  );
}
