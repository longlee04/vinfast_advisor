"use client";

import { ChevronDown, ChevronLeft, ChevronRight, Mail, Menu, Phone, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState, type CSSProperties, type FormEvent } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf7-experience.module.css";

type Slide = Readonly<{
  alt: string;
  description?: string;
  image: string;
  title: string;
}>;

const highlightSlides: readonly Slide[] = [
  {
    image: "/media/vinfast/vf7/feature-1.webp",
    alt: "Triết lý thiết kế Vũ Trụ Phi Đối Xứng",
    title: "Triết lý thiết kế “Vũ Trụ Phi Đối Xứng”",
    description: "Thiết kế ngoại thất thể hiện sự tự do, cá tính, mạnh mẽ và thể thao, thỏa mãn mọi tâm hồn đam mê thẩm mỹ và tốc độ.",
  },
  {
    image: "/media/vinfast/vf7/feature-3.webp",
    alt: "Trải nghiệm lái phấn khích",
    title: "Trải nghiệm lái phấn khích",
    description: "Công suất tối đa 260 kW*, mô-men xoắn cực đại 500 Nm. (*Thông số bản Plus tùy chọn AWD)",
  },
  {
    image: "/media/vinfast/vf7/feature-4.webp",
    alt: "Chi phí lăn bánh hấp dẫn",
    title: "Chi phí lăn bánh hấp dẫn",
    description: "Mức giá lăn bánh cạnh tranh, được miễn phí lệ phí trước bạ theo chính sách hiện hành.",
  },
  {
    image: "/media/vinfast/vf7/feature-5.webp",
    alt: "Chi phí vận hành tối ưu",
    title: "Chi phí vận hành tối ưu",
    description: "Chương trình miễn phí sạc của VinFast giúp tối ưu chi phí sử dụng mỗi ngày.",
  },
  {
    image: "/media/vinfast/vf7/feature-6.webp",
    alt: "Hậu mãi cực tốt",
    title: "Hậu mãi cực tốt",
    description: "Bảo hành xe mới 7 năm hoặc 160.000 km; xưởng dịch vụ không ngày nghỉ và cứu hộ 24/7.",
  },
];

const colorFrames = [
  { name: "Solar Ruby", image: "/media/vinfast/vf7/color-solar-ruby.webp", paint: "#d11232" },
  { name: "Zenith Grey", image: "/media/vinfast/vf7/color-zenith-grey.webp", paint: "#8b8d8e" },
  { name: "Urban Mint", image: "/media/vinfast/vf7/color-urban-mint.webp", paint: "#aeb9a5" },
  { name: "Infinity Blanc", image: "/media/vinfast/vf7/color-infinity-blanc.webp", paint: "#f2f2ee" },
  { name: "Jet Black", image: "/media/vinfast/vf7/color-jet-black.webp", paint: "#121315" },
] as const;

const masterpieceSlides: readonly Slide[] = [
  { image: "/media/vinfast/vf7/masterpiece-1.webp", alt: "VinFast VF 7 - tác phẩm nghệ thuật số 1", title: "Dấu ấn từ mọi góc nhìn" },
  { image: "/media/vinfast/vf7/masterpiece-2.webp", alt: "VinFast VF 7 - tác phẩm nghệ thuật số 2", title: "Đường nét giàu cảm xúc" },
  { image: "/media/vinfast/vf7/masterpiece-3.webp", alt: "VinFast VF 7 - tác phẩm nghệ thuật số 3", title: "La-zăng thể thao" },
  { image: "/media/vinfast/vf7/masterpiece-4.webp", alt: "VinFast VF 7 - tác phẩm nghệ thuật số 4", title: "Thân xe khí động học" },
  { image: "/media/vinfast/vf7/masterpiece-5.webp", alt: "VinFast VF 7 - tác phẩm nghệ thuật số 5", title: "Gương chiếu hậu tối ưu tầm nhìn" },
];

