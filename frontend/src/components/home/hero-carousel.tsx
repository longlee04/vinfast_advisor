"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

const slides = [
  {
    image: "/hero/ev-coast.png",
    eyebrow: "Di chuyển theo cách của bạn",
    title: "Mở lối cho mọi hành trình",
    description: "Khám phá xe điện phù hợp với phong cách sống, ngân sách và nhu cầu sử dụng của bạn.",
    primary: { href: "/vehicles", label: "Khám phá dòng xe" },
    secondary: { href: "/test-drive", label: "Đăng ký lái thử" },
    theme: "light",
  },
  {
    image: "/hero/ev-blue-hour.png",
    eyebrow: "VinFast AI Sales Advisor",
    title: "Tư vấn riêng cho chính bạn",
    description: "Một cuộc trò chuyện ngắn để thu hẹp lựa chọn và đưa ra đề xuất dễ hiểu, có thể so sánh.",
    primary: { href: "/consultation", label: "Trò chuyện với AI" },
    secondary: { href: "/compare", label: "So sánh xe" },
    theme: "dark",
  },
  {
    image: "/hero/ev-interior.png",
    eyebrow: "Không gian sống di động",
    title: "Thoải mái trong từng khoảnh khắc",
    description: "Cân nhắc không gian, tầm hoạt động và chi phí sở hữu trước khi đưa ra quyết định.",
    primary: { href: "/tco", label: "Ước tính chi phí" },
    secondary: { href: "/vehicles", label: "Xem catalog" },
    theme: "light",
  },
] as const;

export function HeroCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setActiveIndex((current) => (current + 1) % slides.length), 6500);
    return () => window.clearInterval(timer);
  }, []);

  function move(direction: -1 | 1): void {
    setActiveIndex((current) => (current + direction + slides.length) % slides.length);
  }

  return (
    <section className="customer-hero-carousel" aria-roledescription="carousel" aria-label="Điểm nổi bật">
      <div className="hero-slide-track" style={{ transform: `translateX(-${activeIndex * 100}%)` }}>
        {slides.map((slide, index) => (
          <article aria-hidden={index !== activeIndex} className={`customer-hero-slide is-${slide.theme}`} key={slide.image}>
            <Image alt="Không gian trải nghiệm xe điện VinFast" fill priority={index === 0} sizes="100vw" src={slide.image} />
            <div className="hero-image-shade" />
            <div className="hero-slide-copy"><span>{slide.eyebrow}</span><h1>{slide.title}</h1><p>{slide.description}</p><div><Link className="hero-primary-action" href={slide.primary.href}>{slide.primary.label}</Link><Link className="hero-secondary-action" href={slide.secondary.href}>{slide.secondary.label}</Link></div></div>
          </article>
        ))}
      </div>
      <button className="hero-carousel-arrow is-left" aria-label="Ảnh trước" onClick={() => move(-1)} type="button"><ChevronLeft size={24} /></button>
      <button className="hero-carousel-arrow is-right" aria-label="Ảnh tiếp theo" onClick={() => move(1)} type="button"><ChevronRight size={24} /></button>
      <div className="hero-carousel-dots" aria-label="Chọn ảnh">{slides.map((slide, index) => <button aria-label={`Xem ảnh ${index + 1}`} className={index === activeIndex ? "is-active" : ""} key={slide.image} onClick={() => setActiveIndex(index)} type="button" />)}</div>
    </section>
  );
}
