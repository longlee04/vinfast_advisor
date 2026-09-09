import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InteractiveVehicleModel } from "@/components/showroom/interactive-vehicle-model";
import type { VinFastModelAsset } from "@/data/vinfast-models";

vi.mock("@google/model-viewer", () => ({}));

const authorizedAsset: VinFastModelAsset = {
  id: "vf-6",
  name: "VF 6",
  variant: "Plus",
  assetStatus: "authorized",
  modelPath: "/models/vinfast/vf-6/model.glb",
  posterPath: "/models/vinfast/vf-6/poster.webp",
  availableColors: [
    { id: "blue", name: "Xanh", hex: "#315f89", materialName: "CarPaint" },
    { id: "red", name: "Đỏ", hex: "#8f3034", materialName: "CarPaint" },
  ],
};

describe("InteractiveVehicleModel", () => {
  it("render model đúng xe và cho phép chọn màu sơn", async () => {
    const user = userEvent.setup();
    render(<InteractiveVehicleModel asset={authorizedAsset} />);

    const viewer = screen.getByLabelText("Mô hình 3D VF 6 Plus");
    expect(viewer).toHaveAttribute("src", authorizedAsset.modelPath);
    expect(viewer).toHaveAttribute("poster", authorizedAsset.posterPath);
    expect(viewer).toHaveAttribute("camera-controls");

    const setBaseColorFactor = vi.fn();
    Object.defineProperty(viewer, "model", {
      configurable: true,
      value: {
        materials: [
          { name: "CarPaint", pbrMetallicRoughness: { setBaseColorFactor } },
        ],
      },
    });

    await user.click(screen.getByRole("button", { name: "Màu sơn" }));
    await user.click(screen.getByRole("button", { name: "Chọn màu Đỏ" }));

    expect(screen.getByRole("button", { name: "Chọn màu Đỏ" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(setBaseColorFactor).toHaveBeenCalledWith("#8f3034"));
  });
});
