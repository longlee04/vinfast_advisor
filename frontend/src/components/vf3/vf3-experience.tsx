"use client";

import { Mail, Menu, Phone, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";

import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

import styles from "./vf3-experience.module.css";

const colorFrames = [
  { slug: "summer-yellow", name: "Summer Yellow", image: "/media/vinfast/vf3/color-summer-yellow.webp", paint: "#f4d628" },
  { slug: "rose-pink", name: "Rose Pink", image: "/media/vinfast/vf3/color-rose-pink.webp", paint: "#bd8796" },
  { slug: "zenith-grey", name: "Zenith Grey", image: "/media/vinfast/vf3/color-zenith-grey.webp", paint: "#858588" },
  { slug: "solar-ruby", name: "Solar Ruby", image: "/media/vinfast/vf3/color-solar-ruby.webp", paint: "#e20b3d" },
  { slug: "sky-blue", name: "Sky Blue", image: "/media/vinfast/vf3/color-sky-blue.webp", paint: "#38c7d8" },
  { slug: "urban-mint", name: "Urban Mint", image: "/media/vinfast/vf3/color-urban-mint.webp", paint: "#7c8273" },
  { slug: "infinity-blanc", name: "Infinity Blanc", image: "/media/vinfast/vf3/color-infinity-blanc.webp", paint: "#f4f4f1" },
] as const;

const SPIN_FRAME_COUNT = 36;
const DRAG_STEP_PX = 28;

function getSpinFrameImage(color: (typeof colorFrames)[number], frameIndex: number) {
  if (frameIndex === 0) return color.image;
  return `/media/vinfast/vf3/color-${color.slug}-f${String(frameIndex + 1).padStart(2, "0")}.webp`;
}

const specifications = [
  ["Động cơ", "01 Motor"],
  ["Công suất tối đa (kW)", "30"],
  ["Mô men xoắn cực đại (Nm)", "110"],
  ["Quãng đường chạy một lần sạc đầy (km)", "215"],
  ["Thời gian nạp pin nhanh nhất", "36 phút (10% - 70%)"],
  ["Dẫn động", "RWD/Cầu sau"],
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
          <a href="#ngoai-that" onClick={() => setMenuOpen(false)}>Ngoại thất</a>
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
    <nav className={styles.modelNav} aria-label="Điều hướng VinFast VF 3">
      <a className={styles.modelLogo} href="#dau-trang" aria-label="Về đầu trang VF 3">
        <Image alt="VF 3" height={30} src="/media/vinfast/vf3/vf3-logo.svg" width={117} />
      </a>
      <div className={styles.modelLinks}>
        <a href="#gia-ban">Giá bán</a>
        <a href="#gioi-thieu">Giới thiệu</a>
        <a href="#ngoai-that">Ngoại thất</a>
        <a href="#noi-that">Nội thất</a>
        <a href="#thong-so">Thông số</a>
      </div>
      <Link className={styles.consultButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
    </nav>
  );
}

function PriceSection() {
  return (
    <section className={styles.pricing} id="gia-ban">
      <div className={styles.container}>
        <h2>Tùy chọn cho ngân sách của bạn.</h2>
        <div className={styles.priceCards}>
          <article>
            <h3>VF 3 Eco</h3>
            <span>Giá bán từ</span>
            <p><strong>270.750.000</strong> VNĐ*</p>
            <del>285.000.000 VNĐ</del>
          </article>
          <article>
            <h3>VF 3 Plus</h3>
            <span>Giá bán từ</span>
            <p><strong>281.200.000</strong> VNĐ*</p>
            <del>296.000.000 VNĐ</del>
          </article>
        </div>
        <Link className={styles.depositButton} href="/test-drive">ĐẶT LỊCH LÁI THỬ</Link>
        <small>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.</small>
      </div>
    </section>
  );
}

function ColorShowcase() {
  const [colorIndex, setColorIndex] = useState(0);
  const [spinFrame, setSpinFrame] = useState(0);
  const pointerStart = useRef<number | null>(null);
  const activeColor = colorFrames[colorIndex];
  const activeImage = getSpinFrameImage(activeColor, spinFrame);

  function rotateBy(step: number) {
    setSpinFrame((frame) => (frame + step + SPIN_FRAME_COUNT) % SPIN_FRAME_COUNT);
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    pointerStart.current = event.clientX;
    if ("setPointerCapture" in event.currentTarget) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (pointerStart.current === null) return;
    const distance = event.clientX - pointerStart.current;
    if (Math.abs(distance) < DRAG_STEP_PX) return;
    const steps = Math.max(1, Math.floor(Math.abs(distance) / DRAG_STEP_PX));
    rotateBy(distance < 0 ? steps : -steps);
    pointerStart.current = event.clientX;
  }

  function handlePointerEnd(event: PointerEvent<HTMLDivElement>) {
    pointerStart.current = null;
    if (
      "hasPointerCapture" in event.currentTarget
      && event.currentTarget.hasPointerCapture(event.pointerId)
    ) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <section className={styles.colorSection} id="ngoai-that">
      <div className={styles.container}>
        <h2>VinFast VF 3 - Tự do sáng tạo, toả sáng chất riêng!</h2>
        <p>Với dải màu ngoại thất đa dạng và độc đáo, bao gồm 7 tùy chọn màu sắc trẻ trung và thời thượng, VF 3 là sự lựa chọn hoàn hảo giúp bạn thoả sức thể hiện sự khác biệt và cá tính của riêng mình. Dù bạn là ai, hãy lựa chọn màu sắc và trang bị VF 3 theo sở thích của bạn, và cùng VinFast biến ước mơ của bạn thành hiện thực.</p>
        <div
          aria-label="Xoay 360° VinFast VF 3"
          aria-valuemax={SPIN_FRAME_COUNT}
          aria-valuemin={1}
          aria-valuenow={spinFrame + 1}
          className={styles.colorStage}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") rotateBy(-1);
            if (event.key === "ArrowRight") rotateBy(1);
          }}
          onPointerCancel={handlePointerEnd}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerEnd}
          role="slider"
          tabIndex={0}
        >
          <div className={styles.vehicleFrame}>
            <Image
              alt={`VinFast VF 3 màu ${activeColor.name}`}
              fill
              key={activeImage}
              priority
              sizes="(max-width: 760px) 100vw, 900px"
              src={activeImage}
            />
          </div>
          <span className={styles.spinLabel}>360°</span>
        </div>
        <span className={styles.colorName} aria-live="polite" role="status">
          {activeColor.name}
        </span>
        <div className={styles.colorControls} aria-label="Bảng màu VinFast VF 3">
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
      </div>
    </section>
  );
}

