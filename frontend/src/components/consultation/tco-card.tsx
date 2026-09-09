"use client";

import { useEffect, useRef, useState } from "react";

import { estimateTco, fetchProvinceOptions } from "@/lib/api/agent";
import { computeTco } from "@/lib/tco";
import { useAnimatedNumber } from "@/lib/use-animated-number";
import { usePrefersReducedMotion } from "@/lib/use-prefers-reduced-motion";
import type { ProvinceOption, TcoCard as TcoCardData } from "@/types/agent";

/**
 * Chỉ gộp lượt gọi mạng của đường CŨ (không có `rates`) — thẻ mới không gọi
 * mạng cho thanh km nữa nên không cần gộp.
 */
const KM_DEBOUNCE_MS = 300;

const RATE_LABELS = {
  fixed: "Chi phí cố định (xe, lệ phí, đăng kiểm...)",
  energy: "Nhiên liệu / điện",
  insurance: "Bảo hiểm",
  maintenance: "Bảo dưỡng định kỳ",
  battery: "Thuê pin",
} as const;

const ZERO_COMPONENTS = { fixed: 0, energy: 0, insurance: 0, maintenance: 0, battery: 0 };

/**
 * Mã SENTINEL cho "Tỉnh/thành khác": client đổi về `null` TRƯỚC khi gọi API —
 * không gửi một mã tỉnh bịa lên server (bài học "Cần Thơ" ở /tco: số tiền đúng
 * nhưng dữ liệu bịa lọt vào log và slot của phiên).
 */
const OTHER_PROVINCE = "__khac__";

/**
 * Fallback khi backend KHÔNG gửi `province_options` kèm thẻ và lời gọi
 * `/agent/tco/provinces` cũng hỏng/rỗng (đợt 10). Ba mục là ĐỦ đúng cho mọi
 * khách — cùng lý do với trang /tco: lệ phí biển chỉ phân biệt Hà Nội/TP.HCM
 * (Khu vực I) với phần còn lại (Khu vực II). Thiếu bộ này thì ô chọn khu vực
 * trống trơn đúng lúc mất mạng phụ — khách hết đường sửa chỗ sai đắt nhất
 * (chênh 100 lần).
 */
