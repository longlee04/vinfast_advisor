// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VehicleDetailPage from "@/app/vehicles/[slug]/page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  notFound: vi.fn(),
}));

vi.mock("@/components/vf2/vf2-experience", () => ({
  Vf2Experience: () => <div data-testid="vf2-campaign-page" />,
}));

vi.mock("@/components/vf3/vf3-experience", () => ({
  Vf3Experience: () => <div data-testid="vf3-campaign-page" />,
}));

vi.mock("@/components/vf5/vf5-experience", () => ({
  Vf5Experience: () => <div data-testid="vf5-campaign-page" />,
}));

vi.mock("@/components/vf6/vf6-experience", () => ({
  Vf6Experience: () => <div data-testid="vf6-campaign-page" />,
}));

vi.mock("@/components/vf7/vf7-experience", () => ({
  Vf7Experience: () => <div data-testid="vf7-campaign-page" />,
}));

vi.mock("@/components/vf8/vf8-experience", () => ({
  Vf8Experience: () => <div data-testid="vf8-campaign-page" />,
}));

vi.mock("@/components/vf8-all-new/vf8-all-new-experience", () => ({
  Vf8AllNewExperience: () => <div data-testid="vf8-all-new-campaign-page" />,
}));

vi.mock("@/components/vf9/vf9-experience", () => ({
  Vf9Experience: () => <div data-testid="vf9-campaign-page" />,
}));

vi.mock("@/components/mpv7/mpv7-experience", () => ({
  Mpv7Experience: () => <div data-testid="mpv7-campaign-page" />,
}));

vi.mock("@/components/product/product-experience", () => ({
  ProductExperience: ({ vehicle }: { vehicle: { id: string } }) => <div data-product-id={vehicle.id} />,
}));

vi.mock("@/components/shared/customer-shell", () => ({
  CustomerShell: ({ children }: { children: React.ReactNode }) => <div data-testid="customer-shell">{children}</div>,
}));

afterEach(cleanup);

describe("VehicleDetailPage", () => {
  it("serves the VF 2 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-2" }) });

    render(page);

    expect(screen.getByTestId("vf2-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 3 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-3" }) });

    render(page);

    expect(screen.getByTestId("vf3-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 5 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-5" }) });

    render(page);

    expect(screen.getByTestId("vf5-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 6 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-6" }) });

    render(page);

    expect(screen.getByTestId("vf6-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 7 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-7" }) });

    render(page);

    expect(screen.getByTestId("vf7-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF MPV 7 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-mpv-7" }) });

    render(page);

    expect(screen.getByTestId("mpv7-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 8 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-8" }) });

    render(page);

    expect(screen.getByTestId("vf8-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 8 All New campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-8-all-new" }) });

    render(page);

    expect(screen.getByTestId("vf8-all-new-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });

  it("serves the VF 9 campaign from the canonical vehicle link", async () => {
    const page = await VehicleDetailPage({ params: Promise.resolve({ slug: "vf-9" }) });

    render(page);

    expect(screen.getByTestId("vf9-campaign-page")).toBeInTheDocument();
    expect(screen.getByTestId("customer-shell")).toBeInTheDocument(); // 2026-08-31: bespoke cũng bọc CustomerShell — một header cho cả site
  });
});