function ExteriorStory() {
  return (
    <section className={styles.exteriorStory}>
      <div className={styles.storyContainer}>
        <div className={styles.storyCopy}>
          <h2>VinFast VF 3 - Biểu tượng mới của cuộc sống đô thị.</h2>
          <p>Vượt lên trên một phương tiện di chuyển thông thường, VinFast VF 3 là biểu tượng mới mang tính cách mạng trong cuộc sống đô thị. Với thiết kế hiện đại, hiệu suất vận hành linh hoạt, tính năng an toàn tiên tiến, cùng chi phí vận hành siêu rẻ, VF 3 sẽ mở ra một cách tiếp cận hoàn toàn mới trong việc lựa chọn phương tiện di chuyển hàng ngày, mang lại sự thuận tiện, dễ dàng và đặc biệt thoải mái cho tất cả mọi người.</p>
        </div>
        <Image alt="Ngoại thất phía sau VinFast VF 3" height={713} sizes="(max-width: 900px) 100vw, 1200px" src="/media/vinfast/vf3/exterior-rear.webp" width={1824} />
        <div className={styles.secondaryStory}>
          <h3>VF 3 không chỉ là một chiếc xe điện tiên tiến.</h3>
          <p>Mà còn là một tác phẩm nghệ thuật kết hợp giữa công nghệ và sự sáng tạo trong thiết kế.</p>
        </div>
        <Image alt="Ngoại thất phía trước VinFast VF 3" height={1027} sizes="(max-width: 900px) 100vw, 1200px" src="/media/vinfast/vf3/exterior-front.webp" width={1824} />
      </div>
    </section>
  );
}

