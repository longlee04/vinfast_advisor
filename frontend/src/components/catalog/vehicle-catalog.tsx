"use client";

import { ArrowLeftRight, ArrowRight, BatteryCharging, BatteryFull, Check, Gauge, Info, Plus, Search, UsersRound, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";

import { OpenAgentDockButton } from "@/components/customer/open-agent-dock-button";
import { localCatalogVehicles, type LocalCatalogVehicle } from "@/data/product-experience";
import { formatVnd } from "@/lib/format";
import { useDemoStore } from "@/store/demo-store";

type CatalogFilter = "all" | LocalCatalogVehicle["vehicleType"];

function formatPrice(priceVnd: number | null): string {
  return priceVnd === null ? "Đang cập nhật" : formatVnd(priceVnd);
}

export function VehicleCatalog({ initialFilter = "all" }: Readonly<{ initialFilter?: CatalogFilter }>) {
  const { state, toggleSelectedVehicle } = useDemoStore();
  const [filter, setFilter] = useState<CatalogFilter>(initialFilter);
  const [query, setQuery] = useState("");
  const [detailVehicle, setDetailVehicle] = useState<LocalCatalogVehicle | null>(null);
  const [expanded, setExpanded] = useState(false);

  const filteredVehicles = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("vi");
    return localCatalogVehicles.filter((vehicle) => {
      const matchesType = filter === "all" || vehicle.vehicleType === filter;
      return matchesType && (!normalizedQuery || vehicle.modelName.toLocaleLowerCase("vi").includes(normalizedQuery));
    });
  }, [filter, query]);
  const visibleVehicles = expanded ? filteredVehicles : filteredVehicles.slice(0, 7);

  return (
    <>
      <div className="catalog-toolbar">
        <div className="catalog-filter-tabs" aria-label="Lọc loại phương tiện">
          {([ ["all", "Tất cả"], ["car", "Ô tô điện"], ["electric_motorbike", "Xe máy điện"] ] as const).map(([value, label]) => (
            <button className={filter === value ? "is-active" : ""} key={value} onClick={() => setFilter(value)} type="button">{label}</button>
          ))}
        </div>
        <label className="catalog-search"><Search size={17} /><span className="sr-only">Tìm mẫu xe</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Tìm theo tên xe..." value={query} /></label>
      </div>

      {/* Một dòng nhẹ, một màu — không phải hai cụm chữ hai màu như bảng điều khiển. */}
      <p className="catalog-result-note">{filteredVehicles.length} mẫu xe sẵn sàng để anh/chị khám phá</p>

      {filteredVehicles.length ? (
        <div className="customer-catalog-grid">
          {visibleVehicles.map((vehicle) => {
            const selected = state.selectedVehicleIds.includes(vehicle.id);
            return (
              <article className="customer-vehicle-card" id={vehicle.id} key={vehicle.id}>
                <div className="catalog-vehicle-visual"><Image alt={vehicle.modelName} fill sizes="(max-width: 640px) 100vw, 50vw" src={vehicle.imageUrl} /></div>
                <div className="catalog-vehicle-content">
                  <div className="catalog-title-row"><div><small>{vehicle.vehicleType === "car" ? "Ô tô điện" : "Xe máy điện"}</small><h2>{vehicle.modelName}</h2></div><strong>{formatPrice(vehicle.priceVnd)}</strong></div>
                  <div className="catalog-spec-row">
                    {vehicle.rangeKm !== null ? <span><Gauge size={16} />{vehicle.rangeKm} km</span> : null}
                    {vehicle.seats !== null ? <span><UsersRound size={16} />{vehicle.seats} chỗ</span> : null}
                    {vehicle.chargeMinutes !== null ? <span><BatteryCharging size={16} />{vehicle.chargeMinutes} phút sạc</span> : null}
                    {vehicle.batteryCapacityKwh !== null ? <span><BatteryFull size={16} />{vehicle.batteryCapacityKwh} kWh</span> : null}
                  </div>
                  {/* "Thông tin sản phẩm local" là chữ nội bộ — đã BỎ, không lộ ra khách. */}
                  {/* Một việc chính "Xem chi tiết" (nút đậm), hai việc phụ thu về icon tròn
                      40px (ⓘ thông số nhanh, ⇄ so sánh) — tên đọc được nằm ở aria-label +
                      title, chọn so sánh thì icon đổi màu viền (Sếp 2026-08-31). */}
                  <div className="catalog-card-actions">
                    <Link className="catalog-action-primary" href={vehicle.href}>Xem chi tiết<ArrowRight size={16} /></Link>
                    <button
                      aria-label={`Thông số nhanh ${vehicle.modelName}`}
                      className="catalog-action-icon"
                      onClick={() => setDetailVehicle(vehicle)}
                      title="Thông số nhanh"
                      type="button"
                    >
                      <Info aria-hidden="true" size={18} />
                    </button>
                    <button
                      aria-label={selected ? `Đã chọn so sánh ${vehicle.modelName}` : `So sánh ${vehicle.modelName}`}
                      aria-pressed={selected}
                      className={selected ? "catalog-action-icon is-selected" : "catalog-action-icon"}
                      onClick={() => toggleSelectedVehicle(vehicle.id)}
                      title="So sánh"
                      type="button"
                    >
                      <ArrowLeftRight aria-hidden="true" size={18} />
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : <div className="state-panel compact-state"><Search size={34} /><h2>Không tìm thấy mẫu xe</h2><p>Thử đổi từ khoá hoặc chọn lại loại phương tiện.</p><button className="secondary-button" onClick={() => { setFilter("all"); setQuery(""); }} type="button">Xoá bộ lọc</button></div>}

      {filteredVehicles.length > 7 ? <button className="catalog-show-more" onClick={() => setExpanded((value) => !value)} type="button">{expanded ? "Rút gọn" : `Xem thêm ${filteredVehicles.length - 7} mẫu xe`}</button> : null}

      {/* Thanh so sánh dính đáy: CHỈ hiện khi khách đã chọn ≥1 xe — không chọn gì
          thì "0 xe đang được chọn" chỉ là tiếng ồn. Đặt NGAY TRÊN thanh trợ lý
          (agent-dock) bằng CSS, không đè lên nhau (Sếp 2026-08-31). */}
      {state.selectedVehicleIds.length > 0 ? (
        <div className="catalog-compare-tray" role="status">
          <span>{state.selectedVehicleIds.length} xe đang được chọn để so sánh</span>
          <Link className="primary-button" href="/compare">So sánh ngay <ArrowRight size={16} /></Link>
        </div>
      ) : null}

      {detailVehicle ? <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="vehicle-detail-title"><button className="dialog-backdrop" aria-label="Đóng chi tiết xe" onClick={() => setDetailVehicle(null)} type="button" /><section className="mock-dialog vehicle-detail-dialog"><div className="dialog-heading"><div><span className="eyebrow">Thông tin xe</span><h2 id="vehicle-detail-title">{detailVehicle.modelName}</h2></div><button className="icon-button" onClick={() => setDetailVehicle(null)} aria-label="Đóng" type="button"><X size={19} /></button></div><div className="vehicle-detail-hero"><Image alt={detailVehicle.modelName} fill sizes="720px" src={detailVehicle.imageUrl} /></div><div className="vehicle-detail-grid"><div><span>Giá niêm yết</span><strong>{formatPrice(detailVehicle.priceVnd)}</strong></div>{detailVehicle.quickSpecs.map((spec) => <div key={spec.label}><span>{spec.label}</span><strong>{spec.value}</strong></div>)}</div>{(() => { const chosen = state.selectedVehicleIds.includes(detailVehicle.id); return (
                  <div className="dialog-actions vehicle-detail-actions">
                    <Link className="secondary-button" href={detailVehicle.href}>Xem chi tiết<ArrowRight size={16} /></Link>
                    <button aria-pressed={chosen} className={chosen ? "secondary-button is-selected" : "secondary-button"} onClick={() => toggleSelectedVehicle(detailVehicle.id)} type="button">{chosen ? <Check size={16} /> : <Plus size={16} />}{chosen ? "Đã chọn so sánh" : "Thêm so sánh"}</button>
                    <OpenAgentDockButton className="primary-button" prompt={`Tư vấn giúp tôi về ${detailVehicle.modelName}`}>Tư vấn mẫu này</OpenAgentDockButton>
                  </div>); })()}</section></div> : null}
    </>
  );
}
