import { Box, ShieldCheck } from "lucide-react";

export function VehiclePosterFallback({ modelName }: Readonly<{ modelName: string }>) {
  return (
    <div className="vehicle-asset-fallback" role="img" aria-label={`Khu vực hình ảnh ${modelName} đang chờ tài nguyên chính thức`}>
      <div className="fallback-horizon" aria-hidden="true"><span /><span /><span /></div>
      <div className="fallback-monogram" aria-hidden="true">V</div>
      <div className="fallback-copy">
        <span className="asset-state"><ShieldCheck size={15} /> Chỉ dùng tài nguyên được cấp phép</span>
        <h2>{modelName}</h2>
        <p><Box size={15} /> Chế độ xem 3D sẽ được bổ sung khi có tài nguyên chính thức.</p>
      </div>
    </div>
  );
}
