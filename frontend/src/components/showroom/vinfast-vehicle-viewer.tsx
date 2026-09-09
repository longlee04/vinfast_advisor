import { Box } from "lucide-react";

import { InteractiveVehicleModel } from "@/components/showroom/interactive-vehicle-model";
import { VehicleImage } from "@/components/shared/vehicle-image";
import { getVinFastModelAsset } from "@/data/vinfast-models";

export function VinFastVehicleViewer({
  modelName,
  posterUrl,
  variant,
  vehicleId,
}: Readonly<{
  modelName: string;
  posterUrl: string;
  variant: string;
  vehicleId: string;
}>) {
  const asset = getVinFastModelAsset(vehicleId);

  if (asset?.assetStatus === "authorized" && asset.modelPath) {
    return <InteractiveVehicleModel asset={{ ...asset, posterPath: asset.posterPath ?? posterUrl }} />;
  }

  return (
    <div className="vehicle-detail-viewer">
      <VehicleImage alt={`Ảnh xe ${modelName}`} className="vehicle-detail-poster" preload sizes="(max-width: 900px) 100vw, 56vw" src={posterUrl} />
      <div className="vehicle-3d-pending" role="status">
        <Box aria-hidden="true" size={16} />
        <span>Chế độ xem 3D đang chờ model chính thức của {modelName} {variant}.</span>
      </div>
    </div>
  );
}
