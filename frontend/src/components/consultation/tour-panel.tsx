"use client";

import { LocateFixed, MapPin, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import { TestDriveAutoLocate, TestDriveLocateControls, useTestDriveLocate, type LocateWhere } from "./test-drive-card";
import { TourVehicleSummary } from "./tour-vehicle-summary";
import { fetchTestDriveAvailability } from "@/lib/api/agent";
import type { TourPanelState } from "@/store/agent-session";
import type {
  NavigateMap,
  TestDriveCard as TestDriveCardData,
  TestDriveOption,
  TestDriveOptionsResponse,
} from "@/types/agent";

// Leaflet đụng `window` ngay khi import → chỉ nạp ở client, giống /locations.
const TourMap = dynamic(() => import("./tour-map"), {
  loading: () => <TourSkeleton />,
  ssr: false,
});

/** Khung xám chờ nội dung — hiện NGAY khi panel mở, không để ô trắng trong lúc nạp. */
export function TourSkeleton() {
  return (
    <div aria-hidden="true" className="tour-panel__skeleton">
      <span />
      <span />
      <span />
    </div>
  );
}

/**
 * Khách bật "giảm chuyển động" thì panel chỉ hiện/ẩn, không trượt/mờ. Đọc một
 * lần lúc mount và nghe đổi — không có `matchMedia` (SSR, jsdom cũ) coi như
 * bình thường.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent): void => setReduced(event.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * Panel "trang web đi theo hội thoại" (đợt 9, 2026-08-31).
 *
 * Khách chốt xe → trang chi tiết xe hiện NGAY CẠNH khung chat; khách xin lái
 * thử → bản đồ showroom. KHÔNG điều hướng trang: rời `/consultation` là mất
 * mạch trò chuyện, và quay lại là một lần tải phiên nữa. Desktop: cột phải
 * ~45%, chat giữ bên trái; mobile: bottom-sheet. Nút "Thu gọn" chỉ ẩn — nội
 * dung vẫn ở store để mở lại.
 *
 * Panel KHÔNG tự quyết gì về hội thoại: chọn ghim, xin vị trí đều báo lên
 * `consultation-flow` để đi chung đường với thẻ lái thử trong chat.
 */
export function TourPanel({
  disabled = false,
  onClose,
  onLocated,
  onSendMessage,
  onShowroomPick,
  panel,
  sessionId,
  testDriveCard = null,
}: {
  disabled?: boolean;
  panel: TourPanelState;
  sessionId?: string;
  /**
   * Thẻ lái thử của lượt (đợt 11): panel bản đồ bày luôn NGÀY + KHUNG GIỜ của
   * showroom đang chọn để khách đặt lịch ngay tại panel — Sếp: "đăng ký giờ
   * của tôi ở đâu". Thẻ trong chat GIỮ NGUYÊN, panel chỉ là lối vào thứ hai.
   */
  testDriveCard?: TestDriveCardData | null;
  onClose: () => void;
  onShowroomPick: (showroomId: string) => void;
  onLocated: (result: TestDriveOptionsResponse, where: LocateWhere) => void;
  /** Gửi mã giờ đã ký (`__lichlaithu__…`) vào chat — cùng đường với thẻ trong chat. */
  onSendMessage?: (value: string) => void;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const asideRef = useRef<HTMLElement>(null);
  // ESC đóng cửa sổ — cùng phím với mọi lớp phủ khác trong app (menu, modal).
  const open = panel.open;
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") return;
      // Đang gõ IME (ghép chữ tiếng Việt/Nhật…) thì ESC là hủy chuỗi đang gõ,
      // không phải lệnh đóng; ai đó đã preventDefault thì cũng nhường.
      if (event.isComposing || event.defaultPrevented) return;
      const target = event.target;
      // ESC trong ô nhập của CHÍNH panel: khách muốn thoát ô nhập — chỉ blur,
      // không sập cả cửa sổ ngay dưới tay họ.
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA") &&
        asideRef.current?.contains(target)
      ) {
        target.blur();
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  const navigate = panel.navigate;
  if (!navigate) return null;
  const title = navigate.kind === "vehicle" ? navigate.name : "Showroom gần anh/chị";
  // Khoá nội dung: đổi (vehicle → map, hay xe khác) thì khối cũ gỡ, khối mới
  // mount lại và chạy fade-in — không nháy trắng vì nền panel đứng yên.
  const contentKey = navigate.kind === "vehicle" ? `vehicle:${navigate.slug}` : `map:${navigate.vehicle_id}`;
  const className = ["tour-panel", panel.open ? "is-open" : "", reducedMotion ? "" : "is-animated"]
    .filter(Boolean)
    .join(" ");

  return (
    // `inert` khi đóng: panel chỉ trượt khuất chứ vẫn trong DOM — không inert thì
    // Tab vẫn lọt vào các nút vô hình và chuột vẫn bấm trúng chúng.
    <aside aria-hidden={!panel.open} aria-label="Trang đi theo hội thoại" className={className} inert={!panel.open} ref={asideRef}>
      <div className="tour-panel__bar">
        <strong className="tour-panel__title">{title}</strong>
        {/* Sếp báo "không tắt được cửa sổ": nút chỉ là icon ✕ 34px nên dễ trượt
            và khó nhận ra khi nội dung là iframe. Thêm CHỮ "Đóng" cạnh icon +
            phóng nút ≥40x40 (CSS). Nút nằm trong bar NGOÀI iframe nên click
            luôn tới được kể cả khi iframe đang giữ focus. */}
        <button aria-label="Đóng cửa sổ" className="tour-panel__collapse" onClick={onClose} title="Đóng (Esc)" type="button">
          <X aria-hidden="true" size={18} />
          <span>Đóng</span>
        </button>
      </div>
      <div className="tour-panel__body">
        <div className="tour-panel__content" key={contentKey}>
        {navigate.kind === "vehicle" ? (
          (navigate.path || navigate.slug) ? (
            // Sếp 2026-08-31: mở TOÀN TRANG ngay trong cửa sổ. Iframe cùng
            // domain nên trang thật tự co theo khung (viewport = iframe, CSS
            // responsive của trang tự lo) — không vỡ như nhúng component;
            // `?embed=1` để trang tự ẩn header/dock/footer.
            <iframe
              className="tour-panel__frame"
              src={`${navigate.path || `/vehicles/${navigate.slug}`}?embed=1`}
              title={`Trang chi tiết ${navigate.name || navigate.slug}`}
            />
          ) : (
            // Xe máy chưa có trang riêng: giữ bản tóm tắt.
            <TourVehicleSummary navigate={navigate} />
          )
        ) : (
          <MapBody
            disabled={disabled}
            navigate={navigate}
            onLocated={onLocated}
            onSendMessage={onSendMessage}
            onShowroomPick={onShowroomPick}
            selectedShowroomId={panel.selectedShowroomId}
            sessionId={sessionId}
            testDriveCard={testDriveCard}
          />
        )}
        </div>
      </div>
    </aside>
  );
}

function MapBody({
  disabled,
  navigate,
  onLocated,
  onSendMessage,
  onShowroomPick,
  selectedShowroomId,
  sessionId,
  testDriveCard,
}: {
  disabled: boolean;
  navigate: NavigateMap;
  sessionId?: string;
  selectedShowroomId: string | null;
  testDriveCard: TestDriveCardData | null;
  onShowroomPick: (showroomId: string) => void;
  onLocated: (result: TestDriveOptionsResponse, where: LocateWhere) => void;
  onSendMessage?: (value: string) => void;
}) {
  // Sếp 2026-08-31: đã có ghim rồi vẫn phải đổi được vị trí ngay TRONG panel
  // — bật cờ này là khối bản đồ bày lại flow xin vị trí (tự GPS, fallback gõ).
  const [relocating, setRelocating] = useState(false);
  // Accordion khung giờ (Sếp 2026-08-31): MỖI showroom sở hữu một khối giờ.
  // Click mở khối của nó, click lại tắt, click showroom khác thì khối cũ tắt
  // — chỉ một khối mở. Mở panel thì chưa khối nào bung: khách nhìn map +
  // danh sách trước, chọn showroom rồi mới thấy giờ.
  const [openShowroomId, setOpenShowroomId] = useState<string | null>(null);
  const navKey = `${navigate.vehicle_id}|${navigate.showrooms.map((item) => item.showroom_id).join(",")}`;
  useEffect(() => {
    setOpenShowroomId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset theo GIÁ TRỊ danh sách showroom
  }, [navKey]);
  // Chọn showroom từ NGOÀI panel (bấm trên thẻ trong chat, đồng bộ qua store)
  // cũng là ý "xem showroom này" → mở khối giờ của nó. So với giá trị trước để
  // không tự bung ngay khi panel vừa mount với ghim mặc định.
  const prevSelectedRef = useRef(selectedShowroomId);
  useEffect(() => {
    if (selectedShowroomId && selectedShowroomId !== prevSelectedRef.current) {
      setOpenShowroomId(selectedShowroomId);
    }
    prevSelectedRef.current = selectedShowroomId;
  }, [selectedShowroomId]);
  const toggleShowroom = (showroomId: string): void => {
    setOpenShowroomId((current) => (current === showroomId ? null : showroomId));
    // Ghim trên map vẫn trỏ showroom vừa bấm kể cả khi khối giờ tắt: tắt lịch
    // không có nghĩa là hết quan tâm showroom đó.
    onShowroomPick(showroomId);
  };
  const canSchedule = Boolean(
    onSendMessage && testDriveCard && !testDriveCard.needs_location && testDriveCard.showrooms.length > 0,
  );
  // Cùng logic xin vị trí với thẻ lái thử: GPS trước, gõ quận/huyện dự phòng.
  const locate = useTestDriveLocate({
    sessionId,
    vehicleId: navigate.vehicle_id,
    onFound: (result, where) => {
      // Tắt cờ TRƯỚC khi báo lên cha: `onLocated` thay navigate + thẻ trong
      // chat, nhưng nếu ghim/khung giờ mới trùng hệt cũ thì props không đổi và
      // không ai khác tắt hộ — khối locate sẽ đứng chắn danh sách mới mãi.
      setRelocating(false);
      onLocated(result, where);
    },
  });

  if (navigate.needs_location) {
    return (
      <div className="tour-panel__locate">
        <MapPin aria-hidden="true" size={28} />
        <p>Cho em biết anh/chị ở đâu để em ghim showroom gần nhất lên bản đồ nhé.</p>
        <TestDriveLocateControls disabled={disabled} locate={locate} />
      </div>
    );
  }

  return (
    <div className="tour-panel__map">
      <TourMap
        center={navigate.center}
        onSelect={onShowroomPick}
        selectedId={selectedShowroomId}
        showrooms={navigate.showrooms}
      />
      {relocating ? (
        // Đổi vị trí ngay trong panel: bản đồ đứng yên phía trên, khối xin vị
        // trí thế chỗ danh sách showroom. Kết quả mới đi qua `onLocated` →
        // consultation-flow thay navigate + thẻ trong chat → ghim và khung giờ
        // cùng đổi theo, panel không cần tự vá gì thêm.
        <div className="tour-panel__locate">
          <TestDriveAutoLocate
            description="Cho em biết vị trí mới để em ghim lại showroom gần nhất nhé."
            disabled={disabled}
            locate={locate}
          />
          <button
            aria-label="Giữ danh sách showroom hiện tại"
            className="test-drive-card__locate-cancel"
            disabled={disabled}
            onClick={() => setRelocating(false)}
            type="button"
          >
            Giữ danh sách showroom hiện tại
          </button>
        </div>
      ) : navigate.showrooms.length > 0 ? (
        <ul aria-label="Showroom trên bản đồ" className="tour-panel__showrooms">
          {navigate.showrooms.map((showroom) => (
            <li key={showroom.showroom_id}>
              <button
                aria-expanded={canSchedule ? showroom.showroom_id === openShowroomId : undefined}
                aria-pressed={showroom.showroom_id === selectedShowroomId}
                className="tour-panel__showroom"
                disabled={disabled}
                onClick={() => toggleShowroom(showroom.showroom_id)}
                type="button"
              >
                <span className="tour-panel__showroom-name">{showroom.name}</span>
                {showroom.distance_km != null ? (
                  <span className="tour-panel__showroom-meta">{showroom.distance_km.toFixed(1)} km</span>
                ) : null}
                <span className="tour-panel__showroom-address">{showroom.address}</span>
              </button>
              {canSchedule && onSendMessage && testDriveCard && showroom.showroom_id === openShowroomId ? (
                <TourSchedule
                  card={testDriveCard}
                  disabled={disabled}
                  onConfirm={onSendMessage}
                  selectedShowroomId={showroom.showroom_id}
                  sessionId={sessionId}
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="tour-panel__notice">
          Showroom và khung giờ đã hiện trong thẻ lái thử ở khung chat.
        </p>
      )}
      {/* Nút phụ cạnh danh sách showroom — cùng chữ, cùng flow với nút trên
          thẻ trong chat. Ẩn khi đang relocate: khối xin vị trí đã thế chỗ. */}
      {!relocating ? (
        <button
          aria-label="Đổi vị trí, tìm showroom khác"
          className="tour-panel__relocate"
          disabled={disabled}
          onClick={() => setRelocating(true)}
          type="button"
        >
          <LocateFixed aria-hidden="true" size={14} />
          <span>Đổi vị trí · tìm showroom khác</span>
        </button>
      ) : null}
      {/* Đợt 11 → đổi accordion (Sếp 2026-08-31): khung giờ không còn đứng cố
          định dưới bản đồ mà nằm trong danh sách, dưới đúng showroom đang mở.
          Chưa mở khối nào thì nhắc khách bấm showroom — không nhắc thì map +
          danh sách đọc như "hết đường đặt giờ". Đang relocate thì thôi: khối
          xin vị trí đã thế chỗ danh sách. */}
      {!relocating && canSchedule && openShowroomId === null ? (
        <p className="tour-panel__notice">Bấm chọn showroom để xem khung giờ lái thử.</p>
      ) : null}
    </div>
  );
}

/**
 * Khung NGÀY + GIỜ lái thử trong panel bản đồ — dữ liệu lấy từ CHÍNH
 * `test_drive_card` của lượt, và bấm "Đặt lịch" gửi đúng `option.value`
 * (mã `__lichlaithu__…` backend đã ký) vào chat, cùng đường với thẻ trong
 * chat. Client KHÔNG tự ghép mã: sai một tiếng là hẹn khách tới lúc không ai
 * đợi (cùng luật với `test-drive-card.tsx`).
 *
 * Trạng thái ô giờ soi theo thẻ: ô hết chỗ mờ + không bấm được, ô đang chọn
 * `aria-pressed`. Ngày ngoài ngày mặc định nạp lười qua
 * `fetchTestDriveAvailability` — payload lượt chỉ chở ô của ngày mặc định
 * (cùng lý do với thẻ trong chat).
 */
function TourSchedule({
  card,
  disabled,
  onConfirm,
  selectedShowroomId,
  sessionId,
}: {
  card: TestDriveCardData;
  disabled: boolean;
  sessionId?: string;
  selectedShowroomId: string | null;
  onConfirm: (value: string) => void;
}) {
  // Showroom "đang chọn" = ghim trên bản đồ (đồng bộ qua store với thẻ trong
  // chat); ghim chỉ hợp lệ khi có trong thẻ — ghim của một lượt bản đồ khác
  // không được kéo lịch về một showroom không có giờ nào.
  const showroom =
    (selectedShowroomId ? card.showrooms.find((item) => item.showroom_id === selectedShowroomId) : undefined) ??
    card.showrooms.find((item) => item.showroom_id === card.default_showroom_id) ??
    card.showrooms[0];

  const [date, setDate] = useState(card.default_date);
  // Giờ đã bấm, lưu theo `scheduled_at` (không kèm showroom): đổi ghim showroom
  // thì GIỮ nguyên giờ nếu showroom mới còn chỗ giờ đó — cùng hành vi thẻ trong
  // chat; còn hết chỗ thì `pickedValue` bên dưới tự về null, không cần effect.
  const [picked, setPicked] = useState<string | null>(null);
  const [loadedDays, setLoadedDays] = useState<Record<string, readonly TestDriveOption[]>>({});
  const [loadingDate, setLoadingDate] = useState<string | null>(null);
  const [failedDate, setFailedDate] = useState<string | null>(null);

  // Danh tính thẻ theo GIÁ TRỊ (cùng bẫy đã ghi ở `test-drive-card.tsx`): cha
  // dựng object mới mỗi render mà reset theo identity thì cache ngày bay sạch.
  const cardKey = useMemo(
    () =>
      [
        card.vehicle_id,
        card.default_showroom_id,
        card.default_date,
        card.showrooms.map((item) => item.showroom_id).join(","),
      ].join("|"),
    [card],
  );
  useEffect(() => {
    setDate(card.default_date);
    setPicked(null);
    setLoadedDays({});
    setLoadingDate(null);
    setFailedDate(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset theo GIÁ TRỊ thẻ
  }, [cardKey]);

  // Ngày mà lượt chat ĐÃ chở sẵn ô giờ — đọc từ `default_date`, không suy từ
  // "ngày này có option" (ngày mặc định kín chỗ thì options rỗng nhưng vẫn là
  // ngày đã gửi).
  const shippedDate = card.default_date;

  // Nạp ô giờ của ngày khách bấm sang — mirror đúng vòng nạp lười của thẻ
  // trong chat, vì payload lượt chỉ chở ô của ngày mặc định.
  useEffect(() => {
    if (!sessionId || date === shippedDate || loadedDays[date]) return;
    let alive = true;
    setLoadingDate(date);
    setFailedDate((current) => (current === date ? null : current));
    fetchTestDriveAvailability({ sessionId, date })
      .then((result) => {
        if (alive) setLoadedDays((current) => ({ ...current, [result.date]: result.options }));
      })
      .catch(() => {
        // Nói ra chứ không im: lưới mờ toàn bộ không lời giải thích đọc như
        // "hết chỗ cả ngày", trong khi thật ra là chưa hỏi được.
        if (alive) setFailedDate(date);
      })
      .finally(() => {
        if (alive) setLoadingDate((current) => (current === date ? null : current));
      });
    return () => {
      alive = false;
    };
  }, [sessionId, date, shippedDate, loadedDays]);

  const freeCells = useMemo(() => {
    const map = new Map<string, string>();
    for (const option of [...card.options, ...Object.values(loadedDays).flat()]) {
      map.set(`${option.showroom_id}@${option.scheduled_at}`, option.value);
    }
    return map;
  }, [card.options, loadedDays]);

  const day = card.days.find((item) => item.date === date) ?? card.days[0];
  if (!day || !showroom) return null;

  const pickedValue = picked ? (freeCells.get(`${showroom.showroom_id}@${picked}`) ?? null) : null;

  return (
    <div aria-label="Đặt lịch lái thử tại showroom đang chọn" className="tour-panel__schedule" role="group">
      <p className="tour-panel__schedule-title">
        Đặt lịch lái thử {card.vehicle_name} — {showroom.name}
      </p>
      {card.days.length > 1 ? (
        <ul aria-label="Chọn ngày" className="tour-panel__schedule-days">
          {card.days.map((item) => (
            <li key={item.date}>
              <button
                aria-pressed={item.date === day.date}
                className="tour-panel__schedule-day"
                disabled={disabled}
                onClick={() => {
                  setDate(item.date);
                  setPicked(null);
                }}
                type="button"
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="tour-panel__schedule-daylabel">{day.label}</p>
      )}
      <ul aria-label="Chọn khung giờ" className="tour-panel__schedule-times">
        {day.times.map((time) => {
          const free = freeCells.has(`${showroom.showroom_id}@${time.scheduled_at}`);
          return (
            <li key={time.scheduled_at}>
              <button
                aria-pressed={picked === time.scheduled_at && free}
                className="tour-panel__schedule-time"
                disabled={disabled || !free}
                onClick={() => setPicked(time.scheduled_at)}
                title={free ? undefined : `${showroom.name} đã kín giờ này`}
                type="button"
              >
                {time.label}
              </button>
            </li>
          );
        })}
      </ul>
      {loadingDate === date ? (
        <p className="tour-panel__notice" role="status">Đang tải khung giờ…</p>
      ) : null}
      {failedDate === date ? (
        <p className="tour-panel__notice" role="status">
          Dạ em chưa tải được khung giờ của ngày này. Anh/chị chọn lại ngày giúp em nhé.
        </p>
      ) : null}
      {/* Có nút xác nhận, không gửi ngay khi bấm ô giờ — đặt lịch là bước
          không được lỡ tay (cùng luật với thẻ trong chat). */}
      <button
        className="tour-panel__schedule-confirm"
        disabled={disabled || !pickedValue}
        onClick={() => pickedValue && onConfirm(pickedValue)}
        type="button"
      >
        Đặt lịch
      </button>
    </div>
  );
}
