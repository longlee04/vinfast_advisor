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

import styles from "./vf8-all-new-experience.module.css";

const standardColors = [
  { code: "13", name: "Solar Ruby", paint: "#7d1028" },
  { code: "15", name: "Infinity Blanc", paint: "#f1f0eb" },
  { code: "21", name: "Jet Black", paint: "#101317" },
  { code: "23", name: "Starburst Blue", paint: "#93abc0" },
] as const;

const premiumColors = [
  { code: "17", name: "Mysterioso Purple", paint: "#553448" },
  { code: "19", name: "Vitality Orange", paint: "#bb3823" },
  { code: "14", name: "Solar Ruby Body - Jet Black Roof", paint: "linear-gradient(135deg, #7d1028 50%, #111 50%)" },
  { code: "16", name: "Vitality Orange Body - Infinity Blanc Roof", paint: "linear-gradient(135deg, #bb3823 50%, #f2f1ec 50%)" },
  { code: "18", name: "Mysterioso Purple Body - Stealth Gray Roof", paint: "linear-gradient(135deg, #553448 50%, #777b80 50%)" },
  { code: "20", name: "Vitality Orange Body - Jet Black Roof", paint: "linear-gradient(135deg, #bb3823 50%, #111 50%)" },
  { code: "22", name: "Jet Black Body - Stealth Gray Roof", paint: "linear-gradient(135deg, #111 50%, #777b80 50%)" },
  { code: "24", name: "Starburst Blue Body - Infinity Blanc Roof", paint: "linear-gradient(135deg, #93abc0 50%, #f2f1ec 50%)" },
] as const;

const colors = [...standardColors, ...premiumColors] as const;

const technologySlides = [
  {
    title: "Kiến trúc điện - điện tử",
    image: "/media/vinfast/vf8-all-new/technology-1.webp",
    alt: "Kiến trúc điện - điện tử VF 8 Thế Hệ Mới",
    copy: "Nơi công nghệ, sự tiện nghi và cảm xúc được kết nối một cách tự nhiên hơn trong từng trải nghiệm hằng ngày.",
  },
  {
    title: "Hệ thống hỗ trợ lái nâng cao (ADAS)",
    image: "/media/vinfast/vf8-all-new/technology-2.webp",
    alt: "Hệ thống hỗ trợ lái nâng cao ADAS",
    copy: "Hỗ trợ di chuyển trên đường cao tốc, ga tự động thích ứng, hỗ trợ giữ làn, cảnh báo điểm mù và camera 360 độ sắc nét.",
  },
  {
    title: "Trợ lý ảo",
    image: "/media/vinfast/vf8-all-new/technology-3.webp",
    alt: "Trợ lý ảo VF 8 Thế Hệ Mới",
    copy: "Trợ lý ảo thông minh với khả năng hiểu ngữ cảnh và trò chuyện tự nhiên, đồng hành cùng bạn trong mỗi hành trình.",
  },
  {
    title: "Hệ thống treo thích ứng FSD",
    image: "/media/vinfast/vf8-all-new/technology-4.webp",
    alt: "Hệ thống treo thích ứng FSD",
    copy: "Hệ thống linh hoạt thay đổi độ cứng, mềm của phuộc để duy trì sự êm ái trên đường xấu và độ đằm chắc khi vận hành.",
  },
] as const;

const currency = new Intl.NumberFormat("vi-VN");

