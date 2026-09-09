"use client";

import { LocateFixed, Send } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { fetchTestDriveAvailability, fetchTestDriveOptions } from "@/lib/api/agent";
import type {
  QuickReply,
  TestDriveCard as TestDriveCardData,
  TestDriveOption,
  TestDriveOptionsResponse,
} from "@/types/agent";

/**
 * Thẻ chọn lịch lái thử: cột showroom bên trái, cột giờ dùng chung bên phải.
 *
 * Sếp 2026-08-28: *"hiện ra các thao tác chọn chứ không phải yêu cầu người dùng
 * nhập chat"* — ba showroom gần nhất, cột giờ bên cạnh, *"khi 1 showroom không
 * còn trống giờ đó thì ô chọn giờ đó sẽ bị mờ đi nên sẽ tận dụng được cột giờ,
 * chỉ cần thay đổi cột các showroom"*.
 *
 * **Cột giờ KHÔNG co lại khi đổi showroom.** Ô nào showroom đang chọn hết chỗ
 * thì mờ và không bấm được, nhưng vẫn đứng nguyên chỗ cũ — lưới nhảy mỗi lần bấm
 * là khách mất mốc để so giữa "gần hơn" và "giờ đẹp hơn".
 *
 * **Chỗ trống đọc từ `options`, không tự suy.** Mỗi ô còn chỗ mang sẵn một mã do
 * backend sinh (`domain/test_drive_booking`) chở cả showroom lẫn mốc thời gian.
 * Client không ghép chuỗi đó: sai một tiếng là hẹn khách tới lúc không ai đợi.
 *
 * **Có nút xác nhận.** Bấm ô giờ chỉ là chọn; lịch chỉ chốt khi khách bấm "Đặt
 * lịch" — bước này không được lỡ tay.
 *
 * **MỘT thẻ cho cả xin vị trí lẫn chọn giờ** (Sếp 2026-08-30). Thẻ tới với
 * `needs_location=true` thì chính thẻ xin vị trí — nút GPS hoặc ô gõ quận/huyện
 * — rồi gọi `/agent/test-drive/options` và báo cha THAY thẻ tại chỗ
 * (`onCardReplaced`), không mọc thêm message. Trước đây bot hỏi tỉnh bằng chữ
 * thành một lượt riêng, khách gõ xong mới thấy thẻ: hai lượt cho một việc.
 */