function InteriorAndCharging() {
  return (
    <>
      <section className={styles.interior} id="noi-that">
        <div className={styles.container}>
          <h2>VinFast VF 3 - Luôn đủ chỗ cho mọi người!</h2>
          <p>Thiết kế thông minh và không gian nội thất tối ưu hóa của VF 3 mang lại trải nghiệm di chuyển tiện lợi, đảm bảo sự thoải mái và tiện nghi cho cả 4 chỗ ngồi. Màu sắc nội thất trang nhã, trẻ trung và cá tính, cùng chất liệu thân thiện tạo ra một không gian đặc biệt, nơi chứa đựng những kỷ niệm đáng nhớ trên mọi hành trình khám phá phong cách sống của riêng bạn!</p>
          <Image alt="Khoang nội thất VinFast VF 3" height={685} sizes="(max-width: 900px) 100vw, 1200px" src="/media/vinfast/vf3/interior.webp" width={1216} />
        </div>
      </section>
      <section className={styles.charging} id="tram-sac">
        <div>
          <h2>3,5 km - Khoảng cách nhỏ cho mục tiêu lớn</h2>
          <p>Định hình tiên phong thúc đẩy ngành công nghiệp xe điện, hướng tới một tương lai Xanh và Thông Minh, VinFast đã đầu tư hàng trăm triệu USD phát triển hạ tầng, từng bước &quot;phủ rộng&quot; trạm sạc xe điện:</p>
          <ul>
            <li>Hệ thống trạm sạc xe điện VinFast trải dài 34 Tỉnh và Thành phố.</li>
            <li>106 tuyến quốc lộ quan trọng đều có trạm sạc.</li>
            <li>80/85 thành phố đã được lắp đặt hệ thống trạm sạc.</li>
            <li>Khoảng cách ngắn 3,5 km giữa 2 trạm sạc trong thành phố.</li>
          </ul>
          <blockquote>VinFast cam kết nỗ lực mang đến nhiều tiện ích, giúp hành trình lái xe điện của người Việt thật dễ dàng!</blockquote>
        </div>
        <Image alt="Mạng lưới trạm sạc VinFast trên toàn quốc" height={1026} sizes="(max-width: 800px) 100vw, 440px" src="/media/vinfast/vf3/charging-map.webp" width={890} />
      </section>
    </>
  );
}

function Specifications() {
  return (
    <section className={styles.specifications} id="thong-so">
      <div className={styles.container}>
        <h2>Thông số kỹ thuật</h2>
        <dl>
          {specifications.map(([term, value]) => (
            <div key={term}><dt>{term}</dt><dd>{value}</dd></div>
          ))}
        </dl>
        <div className={styles.specVehicle}>
          <Image alt="VinFast VF 3 nhìn từ phía sau" fill sizes="(max-width: 760px) 100vw, 780px" src="/media/vinfast/vf3/side-profile.webp" />
        </div>
      </div>
    </section>
  );
}

