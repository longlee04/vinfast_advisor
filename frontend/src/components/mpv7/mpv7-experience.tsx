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
import { useMemo, useState, type FormEvent } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./mpv7-experience.module.css";

const gallery = [
  { image: "/media/vinfast/mpv7/gallery-1.webp", alt: "VinFast VF MPV 7 Solar Ruby nhìn từ phía trước" },
  { image: "/media/vinfast/mpv7/gallery-2.webp", alt: "VinFast VF MPV 7 Solar Ruby nhìn từ phía sau" },
  { image: "/media/vinfast/mpv7/gallery-3.webp", alt: "VinFast VF MPV 7 mở cửa, khoang xe rộng rãi" },
  { image: "/media/vinfast/mpv7/gallery-4.webp", alt: "VinFast VF MPV 7 nhìn từ trên cao" },
  { image: "/media/vinfast/mpv7/gallery-5.webp", alt: "Khoang ghế trước VinFast VF MPV 7" },
] as const;

const specifications = [
  ["Dài x rộng x Cao", "4740 x 1872 x 1734"],
  ["Chiều dài cơ sở", "2840 mm"],
  ["Khoảng sáng gầm xe", "185 mm"],
  ["Công suất tối đa", "150 kW"],
  ["Mô men xoắn cực đại", "280 Nm"],
  ["Quãng đường chạy (NEDC)", "450 km/lần sạc đầy"],
  ["Dung lượng pin khả dụng", "60,13 kWh"],
  ["Công suất sạc nhanh DC tối đa", "80 kW"],
  ["Thời gian nạp pin nhanh nhất", "30 phút (10%-70%)"],
  ["Dẫn động", "FWD/Cầu trước"],
  ["Chế độ lái", "Eco/Normal/Sport"],
  ["Kích thước la-zăng", "Mâm hợp kim 19 inch"],
  ["Hệ thống treo (trước/sau)", "MacPherson/Đa liên kết"],
  ["Hệ thống phanh (trước/sau)", "Đĩa thông gió/Đĩa"],
  ["Đèn chiếu sáng phía trước", "LED"],
  ["Đóng/mở cốp sau", "Chỉnh cơ"],
  ["Hệ thống điều hòa", "Tự động 1 vùng"],
  ["Màn hình giải trí cảm ứng", "10,1 inch"],
  ["Hệ thống loa", "4 loa"],
  ["Ghế lái", "Chỉnh cơ 6 hướng"],
] as const;

const currency = new Intl.NumberFormat("vi-VN");

function VinFastLogo() {
  return (
    <Link className={styles.brand} href="/" aria-label="VinFast - Trang chủ">
      <Image
        alt="VinFast"
        height={58}
        priority
        src="/media/vinfast/vf2-page/vinfast-logo.webp"
        style={{ width: "auto", height: "auto" }}
        width={290}
      />
    </Link>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className={styles.header}>
      <VinFastLogo />
      <nav className={styles.mainNav} aria-label="Điều hướng chính">
        <a href="#tong-quan">Giới thiệu</a>
        <VehicleMegaMenu />
        <Link href="/motorbikes">Xe máy điện</Link>
        <a href="#thong-so">Phụ kiện xe</a>
        <a href="#ho-tro-mpv7">Dịch vụ hậu mãi</a>
        <a href="#so-sanh">Pin và trạm sạc</a>
        <a href="#so-sanh">Lưu trữ năng lượng</a>
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
          <a href="#tong-quan" onClick={() => setMenuOpen(false)}>Giới thiệu</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#thong-so" onClick={() => setMenuOpen(false)}>Thông số</a>
          <a href="#so-sanh" onClick={() => setMenuOpen(false)}>So sánh chi phí</a>
        </nav>
      ) : null}
    </header>
  );
}

