"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useState } from "react";

import styles from "@/components/home/home-experience.module.css";
import { HomeHeroSlider } from "@/components/home/home-hero-slider";
import { HomeQuickLinks } from "@/components/home/home-quick-links";
import { HomeVehicleSlider } from "@/components/home/home-vehicle-slider";
import { ScrollReveal } from "@/components/shared/scroll-reveal";
import { homepageAccessories, homepageCars, homepageMotorbikes } from "@/data/homepage";

export function HomeExperience() {
  const [newsletterSubmitted, setNewsletterSubmitted] = useState(false);

  function submitNewsletter(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setNewsletterSubmitted(true);
  }

  return (
    <div className={styles.root}>
      <HomeHeroSlider />
      <HomeQuickLinks />

      <ScrollReveal className={styles.revealBlock} durationMs={720}>
        <HomeVehicleSlider
          ariaLabel="Ô tô điện VinFast"
          dotLabel="mẫu ô tô"
          initialIndex={1}
          items={homepageCars}
          variant="car"
        />
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock} durationMs={720}>
        <HomeVehicleSlider
          ariaLabel="Xe máy điện VinFast"
          dotLabel="mẫu xe máy điện"
          initialIndex={1}
          items={homepageMotorbikes}
          variant="motorbike"
        />
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock}>
        <section aria-labelledby="homepage-accessories-title" className={styles.accessories} id="accessories">
          <header className={styles.sectionHeader}>
            <h2 id="homepage-accessories-title">Phụ kiện xe</h2>
            <Link href="/vehicles">XEM THÊM</Link>
          </header>
          <div className={styles.accessoryGrid}>
            {homepageAccessories.map((accessory) => (
              <Link className={styles.accessoryCard} href={accessory.href} key={accessory.name}>
                <span className={styles.accessoryImage}>
                  <Image alt={accessory.name} fill sizes="(max-width: 720px) 80vw, 25vw" src={accessory.image} />
                </span>
                <strong>{accessory.name}</strong>
                <span>{accessory.price}</span>
              </Link>
            ))}
          </div>
        </section>
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock}>
        <section aria-label="Giải pháp pin và trạm sạc" className={styles.charging} id="charging">
          <div className={styles.chargingStack}>
            <Link className={styles.chargingCard} href="/locations">
              <Image alt="Trạm sạc ô tô điện VinFast" fill sizes="(max-width: 760px) 100vw, 50vw" src="/media/vinfast/home/charging-car.webp" />
              <strong>Pin &amp; Trạm sạc ô tô điện</strong>
            </Link>
            <Link className={styles.chargingCard} href="/locations">
              <Image alt="Trạm sạc xe máy điện VinFast" fill sizes="(max-width: 760px) 100vw, 50vw" src="/media/vinfast/home/charging-motorbike.webp" />
              <strong>Pin &amp; Trạm sạc xe máy điện</strong>
            </Link>
          </div>
          <div className={styles.mobileCharger}>
            <div>
              <h2>Thiết bị sạc di động</h2>
              <p>VinFast cung cấp đa dạng giải pháp sạc để đáp ứng nhu cầu sử dụng của khách hàng một cách thuận tiện nhất.</p>
              <Link href="/locations">XEM CHI TIẾT</Link>
            </div>
            <span>
              <Image alt="Thiết bị sạc di động VinFast" fill sizes="(max-width: 760px) 100vw, 50vw" src="/media/vinfast/home/mobile-charger.webp" />
            </span>
          </div>
        </section>
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock} direction="left">
        <section aria-labelledby="homepage-service-title" className={styles.service} id="service">
          <Image alt="Kỹ thuật viên VinFast bảo dưỡng ô tô" fill sizes="100vw" src="/media/vinfast/home/service.webp" />
          <div className={styles.serviceContent}>
            <h2 id="homepage-service-title">Bảo hành &amp; Dịch vụ</h2>
            <p>VinFast đã đầu tư nghiêm túc và bài bản để phát triển hệ thống Showroom, Nhà phân phối và xưởng dịch vụ rộng khắp, đáp ứng tối đa nhu cầu của Khách hàng.</p>
            <div>
              <Link className={styles.primaryButton} href="/locations">ĐẶT LỊCH BẢO DƯỠNG</Link>
              <Link className={styles.lightButton} href="/locations">CHÍNH SÁCH</Link>
            </div>
          </div>
        </section>
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock} direction="right">
        <section aria-labelledby="homepage-green-title" className={styles.greenFuture} id="green-future">
          <Image alt="Mãnh liệt Tinh thần Việt Nam - Vì Tương lai Xanh" fill sizes="100vw" src="/media/vinfast/home/green-future.webp" />
          <div className={styles.greenContent}>
            <h2 id="homepage-green-title">Mãnh liệt Tinh thần Việt Nam - Vì Tương lai Xanh</h2>
            <p>Chiến dịch Mãnh liệt Tinh thần Việt Nam - Vì Tương lai Xanh là lời khẳng định mạnh mẽ của VinFast trong hành trình thúc đẩy cuộc cách mạng xe điện và kiến tạo một tương lai bền vững. Chiến dịch không chỉ thể hiện tinh thần tiên phong của thương hiệu Việt trên bản đồ xe điện toàn cầu mà còn kêu gọi cộng đồng cùng chung tay chuyển đổi xanh, góp phần xây dựng một Việt Nam phát triển vững bền, nơi giao thông không chỉ hiện đại mà còn thân thiện với môi trường.</p>
            <Link className={styles.lightButton} href="/consultation">XEM CHI TIẾT</Link>
          </div>
        </section>
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock}>
        <section aria-label="Khám phá hệ thống VinFast" className={styles.exploreGrid}>
          <Link className={styles.exploreCard} href="/locations">
            <Image alt="Showroom và trạm sạc VinFast" fill sizes="(max-width: 720px) 100vw, 50vw" src="/media/vinfast/home/showroom.webp" />
            <span><strong>Showroom &amp; Trạm sạc</strong></span>
          </Link>
          <Link className={styles.exploreCard} href="/consultation">
            <Image alt="Cộng đồng VinFast toàn cầu" fill sizes="(max-width: 720px) 100vw, 50vw" src="/media/vinfast/home/community.webp" />
            <span><strong>Cộng đồng VinFast Toàn cầu</strong><small>TÌM HIỂU THÊM</small></span>
          </Link>
        </section>
      </ScrollReveal>

      <ScrollReveal className={styles.revealBlock}>
        <section aria-labelledby="homepage-newsletter-title" className={styles.newsletter}>
          <Image alt="Cộng đồng VinFast" fill sizes="100vw" src="/media/vinfast/home/newsletter.webp" />
          <div>
            <h2 id="homepage-newsletter-title">Đăng ký nhận thông tin</h2>
            <p>Đăng ký nhận thông tin chương trình khuyến mãi, dịch vụ VinFast.</p>
            <form onSubmit={submitNewsletter}>
              <label className="sr-only" htmlFor="homepage-newsletter-email">Email</label>
              <input id="homepage-newsletter-email" name="email" placeholder="Nhập email của bạn" required type="email" />
              <button type="submit">ĐĂNG KÝ</button>
            </form>
            {newsletterSubmitted ? <p className={styles.newsletterSuccess} role="status">Cảm ơn Quý khách đã đăng ký.</p> : null}
            <small>Bằng cách đăng ký, Quý khách xác nhận đã đọc, hiểu và đồng ý với Chính sách Quyền riêng tư của VinFast.</small>
          </div>
        </section>
      </ScrollReveal>
    </div>
  );
}