function VinFastMark({ footer = false }: Readonly<{ footer?: boolean }>) {
  return (
    <Link aria-label="VinFast - Trang chủ" className={footer ? styles.footerBrand : styles.brand} href="/">
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
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className={styles.header}>
      <VinFastMark />
      <nav aria-label="Điều hướng chính" className={styles.mainNav}>
        <a href="#tong-quan">Giới thiệu</a>
        <VehicleMegaMenu />
        <Link href="/motorbikes">Xe máy điện</Link>
        <a href="#thiet-ke">Phụ kiện xe</a>
        <a href="#ho-tro-vf8-all-new">Dịch vụ hậu mãi</a>
        <a href="#cong-nghe">Pin và trạm sạc</a>
        <a href="#cong-nghe">Lưu trữ năng lượng</a>
      </nav>
      <div className={styles.headerActions}>
        <Link className={styles.account} href="/account">TÀI KHOẢN</Link>
        <Link className={styles.testDrive} href="/test-drive">ĐĂNG KÝ LÁI THỬ</Link>
        <button
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Đóng menu" : "Mở menu"}
          className={styles.menuButton}
          onClick={() => setMobileOpen((open) => !open)}
          type="button"
        >
          {mobileOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </div>
      {mobileOpen ? (
        <nav aria-label="Điều hướng di động" className={styles.mobileNav}>
          <a href="#tong-quan" onClick={() => setMobileOpen(false)}>Tổng quan</a>
          <MobileVehicleMenu onVehicleClick={() => setMobileOpen(false)} />
          <a href="#thiet-ke" onClick={() => setMobileOpen(false)}>Thiết kế</a>
          <a href="#noi-that" onClick={() => setMobileOpen(false)}>Nội thất</a>
          <a href="#cong-nghe" onClick={() => setMobileOpen(false)}>Công nghệ</a>
        </nav>
      ) : null}
    </header>
  );
}

function IntroSection() {
  return (
    <section className={styles.intro} id="tong-quan">
      <h1>Khi phong cách<br />{" "}trở thành dấu ấn</h1>
      <p>
        Phát triển trên nền tảng “trải nghiệm chuẩn 5 sao”, VF 8 thế hệ mới định hình phong cách
        di chuyển Xanh hiện đại, nâng chuẩn công nghệ Việt và mở ra trải nghiệm khác biệt.
      </p>
      <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </section>
  );
}

function ColorSwatches({
  activeCode,
  items,
  onChange,
}: Readonly<{
  activeCode: string;
  items: readonly (typeof colors)[number][];
  onChange: (code: string) => void;
}>) {
  return (
    <div className={styles.swatches}>
      {items.map((color) => (
        <button
          aria-label={`Xem màu ${color.name}`}
          aria-pressed={activeCode === color.code}
          className={activeCode === color.code ? styles.swatchActive : undefined}
          key={color.code}
          onClick={() => onChange(color.code)}
          style={{ "--paint": color.paint } as CSSProperties}
          type="button"
        />
      ))}
    </div>
  );
}

function DesignSection() {
  const [activeCode, setActiveCode] = useState("13");
  const activeColor = colors.find((color) => color.code === activeCode) ?? colors[0];

  return (
    <section className={styles.design} id="thiet-ke">
      <div className={styles.designCard}>
        <div className={styles.designCopy}>
          <h2>Thiết kế phong cách<br />cho thế hệ khách hàng hiện đại</h2>
          <p>
            VF 8 thế hệ mới với ngoại hình hoàn toàn mới tạo dấu ấn bằng sự liền mạch trong từng
            đường nét, cảm giác chuyển động trong từng chi tiết và khí chất hiện đại toát ra từ tổng thể.
          </p>
          <dl>
            <div><dt>170 kW</dt><dd>Công suất tối đa</dd></div>
            <div><dt>330 Nm</dt><dd>Mô men xoắn cực đại</dd></div>
            <div><dt>480–500 km</dt><dd>(NEDC) Tùy điều kiện di chuyển</dd></div>
            <div><dt>60 kWh</dt><dd>Dung lượng pin</dd></div>
          </dl>
        </div>
        <div className={styles.colorCar}>
          <Image
            alt={`VF 8 Thế Hệ Mới màu ${activeColor.name}`}
            fill
            key={activeColor.code}
            priority
            sizes="(max-width: 800px) 100vw, 55vw"
            src={`/media/vinfast/vf8-all-new/color-vf8ph-${activeColor.code}.webp`}
          />
        </div>
        <div className={styles.colorPicker}>
          <strong aria-live="polite" className={styles.colorName}>{activeColor.name}</strong>
          <div className={styles.colorGroups}>
            <div><span>Màu tiêu chuẩn</span><ColorSwatches activeCode={activeCode} items={standardColors} onChange={setActiveCode} /></div>
            <div><span>Màu nâng cao</span><ColorSwatches activeCode={activeCode} items={premiumColors} onChange={setActiveCode} /></div>
          </div>
          <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        </div>
      </div>
    </section>
  );
}

function TechFluidSection() {
  return (
    <section className={styles.techFluid}>
      <p>
        VF 8 thế hệ mới được phát triển dựa trên triết lý thiết kế <strong>Tech Fluid - Dòng chảy công nghệ</strong>,
        nơi công nghệ không hiện diện một cách khô cứng hay cơ học, mà được hòa quyện tự nhiên vào từng
        đường nét, từng bề mặt và từng trải nghiệm sử dụng hằng ngày.
      </p>
      <div className={styles.storyGrid}>
        <div className={styles.storyLead}><Image alt="VF 8 Thế Hệ Mới trong bối cảnh đô thị" fill sizes="50vw" src="/media/vinfast/vf8-all-new/story-city.webp" /></div>
        <article><Image alt="VF 8 Thế Hệ Mới trên cung đường biển" fill sizes="25vw" src="/media/vinfast/vf8-all-new/story-coast.webp" /><h3>Trải nghiệm thị giác không giới hạn</h3></article>
        <article><Image alt="VF 8 Thế Hệ Mới vận hành ven biển" fill sizes="25vw" src="/media/vinfast/vf8-all-new/story-road.webp" /></article>
      </div>
      <p className={styles.storyCopy}>
        Ngoại thất gây ấn tượng với diện mạo đặc trưng của xe điện thế hệ mới, kết hợp dấu ấn khí động học,
        thân xe gân bắt sáng và dải đèn cánh chim kéo dài đầy chiều sâu.
      </p>
    </section>
  );
}

function HighlightSection() {
  return (
    <section className={styles.highlights}>
      <header><span>VF8</span><h2>Điểm nhấn công nghệ, nâng cấp trải nghiệm</h2><p>Quản lý và điều khiển các tính năng xe từ xa mượt mà, cùng không gian tiện nghi và âm thanh sống động.</p></header>
      <div className={styles.highlightGrid}>
        <div><Image alt="VF 8 Thế Hệ Mới nhìn nghiêng" fill sizes="45vw" src="/media/vinfast/vf8-all-new/exterior-car.webp" /></div>
        <div className={styles.highlightFeature}><Image alt="Khoang lái và vô lăng VF 8 Thế Hệ Mới" fill sizes="45vw" src="/media/vinfast/vf8-all-new/interior-wheel.webp" /></div>
      </div>
    </section>
  );
}

function InteriorSection() {
  return (
    <section className={styles.interior} id="noi-that">
      <div className={styles.interiorGrid}>
        <div className={styles.interiorWide}><Image alt="Không gian lái VF 8 Thế Hệ Mới" fill sizes="60vw" src="/media/vinfast/vf8-all-new/interior-1.webp" /></div>
        <div className={styles.interiorTall}><Image alt="Nội thất cao cấp VF 8 Thế Hệ Mới" fill sizes="35vw" src="/media/vinfast/vf8-all-new/interior-2.webp" /></div>
        <div className={styles.interiorDetail}><Image alt="Nội thất VF 8 Thế Hệ Mới sang trọng" fill sizes="45vw" src="/media/vinfast/vf8-all-new/interior-3.webp" /></div>
        <div className={styles.interiorCopy}>
          <h2>Nội thất khoáng đạt - Nâng tầm tiện nghi</h2>
          <p>Chất liệu và kiểu dáng ghế được cải tiến để hỗ trợ tư thế vững chãi, mang lại cảm giác thoải mái trong mọi điều kiện di chuyển.</p>
        </div>
      </div>
    </section>
  );
}

function TechnologySection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = technologySlides[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + technologySlides.length) % technologySlides.length);
  }

  return (
    <section className={styles.technology} id="cong-nghe">
      <div className={styles.technologyStage}>
        <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="(max-width: 800px) 100vw, 54vw" src={activeSlide.image} />
      </div>
      <div className={styles.technologyCopy}>
        <span>{String(activeIndex + 1).padStart(2, "0")} / {String(technologySlides.length).padStart(2, "0")}</span>
        <h2>Nâng cấp trải nghiệm<br />thực tế mỗi ngày</h2>
        <p>SUV điện cỡ D VF 8 thế hệ mới được nâng cấp toàn diện về nền tảng công nghệ, mang đến trải nghiệm vận hành êm ái, tiện nghi và ổn định.</p>
        <h3>{activeSlide.title}</h3>
        <p>{activeSlide.copy}</p>
        <div className={styles.technologyControls}>
          <button aria-label="Công nghệ trước" onClick={() => move(-1)} type="button"><ChevronLeft aria-hidden="true" /></button>
          <button aria-label="Công nghệ tiếp theo" onClick={() => move(1)} type="button"><ChevronRight aria-hidden="true" /></button>
        </div>
      </div>
    </section>
  );
}

