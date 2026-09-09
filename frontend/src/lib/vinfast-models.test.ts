import { describe, expect, it } from "vitest";

import { getVinFastModelAsset } from "@/data/vinfast-models";

describe("getVinFastModelAsset", () => {
  it("keeps an unregistered vehicle on the authorized poster fallback", () => {
    expect(getVinFastModelAsset("vf-6")).toBeUndefined();
  });
});
