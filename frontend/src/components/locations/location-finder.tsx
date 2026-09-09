"use client";

import dynamic from "next/dynamic";
import {
  BatteryCharging,
  Bike,
  BusFront,
  CarFront,
  ChevronRight,
  Crosshair,
  LocateFixed,
  MapPin,
  Navigation,
  RefreshCw,
  Search,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchCategories,
  fetchLocations,
  fetchNearby,
  fetchRegions,
  type LocationCategory,
  type LocationRegion,
  type MapBounds,
} from "@/lib/api/locations";
import type { MobilityLocation, MobilityLocationCategory, UserPosition } from "@/types/location";

const LocationMap = dynamic(() => import("@/components/locations/location-map"), {
  loading: () => <div className="location-map-loading">Đang tải bản đồ…</div>,
  ssr: false,
});

type CategoryOption = {
  id: MobilityLocationCategory;
  label: string;
  icon: LucideIcon;
  appearance: "showroom" | "service" | "charge" | "swap";
  defaultEnabled: boolean;
};

const CATEGORY_OPTIONS: CategoryOption[] = [
  { id: "showroom_car", label: "Showroom Ô tô", icon: CarFront, appearance: "showroom", defaultEnabled: true },
  { id: "showroom_escooter", label: "Showroom Xe máy điện", icon: Bike, appearance: "showroom", defaultEnabled: true },
  { id: "service_car", label: "Xưởng dịch vụ Ô tô", icon: Wrench, appearance: "service", defaultEnabled: false },
  { id: "service_car_partner", label: "Xưởng dịch vụ Ô tô - Đối tác", icon: Wrench, appearance: "service", defaultEnabled: false },
  { id: "service_bus", label: "Xưởng dịch vụ Bus", icon: BusFront, appearance: "service", defaultEnabled: false },
  { id: "service_escooter", label: "Xưởng dịch vụ Xe máy điện", icon: Wrench, appearance: "service", defaultEnabled: false },
  { id: "service_gsm", label: "Xưởng dịch vụ GSM", icon: Wrench, appearance: "service", defaultEnabled: false },
  { id: "car_charging_station", label: "Trạm sạc Ô tô điện", icon: BatteryCharging, appearance: "charge", defaultEnabled: false },
  { id: "bike_charging_station", label: "Trạm sạc Xe máy điện", icon: BatteryCharging, appearance: "charge", defaultEnabled: false },
  { id: "battery_swap_station", label: "Tủ đổi pin", icon: RefreshCw, appearance: "swap", defaultEnabled: false },
];

const DEFAULT_FILTERS = Object.fromEntries(
  CATEGORY_OPTIONS.map((option) => [option.id, option.defaultEnabled]),
) as Record<MobilityLocationCategory, boolean>;

const STATUS_LABELS: Record<MobilityLocation["status"], string> = {
  open: "Đang hoạt động",
  maintenance: "Tạm ngừng hoạt động",
};

const NUMBER_FORMATTER = new Intl.NumberFormat("vi-VN");
const RESULT_LIMIT = 80;

function categoryOption(category: MobilityLocationCategory): CategoryOption {
  return CATEGORY_OPTIONS.find((option) => option.id === category) ?? CATEGORY_OPTIONS[0];
}

