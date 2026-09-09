"use client";

import {
  ArrowRight,
  BatteryCharging,
  ChevronLeft,
  ChevronRight,
  Headphones,
  Menu,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState, type CSSProperties } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf9-experience.module.css";

const exteriorColors = [
  { name: "Zenith Grey", image: "/media/vinfast/vf9/color-zenith-grey.webp", detail: "/media/vinfast/vf9/detail-zenith-grey.webp", paint: "#777b7e" },
  { name: "Urban Mint", image: "/media/vinfast/vf9/color-urban-mint.webp", detail: "/media/vinfast/vf9/detail-urban-mint.webp", paint: "#788275" },
  { name: "Jet Black", image: "/media/vinfast/vf9/color-jet-black.webp", detail: "/media/vinfast/vf9/detail-jet-black.webp", paint: "#181b1b" },
  { name: "Ivy Green", image: "/media/vinfast/vf9/color-ivy-green.webp", detail: "/media/vinfast/vf9/detail-ivy-green.webp", paint: "#26382e" },
  { name: "Infinity Blanc", image: "/media/vinfast/vf9/color-infinity-blanc.webp", detail: "/media/vinfast/vf9/detail-infinity-blanc.webp", paint: "#f0f0ed" },
  { name: "Desat Silver", image: "/media/vinfast/vf9/color-desat-silver.webp", detail: "/media/vinfast/vf9/detail-desat-silver.webp", paint: "#c5c9c7" },
  { name: "Crimson Red", image: "/media/vinfast/vf9/color-crimson-red.webp", detail: "/media/vinfast/vf9/detail-crimson-red.webp", paint: "#b81834" },
] as const;

const interiorSlides = [
  {
    image: "/media/vinfast/vf9/interior-01.webp",
    alt: "Khoang lái VinFast VF 9",
    copy: "Tùy chọn hàng ghế cơ trưởng chỉnh điện, tích hợp làm mát, sưởi, massage và sạc không dây.",
  },
  {
    image: "/media/vinfast/vf9/interior-02.webp",
    alt: "Hàng ghế cơ trưởng VinFast VF 9",
    copy: "Không gian 6 hoặc 7 chỗ linh hoạt, rộng rãi và riêng tư cho mọi hành khách.",
  },
  {
    image: "/media/vinfast/vf9/interior-03.webp",
    alt: "Bệ điều khiển trung tâm VinFast VF 9",
    copy: "Nút chuyển số trực quan cùng bệ tì tay hoàn thiện bằng vật liệu cao cấp.",
  },
  {
    image: "/media/vinfast/vf9/interior-04.webp",
    alt: "Màn hình hàng ghế sau VinFast VF 9",
    copy: "Màn hình cảm ứng 8 inch giúp hàng ghế sau chủ động điều chỉnh tiện nghi.",
  },
] as const;

const technologyTabs = [
  {
    label: "Công nghệ cho cuộc sống",
    image: "/media/vinfast/vf9/technology-life.webp",
    alt: "Công nghệ VinFast VF 9 cho cuộc sống",
    copy: "Hệ thống công nghệ tập trung vào con người, kết nối hành trình liền mạch và trực quan.",
  },
  {
    label: "Trợ lý ảo tiếng Việt",
    image: "/media/vinfast/vf9/technology-assistant.webp",
    alt: "Trợ lý ảo tiếng Việt trên VinFast VF 9",
    copy: "Điều khiển các tính năng xe bằng giọng nói tự nhiên và nhận hỗ trợ thông minh trên mọi hành trình.",
  },
] as const;

