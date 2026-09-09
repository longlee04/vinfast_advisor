export type VinFastModelColor = Readonly<{
  id: string;
  name: string;
  hex: string;
  materialName?: string;
  variantName?: string;
}>;

export type VinFastModelAsset = Readonly<{
  id: string;
  name: string;
  variant: string;
  assetStatus: "authorized" | "pending";
  modelPath?: string;
  posterPath?: string;
  availableColors: readonly VinFastModelColor[];
}>;

const VINFAST_MODEL_ASSETS: readonly VinFastModelAsset[] = [];

/** Return an authorized VinFast 3D asset when one is registered locally. */
export function getVinFastModelAsset(vehicleId: string): VinFastModelAsset | undefined {
  return VINFAST_MODEL_ASSETS.find((asset) => asset.id === vehicleId);
}