export function TestDriveCard({
  card,
  disabled = false,
  onConfirm,
  onCardReplaced,
  onShowroomChange,
  selectedShowroomId,
  sessionId,
}: {
  card: TestDriveCardData;
  disabled?: boolean;
  sessionId?: string;
  onConfirm: (value: string) => void;
  onCardReplaced?: (card: TestDriveCardData, quickReplies: readonly QuickReply[]) => void;
  /**
   * Đồng bộ với ghim trên bản đồ panel (đợt 9): bấm ghim = chọn showroom ở đây,
   * bấm showroom ở đây = ghim đổi. Tuỳ chọn — thẻ đứng một mình vẫn tự quản.
   */
  onShowroomChange?: (showroomId: string) => void;
  selectedShowroomId?: string | null;
}) {
  const [showroomId, setShowroomId] = useState(card.default_showroom_id);
  // Sếp 2026-08-31: thẻ ĐÃ có showroom vẫn phải đổi được vị trí ngay TRÊN thẻ
  // — khách đặt hộ người thân ở tỉnh khác, hay GPS lần đầu bắt nhầm chỗ. Bật
  // cờ này là thẻ quay về khối xin vị trí (tự xin GPS lại, fallback ô gõ),
  // kết quả mới THAY danh sách showroom tại chỗ qua đúng đường `onCardReplaced`.
  const [relocating, setRelocating] = useState(false);
  // Hook gọi vô điều kiện (luật hooks) — chỉ nhánh relocating dùng tới. Tự tắt
  // cờ NGAY trong onFound: nếu kết quả mới trùng hệt thẻ cũ thì `cardKey` không
  // đổi, effect reset không chạy, và không tắt ở đây là kẹt luôn ở khối locate.
  const relocate = useTestDriveLocate({
    sessionId,
    vehicleId: card.vehicle_id,
    onFound: (result) => {
      setRelocating(false);
      onCardReplaced?.(result.test_drive_card, result.quick_replies ?? []);
    },
  });
  // Chỉ nghe ghim khi nó chỉ vào một showroom CÓ trong thẻ này — ghim của một
  // lượt bản đồ khác không được kéo thẻ về một showroom không có trong cột.
  useEffect(() => {
    if (selectedShowroomId && card.showrooms.some((item) => item.showroom_id === selectedShowroomId)) {
      setShowroomId(selectedShowroomId);
    }
  }, [selectedShowroomId, card.showrooms]);
  const [date, setDate] = useState(card.default_date);
  const [picked, setPicked] = useState<string | null>(null);
  const [showAllDays, setShowAllDays] = useState(false);
  //: Ô giờ nạp thêm cho những ngày lượt chat KHÔNG chở theo, khoá theo ngày.
  const [loadedDays, setLoadedDays] = useState<Record<string, readonly TestDriveOption[]>>({});
  const [loadingDate, setLoadingDate] = useState<string | null>(null);
  //: NGÀY nào hỏng, không phải một cờ chung. Cờ chung thì dòng lỗi của ngày
  //: hỏng còn đứng nguyên sau khi khách quay về một ngày đã có sẵn — effect
  //: thoát sớm ở đó nên không ai xoá nó.
  const [failedDate, setFailedDate] = useState<string | null>(null);

  //: Danh tính của thẻ theo GIÁ TRỊ, không theo object.
  //
  // `useEffect(..., [card])` so bằng identity. Một cha dựng object thẻ mới mỗi
  // lần render sẽ xoá sạch cache sau mỗi lần render, và mỗi lần đổi ngày lại là
  // một vòng chờ mạng nữa. Khoá theo nội dung thì không dính vào chuyện đó, mà
  // thẻ của một LƯỢT MỚI (khác xe, khác ngày, khác showroom) vẫn reset đúng.
  const cardKey = useMemo(
    () =>
      [
        card.vehicle_name,
        card.default_showroom_id,
        card.default_date,
        card.showrooms.map((item) => item.showroom_id).join(","),
        card.days.map((item) => item.date).join(","),
      ].join("|"),
    [card],
  );

  // Thẻ mới của một lượt mới thì bỏ hết lựa chọn đang dở: giờ của lượt trước
  // thuộc về một danh sách showroom khác.
  useEffect(() => {
    setShowroomId(card.default_showroom_id);
    setDate(card.default_date);
    setPicked(null);
    setShowAllDays(false);
    setLoadedDays({});
    setLoadingDate(null);
    setFailedDate(null);
    setRelocating(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset theo GIÁ TRỊ thẻ
  }, [cardKey]);

  //: Ngày mà lượt chat ĐÃ chở sẵn ô giờ — không cần hỏi lại server.
  //
  // Đọc từ `default_date`, KHÔNG suy từ "ngày này có option". Ngày mặc định vẫn
  // là ngày đã gửi kể cả khi nó kín chỗ và `options` rỗng — suy từ chỗ trống thì
  // đúng ca đó client hỏi lại server một câu đã có câu trả lời.
  const shippedDate = card.default_date;

  // Nạp ô giờ của ngày khách vừa bấm sang.
  //
  // Bước nạp lười cắt `options` xuống còn ô của ngày mặc định (126 → 18 ô).
  // Thẻ vẫn bày đủ bảy ngày, nên thiếu vòng này thì khách bấm sang ngày thứ tư
  // và thấy MỌI khung đều mờ: payload nhẹ đi, chức năng thì gãy.
  //
  // Nạp rồi thì giữ lại: khách so qua so lại giữa hai ngày là chuyện thường, và
  // hỏi server mỗi lần bấm là một vòng chờ không cần thiết.
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
        // Nói ra chứ không im: một lưới mờ toàn bộ mà không có lời giải thích
        // đọc như "hết chỗ cả ngày", trong khi thật ra là chưa hỏi được.
        if (alive) setFailedDate(date);
      })
      .finally(() => {
        // Chỉ tắt chữ "đang tải" nếu yêu cầu này VẪN là yêu cầu hiện tại. Khách
        // bấm nhanh qua hai ngày thì yêu cầu cũ về trước, và nếu nó tắt vô điều
        // kiện thì ngày đang chờ trông như đã tải xong.
        if (alive) setLoadingDate((current) => (current === date ? null : current));
      });
    return () => {
      alive = false;
    };
  }, [sessionId, date, shippedDate, loadedDays]);

  //: Tra "ô này còn chỗ không" trong một bước, thay vì quét lại mảng cho từng ô.
  const freeCells = useMemo(() => {
    const map = new Map<string, string>();
    for (const option of [...card.options, ...Object.values(loadedDays).flat()]) {
      map.set(`${option.showroom_id}@${option.scheduled_at}`, option.value);
    }
    return map;
  }, [card.options, loadedDays]);

  const day = card.days.find((item) => item.date === date) ?? card.days[0];
  const showroom = card.showrooms.find((item) => item.showroom_id === showroomId) ?? card.showrooms[0];

  if (card.needs_location || !day || !showroom) {
    // Thẻ chưa có showroom nào — hoặc backend nói thẳng `needs_location`, hoặc
    // trả 200 với `showrooms=[]` (geocode không ra). Cả hai đều về cùng một
    // khối xin vị trí, để khách thử lại ngay trong thẻ thay vì thẻ biến mất.
    return (
      <TestDriveLocate
        card={card}
        disabled={disabled}
        onCardReplaced={onCardReplaced}
        sessionId={sessionId}
      />
    );
  }

  if (relocating) {
    // Khách bấm "Đổi vị trí": chính thẻ quay về khối xin vị trí — cùng flow
    // với thẻ `needs_location` (tự xin GPS, quá 8s/từ chối thì bày ô gõ). Danh
    // sách showroom cũ vẫn nằm trong `card`, nên có nút giữ lại để lùi.
    return (
      <section aria-label="Chọn lịch lái thử" className="test-drive-card">
        <p className="test-drive-card__title">Đặt lịch lái thử {card.vehicle_name}</p>
        <div className="test-drive-card__locate">
          <TestDriveAutoLocate
            description="Cho em biết vị trí mới để em tìm lại showroom gần nhất và khung giờ còn trống nhé."
            disabled={disabled}
            locate={relocate}
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
      </section>
    );
  }

  const pickedValue = picked && freeCells.has(picked) ? freeCells.get(picked) : null;

  return (
    <section aria-label="Chọn lịch lái thử" className="test-drive-card">
      <p className="test-drive-card__title">Đặt lịch lái thử {card.vehicle_name}</p>

      <p className="test-drive-card__day">{day.label}</p>

      <div className="test-drive-card__grid">
        <ul className="test-drive-card__showrooms">
          {card.showrooms.map((item) => (
            <li key={item.showroom_id}>
              <button
                aria-pressed={item.showroom_id === showroom.showroom_id}
                className="test-drive-card__showroom"
                disabled={disabled}
                onClick={() => {
                  setShowroomId(item.showroom_id);
                  onShowroomChange?.(item.showroom_id);
                  // Giữ nguyên giờ đang chọn NẾU showroom mới cũng còn chỗ giờ
                  // đó — khách không phải bấm lại. Không còn chỗ thì bỏ chọn,
                  // chứ không để một ô mờ trông như đang được chọn.
                  setPicked((current) => {
                    if (!current) return null;
                    const moved = `${item.showroom_id}@${current.split("@")[1]}`;
                    return freeCells.has(moved) ? moved : null;
                  });
                }}
                type="button"
              >
                <span className="test-drive-card__showroom-name">{item.name}</span>
                <span className="test-drive-card__showroom-meta">{item.distance_label}</span>
                <span className="test-drive-card__showroom-address">{item.address}</span>
              </button>
            </li>
          ))}
        </ul>

        <ul className="test-drive-card__times">
          {day.times.map((time) => {
            const key = `${showroom.showroom_id}@${time.scheduled_at}`;
            const free = freeCells.has(key);
            return (
              <li key={time.scheduled_at}>
                <button
                  aria-pressed={picked === key}
                  className="test-drive-card__time"
                  disabled={disabled || !free}
                  onClick={() => setPicked(key)}
                  title={free ? undefined : `${showroom.name} đã kín giờ này`}
                  type="button"
                >
                  {time.label}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Nút phụ ngay dưới cột showroom: mọi thao tác vị trí nằm TRÊN thẻ,
          không bắt khách gõ chat "tôi ở chỗ khác" rồi chờ một lượt mới. */}
      <button
        aria-label="Đổi vị trí, tìm showroom khác"
        className="test-drive-card__relocate"
        disabled={disabled}
        onClick={() => setRelocating(true)}
        type="button"
      >
        <LocateFixed aria-hidden="true" size={14} />
        <span>Đổi vị trí · tìm showroom khác</span>
      </button>

      {card.days.length > 1 ? (
        showAllDays ? (
          <ul className="test-drive-card__days">
            {card.days.map((item) => (
              <li key={item.date}>
                <button
                  aria-pressed={item.date === day.date}
                  className="test-drive-card__day-tab"
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
          <button
            className="test-drive-card__more-days"
            disabled={disabled}
            onClick={() => setShowAllDays(true)}
            type="button"
          >
            Xem ngày khác
          </button>
        )
      ) : null}

      {/* Chỉ hiện cho ĐÚNG ngày đang xem. Yêu cầu của một ngày bị bỏ giữa chừng
          không bao giờ chạy `.finally()`, nên `loadingDate` kẹt lại ở ngày cũ —
          và dòng "Đang tải…" đứng mãi trên một ngày đã có sẵn đủ ô. */}
      {loadingDate === date ? (
        <p className="test-drive-card__notice" role="status">
          Đang tải khung giờ…
        </p>
      ) : null}
      {failedDate === date ? (
        <p className="test-drive-card__notice" role="status">
          Dạ em chưa tải được khung giờ của ngày này. Anh/chị chọn lại ngày giúp em nhé.
        </p>
      ) : null}

      <button
        className="test-drive-card__confirm"
        disabled={disabled || !pickedValue}
        onClick={() => pickedValue && onConfirm(pickedValue)}
        type="button"
      >
        Đặt lịch
      </button>
    </section>
  );
}

type LocateStatus =
  | { readonly kind: "idle" }
  | { readonly kind: "locating" }
  | { readonly kind: "searching" }
  | { readonly kind: "error"; readonly text: string };

export type LocateWhere = { latitude: number; longitude: number } | { locationText: string };

/**
 * Logic xin vị trí rồi gọi `/agent/test-drive/options` — tách khỏi giao diện để
 * hai chỗ dùng chung: khối xin vị trí TRONG thẻ lái thử, và panel bản đồ (đợt
 * 9) khi `needs_location`. Hai nguồn, cùng luật với `location-request.tsx`
 * (trạm sạc): `navigator.geolocation` là nút chính, ô gõ quận/huyện là đường
 * dự phòng. Kết quả KHÔNG gửi tin nhắn chat mà giao cho `onFound` — nơi gọi tự
 * quyết thay thẻ tại chỗ / mở bản đồ.
 */
export function useTestDriveLocate({
  onFound,
  sessionId,
  vehicleId,
}: {
  sessionId?: string;
  vehicleId: string;
  onFound: (result: TestDriveOptionsResponse, where: LocateWhere) => void;
}) {
  const [status, setStatus] = useState<LocateStatus>({ kind: "idle" });
  const busy = status.kind === "locating" || status.kind === "searching";

  async function lookup(where: LocateWhere): Promise<void> {
    if (!sessionId) {
      setStatus({ kind: "error", text: "Phiên chat chưa sẵn sàng, anh/chị thử lại sau giây lát nhé." });
      return;
    }
    setStatus({ kind: "searching" });
    try {
      const result = await fetchTestDriveOptions({ sessionId, vehicleId, ...where });
      const found = result.test_drive_card;
      if (!found || found.showrooms.length === 0) {
        // Geocode không ra: giữ nguyên khối xin vị trí, nói lý do, cho gõ lại.
        setStatus({ kind: "error", text: result.message || "Chưa tìm thấy showroom quanh đây." });
        return;
      }
      setStatus({ kind: "idle" });
      onFound(result, where);
    } catch {
      setStatus({ kind: "error", text: "Dạ em chưa tìm được showroom lúc này. Anh/chị thử lại giúp em nhé." });
    }
  }

  function requestPosition(): void {
    // Kiểm GIÁ TRỊ chứ không kiểm `in`: môi trường có property nhưng giá trị
    // `undefined` (webview khoá GPS, jsdom) mà lọt qua là crash ngay dòng dưới
    // — và giờ hàm này TỰ chạy lúc thẻ mount nên crash là sập cả khung chat.
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setStatus({ kind: "error", text: "Không lấy được toạ độ GPS lúc này. Anh/chị gõ quận/huyện bên dưới nhé." });
      return;
    }
    setStatus({ kind: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) =>
        void lookup({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      (error) =>
        setStatus({
          kind: "error",
          text:
            error.code === error.PERMISSION_DENIED
              ? "Trình duyệt đã từ chối quyền vị trí. Anh/chị gõ quận/huyện bên dưới nhé."
              : "Không lấy được toạ độ GPS lúc này. Anh/chị gõ quận/huyện bên dưới nhé.",
        }),
      // timeout 8s (đợt 10): GPS giờ TỰ chạy ngay khi thẻ hiện — khách đang
      // nhìn dòng "Đang xác định vị trí…" chờ, nên quá 8 giây không ra toạ độ
      // thì thà nhả sớm về ô gõ quận/huyện còn hơn bắt chờ thêm.
      { enableHighAccuracy: true, maximumAge: 60_000, timeout: 8_000 },
    );
  }

  return { busy, lookupText: (text: string) => lookup({ locationText: text }), requestPosition, status };
}

/**
 * Nút GPS + ô gõ quận/huyện + dòng trạng thái. Mọi trạng thái (đang định vị /
 * đang tìm / lỗi / không thấy showroom) hiện NGAY TẠI khối — khách không phải
 * đọc lỗi ở một chỗ khác.
 */
export function TestDriveLocateControls({
  disabled = false,
  locate,
}: {
  disabled?: boolean;
  locate: ReturnType<typeof useTestDriveLocate>;
}) {
  const [draft, setDraft] = useState("");
  const { busy, status } = locate;

  function submitText(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    void locate.lookupText(text);
  }

  return (
    <>
      <button
        className="location-gps-button"
        disabled={disabled || busy}
        onClick={locate.requestPosition}
        type="button"
      >
        <LocateFixed className={status.kind === "locating" ? "animate-spin" : ""} size={18} />
        <span>{status.kind === "locating" ? "Đang xác định toạ độ..." : "Dùng vị trí của tôi"}</span>
      </button>
      <div className="location-divider">
        <span>hoặc gõ quận/huyện</span>
      </div>
      <form className="location-input-form" onSubmit={submitText}>
        <input
          aria-label="Quận/huyện, tỉnh"
          disabled={disabled || busy}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Quận/huyện, tỉnh — ví dụ: Cầu Giấy, Hà Nội"
          value={draft}
        />
        <button aria-label="Tìm showroom" disabled={disabled || busy || !draft.trim()} type="submit">
          <Send size={15} />
          <span>Tìm</span>
        </button>
      </form>
      {status.kind === "searching" ? (
        <p className="test-drive-card__notice" role="status">
          Đang tìm showroom và khung giờ…
        </p>
      ) : null}
      {status.kind === "error" ? (
        <p className="location-request-error" role="status">
          {status.text}
        </p>
      ) : null}
    </>
  );
}

/**
 * Khối "tự xin GPS rồi mới bày ô gõ" — phần dùng chung của flow xin vị trí
 * (đợt 10), tách riêng vì nay có BA chỗ mount nó: thẻ `needs_location`, thẻ
 * đã có showroom bấm "Đổi vị trí", và khối bản đồ trong panel.
 *
 * GPS TỰ chạy ngay khi khối hiện ra — đa số khách chỉ cần bấm "Cho phép" của
 * trình duyệt là xong, không phải bấm thêm nút nào. Ô gõ quận/huyện là đường
 * DỰ PHÒNG: chỉ bày ra sau khi GPS thất bại (từ chối / quá 8s / không hỗ
 * trợ), vì bày cùng lúc với dòng "Đang xác định vị trí…" thì khách không biết
 * nên chờ hay nên gõ. Nút "Dùng vị trí của tôi" vẫn còn trong khối dự phòng
 * để thử GPS lại.
 */
export function TestDriveAutoLocate({
  description,
  disabled = false,
  locate,
}: {
  description: string;
  disabled?: boolean;
  locate: ReturnType<typeof useTestDriveLocate>;
}) {
  const { requestPosition, status } = locate;

  // Tự xin GPS đúng MỘT lần cho mỗi lần khối này mount — không theo render và
  // không tự chạy lại sau khi khách từ chối: prompt quyền bật lại liên tục là
  // cách nhanh nhất để bị trình duyệt chặn hẳn; muốn thử lại đã có nút GPS.
  const autoRequested = useRef(false);
  useEffect(() => {
    if (autoRequested.current) return;
    autoRequested.current = true;
    requestPosition();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chạy một lần lúc mount; requestPosition dựng lại mỗi render
  }, []);

  // Đã rơi vào lỗi một lần thì khối dự phòng Ở LẠI: khách bấm thử GPS lần nữa
  // (status quay về "locating") mà ô gõ biến mất thì đường lui vừa hứa bị rút.
  const [fallbackShown, setFallbackShown] = useState(false);
  useEffect(() => {
    if (status.kind === "error") setFallbackShown(true);
  }, [status.kind]);

  return fallbackShown ? (
    <>
      <p className="test-drive-card__locate-desc">{description}</p>
      <TestDriveLocateControls disabled={disabled} locate={locate} />
    </>
  ) : (
    // GPS đang chạy (hoặc đã có toạ độ, đang hỏi khung giờ): chỉ một dòng
    // trạng thái. Thành công thì nơi gọi tự xử lý kết quả, thất bại thì nhánh
    // trên hiện khối dự phòng — không có ngã ba thứ ba.
    <p className="test-drive-card__notice" role="status">
      {status.kind === "searching" ? "Đang tìm showroom và khung giờ…" : "Đang xác định vị trí…"}
    </p>
  );
}

/**
 * Khối xin vị trí bên trong thẻ lái thử `needs_location`. Khi có showroom thì
 * báo cha THAY thẻ tại chỗ (`onCardReplaced`), không mọc thêm message.
 */
function TestDriveLocate({
  card,
  disabled,
  onCardReplaced,
  sessionId,
}: {
  card: TestDriveCardData;
  disabled: boolean;
  sessionId?: string;
  onCardReplaced?: (card: TestDriveCardData, quickReplies: readonly QuickReply[]) => void;
}) {
  const locate = useTestDriveLocate({
    sessionId,
    vehicleId: card.vehicle_id,
    onFound: (result) => onCardReplaced?.(result.test_drive_card, result.quick_replies ?? []),
  });

  return (
    <section aria-label="Chọn lịch lái thử" className="test-drive-card">
      <p className="test-drive-card__title">Đặt lịch lái thử {card.vehicle_name}</p>
      <div className="test-drive-card__locate">
        <TestDriveAutoLocate
          description="Cho em biết anh/chị ở đâu để em tìm showroom gần nhất và khung giờ còn trống nhé."
          disabled={disabled}
          locate={locate}
        />
      </div>
    </section>
  );
}