function FuelComparison() {
  const [distance, setDistance] = useState("");
  const [consumption, setConsumption] = useState("");
  const [fuelType, setFuelType] = useState<"gasoline" | "diesel">("gasoline");
  const [monthlySaving, setMonthlySaving] = useState<number | null>(null);

  function compareFuelCost() {
    const monthlyDistance = Number(distance.replace(",", "."));
    const fuelConsumption = Number(consumption.replace(",", "."));
    const fuelPrice = fuelType === "gasoline" ? 22_060 : 27_130;
    setMonthlySaving(Math.max(0, Math.round(monthlyDistance / 100 * fuelConsumption * fuelPrice)));
  }

  return (
    <section className={styles.comparison} id="so-sanh">
      <div className={styles.container}>
        <h2>So sánh giữa xe VinFast VF 3 và xe động cơ đốt trong</h2>
        <div className={styles.comparisonGrid}>
          <form onSubmit={(event) => { event.preventDefault(); compareFuelCost(); }}>
            <p>Vui lòng nhập thông tin xe động cơ đốt trong cần so sánh:</p>
            <fieldset>
              <legend>Loại nhiên liệu sử dụng</legend>
              <label><input checked={fuelType === "gasoline"} name="fuel" onChange={() => setFuelType("gasoline")} type="radio" /> Xăng</label>
              <label><input checked={fuelType === "diesel"} name="fuel" onChange={() => setFuelType("diesel")} type="radio" /> Dầu</label>
            </fieldset>
            <label className={styles.compareField}>Mức tiêu thụ nhiên liệu/100km *<span><input aria-label="Mức tiêu thụ nhiên liệu" inputMode="decimal" onChange={(event) => setConsumption(event.target.value)} value={consumption} /><b>lít</b></span></label>
            <p>Vui lòng nhập quãng đường di chuyển mỗi tháng:</p>
            <label className={styles.compareField}>Quãng đường di chuyển/tháng *<span><input aria-label="Quãng đường di chuyển mỗi tháng" inputMode="decimal" onChange={(event) => setDistance(event.target.value)} value={distance} /><b>km</b></span></label>
            <small>(*) Nhập số (phân cách bằng dấu phẩy &quot;,&quot;). Ví dụ: 6,5 lít.</small>
            <button type="submit">SO SÁNH</button>
          </form>
          <div className={styles.results}>
            <div className={styles.resultHeading}><h3>Lợi thế chi phí nhiên liệu</h3><Image alt="VinFast VF 3" height={128} src="/media/vinfast/vf3/comparison-car.webp" width={230} /></div>
            <p>Chi phí nhiên liệu/tháng của VF 3 <strong>0 VNĐ</strong></p>
            {monthlySaving === null ? <span>(*) Chưa có dữ liệu so sánh. Vui lòng nhập thông tin!</span> : (
              <>
                <p>Chi phí nhiên liệu tiết kiệm/tháng <strong>{new Intl.NumberFormat("vi-VN").format(monthlySaving)} VNĐ</strong></p>
                <p>Chi phí nhiên liệu tiết kiệm/năm <strong>{new Intl.NumberFormat("vi-VN").format(monthlySaving * 12)} VNĐ</strong></p>
              </>
            )}
          </div>
        </div>
        <p className={styles.disclaimer}>(*) Lưu ý: Các thông số, đơn giá và giả định sử dụng để tính chi phí nhiên liệu có thể thay đổi. Công cụ chỉ mang tính tham khảo.</p>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.companyInfo}>
        <VinFastMark footer />
        <h2>CÔNG TY TNHH KINH DOANH THƯƠNG MẠI VÀ DỊCH VỤ VINFAST</h2>
        <p><strong>MST/MSDN:</strong> 0108926276 do Sở KHĐT TP Hà Nội cấp lần đầu ngày 01/10/2019 và các lần thay đổi tiếp theo.</p>
        <p><strong>Địa chỉ trụ sở chính:</strong> Số 7, Đường Bằng Lăng 1, Khu đô thị Vinhomes Riverside, Phường Phúc Lợi, Thành phố Hà Nội, Việt Nam.</p>
      </div>
      <nav aria-label="Thông tin VinFast"><a href="#gioi-thieu">VỀ VINFAST</a><a href="#gioi-thieu">VỀ VINGROUP</a><a href="#ngoai-that">TIN TỨC</a><a href="#tram-sac">SHOWROOM VÀ ĐẠI LÝ</a><a href="#lien-he">ĐIỀU KHOẢN CHÍNH SÁCH</a></nav>
      <div className={styles.customerService}>
        <h2>HOTLINE</h2>
        <a href="tel:1900232389"><Phone aria-hidden="true" />1900 23 23 89 - Nhánh 1</a>
        <a href="mailto:support.vn@vinfastauto.com"><Mail aria-hidden="true" />support.vn@vinfastauto.com</a>
      </div>
      <div className={styles.newsletter}>
        <h2>ĐĂNG KÝ NHẬN THÔNG TIN</h2>
        <p>Đăng ký nhận thông tin chương trình khuyến mãi, dịch vụ VinFast</p>
        <label><span className="sr-only">Email của quý khách</span><input placeholder="Nhập email của quý khách" type="email" /><button type="button">Đăng ký</button></label>
      </div>
    </footer>
  );
}

export function Vf3Experience() {
  return (
    <div className={styles.page} id="dau-trang">
      <GlobalHeader />
      <ModelNavigation />
      <main>
        <section className={styles.hero}>
          <Image alt="VinFast VF 3 - Chiếc xe đô thị dành cho thế hệ người Việt mới" fill priority sizes="100vw" src="/media/vinfast/vf3/campaign-hero.webp" />
        </section>
        <PriceSection />
        <section className={styles.introduction} id="gioi-thieu">
          <div className={styles.container}>
            <h2>VinFast VF 3 - Xe nhỏ, giá trị lớn.</h2>
            <p>Với thiết kế tối giản, nhỏ gọn, cá tính và năng động, VinFast VF 3 sẽ luôn cùng bạn hoà nhịp với xu thế công nghệ di chuyển xanh toàn cầu, trải nghiệm giá trị trên mỗi hành trình, và tự do thể hiện phong cách sống.</p>
            <Image alt="VinFast VF 3 - Sáng tạo chất riêng" height={1125} sizes="(max-width: 900px) 100vw, 1200px" src="/media/vinfast/vf3/campaign-feature.webp" width={2400} />
          </div>
        </section>
        <ColorShowcase />
        <ExteriorStory />
        <InteriorAndCharging />
        <Specifications />
        <FuelComparison />
        <VehicleSupportChoice anchorId="lien-he" from="/vehicles/vf-3" model="VF 3" />
      </main>
      <Footer />
    </div>
  );
}
