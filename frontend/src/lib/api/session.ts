/**
 * Giữ phiên đăng nhập sống bằng refresh token đã có sẵn trong cookie.
 *
 * Backend phát hai token: access token sống 15 phút, refresh token sống 30 ngày
 * (`src/auth/contracts.py`), và có sẵn `POST /auth/refresh` để đổi refresh token
 * lấy cặp token mới. Nhưng trước module này KHÔNG chỗ nào trong frontend gọi
 * endpoint đó — nên đúng 15 phút sau khi đăng nhập, mọi request bắt đầu trả 401
 * và khách đọc được "Phiên đăng nhập đã hết hạn", dù trong cookie vẫn còn một
 * refresh token hợp lệ suốt 29 ngày rưỡi nữa.
 *
 * Cách chữa là dùng đúng thứ đã có: gặp 401 thì làm mới phiên MỘT lần rồi phát
 * lại request. Không đụng tới thời hạn token ở backend — hạ tuổi thọ của một
 * cam kết bảo mật để né một lỗi thiếu wiring là chữa nhầm chỗ.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");
const CSRF_COOKIE_NAME = "__Host-p150_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Header CSRF đọc từ cookie NGAY LÚC GỌI.
 *
 * Phải đọc lại ở từng lần thử chứ không bắt sẵn một lần: `/auth/refresh` phát
 * một CSRF token mới cùng lúc với cặp token mới, nên request phát lại mà mang
 * token cũ sẽ bị từ chối lần thứ hai — và trông y hệt như refresh đã thất bại.
 */
export function csrfHeader(): Record<string, string> {
  const token = readCookie(CSRF_COOKIE_NAME);
  return token ? { [CSRF_HEADER_NAME]: token } : {};
}

/**
 * Một lần refresh đang bay, dùng chung cho mọi caller.
 *
 * Trang tư vấn bắn nhiều request song song (gửi lượt, poll deliveries, SSE).
 * Không gom lại thì một access token hết hạn sinh ra N lần refresh cùng lúc, mà
 * refresh token XOAY VÒNG sau mỗi lần dùng — lần đầu thắng, các lần sau cầm
 * token đã bị tiêu và làm chết cả phiên. Gom về một promise là điều kiện đúng
 * đắn, không phải tối ưu tốc độ.
 */
let inFlight: Promise<boolean> | null = null;

async function postRefresh(): Promise<boolean> {
  // Không có cookie CSRF nghĩa là chưa từng đăng nhập trong trình duyệt này.
  // Gọi refresh khi đó chỉ tạo thêm một 401 vô nghĩa trong log.
  if (readCookie(CSRF_COOKIE_NAME) === null) return false;
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...csrfHeader() },
    });
    return response.ok;
  } catch {
    // Mất mạng thì coi như không làm mới được; caller trả về 401 gốc.
    return false;
  }
}

export function refreshSession(): Promise<boolean> {
  if (inFlight === null) {
    inFlight = postRefresh().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

/** Chỉ dùng trong test: xoá lần refresh đang bay giữa các ca. */
export function resetSessionRefreshState(): void {
  inFlight = null;
}

type Attempt = () => Promise<Response>;

/**
 * Chạy `attempt`; gặp 401 thì làm mới phiên đúng MỘT lần rồi chạy lại.
 *
 * Một lần, không phải vòng lặp: 401 vẫn còn sau khi refresh thành công nghĩa là
 * refresh token cũng đã hết hạn, hoặc tài khoản bị vô hiệu hoá. Thử tiếp chỉ
 * quay vòng trên một phiên đã chết.
 */
export async function withSessionRetry(attempt: Attempt): Promise<Response> {
  const response = await attempt();
  if (response.status !== 401) return response;
  return (await refreshSession()) ? attempt() : response;
}