function Specifications() {
  return (
    <section className={styles.specifications}>
      <h2>Thông số kỹ thuật</h2>
      <div className={styles.specGrid}>
        <div><span>Dài x rộng x Cao (mm)</span><strong>4701 x 1872 x 1670</strong></div>
        <div><span>Dung lượng pin khả dụng</span><strong>60,13 kWh</strong></div>
        <div><span>Kích thước mâm xe</span><strong>19 Inch</strong></div>
        <div><span>Ghế lái</span><strong>Chỉnh điện 6 hướng, nhớ vị trí</strong></div>
        <div><span>Số ghế ngồi</span><strong>5 ghế</strong></div>
        <div><span>Thời gian nạp pin nhanh nhất (10%-70%)</span><strong>Dưới 30 phút</strong></div>
        <div><span>Màn hình giải trí trung tâm</span><strong>12,9 Inch</strong></div>
        <div><span>Hàng ghế thứ 2 điều chỉnh hướng</span><strong>Ngả ghế; tỉ lệ gập 60:40</strong></div>
      </div>
      <div className={styles.safetyColumns}>
        <div><h3>AN TOÀN &amp; AN NINH</h3><ul><li>Khóa cửa xe tự động khi xe di chuyển</li><li>Cảnh báo chống trộm</li><li>Tính năng khóa động cơ khi có trộm</li><li>Giám sát áp suất lốp dTPMS</li></ul></div>
        <div><h3>HỆ THỐNG HỖ TRỢ LÁI NÂNG CAO ADAS</h3><ul><li>Trợ lái trên cao tốc và khi tắc đường</li><li>Ga tự động thích ứng</li><li>Phanh tự động khẩn cấp trước</li><li>Hỗ trợ giữ làn khẩn cấp</li></ul></div>
      </div>
      <div className={styles.specActions}>
        <a href="https://static-cms-prod.vinfastauto.com/brochure/26052026/VF%208%20The%20he%20moi_Brochure_final%2020.05.pdf" rel="noreferrer" target="_blank">TẢI BROCHURE</a>
        <Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      </div>
    </section>
  );
}

