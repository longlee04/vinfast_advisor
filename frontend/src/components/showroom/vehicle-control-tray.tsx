"use client";

import { CircleDot, Focus, RotateCcw, Sparkles, View } from "lucide-react";
import { useState, type CSSProperties } from "react";

import type { VinFastModelAsset } from "@/data/vinfast-models";

type ControlGroup = "color" | "wheel" | "view" | "highlights" | null;

export function VehicleControlTray({
  activeColorId,
  asset,
  onColorChange,
  onReset,
}: Readonly<{
  activeColorId: string;
  asset: VinFastModelAsset;
  onColorChange: (colorId: string) => void;
  onReset: () => void;
}>) {
  const [activeGroup, setActiveGroup] = useState<ControlGroup>(null);

  function toggle(group: Exclude<ControlGroup, null>): void {
    setActiveGroup((current) => (current === group ? null : group));
  }

  return (
    <div className="vehicle-control-wrap">
      {activeGroup ? (
        <div className="vehicle-control-popover">
          {activeGroup === "color" ? <div className="color-options">{asset.availableColors.map((color) => <button aria-label={`Chọn màu ${color.name}`} aria-pressed={activeColorId === color.id} className={activeColorId === color.id ? "color-option is-active" : "color-option"} key={color.id} onClick={() => onColorChange(color.id)} style={{ "--paint": color.hex } as CSSProperties} type="button"><span /><small>{color.name}</small></button>)}</div> : null}
          {activeGroup === "wheel" ? <p>Mâm xe sẽ hiển thị khi bộ asset chính thức cung cấp biến thể vật liệu.</p> : null}
          {activeGroup === "view" ? <div className="inline-choice"><button className="is-active" type="button">Ngoại thất</button><button disabled type="button">Nội thất</button></div> : null}
          {activeGroup === "highlights" ? <p>Điểm nổi bật sẽ liên kết tới hotspot trên model 3D được cấp phép.</p> : null}
        </div>
      ) : null}
      <div className="vehicle-control-tray" aria-label="Tùy chỉnh xe">
        <button className={activeGroup === "color" ? "is-active" : ""} onClick={() => toggle("color")} type="button"><CircleDot size={17} /> Màu sơn</button>
        <button className={activeGroup === "wheel" ? "is-active" : ""} onClick={() => toggle("wheel")} type="button"><Focus size={17} /> Mâm xe</button>
        <button className={activeGroup === "view" ? "is-active" : ""} onClick={() => toggle("view")} type="button"><View size={17} /> Ngoại thất / Nội thất</button>
        <button className={activeGroup === "highlights" ? "is-active" : ""} onClick={() => toggle("highlights")} type="button"><Sparkles size={17} /> Điểm nổi bật</button>
        <button onClick={() => { setActiveGroup(null); onReset(); }} type="button"><RotateCcw size={17} /> Đặt lại</button>
      </div>
    </div>
  );
}
