"use client";

import { type FormEvent, useState } from "react";

import type { UserProfile } from "@/lib/api/auth";
import { normalizeVnPhone, saveCustomerProfile } from "@/lib/api/customer-profile";

export type ProfileCompletionFormProps = {
  readonly profile: UserProfile | null;
  readonly onSaved: (profile: UserProfile) => void;
  readonly onSkip: () => void;
};

/**
 * Sau khi đăng nhập: xin tên, SĐT, địa chỉ để tư vấn viên thấy người thật thay vì mã khách
 * (plan §19). Tên + SĐT bắt buộc; địa chỉ tuỳ chọn. "Để sau" không chặn khách — lần đăng
 * nhập sau hỏi lại nếu vẫn thiếu.
 */
export function ProfileCompletionForm({ profile, onSaved, onSkip }: ProfileCompletionFormProps) {
  const [fullName, setFullName] = useState(profile?.full_name ?? "");
  const [phone, setPhone] = useState(profile?.phone_number ?? "");
  const [address, setAddress] = useState(profile?.address ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = fullName.trim();
    if (name.length < 2) {
      setError("Anh/chị cho em xin họ tên để tư vấn viên xưng hô cho đúng ạ.");
      return;
    }
    const normalized = normalizeVnPhone(phone);
    if (!normalized) {
      setError("Số điện thoại chưa đúng — ví dụ 0912 345 678.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      onSaved(await saveCustomerProfile({ full_name: name, phone_number: normalized, address: address.trim() || null }));
    } catch {
      setError("Chưa lưu được thông tin, anh/chị thử lại giúp em nhé.");
      setSaving(false);
    }
  }

  return (
    <form aria-labelledby="profile-completion-title" className="profile-completion" noValidate onSubmit={(event) => void submit(event)}>
      <h1 id="profile-completion-title">Cho em xin vài thông tin cơ bản</h1>
      <p>Để tư vấn viên liên hệ đúng người, gợi ý showroom gần anh/chị và giữ lịch lái thử. Thông tin chỉ tư vấn viên phụ trách được xem.</p>
      <label className="field-label">
        Họ và tên
        <input autoComplete="name" onChange={(event) => setFullName(event.target.value)} required value={fullName} />
      </label>
      <label className="field-label">
        Số điện thoại
        <input autoComplete="tel" inputMode="tel" onChange={(event) => setPhone(event.target.value)} placeholder="0912 345 678" required type="tel" value={phone} />
      </label>
      <label className="field-label">
        Địa chỉ <small>(không bắt buộc)</small>
        <input autoComplete="street-address" onChange={(event) => setAddress(event.target.value)} placeholder="Số nhà, đường, quận/huyện, tỉnh/thành" value={address} />
      </label>
      {error ? (
        <p className="inline-warning" role="alert">
          {error}
        </p>
      ) : null}
      <div className="profile-completion-actions">
        <button className="primary-button" disabled={saving} type="submit">
          {saving ? "Đang lưu..." : "Lưu và tiếp tục"}
        </button>
        <button className="text-button" onClick={onSkip} type="button">
          Để sau
        </button>
      </div>
    </form>
  );
}