function ClosingBanner() {
  return (
    <section className={styles.closingBanner}>
      <Image alt="VF 8 Thế Hệ Mới nâng cấp toàn diện" fill sizes="100vw" src="/media/vinfast/vf8-all-new/specs-background.webp" />
      <div><h2>Nâng cấp trải nghiệm<br />cùng thế hệ hoàn toàn mới</h2><p>Mang dòng chảy công nghệ trở thành một phần tự nhiên trong mọi hành trình.</p><Link href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link></div>
    </section>
  );
}

function FuelComparison() {
  const [distance, setDistance] = useState("3000");
  const [consumption, setConsumption] = useState("8");
  const [fuelType, setFuelType] = useState<"gasoline" | "diesel">("gasoline");
  const [calculation, setCalculation] = useState({ distance: 3000, consumption: 8, fuelPrice: 22110 });
  const monthlySaving = useMemo(
    () => Math.round(calculation.distance / 100 * calculation.consumption * calculation.fuelPrice),
    [calculation],
  );

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCalculation({
      distance: Math.max(0, Number(distance) || 0),
      consumption: Math.max(0, Number(consumption) || 0),
      fuelPrice: fuelType === "gasoline" ? 22110 : 29330,
    });
  }

  return (
    <section className={styles.comparison}>
      <h2>So sánh giữa xe VinFast VF 8 The All New và xe động cơ đốt trong</h2>
      <div className={styles.comparisonGrid}>
        <form onSubmit={calculate}>
          <label>Quãng đường di chuyển/tháng<span><input aria-label="Quãng đường VF 8 All New mỗi tháng" min="0" onChange={(event) => setDistance(event.target.value)} type="number" value={distance} /><small>km</small></span></label>
          <fieldset><legend>Loại nhiên liệu sử dụng</legend><button aria-pressed={fuelType === "gasoline"} onClick={() => setFuelType("gasoline")} type="button">Xăng</button><button aria-pressed={fuelType === "diesel"} onClick={() => setFuelType("diesel")} type="button">Dầu</button></fieldset>
          <label>Mức tiêu thụ nhiên liệu/100km<span><input aria-label="Mức tiêu thụ nhiên liệu VF 8 All New" min="0" onChange={(event) => setConsumption(event.target.value)} step="0.1" type="number" value={consumption} /><small>lít</small></span></label>
          <button className={styles.compareButton} type="submit">SO SÁNH</button>
        </form>
        <article>
          <Image alt="VinFast VF 8 The All New" height={128} src="/media/vinfast/vf8-all-new/comparison-car.webp" width={230} />
          <p>Lợi thế chi phí nhiên liệu của VF 8 The All New</p>
          <strong>{currency.format(monthlySaving)} VNĐ/tháng</strong>
          <small>{currency.format(monthlySaving * 12)} VNĐ/năm</small>
        </article>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div><VinFastMark footer /><p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p></div>
      <nav aria-label="Thông tin VinFast"><a href="#tong-quan">VỀ VINFAST</a><a href="#cong-nghe">ĐIỀU KHOẢN CHÍNH SÁCH</a></nav>
      <div><a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a><a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a></div>
    </footer>
  );
}

export function Vf8AllNewExperience() {
  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <main>
        <section className={styles.hero}>
          <picture>
            <source media="(max-width: 620px)" srcSet="/media/vinfast/vf8-all-new/hero-mobile.webp" />
            <Image alt="VinFast VF 8 Thế Hệ Mới" fill priority sizes="100vw" src="/media/vinfast/vf8-all-new/hero.webp" />
          </picture>
        </section>
        <IntroSection />
        <DesignSection />
        <TechFluidSection />
        <HighlightSection />
        <InteriorSection />
        <TechnologySection />
        <Specifications />
        <ClosingBanner />
        <FuelComparison />
        <VehicleSupportChoice anchorId="ho-tro-vf8-all-new" from="/vehicles/vf-8-all-new" model="VF 8 The All New" />
      </main>
      <Footer />
    </div>
  );
}