const privileges = [
  {
    icon: "/media/vinfast/vf9/privilege-vip.webp",
    iconAlt: "Biểu tượng trải nghiệm VIP VinFast",
    title: "Trải nghiệm VIP tại xưởng dịch vụ VinFast",
    copy: [
      "Được tiếp đón và tư vấn bởi đội ngũ cố vấn dịch vụ, kỹ thuật viên giàu kinh nghiệm và có tay nghề cao nhất.",
      "Quý khách sẽ được ưu tiên sắp xếp lịch bảo dưỡng, sửa chữa theo thời gian và nhu cầu của bản thân. Xe được tiếp nhận, ưu tiên sửa chữa và kiểm tra chất lượng trước khi giao.",
    ],
  },
  {
    icon: "/media/vinfast/vf9/privilege-support.webp",
    iconAlt: "Biểu tượng dịch vụ sửa chữa VinFast",
    title: "Tiếp cận dịch vụ sửa chữa nhanh chóng và thuận tiện",
    copy: [
      "Miễn phí giao nhận xe tại địa điểm theo yêu cầu của Quý khách trong giờ hành chính, phạm vi 30 km từ xưởng dịch vụ VinFast gần nhất.",
      "Hỗ trợ chi phí sửa chữa cho đại lý, đảm bảo Quý khách được phục vụ nhanh chóng và hiệu quả nhất.",
    ],
  },
  {
    icon: "/media/vinfast/vf9/privilege-urgent.webp",
    iconAlt: "Biểu tượng chăm sóc khách hàng VinFast",
    title: "Dịch vụ chăm sóc Khách hàng tận tâm, chu đáo",
    copy: [
      "Hotline 24/7 với nhân viên Chăm sóc Khách hàng chuyên trách tiếp đón, đảm bảo mọi yêu cầu và phản hồi được giải đáp nhanh chóng, chuyên nghiệp.",
    ],
  },
  {
    icon: "/media/vinfast/vf9/privilege-charging.webp",
    iconAlt: "Biểu tượng sạc điện VinFast",
    title: "Sạc điện miễn phí lên tới 3 năm",
    copy: [
      "Theo chương trình miễn phí sạc từ V-Green, áp dụng kèm điều kiện và điều khoản. Vui lòng liên hệ đại lý để biết thông tin chi tiết.",
    ],
  },
] as const;

function VinFastBrand({ footer = false }: Readonly<{ footer?: boolean }>) {
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
      <VinFastBrand />
      <nav className={styles.mainNav} aria-label="Điều hướng chính">
        <a href="#tong-quan">Giới thiệu</a>
        <VehicleMegaMenu />
        <Link href="/motorbikes">Xe máy điện</Link>
        <a href="#ngoai-that">Phụ kiện xe</a>
        <a href="#dac-quyen">Dịch vụ hậu mãi</a>
        <a href="#pin-sac">Pin và trạm sạc</a>
        <a href="#cong-nghe">Lưu trữ năng lượng</a>
      </nav>
      <div className={styles.headerActions}>
        <Link className={styles.account} href="/account">TÀI KHOẢN</Link>
        <Link className={styles.primaryAction} href="/test-drive">ĐĂNG KÝ LÁI THỬ</Link>
        <button
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Đóng menu" : "Mở menu"}
          className={styles.menuButton}
          onClick={() => setMenuOpen((current) => !current)}
          type="button"
        >
          {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </div>
      {menuOpen ? (
        <nav className={styles.mobileNav} aria-label="Điều hướng di động">
          <a href="#tong-quan" onClick={() => setMenuOpen(false)}>Phiên bản</a>
          <MobileVehicleMenu onVehicleClick={() => setMenuOpen(false)} />
          <a href="#ngoai-that" onClick={() => setMenuOpen(false)}>Ngoại thất</a>
          <a href="#noi-that" onClick={() => setMenuOpen(false)}>Nội thất</a>
          <a href="#cong-nghe" onClick={() => setMenuOpen(false)}>Công nghệ</a>
          <a href="#dac-quyen" onClick={() => setMenuOpen(false)}>Đặc quyền</a>
          <a href="#pin-sac" onClick={() => setMenuOpen(false)}>Pin sạc</a>
        </nav>
      ) : null}
    </header>
  );
}

