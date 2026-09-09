import { describe, expect, it, vi } from "vitest";

const permanentRedirect = vi.fn();

vi.mock("next/navigation", () => ({ permanentRedirect }));

describe("legacy VF 2 campaign route", () => {
  it("redirects to the canonical vehicle link", async () => {
    const { default: LegacyVf2Page } = await import("@/app/dat-coc-xe-vf2/page");

    LegacyVf2Page();

    expect(permanentRedirect).toHaveBeenCalledWith("/vehicles/vf-2");
  });
});
