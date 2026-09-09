import { AgentDock } from "@/components/customer/agent-dock";
import { HomeFooter } from "@/components/home/home-footer";
import styles from "@/components/home/home-shell.module.css";
import { AppHeader } from "@/components/shared/app-header";

export function HomeShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={styles.shell}>
      {/* MỘT header chung cho mọi trang (Sếp: hai thanh khác nhau là lỗi nặng).
          Biến thể overlay: trong suốt phủ lên hero, cuộn quá 40px thì đặc lại.
          Các mục neo (#green-future…) chuyển thành hàng lối tắt dưới hero. */}
      <AppHeader variant="overlay" />
      {/* Kéo nội dung lên dưới header sticky để hero nằm TRỌN dưới lớp kính. */}
      <main className={`${styles.main} home-overlay-main`}>{children}</main>
      {/* Cùng MỘT thanh trợ lý ngang như mọi trang khách (Sếp 2026-08-29): không còn
          nút tròn riêng của trang chủ — khách ở đâu cũng thấy đúng một khung gõ. */}
      <AgentDock />
      <HomeFooter />
    </div>
  );
}