const specificationRows = [
  ["Chiều dài cơ sở", "2.840 mm", "2.840 mm"],
  ["Dài x Rộng x Cao", "4.545 x 1.890 x 1.635,75 mm", "4.545 x 1.890 x 1.635,75 mm"],
  ["Quãng đường chạy một lần sạc đầy (NEDC)", "440 km", "500,5 km"],
  ["Công suất tối đa", "130 kW", "150 kW"],
  ["Mô-men xoắn cực đại", "250 Nm", "310 Nm"],
  ["Dung lượng pin khả dụng", "59,6 kWh", "70 kWh"],
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
        <a href="#tinh-nang">Dịch vụ hậu mãi</a>
        <a href="#cam-ket">Pin và trạm sạc</a>
        <a href="#cam-ket">Lưu trữ năng lượng</a>
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
          <a href="#ngoai-that" onClick={() => setMenuOpen(false)}>Ngoại thất</a>
          <a href="#noi-that" onClick={() => setMenuOpen(false)}>Nội thất</a>
          <a href="#tinh-nang" onClick={() => setMenuOpen(false)}>Tính năng</a>
        </nav>
      ) : null}
    </header>
  );
}

function ModelNavigation() {
  return (
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 7">
      <a className={styles.modelLogo} href="#dau-trang" aria-label="Về đầu trang VF 7">
        <Image alt="VF 7" height={152} priority src="/media/vinfast/vf7/vf7-logo-light.svg" width={592} />
      </a>
      <div className={styles.modelLinks}>
        <a href="#gia-ban">Giá bán</a>
        <a href="#gioi-thieu">Giới thiệu</a>
        <a href="#ngoai-that">Ngoại thất</a>
        <a href="#noi-that">Nội thất</a>
        <a href="#tinh-nang">Tính năng</a>
      </div>
      <Link className={styles.modelAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function PriceSection() {
  return (
    <section className={styles.priceSection} id="gia-ban">
      <div className={styles.priceVehicle}>
        <Image alt="VinFast VF 7 Solar Ruby nhìn ngang" fill sizes="100vw" src="/media/vinfast/vf7/hero-car.webp" />
      </div>
      <div className={styles.priceContent}>
        <h2>Tùy chọn cho ngân sách của bạn.</h2>
        <div className={styles.priceCards}>
          <article><h3>VF 7 Eco</h3><span>Giá bán từ</span><strong>703.000.000 VNĐ*</strong><del>740.000.000 VNĐ</del></article>
          <article><h3>VF 7 Plus</h3><span>Giá bán từ</span><strong>788.500.000 VNĐ*</strong><del>830.000.000 VNĐ</del></article>
          <article><h3>VF 7 Plus</h3><span>Trần kính toàn cảnh · Giá bán từ</span><strong>807.500.000 VNĐ*</strong><del>850.000.000 VNĐ</del></article>
        </div>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        <small>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản và điều kiện.</small>
      </div>
    </section>
  );
}

function HighlightCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = highlightSlides[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + highlightSlides.length) % highlightSlides.length);
  }

  return (
    <section className={styles.highlights} id="gioi-thieu">
      <h2>VF 7 là một bước tiến đột phá trong thiết kế xe ô tô của VinFast.</h2>
      <div className={styles.highlightStage}>
        <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="(max-width: 900px) 100vw, 72vw" src={activeSlide.image} />
      </div>
      <div className={styles.highlightCaption}>
        <div><strong>{activeSlide.title}</strong><p>{activeSlide.description}</p></div>
        <div className={styles.sliderActions}>
          <button aria-label="Điểm nổi bật trước" onClick={() => move(-1)} type="button"><ChevronLeft aria-hidden="true" /></button>
          <button aria-label="Điểm nổi bật tiếp theo" onClick={() => move(1)} type="button"><ChevronRight aria-hidden="true" /></button>
        </div>
      </div>
      <div className={styles.dots} aria-label="Chọn điểm nổi bật VF 7">
        {highlightSlides.map((slide, index) => (
          <button aria-label={`Điểm nổi bật ${index + 1}`} aria-pressed={index === activeIndex} className={index === activeIndex ? styles.dotActive : undefined} key={slide.image} onClick={() => setActiveIndex(index)} type="button" />
        ))}
      </div>
    </section>
  );
}

