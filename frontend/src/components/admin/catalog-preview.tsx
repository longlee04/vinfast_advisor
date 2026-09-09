"use client";

import { Eye, Pencil, Plus, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { formatVnd } from "@/lib/format";
import { type AdminVehicle, fetchAdminVehicles, VehicleApiError } from "@/lib/api/vehicles";

type DialogMode = "view" | "edit" | "create" | null;

type StatusMeta = { readonly label: string; readonly tone: "neutral" | "info" | "success" | "warning" | "danger" };

const statusMeta: Record<string, StatusMeta> = {
  ACTIVE: { label: "Đang bán", tone: "success" },
  DRAFT: { label: "Bản nháp", tone: "warning" },
  INACTIVE: { label: "Ngừng bán", tone: "neutral" },
  ARCHIVED: { label: "Đã lưu trữ", tone: "danger" },
};

function statusOf(status: string): StatusMeta {
  return statusMeta[status] ?? { label: status, tone: "neutral" };
}

function formatPrice(priceVnd: number | null): string {
  return priceVnd === null ? "Chưa có giá" : formatVnd(priceVnd);
}

export function CatalogPreview() {
  const [vehicles, setVehicles] = useState<AdminVehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [activeVehicle, setActiveVehicle] = useState<AdminVehicle | null>(null);
  const requestSequence = useRef(0);

  const reload = useCallback(async () => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setLoading(true);
    setAuthError(false);
    setLoadError(null);
    try {
      const page = await fetchAdminVehicles({ pageSize: 100 });
      if (sequence !== requestSequence.current) return;
      setVehicles(page.items);
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      if (error instanceof VehicleApiError && (error.status === 401 || error.status === 403)) {
        setAuthError(true);
      } else {
        setLoadError("Không tải được danh sách phương tiện.");
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  function open(mode: Exclude<DialogMode, null>, vehicle: AdminVehicle | null = null): void {
    setActiveVehicle(vehicle);
    setDialog(mode);
  }

  return (
    <>
      <section className="ops-panel"><div className="ops-panel-heading"><div><h2>Danh sách phương tiện</h2><p>Dữ liệu thật từ API quản trị · chỉ xem, chưa nối thao tác tạo/sửa</p></div><button className="primary-button" onClick={() => open("create")} type="button"><Plus size={17} /> Thêm xe</button></div>
        {loading ? <p className="catalog-result-note">Đang tải danh sách phương tiện...</p> : null}
        {!loading && authError ? <p className="catalog-result-note" role="alert">Bạn cần đăng nhập bằng tài khoản quản trị để xem trang này. <Link href="/login">Đăng nhập</Link></p> : null}
        {!loading && !authError && loadError ? <p className="catalog-result-note" role="alert">{loadError} <button className="table-action" onClick={() => void reload()} type="button">Thử lại</button></p> : null}
        {!loading && !authError && !loadError && vehicles.length === 0 ? <p className="catalog-result-note">Không có phương tiện nào.</p> : null}
        {!authError && !loadError ? <div className="catalog-table-wrap"><table className="catalog-table"><thead><tr><th>Loại</th><th>Mẫu xe</th><th>Phiên bản</th><th>Giá</th><th>Trạng thái</th><th>Cập nhật</th><th></th></tr></thead><tbody>{vehicles.map((vehicle) => { const meta = statusOf(vehicle.status); return <tr key={vehicle.id}><td>{vehicle.vehicleType === "car" ? "Ô tô điện" : "Xe máy điện"}</td><td><strong>{vehicle.modelName}</strong><small>{vehicle.id.toUpperCase()}</small></td><td>{vehicle.variant}</td><td>{formatPrice(vehicle.priceVnd)}</td><td><StatusBadge tone={meta.tone}>{meta.label}</StatusBadge></td><td>—</td><td><div className="table-actions"><button onClick={() => open("view", vehicle)} type="button"><Eye size={15} /> Xem</button><button onClick={() => open("edit", vehicle)} type="button"><Pencil size={15} /> Sửa</button></div></td></tr>; })}</tbody></table></div> : null}
      </section>
      {dialog ? <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="catalog-dialog-title"><button className="dialog-backdrop" aria-label="Đóng hộp thoại" onClick={() => setDialog(null)} type="button" /><section className="mock-dialog"><div className="dialog-heading"><div><span className="eyebrow">Quản lý phương tiện</span><h2 id="catalog-dialog-title">{dialog === "create" ? "Thêm phương tiện" : dialog === "edit" ? `Sửa ${activeVehicle?.modelName ?? ""}` : `Chi tiết ${activeVehicle?.modelName ?? ""}`}</h2></div><button className="icon-button" onClick={() => setDialog(null)} aria-label="Đóng" type="button"><X size={19} /></button></div><div className="two-field-row"><label className="field-label">Tên mẫu xe<input defaultValue={dialog === "create" ? "" : activeVehicle?.modelName ?? ""} disabled={dialog === "view"} /></label><label className="field-label">Phiên bản<input defaultValue={dialog === "create" ? "" : activeVehicle?.variant ?? ""} disabled={dialog === "view"} /></label></div><label className="field-label">Giá niêm yết<input defaultValue={dialog === "create" ? "" : activeVehicle?.priceVnd ?? ""} disabled={dialog === "view"} /></label><div className="dialog-actions"><button className="secondary-button" onClick={() => setDialog(null)} type="button">Đóng</button>{dialog !== "view" ? <button className="primary-button" onClick={() => setDialog(null)} type="button">Lưu thay đổi</button> : null}</div></section></div> : null}
    </>
  );
}
