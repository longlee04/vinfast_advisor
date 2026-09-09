"use client";

import { FormEvent, useState } from "react";

export function ContactLead({ model }: Readonly<{ model?: string }>) {
  const [sent, setSent] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setSent(true);
  }

  return (
    <section className="vf-contact" aria-labelledby="contact-lead-title">
      <div className="vf-contact-copy">
        <span>Tư vấn riêng</span>
        <h2 id="contact-lead-title">Cần thêm thông tin trước khi chọn xe?</h2>
        <p>{model ? `Để lại thông tin để được hỗ trợ về ${model} và phiên bản phù hợp.` : "Chia sẻ nhu cầu của bạn. Đội ngũ tư vấn sẽ giúp thu hẹp lựa chọn phù hợp."}</p>
      </div>
      {sent ? (
        <div className="vf-contact-success" role="status"><strong>Đã ghi nhận thông tin.</strong><span>Đây là bản demo giao diện; chưa có dữ liệu nào được gửi ra ngoài.</span></div>
      ) : (
        <form className="vf-contact-form" onSubmit={submit}>
          <label><span>Họ và tên</span><input name="name" required autoComplete="name" /></label>
          <label><span>Số điện thoại</span><input name="phone" required autoComplete="tel" inputMode="tel" /></label>
          <label className="is-wide"><span>Email</span><input name="email" type="email" autoComplete="email" /></label>
          <button type="submit">Nhận tư vấn</button>
          <small>Thông tin chỉ được dùng để mô phỏng trải nghiệm liên hệ trong bản demo này.</small>
        </form>
      )}
    </section>
  );
}
