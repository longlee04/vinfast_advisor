import { ArrowUpRight, CalendarDays, MessagesSquare } from "lucide-react";
import Link from "next/link";

import { consultationHref } from "@/lib/vehicle-links";

import styles from "./vehicle-support-choice.module.css";

type VehicleSupportChoiceProps = {
  readonly anchorId?: string;
  readonly from: string;
  readonly model: string;
};

/** Shared end-of-page support choices for every vehicle detail experience. */
export function VehicleSupportChoice({ anchorId = "ho-tro", from, model }: VehicleSupportChoiceProps) {
  return (
    <section className={styles.section} id={anchorId}>
      <div className={styles.intro}>
        <span>VinFast luôn sẵn sàng</span>
        <h2>Quý khách quan tâm đến {model} hoặc còn thắc mắc?</h2>
        <p>
          Hãy cho chúng tôi biết nhu cầu của Quý khách để VinFast có thể hỗ trợ và phục vụ
          Quý khách tốt hơn.
        </p>
      </div>
      <div
        aria-label={`Lựa chọn hỗ trợ cho ${model}`}
        className={styles.options}
        data-layout="compact-row"
        role="group"
      >
        <Link className={styles.option} href="/test-drive">
          <span className={styles.icon}><CalendarDays aria-hidden="true" /></span>
          <span className={styles.copy}>
            <strong>Tư vấn viên</strong>
            <small>Trao đổi trực tiếp và đặt lịch lái thử phù hợp với Quý khách.</small>
          </span>
          <ArrowUpRight aria-hidden="true" className={styles.arrow} />
        </Link>
        <Link className={`${styles.option} ${styles.vivi}`} href={consultationHref(model, from)}>
          <span className={styles.icon}>
            <MessagesSquare aria-hidden="true" data-testid="vivi-conversation-icon" />
          </span>
          <span className={styles.copy}>
            <strong>Trợ lý ảo ViVi</strong>
            <small>Nhận giải đáp nhanh 24/7 về giá, phiên bản và thông tin {model}.</small>
          </span>
          <ArrowUpRight aria-hidden="true" className={styles.arrow} />
        </Link>
      </div>
    </section>
  );
}