export function LocationFinder() {
  const [locations, setLocations] = useState<MobilityLocation[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<LocationCategory[]>([]);
  const [regions, setRegions] = useState<LocationRegion[]>([]);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [typeFilters, setTypeFilters] = useState(DEFAULT_FILTERS);
  const [dataError, setDataError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  // `?q=` từ URL điền sẵn ô tìm (Sếp 2026-08-31): câu xác nhận đặt lịch trong
  // chat trỏ về "/locations?q=<tên showroom>" — khách vào là thấy đúng showroom
  // của lịch hẹn, bấm nó là có nút Chỉ đường (Google Maps theo toạ độ thật).
  // Đọc trong effect thay vì useSearchParams: trang này prerender tĩnh, đọc URL
  // lúc render server là mismatch hydration.
  //: Vừa vào bằng link ?q= — kết quả đầu tiên sẽ được TỰ CHỌN để panel chi
  //: tiết + nút Chỉ đường hiện ngay, map bay tới điểm đó.
  const presetQueryRef = useRef(false);
  useEffect(() => {
    const preset = new URLSearchParams(window.location.search).get("q");
    if (preset) {
      presetQueryRef.current = true;
      setQuery(preset);
    }
  }, []);
  const [city, setCity] = useState("all");
  const [district, setDistrict] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [userPosition, setUserPosition] = useState<UserPosition | null>(null);
  const [consentOpen, setConsentOpen] = useState(true);
  const [locationState, setLocationState] = useState<"idle" | "loading" | "denied" | "unavailable">("idle");

  // Danh mục và vùng (tỉnh/quận) chỉ đổi khi dữ liệu nguồn đổi, không phụ
  // thuộc bộ lọc hay khung nhìn — nạp một lần khi mount.
  useEffect(() => {
    void (async () => {
      try {
        const [loadedCategories, loadedRegions] = await Promise.all([fetchCategories(), fetchRegions()]);
        setCategories(loadedCategories);
        setRegions(loadedRegions);
      } catch {
        setDataError("Không tải được danh mục địa điểm.");
      }
    })();
  }, []);

  // Danh sách loại đang được tích chọn — dùng chung cho reload() (khung nhìn
  // bản đồ) và selectNearest() (tìm gần nhất) để cả hai luôn tôn trọng cùng
  // một bộ lọc của người dùng.
  const activeTypes = useMemo(
    () => CATEGORY_OPTIONS.filter((option) => typeFilters[option.id]).map((option) => option.id),
    [typeFilters],
  );

  // Theo dõi request /locations đang chạy: mỗi lần reload() được gọi (đổi
  // khung nhìn, đổi bộ lọc) huỷ request trước đó và chỉ request MỚI NHẤT mới
  // được phép ghi vào state — tránh phản hồi đến trễ (pan/zoom nhanh, gõ tìm
  // kiếm liên tục) ghi đè kết quả của một khung nhìn/bộ lọc mới hơn. Cùng mẫu
  // với `activeRequestRef` trong `tco-calculator.tsx`.
  const activeRequestRef = useRef<AbortController | null>(null);

  // Danh sách địa điểm nạp lại mỗi khi khung nhìn bản đồ hoặc bộ lọc đổi.
  // Backend đã lọc theo bbox/loại/tỉnh/quận/từ khoá nên không lọc lại ở client.
  const reload = useCallback(async () => {
    // Chưa có khung nhìn thật từ bản đồ (chưa mount xong) thì không gọi API:
    // tránh một lần tải toàn quốc không giới hạn ở lần đầu, bị lần tải có
    // khung nhìn thật (đến ngay sau đó) ghi đè ngay lập tức.
    // Có TỪ KHOÁ thì không cần chờ khung nhìn: tìm theo tên là tìm toàn quốc.
    if (!bounds && !query) return;

    activeRequestRef.current?.abort();
    const controller = new AbortController();
    activeRequestRef.current = controller;
    setLoading(true);
    setDataError(null);
    try {
      const result = await fetchLocations(
        // Có TỪ KHOÁ thì tìm TOÀN QUỐC, bỏ giới hạn khung nhìn (Sếp 2026-08-31:
        // vào từ link "?q=<showroom>" thấy kết quả rồi "chưa kịp bấm thì mất" —
        // map đổi khung, nhất là lúc cho GPS, là bbox nuốt lại kết quả tìm).
        { bounds: query ? undefined : (bounds ?? undefined), types: activeTypes, city, district, q: query || undefined },
        controller.signal,
      );
      if (activeRequestRef.current !== controller) return; // đã bị request mới hơn thay thế
      setLocations(result.items);
      setTotal(result.total);
      setTruncated(result.truncated);
      if (presetQueryRef.current && result.items.length > 0) {
        // Link từ câu xác nhận đặt lịch: chọn sẵn đúng điểm hẹn — panel chi
        // tiết + nút Chỉ đường hiện luôn, khách chỉ còn một cú bấm.
        presetQueryRef.current = false;
        setSelectedId(result.items[0].id);
      }
    } catch {
      if (activeRequestRef.current !== controller) return;
      setDataError("Không tải được danh sách địa điểm.");
    } finally {
      if (activeRequestRef.current === controller) setLoading(false);
    }
  }, [bounds, activeTypes, city, district, query]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => () => activeRequestRef.current?.abort(), []);

  // Bản đồ chưa từng báo khung nhìn (import động lỗi, mất chunk, v.v.) thì
  // reload() ở trên sẽ mãi không chạy — không có request nào để mà lỗi, nên
  // dataError cũng không tự bật. Đặt một hạn chót ngắn: nếu sau chừng đó vẫn
  // chưa có bounds, báo lỗi rõ ràng thay vì để trang treo ở trạng thái rỗng
  // im lặng mãi mãi.
  useEffect(() => {
    if (bounds) return;
    const timer = setTimeout(() => {
      setDataError((current) => current ?? "Không tải được bản đồ để xác định khu vực tìm kiếm. Vui lòng tải lại trang.");
    }, 8_000);
    return () => clearTimeout(timer);
  }, [bounds]);

  const cities = regions.map((entry) => entry.city);
  const districts = regions.find((entry) => entry.city === city)?.districts ?? [];

  const listLocations = locations.slice(0, RESULT_LIMIT);
  const effectiveSelectedId = selectedId && locations.some((location) => location.id === selectedId)
    ? selectedId
    : null;
  const selectedLocation = locations.find((location) => location.id === effectiveSelectedId) ?? null;

  // Request /locations/nearby riêng cho luồng "vị trí của tôi" — độc lập với
  // activeRequestRef của reload() (khác endpoint, khác vòng đời), nhưng theo
  // cùng kỷ luật huỷ + chỉ nhận kết quả của request mới nhất.
  const nearbyRequestRef = useRef<AbortController | null>(null);

  // Bản gương đồng bộ của `locations`, chỉ để selectNearest() kiểm tra "địa
  // điểm gần nhất đã có trong danh sách chưa" mà không phải lồng thêm một
  // setState nữa bên trong updater của setLocations (lồng setState trong
  // updater có thể chạy hai lần dưới StrictMode và làm `total` tăng sai).
  const locationsRef = useRef<MobilityLocation[]>(locations);
  useEffect(() => {
    locationsRef.current = locations;
  }, [locations]);

  const selectNearest = useCallback(async (position: UserPosition) => {
    nearbyRequestRef.current?.abort();
    const controller = new AbortController();
    nearbyRequestRef.current = controller;
    try {
      // Truyền đúng bộ lọc loại đang bật: nếu không, "gần nhất" có thể trả về
      // một địa điểm thuộc loại người dùng đã bỏ chọn, mâu thuẫn với bộ lọc
      // đang hiển thị cho tới khi reload() kế tiếp chạy.
      const result = await fetchNearby(
        { latitude: position.latitude, longitude: position.longitude, types: activeTypes },
        controller.signal,
      );
      if (nearbyRequestRef.current !== controller) return;
      const nearest = result.items[0];
      if (!nearest) return;

      setSelectedId(nearest.id);
      // Địa điểm gần nhất có thể nằm ngoài khung nhìn bbox hiện tại — chèn
      // thêm vào danh sách để thẻ chi tiết và flyTo trên bản đồ (cả hai đều
      // dựa trên prop `locations`) tìm thấy nó ngay, không chờ vòng reload()
      // kế tiếp (sẽ tự thay thế danh sách này khi bản đồ bay tới). Chỉ tăng
      // `total` khi thực sự chèn thêm — nếu không, số ở đầu trang (lấy từ
      // `total` do server trả) sẽ nhỏ hơn số dòng thực hiển thị, một bất biến
      // (locations.length <= total) mà phần đầu trang ngầm dựa vào.
      const alreadyPresent = locationsRef.current.some((location) => location.id === nearest.id);
      if (!alreadyPresent) {
        setLocations((current) => [nearest, ...current]);
        setTotal((current) => current + 1);
      }
    } catch {
      // Im lặng: không tìm được vị trí gần nhất không nên chặn luồng xem bản đồ.
      if (nearbyRequestRef.current !== controller) return;
    }
  }, [activeTypes]);

  useEffect(() => () => nearbyRequestRef.current?.abort(), []);

  function requestLocation(): void {
    if (!("geolocation" in navigator)) {
      setLocationState("unavailable");
      return;
    }

    setLocationState("loading");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const nextPosition = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        setUserPosition(nextPosition);
        setLocationState("idle");
        setConsentOpen(false);
        void selectNearest(nextPosition);
      },
      (error) => setLocationState(error.code === error.PERMISSION_DENIED ? "denied" : "unavailable"),
      { enableHighAccuracy: true, maximumAge: 60_000, timeout: 10_000 },
    );
  }

  function toggleType(type: MobilityLocationCategory): void {
    setTypeFilters((current) => ({ ...current, [type]: !current[type] }));
  }

  return (
    <div className="locations-page">
      <section className="locations-panel" aria-label="Bộ lọc địa điểm">
        <div className="locations-panel-heading">
          <span className="eyebrow">Mạng lưới toàn quốc</span>
          <h1>Showroom<br />&amp; Trạm sạc</h1>
          <p>
            {categories.length > 0
              ? `${NUMBER_FORMATTER.format(categories.reduce((sum, item) => sum + item.count, 0))} địa điểm trên toàn quốc.`
              : "Đang đọc dữ liệu địa điểm…"}
          </p>
        </div>

        <label className="location-search">
          <span className="sr-only">Tìm theo tên hoặc địa chỉ</span>
          <Search aria-hidden="true" size={19} />
          <input onChange={(event) => setQuery(event.target.value)} placeholder="Tên địa điểm hoặc khu vực" value={query} />
          {query ? <button aria-label="Xóa tìm kiếm" onClick={() => setQuery("")} type="button"><X size={16} /></button> : null}
        </label>

        <div className="location-filter-section">
          <div className="location-filter-heading">
            <strong>Khu vực tìm kiếm</strong>
            <button onClick={() => setConsentOpen(true)} type="button"><LocateFixed size={16} /> Vị trí của tôi</button>
          </div>
          <label className="location-select-label">
            <span>Tỉnh thành</span>
            <select onChange={(event) => { setCity(event.target.value); setDistrict("all"); }} value={city}>
              <option value="all">Tất cả tỉnh thành</option>
              {cities.map((cityName) => <option key={cityName} value={cityName}>{cityName}</option>)}
            </select>
          </label>
          <label className="location-select-label">
            <span>Quận huyện</span>
            <select onChange={(event) => setDistrict(event.target.value)} value={district}>
              <option value="all">Tất cả quận huyện</option>
              {districts.map((districtName) => <option key={districtName} value={districtName}>{districtName}</option>)}
            </select>
          </label>
        </div>

        <fieldset className="location-type-filter">
          <legend>Tìm theo nhu cầu</legend>
          {CATEGORY_OPTIONS.map((option) => {
            const Icon = option.icon;
            const count = categories.find((item) => item.id === option.id)?.count ?? 0;
            return (
              <button aria-pressed={typeFilters[option.id]} key={option.id} onClick={() => toggleType(option.id)} type="button">
                <span className={`location-type-icon is-${option.appearance}`}><Icon size={17} /></span>
                <span>
                  <strong>{option.label}</strong>
                  <small>{`${NUMBER_FORMATTER.format(count)} địa điểm`}</small>
                </span>
                <i aria-hidden="true" className={typeFilters[option.id] ? "is-checked" : ""} />
              </button>
            );
          })}
        </fieldset>

        {dataError ? <div className="location-data-error" role="alert">{dataError}</div> : null}
        <div className="location-results-heading">
          <strong>{NUMBER_FORMATTER.format(total)} địa điểm phù hợp</strong>
          <span>{loading ? "Đang tải…" : locations.length > RESULT_LIMIT ? `Hiển thị ${RESULT_LIMIT} kết quả đầu` : "Trong khung nhìn hiện tại"}</span>
        </div>
        {truncated ? (
          <p className="location-truncated-hint" role="status">
            Khu vực này có nhiều địa điểm hơn số đang hiển thị. Thu nhỏ khu vực trên bản đồ để xem
            chính xác hơn.
          </p>
        ) : null}
        <div className="location-result-list">
          {listLocations.map((location) => {
            const option = categoryOption(location.type);
            const Icon = option.icon;
            return (
              <button className={effectiveSelectedId === location.id ? "is-selected" : ""} key={location.id} onClick={() => setSelectedId(location.id)} type="button">
                <span className={`location-result-icon is-${option.appearance}`}><Icon size={19} /></span>
                <span className="location-result-copy">
                  <small>{option.label}{location.distanceKm !== undefined ? ` · ${location.distanceKm.toFixed(1)} km` : ""}</small>
                  <strong>{location.name}</strong>
                  <span>{location.address}</span>
                </span>
                <ChevronRight aria-hidden="true" size={18} />
              </button>
            );
          })}
          {locations.length === 0 && !loading ? <div className="location-empty"><MapPin size={26} /><strong>Không tìm thấy địa điểm</strong><span>Hãy tích một loại địa điểm hoặc đổi bộ lọc.</span></div> : null}
        </div>
      </section>

      <section className="locations-map-area">
        <LocationMap locations={locations} onBoundsChange={setBounds} onSelect={setSelectedId} selectedId={effectiveSelectedId} userPosition={userPosition} />
        <div className="map-legend"><span><i className="is-showroom" /> Showroom</span><span><i className="is-charge" /> Trạm sạc</span><span><i className="is-service" /> Dịch vụ</span></div>
        {userPosition ? <button className="map-my-location" onClick={() => setConsentOpen(true)} type="button"><Crosshair size={18} /> Đã dùng vị trí của bạn</button> : null}
        {selectedLocation ? (
          <article className="selected-location-card">
            <div className={`selected-location-symbol is-${categoryOption(selectedLocation.type).appearance}`}>
              {(() => { const Icon = categoryOption(selectedLocation.type).icon; return <Icon size={23} />; })()}
            </div>
            <div className="selected-location-main">
              <div><small>{categoryOption(selectedLocation.type).label}</small><h2>{selectedLocation.name}</h2></div>
              <p><MapPin size={15} /> {selectedLocation.address}</p>
              <div className="selected-location-meta">
                <span className={`location-status is-${selectedLocation.status}`}>{STATUS_LABELS[selectedLocation.status]}</span>
                <span>{selectedLocation.openingHours}</span>
                {selectedLocation.phone ? <span>{selectedLocation.phone}</span> : null}
              </div>
            </div>
            <a
              className="location-directions-button"
              href={selectedLocation.directionsUrl || `https://www.google.com/maps/dir/?api=1&destination=${selectedLocation.latitude},${selectedLocation.longitude}`}
              rel="noreferrer"
              target="_blank"
            >
              <Navigation size={17} /> Chỉ đường
            </a>
          </article>
        ) : null}
      </section>

      {consentOpen ? (
        <div className="location-consent-layer" role="dialog" aria-modal="true" aria-labelledby="location-consent-title">
          <div className="location-consent-card">
            <span className="location-consent-icon"><LocateFixed size={25} /></span>
            <span className="eyebrow">Tìm gần bạn</span>
            <h2 id="location-consent-title">Cho phép sử dụng vị trí?</h2>
            <p>Chúng tôi chỉ dùng tọa độ hiện tại để đưa bản đồ về gần bạn và tìm địa điểm gần nhất. Vị trí của bạn không được lưu.</p>
            {locationState === "denied" ? <div className="location-consent-error">Bạn đã từ chối quyền vị trí. Có thể bật lại trong cài đặt quyền của trình duyệt.</div> : null}
            {locationState === "unavailable" ? <div className="location-consent-error">Không thể lấy vị trí lúc này. Bạn vẫn có thể tìm thủ công theo khu vực.</div> : null}
            <div>
              <button className="secondary-button" onClick={() => setConsentOpen(false)} type="button">Tiếp tục không dùng vị trí</button>
              <button className="primary-button" disabled={locationState === "loading"} onClick={requestLocation} type="button">
                <LocateFixed size={17} /> {locationState === "loading" ? "Đang xác định…" : "Cho phép vị trí"}
              </button>
            </div>
            <small>Hộp hỏi này xuất hiện mỗi lần bạn mở trang. Quyết định cấp quyền thực tế do trình duyệt quản lý.</small>
          </div>
        </div>
      ) : null}
    </div>
  );
}
