"use client";

import type { ModelViewerElement } from "@google/model-viewer";
import { useCallback, useEffect, useRef, useState } from "react";

import { VehicleControlTray } from "@/components/showroom/vehicle-control-tray";
import { VehicleImage } from "@/components/shared/vehicle-image";
import type { VinFastModelAsset } from "@/data/vinfast-models";

function applyPaintColor(
  viewer: ModelViewerElement,
  asset: VinFastModelAsset,
  colorId: string,
): void {
  const color = asset.availableColors.find((item) => item.id === colorId);
  if (!color) return;

  if (color.variantName && viewer.availableVariants.includes(color.variantName)) {
    viewer.variantName = color.variantName;
    return;
  }

  if (!color.materialName) return;
  const material = viewer.model?.materials.find((item) => item.name === color.materialName);
  material?.pbrMetallicRoughness.setBaseColorFactor(color.hex);
}

/** Viewer GLB tương tác, chỉ được render với asset VinFast đã được cấp phép. */
export function InteractiveVehicleModel({ asset }: Readonly<{ asset: VinFastModelAsset }>) {
  const viewerRef = useRef<ModelViewerElement | null>(null);
  const firstColorId = asset.availableColors[0]?.id ?? "";
  const [activeColorId, setActiveColorId] = useState(firstColorId);
  const [modelFailed, setModelFailed] = useState(false);

  useEffect(() => {
    if (!customElements.get("model-viewer")) {
      void import("@google/model-viewer").catch(() => setModelFailed(true));
    }
  }, []);

  const applyActiveColor = useCallback((): void => {
    if (viewerRef.current) applyPaintColor(viewerRef.current, asset, activeColorId);
  }, [activeColorId, asset]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    viewer.addEventListener("load", applyActiveColor);
    viewer.addEventListener("error", () => setModelFailed(true), { once: true });
    applyActiveColor();
    return () => viewer.removeEventListener("load", applyActiveColor);
  }, [applyActiveColor]);

  if (!asset.modelPath || modelFailed) {
    return (
      <div className="interactive-model-fallback">
        <VehicleImage
          alt={`Ảnh xe ${asset.name}`}
          className="vehicle-detail-poster"
          preload
          sizes="(max-width: 900px) 100vw, 56vw"
          src={asset.posterPath}
        />
        <p>Không tải được mô hình 3D. Đang hiển thị ảnh xe thay thế.</p>
      </div>
    );
  }

  function resetViewer(): void {
    setActiveColorId(firstColorId);
    if (!viewerRef.current) return;
    viewerRef.current.cameraOrbit = "35deg 70deg 105%";
    viewerRef.current.fieldOfView = "30deg";
    viewerRef.current.jumpCameraToGoal();
  }

  return (
    <div className="interactive-vehicle-model">
      <model-viewer
        alt={`Mô hình 3D ${asset.name} ${asset.variant}`}
        aria-label={`Mô hình 3D ${asset.name} ${asset.variant}`}
        auto-rotate
        camera-controls
        camera-orbit="35deg 70deg 105%"
        interaction-prompt="auto"
        loading="eager"
        poster={asset.posterPath}
        ref={viewerRef}
        shadow-intensity="1"
        src={asset.modelPath}
        touch-action="pan-y"
      />
      <VehicleControlTray
        activeColorId={activeColorId}
        asset={asset}
        onColorChange={setActiveColorId}
        onReset={resetViewer}
      />
    </div>
  );
}
