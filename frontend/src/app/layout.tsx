import type { Metadata } from "next";
import { Be_Vietnam_Pro, Manrope } from "next/font/google";

import "./globals.css";
import "./redesign.css";

import { EmbedBodyFlag } from "@/components/shared/embed-body-flag";
import { AuthProvider } from "@/store/auth-store";
import { DemoStoreProvider } from "@/store/demo-store";

export const metadata: Metadata = {
  title: "VinFast AI Sales Advisor",
  description: "Tư vấn lựa chọn xe VinFast theo nhu cầu của bạn.",
};

const bodyFont = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
});

const displayFont = Manrope({
  subsets: ["latin", "vietnamese"],
  variable: "--font-display",
});

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html className={`${bodyFont.variable} ${displayFont.variable}`} lang="vi">
      <body>
        {/* Gắn cờ `body[data-embed]` khi trang chạy trong cửa sổ hội thoại —
            CSS toàn cục dựa vào cờ này để ẩn nav nội bộ của trang chi tiết. */}
        <EmbedBodyFlag />
        <AuthProvider>
          <DemoStoreProvider>{children}</DemoStoreProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