const FALLBACK_PROVINCES: readonly ProvinceOption[] = [
  { code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" },
  { code: "HCM", name: "TP. Hồ Chí Minh", region_code: "KHU_VUC_I" },
  { code: OTHER_PROVINCE, name: "Tỉnh/thành khác (Khu vực II)", region_code: "KHU_VUC_II" },
];

/**
 * Thẻ chi phí 5 năm mà khách CHỈNH ĐƯỢC ngay tại chỗ.
 *
 * Sếp 2026-08-27: *"phải có ô hay điền gì đó hoặc kéo số km còn tỉnh thành để
 * cho người ta chọn chứ không cần phải chat rồi cập nhật lại"*.
 *
 * Hai ô vì đúng hai thứ có thể sai trong một ước tính: quãng đường mỗi ngày, và
 * tỉnh đăng ký. Tỉnh là chỗ sai đắt nhất — lệ phí biển ô tô là 140.000đ ở Khu
 * vực II và 14.000.000đ ở Hà Nội/TP.HCM, chênh đúng 100 lần.
 *
 * Sếp 2026-08-29: kéo thanh km phải đổi số NGAY, không đợi một lượt mạng. Có
 * `rates` (đơn giá kèm thẻ) thì tính bằng `computeTco` ngay tại đây — công
 * thức TẤT ĐỊNH giống hệt server, không qua LLM, kéo bao nhiêu lần cũng rẻ.
 * Tỉnh vẫn phải hỏi server: lệ phí biển phụ thuộc bảng giá theo khu vực, không
 * phải một hằng số client biết trước. Thẻ CŨ (chưa có `rates`) rơi về đúng
 * đường gọi `/agent/tco/estimate` như trước, chỉ thêm gộp lại 300ms để kéo
 * nhanh tay không bắn một lượt mạng cho mỗi nấc trượt.
 */
export function TcoCard({ card, sessionId }: { card: TcoCardData; sessionId?: string | null }) {
  const [current, setCurrent] = useState<TcoCardData>(card);
  // Ưu tiên danh sách GỬI KÈM thẻ: có sẵn ngay lúc thẻ hiện ra, không phụ thuộc
  // một lần gọi mạng nữa. Backend cũ không gửi thì hiện NGAY bộ 3 khu vực
  // fallback (ô chọn không bao giờ trống), rồi lời gọi riêng bên dưới thay bằng
  // danh sách đầy đủ khi nó về.
  const [provinces, setProvinces] = useState<readonly ProvinceOption[]>(
    card.province_options?.length ? card.province_options : FALLBACK_PROVINCES,
  );
  // Khách đã chọn "Tỉnh/thành khác": `province_code` gửi đi là null (đúng mặc
  // định Khu vực II của backend) nhưng ô chọn vẫn phải HIỂN THỊ lựa chọn đó —
  // không có cờ này thì select rơi về "Chọn tỉnh…" như thể khách chưa làm gì.
  const [pickedOther, setPickedOther] = useState(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  // Nháy viền ~1s khi thẻ được CẬP NHẬT tại chỗ từ một lượt chat mới (Sếp
  // 2026-08-31: một thẻ sống cả phiên) — khách phải thấy đúng thẻ cũ đổi số,
  // không tưởng nhầm mình đang nhìn một thẻ khác.
  const [flash, setFlash] = useState(false);
  const firstCardRender = useRef(true);
  //: Giả định ĐÃ TÍNH gần nhất, để bỏ qua lời gọi lặp.
  const applied = useRef({ km: card.daily_distance_km, province: card.province_code });
  const requestSequence = useRef(0);
  const kmDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  // Thẻ mới từ một lượt chat mới thì bỏ hết trạng thái đang chỉnh: con số của
  // lượt trước thuộc về một chiếc xe khác.
  useEffect(() => {
    setCurrent(card);
    setFailed(false);
    setPickedOther(false);
    applied.current = { km: card.daily_distance_km, province: card.province_code };
    if (kmDebounce.current) {
      clearTimeout(kmDebounce.current);
      kmDebounce.current = null;
    }
    // Lần gắn đầu KHÔNG nháy: hiệu ứng chỉ dành cho thẻ bị lượt sau cập nhật.
    if (firstCardRender.current) {
      firstCardRender.current = false;
      return;
    }
    setFlash(true);
    const timer = setTimeout(() => setFlash(false), 1100);
    return () => clearTimeout(timer);
  }, [card]);

  useEffect(() => {
    if (card.province_options?.length) {
      setProvinces(card.province_options);
      return;
    }
    // Đặt fallback TRƯỚC khi hỏi mạng: thẻ mới của một lượt mới không được
    // mượn danh sách của thẻ trước trong lúc chờ.
    setProvinces(FALLBACK_PROVINCES);
    let alive = true;
    fetchProvinceOptions()
      .then((options) => {
        // Danh sách rỗng cũng GIỮ fallback: một ô chọn không có lựa chọn nào
        // là khách hết đường sửa chỗ sai đắt nhất (lệ phí biển chênh 100 lần).
        if (alive && options.length > 0) setProvinces(options);
      })
      // Mạng hỏng thì thẻ vẫn dùng được với bộ 3 khu vực fallback.
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [card.province_options]);

  // Dọn hẹn giờ gộp lượt gọi mạng khi rời thẻ giữa chừng.
  useEffect(
    () => () => {
      if (kmDebounce.current) clearTimeout(kmDebounce.current);
    },
    [],
  );

  const localBreakdown = current.rates ? computeTco(current.rates, current.daily_distance_km) : null;
  const hasLocalRates = localBreakdown !== null;
  const animationDisabled = reducedMotion || !hasLocalRates;
  const targets = localBreakdown?.components ?? ZERO_COMPONENTS;

  const displayTotal = useAnimatedNumber(localBreakdown?.total ?? Number(current.total_vnd ?? 0), {
    disabled: animationDisabled,
  });
  const displayFixed = useAnimatedNumber(targets.fixed, { disabled: animationDisabled });
  const displayEnergy = useAnimatedNumber(targets.energy, { disabled: animationDisabled });
  const displayInsurance = useAnimatedNumber(targets.insurance, { disabled: animationDisabled });
  const displayMaintenance = useAnimatedNumber(targets.maintenance, { disabled: animationDisabled });
  const displayBattery = useAnimatedNumber(targets.battery, { disabled: animationDisabled });
  // Sếp 2026-08-31 ("giá lăn bánh với TCO là MỘT"): backend gán `group` cho
  // từng khoản để thẻ tách hai nhóm — "Chi phí lăn bánh ban đầu" (giá xe + lệ
  // phí ban đầu, đúng phần câu dẫn giá lăn bánh trỏ khách nhìn vào) và "Chi
  // phí vận hành 5 năm". Backend cũ chưa gửi `group` → bảng phẳng như cũ.
  const rollingItems = current.components.filter((item) => item.group === "rolling");
  const operatingItems = current.components.filter((item) => item.group === "operating");
  const grouped = rollingItems.length > 0;
  const rollingSubtotal = rollingItems.reduce((sum, item) => sum + readAmount(item.amount_vnd), 0);
  // Nhóm vận hành khi có `rates` chỉ gồm ba khoản đổi theo km/tháng (điện, bảo
  // dưỡng, pin): bảo hiểm TNDS đã nằm trong "Lệ phí ban đầu" của nhóm lăn bánh
  // (components server), cộng cả hai chỗ là đếm ĐÔI cùng một khoản tiền.
  const displayOperating = useAnimatedNumber(targets.energy + targets.maintenance + targets.battery, {
    disabled: animationDisabled,
  });

  async function recalculateViaApi(next: { km?: number; province?: string | null }) {
    const km = next.km ?? current.daily_distance_km;
    const province = next.province !== undefined ? next.province : current.province_code;
    // Thả tay ở đúng chỗ vừa thả, hay bấm phím mũi tên rồi nhả — cả hai đều bắn
    // sự kiện dù không có gì đổi. Gọi lại server cho một giá trị y hệt là làm số
    // nhấp nháy vô cớ và tốn một lượt mạng.
    if (km === applied.current.km && province === applied.current.province) return;
    applied.current = { km, province };
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setPending(true);
    setFailed(false);
    try {
      const updated = await estimateTco({
        vehicleId: current.vehicle_id,
        dailyDistanceKm: km,
        provinceCode: province,
        sessionId,
      });
      if (requestSequence.current === sequence) setCurrent(updated);
    } catch {
      if (requestSequence.current === sequence) setFailed(true);
    } finally {
      if (requestSequence.current === sequence) setPending(false);
    }
  }

  function handleKmChange(km: number): void {
    setCurrent((value) => ({ ...value, daily_distance_km: km }));

    if (hasLocalRates) {
      // Có đơn giá DÙNG ĐƯỢC: tính tại chỗ ngay lúc render (xem `localBreakdown`
      // ở trên) — không gọi mạng, không cần gộp lại. Soi `hasLocalRates` chứ
      // không soi `current.rates`: rates có mặt nhưng hỏng (computeTco trả null,
      // đợt 11) mà rẽ vào nhánh này thì kéo km không đổi gì cả — không tính tại
      // chỗ, cũng không hỏi server.
      applied.current = { ...applied.current, km };
      if (kmDebounce.current) {
        clearTimeout(kmDebounce.current);
        kmDebounce.current = null;
      }
      return;
    }

    if (km === applied.current.km) return;
    if (kmDebounce.current) clearTimeout(kmDebounce.current);
    kmDebounce.current = setTimeout(() => {
      kmDebounce.current = null;
      void recalculateViaApi({ km });
    }, KM_DEBOUNCE_MS);
  }

  return (
    <section aria-label="Chi phí sử dụng 5 năm" className={flash ? "tco-card tco-card--updated" : "tco-card"}>
      <header className="tco-card__head">
        <h3>Chi phí sử dụng 5 năm — {current.vehicle_name}</h3>
        <p className="tco-card__total" data-pending={pending || undefined}>
          {hasLocalRates
            ? formatVndAmount(displayTotal)
            : current.total_vnd
              ? formatVnd(current.total_vnd)
              : "Chưa tính được"}
        </p>
        {hasLocalRates && current.rates?.formula_note ? (
          <p className="tco-card__formula-note">{current.rates.formula_note}</p>
        ) : null}
      </header>

      {grouped ? (
        <>
          <h4 className="tco-card__group-title">Chi phí lăn bánh ban đầu</h4>
          <dl className="tco-card__lines">
            {rollingItems.map((item) => (
              <div className="tco-card__line" key={item.code}>
                <dt>{item.label}</dt>
                <dd>{formatVnd(item.amount_vnd)}</dd>
              </div>
            ))}
            <div className="tco-card__line tco-card__line--subtotal">
              <dt>Cộng lăn bánh</dt>
              <dd>{formatVndAmount(rollingSubtotal)}</dd>
            </div>
          </dl>
          <h4 className="tco-card__group-title">Chi phí vận hành 5 năm</h4>
          <dl className="tco-card__lines">
            {hasLocalRates ? (
              <>
                <div className="tco-card__line">
                  <dt>{RATE_LABELS.energy}</dt>
                  <dd>{formatVndAmount(displayEnergy)}</dd>
                </div>
                <div className="tco-card__line">
                  <dt>{RATE_LABELS.maintenance}</dt>
                  <dd>{formatVndAmount(displayMaintenance)}</dd>
                </div>
                <div className="tco-card__line">
                  <dt>{RATE_LABELS.battery}</dt>
                  <dd>{formatVndAmount(displayBattery)}</dd>
                </div>
                <div className="tco-card__line tco-card__line--subtotal">
                  <dt>Cộng vận hành</dt>
                  <dd>{formatVndAmount(displayOperating)}</dd>
                </div>
              </>
            ) : (
              <>
                {operatingItems.map((item) => (
                  <div className="tco-card__line" key={item.code}>
                    <dt>{item.label}</dt>
                    <dd>{formatVnd(item.amount_vnd)}</dd>
                  </div>
                ))}
                <div className="tco-card__line tco-card__line--subtotal">
                  <dt>Cộng vận hành</dt>
                  <dd>{formatVndAmount(operatingItems.reduce((sum, item) => sum + readAmount(item.amount_vnd), 0))}</dd>
                </div>
              </>
            )}
          </dl>
        </>
      ) : (
        <dl className="tco-card__lines">
          {hasLocalRates ? (
            <>
              <div className="tco-card__line">
                <dt>{RATE_LABELS.fixed}</dt>
                <dd>{formatVndAmount(displayFixed)}</dd>
              </div>
              <div className="tco-card__line">
                <dt>{RATE_LABELS.energy}</dt>
                <dd>{formatVndAmount(displayEnergy)}</dd>
              </div>
              <div className="tco-card__line">
                <dt>{RATE_LABELS.insurance}</dt>
                <dd>{formatVndAmount(displayInsurance)}</dd>
              </div>
              <div className="tco-card__line">
                <dt>{RATE_LABELS.maintenance}</dt>
                <dd>{formatVndAmount(displayMaintenance)}</dd>
              </div>
              <div className="tco-card__line">
                <dt>{RATE_LABELS.battery}</dt>
                <dd>{formatVndAmount(displayBattery)}</dd>
              </div>
            </>
          ) : (
            current.components.map((item) => (
              <div className="tco-card__line" key={item.code}>
                <dt>{item.label}</dt>
                <dd>{formatVnd(item.amount_vnd)}</dd>
              </div>
            ))
          )}
        </dl>
      )}

      <div className="tco-card__controls">
        <label className="tco-card__control">
          <span>
            Quãng đường mỗi ngày
            {!current.daily_distance_known ? <em> (em tạm tính)</em> : null}
          </span>
          <input
            aria-label="Quãng đường mỗi ngày, ki-lô-mét"
            max={300}
            min={0}
            onChange={(event) => handleKmChange(Number(event.target.value))}
            step={5}
            type="range"
            value={current.daily_distance_km}
          />
          <output>{Math.round(current.daily_distance_km)} km</output>
        </label>

        <label className="tco-card__control">
          {/*
            Sếp 2026-08-27: *"khung chọn khu vực không hiển thị cho người dùng
            thấy để chọn"*. Ô vốn đã có trong markup — thứ thiếu là DẤU HIỆU
            rằng nó bấm được: nhãn trần "Tỉnh đăng ký" đứng cạnh một thanh trượt
            nổi bật đọc như một dòng thông tin, và mục rỗng ghi "Chưa chọn" đọc
            như một trạng thái chứ không phải một lời mời.

            Nên: nói thẳng việc bấm ("Chọn tỉnh..."), nói vì sao đáng bấm (lệ phí
            biển chênh 100 lần), và KHÔNG khoá ô khi danh sách rỗng — khoá là
            khách hết đường thử lại.
          */}
          <span>
            Tỉnh đăng ký
            {current.province_code || pickedOther ? null : <em> — chọn để tính đúng lệ phí biển</em>}
          </span>
          <select
            aria-label="Tỉnh thành đăng ký xe"
            className="tco-card__select"
            disabled={pending}
            onChange={(event) => {
              const value = event.target.value;
              // "Tỉnh/thành khác" KHÔNG gửi mã bịa: đổi về null để backend dùng
              // mặc định Khu vực II — cùng quy ước với trang /tco.
              setPickedOther(value === OTHER_PROVINCE);
              void recalculateViaApi({
                province: value === OTHER_PROVINCE ? null : value || null,
              });
            }}
            value={current.province_code ?? (pickedOther ? OTHER_PROVINCE : "")}
          >
            <option value="">Chọn tỉnh…</option>
            {provinces.map((option) => (
              <option key={option.code} value={option.code}>
                {option.name}
              </option>
            ))}
            {/* Danh sách đầy đủ về sau khi khách ĐÃ chọn "khác": giữ mục này để
                select không mất giá trị đang hiển thị. */}
            {pickedOther && !provinces.some((option) => option.code === OTHER_PROVINCE) ? (
              <option value={OTHER_PROVINCE}>Tỉnh/thành khác (Khu vực II)</option>
            ) : null}
          </select>
        </label>
      </div>

      <p className="tco-card__note">{current.assumption_note}</p>
      {failed ? (
        <p className="tco-card__error" role="status">
          Em chưa cập nhật được số mới, anh/chị thử lại giúp em ạ.
        </p>
      ) : null}
    </section>
  );
}

/**
 * Tiền dạng CHUỖI của backend → số để cộng nhóm. Chuỗi lạ tính 0 — tổng nhóm
 * thà thiếu một khoản còn hơn thành NaN kéo sập cả thẻ (bài học VF 7 đợt 11).
 */
function readAmount(value: string | number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * "899000000" → "899.000.000 đồng".
 *
 * Nhận CHUỖI vì tiền không đi qua float. Chuỗi lạ thì trả nguyên vẹn — thà hiện
 * số thô còn hơn hiện `NaN`.
 */
function formatVnd(amount: string | number): string {
  // Hợp đồng nói CHUỖI nhưng payload thật của VF 7 (đợt 11) gửi `total_vnd` là
  // SỐ trần — `.replace` trên số là crash nguyên thẻ. `String()` đỡ cả hai.
  const digits = String(amount).replace(/\.0+$/, "");
  if (!/^\d+$/.test(digits)) return String(amount);
  return `${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".")} đồng`;
}

/**
 * Cùng khuôn với `formatVnd`, nhận thẳng SỐ — dùng cho các giá trị tính tại
 * chỗ bằng `computeTco`/`useAnimatedNumber`, vốn là số đang chạy giữa chừng
 * animation nên không đi qua dạng chuỗi VND của backend.
 */
function formatVndAmount(amount: number): string {
  const digits = String(Math.max(0, Math.round(amount)));
  return `${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".")} đồng`;
}