function ModelNavigation() {
  return (
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 9">
      <a className={styles.modelLogo} href="#dau-trang">VF9</a>
      <div className={styles.modelLinks}>
        <a href="#tong-quan">PHIÊN BẢN</a>
        <a href="#ngoai-that">NGOẠI THẤT</a>
        <a href="#noi-that">NỘI THẤT</a>
        <a href="#cong-nghe">CÔNG NGHỆ</a>
        <a href="#dac-quyen">ĐẶC QUYỀN</a>
        <a href="#pin-sac">PIN SẠC</a>
      </div>
      <Link className={styles.modelAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function Hero() {
  const stats = [
    ["Quãng đường di chuyển/lần sạc đầy", "626 km*"],
    ["Vận hành mạnh mẽ", "402 hp / 620 Nm"],
    ["Bảo hành xe 200.000 km hoặc", "10 năm"],
  ] as const;

  return (
    <section className={styles.hero} id="dau-trang">
      <Image
        alt="VinFast VF 9 - Sự lựa chọn của người thành đạt, tiên phong"
        className={styles.heroDesktop}
        fill
        priority
        sizes="100vw"
        src="/media/vinfast/vf9/hero.webp"
      />
      <Image
        alt=""
        className={styles.heroMobile}
        fill
        priority
        sizes="100vw"
        src="/media/vinfast/vf9/hero-mobile.webp"
      />
      <div className={styles.heroShade} />
      <div className={styles.heroCopy}>
        <span className={styles.heroModel}>VF9</span>
        <h1>Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong</h1>
      </div>
      <div className={styles.heroStats}>
        {stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <small className={styles.heroNote}>(*) Tiêu chuẩn WLTP, phiên bản Eco pin CATL.</small>
    </section>
  );
}

function PriceSection() {
  const variants = [
    { name: "VF 9 Eco", price: "1.280.600.000 VNĐ*", oldPrice: "1.348.000.000 VNĐ" },
    { name: "VF 9 Plus", price: "1.452.550.000 VNĐ*", oldPrice: "1.529.000.000 VNĐ" },
  ] as const;

  return (
    <section className={styles.pricing} id="tong-quan">
      <div className={styles.pricingIntro}>
        <span>Mẫu eSUV cỡ lớn</span>
        <h2>Hạng sang</h2>
        <p>
          VF 9 là mẫu SUV 7 chỗ hàng đầu của VinFast. Kiểu dáng tinh tế, công nghệ tiên tiến
          và sự tỉ mỉ trong từng chi tiết mang đến trải nghiệm cao cấp cho người sở hữu.
        </p>
      </div>
      <div className={styles.silhouette}>
        <Image alt="VinFast VF 9 nhìn từ trên cao" fill sizes="50vw" src="/media/vinfast/vf9/silhouette.webp" />
      </div>
      <div className={styles.priceCards}>
        {variants.map((variant) => (
          <article key={variant.name}>
            <span>{variant.name}</span>
            <small>Giá bán từ</small>
            <strong>{variant.price}</strong>
            <del>{variant.oldPrice}</del>
          </article>
        ))}
      </div>
      <p className={styles.priceNote}>
        Giá đã bao gồm VAT. Mức giá ưu đãi mang tính chất tham khảo và áp dụng theo điều khoản,
        điều kiện của chương trình.
      </p>
      <Link className={styles.sectionAction} href="/test-drive">ĐẶT LỊCH LÁI THỬ <ArrowRight aria-hidden="true" /></Link>
    </section>
  );
}

function ExteriorSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeColor = exteriorColors[activeIndex];

  return (
    <section className={styles.exterior} id="ngoai-that">
      <div className={styles.sectionHeading}>
        <span>Mạnh mẽ, bề thế</span>
        <h2>Nâng tầm thời thượng</h2>
        <p>
          Thiết kế lấy cảm hứng từ những chiếc du thuyền hạng sang, hòa hợp với đường nét
          mạnh mẽ, phóng khoáng để tạo nên vẻ ngoài độc đáo và sang trọng.
        </p>
      </div>
      <div className={styles.exteriorLead}>
        <Image alt="VinFast VF 9 mạnh mẽ và bề thế" fill sizes="100vw" src="/media/vinfast/vf9/lead.webp" />
      </div>
      <div className={styles.colorShowcase}>
        <div className={styles.colorCar}>
          <Image
            alt={`VinFast VF 9 màu ${activeColor.name}`}
            fill
            key={activeColor.image}
            sizes="(max-width: 760px) 100vw, 68vw"
            src={activeColor.image}
          />
        </div>
        <div className={styles.colorDetail}>
          <Image
            alt={`Chi tiết VinFast VF 9 màu ${activeColor.name}`}
            fill
            key={activeColor.detail}
            sizes="(max-width: 760px) 100vw, 32vw"
            src={activeColor.detail}
          />
        </div>
        <div className={styles.colorPicker} aria-label="Bảng màu VinFast VF 9">
          <div className={styles.colorDots}>
            {exteriorColors.map((color, index) => (
              <button
                aria-label={`Xem màu ${color.name}`}
                aria-pressed={index === activeIndex}
                className={index === activeIndex ? styles.colorActive : undefined}
                key={color.name}
                onClick={() => setActiveIndex(index)}
                style={{ "--paint": color.paint } as CSSProperties}
                type="button"
              />
            ))}
          </div>
          <strong aria-live="polite" className={styles.colorName}>{activeColor.name}</strong>
        </div>
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
      <div className={styles.interiorHero}>
        <Image alt="Không gian nội thất VinFast VF 9" fill sizes="100vw" src="/media/vinfast/vf9/interior-hero.webp" />
      </div>
      <div className={styles.interiorHeading}>
        <h2 className={styles.interiorTitle}>
          <span>Bản giao hưởng</span>
          <span>của <strong>thẩm mỹ</strong> và</span>
          <strong>trải nghiệm <em>tiện nghi</em></strong>
        </h2>
        <p>
          Ngôn ngữ thiết kế tối giản mang hơi hướng tương lai, phối hợp cùng vật liệu cao cấp,
          thân thiện với môi trường, đem lại không gian khoáng đạt trên mọi hành trình.
        </p>
      </div>
      <div className={styles.interiorGallery}>
        <div className={styles.interiorStage}>
          <Image alt={activeSlide.alt} fill key={activeSlide.image} sizes="(max-width: 760px) 100vw, 65vw" src={activeSlide.image} />
          <button aria-label="Nội thất trước" className={styles.previous} onClick={() => move(-1)} type="button">
            <ChevronLeft aria-hidden="true" />
          </button>
          <button aria-label="Nội thất tiếp theo" className={styles.next} onClick={() => move(1)} type="button">
            <ChevronRight aria-hidden="true" />
          </button>
        </div>
        <div className={styles.interiorDetails}>
          <span>0{activeIndex + 1} / 04</span>
          <p>{activeSlide.copy}</p>
          <div className={styles.thumbnails} aria-label="Chọn ảnh nội thất VF 9">
            {interiorSlides.map((slide, index) => (
              <button
                aria-label={`Ảnh nội thất ${index + 1}`}
                aria-pressed={index === activeIndex}
                key={slide.image}
                onClick={() => setActiveIndex(index)}
                type="button"
              >
                <Image alt="" fill sizes="90px" src={slide.image} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function TechnologySection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeTab = technologyTabs[activeIndex];

  return (
    <section className={styles.technology} id="cong-nghe">
      <div className={styles.technologyHeading}>
        <span>Công nghệ</span>
        <h2>Cho cuộc sống</h2>
        <p>
          VinFast hợp tác cùng những đối tác hàng đầu toàn cầu để ứng dụng công nghệ hiện đại,
          hướng tới trải nghiệm tự nhiên và tốt đẹp hơn.
        </p>
      </div>
      <div className={styles.technologyTabs} role="tablist" aria-label="Công nghệ VinFast VF 9">
        {technologyTabs.map((tab, index) => (
          <button
            aria-selected={index === activeIndex}
            key={tab.label}
            onClick={() => setActiveIndex(index)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className={styles.technologyVisual}>
        <Image alt={activeTab.alt} fill key={activeTab.image} sizes="100vw" src={activeTab.image} />
        <div>
          <Sparkles aria-hidden="true" />
          <strong>{activeTab.label}</strong>
          <p>{activeTab.copy}</p>
        </div>
      </div>
    </section>
  );
}

function PrivilegeSection() {
  return (
    <section className={styles.privilege} id="dac-quyen">
      <Image alt="Đặc quyền xứng tầm tinh hoa của VinFast VF 9" fill sizes="100vw" src="/media/vinfast/vf9/exclusive.webp" />
      <div className={styles.privilegeInner}>
        <div className={styles.privilegeHeading}>
          <span>Đặc quyền</span>
          <h2>Xứng tầm tinh hoa</h2>
        </div>
        <div className={styles.privilegeGrid}>
          {privileges.map((privilege) => (
            <article key={privilege.title}>
              <div className={styles.privilegeCardHeading}>
                <Image alt={privilege.iconAlt} height={80} src={privilege.icon} width={80} />
                <h3>{privilege.title}</h3>
              </div>
              <ul>
                {privilege.copy.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function ChargingSection() {
  const cards = [
    {
      image: "/media/vinfast/vf9/charging-station.webp",
      alt: "Hệ thống trạm sạc VinFast",
      icon: BatteryCharging,
      title: "Hệ thống trạm sạc phủ 100% cao tốc",
      value: "34/34 Tỉnh và Thành phố.",
    },
    {
      image: "/media/vinfast/vf9/home-charger.webp",
      alt: "Sạc VinFast tại nhà",
      icon: ShieldCheck,
      title: "Sạc tại nhà",
      value: "chủ động và tiện lợi",
    },
    {
      image: "/media/vinfast/vf9/battery-lease.webp",
      alt: "Giải pháp pin VinFast",
      icon: Headphones,
      title: "Giải pháp pin và hỗ trợ",
      value: "an tâm trên mọi hành trình",
    },
  ] as const;

  return (
    <section className={styles.charging} id="pin-sac">
      <div className={styles.chargingIntro}>
        <div>
          <span>Giải pháp</span>
          <h2>Pin và Trạm sạc</h2>
          <p>Đa dạng giải pháp sạc đáp ứng nhu cầu sử dụng của Khách hàng một cách thuận tiện nhất.</p>
        </div>
        <div className={styles.chargingHero}>
          <Image alt="Giải pháp pin và trạm sạc VinFast" fill sizes="50vw" src="/media/vinfast/vf9/charging-hero.webp" />
        </div>
      </div>
      <div className={styles.chargingGrid}>
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <article key={card.title}>
              <div><Image alt={card.alt} fill sizes="(max-width: 760px) 100vw, 33vw" src={card.image} /></div>
              <Icon aria-hidden="true" />
              <h3>{card.title}</h3>
              <strong>{card.value}</strong>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <VinFastBrand footer />
      <p>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</p>
      <div>
        <Link href="/about">Về VinFast</Link>
        <Link href="/vehicles">Ô tô điện</Link>
        <Link href="/test-drive">Đặt lịch lái thử</Link>
      </div>
      <small>VinFast. All rights reserved. © Copyright 2026</small>
    </footer>
  );
}

export function Vf9Experience() {
  return (
    <div className={styles.page}>
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <Hero />
        <PriceSection />
        <ExteriorSection />
        <InteriorSection />
        <TechnologySection />
        <PrivilegeSection />
        <ChargingSection />
        <VehicleSupportChoice anchorId="ho-tro-vf9" from="vf9-page" model="VF 9" />
      </main>
      <Footer />
    </div>
  );
}