function Gallery() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = gallery[activeIndex];

  function move(direction: -1 | 1) {
    setActiveIndex((current) => (current + direction + gallery.length) % gallery.length);
  }

  return (
    <section className={styles.gallery} id="tong-quan" aria-label="Hình ảnh VinFast VF MPV 7">
      <Image alt={activeSlide.alt} fill key={activeSlide.image} priority sizes="100vw" src={activeSlide.image} />
      <p>Chi tiết trang bị có thể thay đổi tùy theo phiên bản thương mại.</p>
      <button aria-label="Ảnh trước" className={styles.previous} onClick={() => move(-1)} type="button">
        <ChevronLeft aria-hidden="true" />
      </button>
      <button aria-label="Ảnh tiếp theo" className={styles.next} onClick={() => move(1)} type="button">
        <ChevronRight aria-hidden="true" />
      </button>
      <div className={styles.dots} aria-label="Chọn ảnh VF MPV 7">
        {gallery.map((slide, index) => (
          <button
            aria-label={`Ảnh ${index + 1}`}
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

function Specifications() {
  return (
    <section className={styles.specifications} id="thong-so">
      <div className={styles.productLine}>
        <Image alt="VF MPV 7" height={20} src="/media/vinfast/mpv7/logo.webp" width={175} />
        <span>Giá bán từ</span>
        <strong>712.500.000 VNĐ*</strong>
        <del>750.000.000 VNĐ</del>
      </div>
      <p className={styles.promotionNote}>
        (*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.
      </p>
      <dl className={styles.specGrid}>
        {specifications.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Link className={styles.primaryAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
      <div className={styles.notes}>
        <strong>(*) Lưu ý:</strong>
        <ul>
          <li>Hình ảnh xe phiên bản tiền thương mại. Phiên bản thương mại có thể có một số điểm khác biệt.</li>
          <li>Các thông tin sản phẩm có thể thay đổi mà không cần báo trước.</li>
        </ul>
      </div>
    </section>
  );
}

type ComparisonValues = Readonly<{
  consumption: number;
  distance: number;
  fuelPrice: number;
}>;

function FuelComparison() {
  const [distance, setDistance] = useState("3000");
  const [consumption, setConsumption] = useState("8");
  const [fuelPrice, setFuelPrice] = useState("23000");
  const [fuelType, setFuelType] = useState<"petrol" | "diesel">("petrol");
  const [values, setValues] = useState<ComparisonValues>({ distance: 3000, consumption: 8, fuelPrice: 23000 });

  const monthlySaving = useMemo(
    () => Math.round((values.distance / 100) * values.consumption * values.fuelPrice),
    [values],
  );

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValues({
      distance: Math.max(0, Number(distance) || 0),
      consumption: Math.max(0, Number(consumption) || 0),
      fuelPrice: Math.max(0, Number(fuelPrice) || 0),
    });
  }

  return (
    <section className={styles.comparison} id="so-sanh">
      <h2>So sánh giữa xe VinFast VF MPV 7 và xe động cơ đốt trong</h2>
      <div className={styles.comparisonGrid}>
        <form onSubmit={calculate}>
          <label>
            Quãng đường di chuyển/tháng
            <span><input aria-label="Quãng đường di chuyển mỗi tháng" min="0" onChange={(event) => setDistance(event.target.value)} type="number" value={distance} /><small>km</small></span>
          </label>
          <fieldset>
            <legend>Loại nhiên liệu sử dụng</legend>
            <button aria-pressed={fuelType === "petrol"} onClick={() => setFuelType("petrol")} type="button">Xăng</button>
            <button aria-pressed={fuelType === "diesel"} onClick={() => setFuelType("diesel")} type="button">Dầu</button>
          </fieldset>
          <label>
            Mức tiêu thụ nhiên liệu/100km
            <span><input aria-label="Mức tiêu thụ nhiên liệu trên 100 km" min="0" onChange={(event) => setConsumption(event.target.value)} step="0.1" type="number" value={consumption} /><small>lít</small></span>
          </label>
          <label>
            Giá nhiên liệu mỗi lít
            <span><input aria-label="Giá nhiên liệu mỗi lít" min="0" onChange={(event) => setFuelPrice(event.target.value)} step="100" type="number" value={fuelPrice} /><small>VNĐ</small></span>
          </label>
          <button className={styles.compareButton} type="submit">So sánh</button>
        </form>
        <article className={styles.result} aria-live="polite">
          <div>
            <span>Lợi thế chi phí nhiên liệu của</span>
            <strong>VF MPV 7</strong>
          </div>
          <Image alt="VinFast VF MPV 7 màu Infinity Blanc" height={128} src="/media/vinfast/mpv7/comparison-car.webp" width={230} />
          <p>Chi phí nhiên liệu tiết kiệm/tháng</p>
          <strong>{currency.format(monthlySaving)} VNĐ</strong>
          <small>Tương đương {currency.format(monthlySaving * 12)} VNĐ/năm</small>
        </article>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <VinFastLogo />
      <p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p>
      <a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a>
      <a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a>
    </footer>
  );
}

export function Mpv7Experience() {
  return (
    <div className={styles.page}>
      <Header />
      <main>
        <Gallery />
        <Specifications />
        <FuelComparison />
        <VehicleSupportChoice anchorId="ho-tro-mpv7" from="/vehicles/vf-mpv-7" model="VF MPV 7" />
      </main>
      <Footer />
    </div>
  );
}