function ColorShowcase() {
  const [colorIndex, setColorIndex] = useState(0);
  const activeColor = colorFrames[colorIndex];

  return (
    <section className={styles.colorSection} id="ngoai-that">
      <div className={styles.colorHeading}>
        <h2>Ngoại thất kế thừa và đổi mới<br />từ hơn trăm năm lịch sử của ngành ô tô.</h2>
      </div>
      <div className={styles.colorStage}>
        <Image alt={`VinFast VF 7 màu ${activeColor.name}`} fill key={activeColor.image} priority sizes="100vw" src={activeColor.image} />
      </div>
      <strong className={styles.colorName} aria-live="polite">{activeColor.name}</strong>
      <div className={styles.colorControls} aria-label="Bảng màu VinFast VF 7">
        {colorFrames.map((color, index) => (
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
      <Link className={styles.inlineAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      <div className={styles.designStatement}>
        <h3>Triết lý thiết kế “Vũ trụ phi đối xứng”.</h3>
        <p>Lấy cảm hứng từ vũ trụ và các vật thể bay trong không gian, VF 7 hiện thân cho sự tự do, công nghệ, thời đại, cá tính, mạnh mẽ và thể thao, thỏa mãn mọi tâm hồn đam mê thẩm mỹ và tốc độ.</p>
      </div>
      <div className={styles.exteriorProfile}>
        <Image alt="VinFast VF 7 ngoại thất nhìn ngang" fill sizes="100vw" src="/media/vinfast/vf7/feature-slide.webp" />
      </div>
      <p className={styles.exteriorCopy}>Những đường nét và hình khối được sử dụng nhịp nhàng và tinh tế, mang đến không gian trải nghiệm đầy phóng khoáng và tràn đầy năng lượng; song vẫn giữ được sự tối giản, tinh khiết và thời trang.</p>
      <div className={styles.designImage}><Image alt="Thiết kế đầu xe VinFast VF 7" fill sizes="(max-width: 900px) 100vw, 70vw" src="/media/vinfast/vf7/design.webp" /></div>
    </section>
  );
}

function MasterpieceGallery() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = masterpieceSlides[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + masterpieceSlides.length) % masterpieceSlides.length);
  }

  return (
    <section className={styles.masterpiece}>
      <h2>VF 7 không chỉ là một chiếc xe điện tiên tiến, mà còn là một tác phẩm nghệ thuật kết hợp giữa công nghệ và sự sáng tạo trong thiết kế.</h2>
      <div className={styles.masterpieceStage}>
        <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="100vw" src={activeSlide.image} />
        <button aria-label="Tác phẩm trước" className={styles.previous} onClick={() => move(-1)} type="button"><ChevronLeft aria-hidden="true" /></button>
        <button aria-label="Tác phẩm tiếp theo" className={styles.next} onClick={() => move(1)} type="button"><ChevronRight aria-hidden="true" /></button>
        <div className={styles.masterpieceCaption}><strong>{activeSlide.title}</strong><span>0{activeIndex + 1} / 0{masterpieceSlides.length}</span></div>
      </div>
      <div className={styles.dots} aria-label="Chọn tác phẩm VF 7">
        {masterpieceSlides.map((slide, index) => <button aria-label={`Tác phẩm ${index + 1}`} aria-pressed={index === activeIndex} className={index === activeIndex ? styles.dotActive : undefined} key={slide.image} onClick={() => setActiveIndex(index)} type="button" />)}
      </div>
    </section>
  );
}

function InteriorSection() {
  const [comfortIndex, setComfortIndex] = useState(0);
  const comfortSlides = [
    { image: "/media/vinfast/vf7/comfort-1.webp", alt: "Bệ điều khiển trung tâm VinFast VF 7" },
    { image: "/media/vinfast/vf7/comfort-2.webp", alt: "Màn hình dẫn đường VinFast VF 7" },
    { image: "/media/vinfast/vf7/comfort-3.webp", alt: "Màn hình giải trí VinFast VF 7" },
    { image: "/media/vinfast/vf7/comfort-4.webp", alt: "Không gian điều khiển VinFast VF 7" },
  ] as const;
  const activeComfort = comfortSlides[comfortIndex];

  return (
    <section className={styles.interior} id="noi-that">
      <h2>Thiết kế nội thất hướng tới người lái.</h2>
      <div className={styles.interiorOverview}>
        <Image alt="Khoang nội thất VinFast VF 7" fill sizes="100vw" src="/media/vinfast/vf7/interior-overview.webp" />
        <div><h3>Kiến tạo không gian trải nghiệm phóng khoáng, tự do và tràn đầy năng lượng.</h3><p>Tận hưởng hành trình trong không gian riêng tư và rộng rãi, nơi mỗi chi tiết mang đậm dấu ấn cá nhân.</p></div>
      </div>
      <div className={styles.interiorCards}>
        <article><div><Image alt="Tiện nghi hướng vào người lái trên VinFast VF 7" fill sizes="50vw" src="/media/vinfast/vf7/interior-left.webp" /></div><h3>Tiện nghi hướng vào người lái</h3><p>Tất cả tiện nghi đều nằm trong tầm tay người lái, mang tới kết nối liền mạch giữa người và xe.</p></article>
        <article><div><Image alt="Trần kính toàn cảnh VinFast VF 7" fill sizes="50vw" src="/media/vinfast/vf7/interior-right.webp" /></div><h3>Trần kính toàn cảnh (tùy chọn)</h3><p>Mở rộng không gian, mang tới trải nghiệm cao cấp trên mỗi hành trình.</p></article>
      </div>
      <div className={styles.comfortStage}>
        <Image alt={activeComfort.alt} fill key={activeComfort.image} sizes="100vw" src={activeComfort.image} />
        <button aria-label="Tiện nghi trước" className={styles.previous} onClick={() => setComfortIndex((comfortIndex - 1 + comfortSlides.length) % comfortSlides.length)} type="button"><ChevronLeft aria-hidden="true" /></button>
        <button aria-label="Tiện nghi tiếp theo" className={styles.next} onClick={() => setComfortIndex((comfortIndex + 1) % comfortSlides.length)} type="button"><ChevronRight aria-hidden="true" /></button>
      </div>
      <Link className={styles.inlineAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </section>
  );
}

function FeatureSections() {
  return (
    <section className={styles.features} id="tinh-nang">
      <article>
        <div className={styles.featureImage}><Image alt="VinFast VF 7 - Cầm lái với đam mê" fill sizes="(max-width: 800px) 100vw, 46vw" src="/media/vinfast/vf7/passion.webp" /></div>
        <div><span>VẬN HÀNH</span><h2>Cầm lái với đam mê.</h2><strong>7 túi khí*</strong><strong>Mô-men xoắn cực đại 500 Nm**</strong><small>*Áp dụng cho bản VF 7 Plus. **Áp dụng phiên bản VF 7 Plus AWD.</small></div>
      </article>
      <article className={styles.adasCard}>
        <div><span>AN TOÀN</span><h2>Hệ thống trợ lái nâng cao.</h2><h3>Hỗ trợ lái trên đường cao tốc.</h3><p>Ứng dụng công nghệ và trang thiết bị hiện đại, hệ thống trợ lái nâng cao VinFast đem lại trải nghiệm lái thư thái để bạn an tâm tận hưởng cuộc sống.</p></div>
      </article>
      <article id="cam-ket">
        <div className={styles.featureImage}><Image alt="Mạng lưới trạm sạc và dịch vụ VinFast" fill sizes="(max-width: 800px) 100vw, 46vw" src="/media/vinfast/vf7/commitment.webp" /></div>
        <div><span>HẠ TẦNG</span><h2>3,5 km - Khoảng cách nhỏ cho mục tiêu lớn.</h2><p>Hệ thống trạm sạc VinFast trải dài 34 tỉnh thành, phủ 106 tuyến quốc lộ quan trọng và mang đến nhiều tiện ích cho hành trình lái xe điện.</p></div>
      </article>
    </section>
  );
}

function Specifications() {
  return (
    <section className={styles.specifications} id="thong-so">
      <div className={styles.specHeading}><Image alt="VF 7" height={152} src="/media/vinfast/vf7/vf7-logo-light.svg" width={592} /><h2>Tổng quan sự khác biệt.</h2></div>
      <div className={styles.specTableWrap}>
        <table><thead><tr><th>Thông số</th><th>VF 7 Eco</th><th>VF 7 Plus</th></tr></thead><tbody>{specificationRows.map(([name, eco, plus]) => <tr key={name}><th>{name}</th><td>{eco}</td><td>{plus}</td></tr>)}</tbody></table>
      </div>
      <div className={styles.specActions}>
        <a href="https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dw77dca565/Document/VF7_Brochure_T062025.pdf" rel="noreferrer" target="_blank">TẢI BROCHURE</a>
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
  const saving = useMemo(() => Math.round(calculation.distance / 100 * calculation.consumption * fuelPrice), [calculation, fuelPrice]);

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCalculation({ consumption: Math.max(0, Number(consumption) || 0), distance: Math.max(0, Number(distance) || 0), fuel });
  }

  return (
    <section className={styles.comparison}>
      <div className={styles.comparisonIntro}><h2>So sánh giữa xe VinFast VF 7 và xe động cơ đốt trong</h2><p>Vui lòng nhập thông tin xe động cơ đốt trong cần so sánh:</p><div><Image alt="Nhiên liệu hóa thạch" height={56} src="/media/vinfast/vf7/comparison-logo.webp" width={56} /><span>so với</span><Image alt="VinFast VF 7" height={128} src="/media/vinfast/vf7/comparison-car.webp" width={230} /></div></div>
      <form onSubmit={calculate}>
        <label>Loại nhiên liệu sử dụng<span className={styles.selectWrap}><select aria-label="Loại nhiên liệu sử dụng" onChange={(event) => setFuel(event.target.value)} value={fuel}><option value="petrol">Xăng</option><option value="diesel">Dầu</option></select><ChevronDown aria-hidden="true" /></span></label>
        <label>Mức tiêu thụ nhiên liệu/100km<span><input aria-label="Mức tiêu thụ nhiên liệu VF 7" min="0" onChange={(event) => setConsumption(event.target.value)} step="0.1" type="number" value={consumption} /><small>lít</small></span></label>
        <label>Quãng đường di chuyển/tháng<span><input aria-label="Quãng đường di chuyển mỗi tháng VF 7" min="0" onChange={(event) => setDistance(event.target.value)} step="1" type="number" value={distance} /><small>km</small></span></label>
        <button type="submit">SO SÁNH</button>
        <div className={styles.savingResult} aria-live="polite"><span>Chi phí nhiên liệu tiết kiệm/tháng</span><strong>{formatCurrency.format(saving)} VNĐ</strong><small>{formatCurrency.format(saving * 12)} VNĐ/năm</small></div>
      </form>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div><VinFastMark footer /><p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p><small>VinFast. All rights reserved.</small></div>
      <nav aria-label="Thông tin VinFast"><a href="#gioi-thieu">VỀ VINFAST</a><a href="#cam-ket">SHOWROOM VÀ ĐẠI LÝ</a><a href="#gia-ban">ĐIỀU KHOẢN CHÍNH SÁCH</a></nav>
      <div><a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a><a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a></div>
    </footer>
  );
}

export function Vf7Experience() {
  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <section className={styles.hero}>
          <picture><source media="(max-width: 620px)" srcSet="/media/vinfast/vf7/hero-mobile.webp" /><Image alt="VinFast VF 7 - Đam mê tạo phi thường" fill priority sizes="100vw" src="/media/vinfast/vf7/hero.webp" /></picture>
        </section>
        <PriceSection />
        <HighlightCarousel />
        <ColorShowcase />
        <MasterpieceGallery />
        <InteriorSection />
        <FeatureSections />
        <Specifications />
        <FuelComparison />
        <VehicleSupportChoice anchorId="ho-tro-vf7" from="/vehicles/vf-7" model="VF 7" />
      </main>
      <Footer />
    </div>
  );
}
