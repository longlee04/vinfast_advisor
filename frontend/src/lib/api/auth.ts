/**
 * Client cho Auth API thật (`/api/v1/auth/*`). Backend dùng cookie HttpOnly cho
 * access/refresh token + cookie CSRF đọc được (`__Host-p150_csrf`) phải echo lại
 * qua header `X-CSRF-Token` cho các endpoint đổi trạng thái (logout, refresh...).
 * `credentials: "include"` bắt buộc để trình duyệt gửi/nhận cookie cross-origin.
 */

import { csrfHeader, withSessionRetry } from "@/lib/api/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export type AuthUser = {
  id: string;
  email: string;
  role: string;
  state: string;
};

export class AuthApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
    this.name = "AuthApiError";
  }
}

function withCsrfHeader(init: RequestInit): RequestInit {
  return { ...init, headers: { ...init.headers, ...csrfHeader() } };
}

/**
 * Endpoint KHÔNG được thử lại sau khi làm mới phiên.
 *
 * `/auth/refresh` tự nó là bước làm mới — thử lại nó là đệ quy. Còn `login`,
 * `staff/login` và `register` trả 401 để nói "sai mật khẩu"; làm mới phiên rồi
 * gửi lại đúng bộ thông tin sai đó chỉ đổi một lỗi rõ ràng thành hai lần thất
 * bại giống hệt nhau.
 */
const NO_RETRY_PATHS = ["/auth/refresh", "/auth/login", "/auth/staff/login", "/auth/register"];

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Header CSRF dựng lại ở TỪNG lần thử: sau khi làm mới, cookie CSRF đã đổi.
  const attempt = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        ...init.headers,
        ...csrfHeader(),
      },
    });
  const retryable = !NO_RETRY_PATHS.some((prefix) => path.startsWith(prefix));
  const response = retryable ? await withSessionRetry(attempt) : await attempt();
  const body = await response.json().catch(() => ({}));
  // Mã HTTP KHÔNG đủ để biết thành hay bại. Đăng ký trả 202 cho cả hai đường —
  // cố ý, để "email đã tồn tại" không phân biệt được với lần đăng ký đầu. Chỉ
  // xét `response.ok` thì mọi lần từ chối đều lọt qua thành công, và khách nhận
  // màn "đã gửi yêu cầu" rồi chờ mãi một lá thư không bao giờ tới.
  //
  // Trường `error` trong thân là tín hiệu quyết định; `ok` chỉ là lớp bọc ngoài.
  const failureCode = typeof body.error === "string" ? body.error : null;
  if (!response.ok || failureCode !== null) {
    throw new AuthApiError(failureCode ?? "request_failed", response.status);
  }
  if (body && typeof body.error === "string" && body.error.length > 0) {
    throw new AuthApiError(body.error, response.status);
  }
  return body as T;
}

export function register(email: string, password: string): Promise<{ message?: string; error?: string }> {
  return request("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function login(email: string, password: string): Promise<{ message: string }> {
  return request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export const staffApi = {
  login(email: string, password: string): Promise<{ message: string }> {
    return request("/auth/staff/login", { method: "POST", body: JSON.stringify({ email, password }) });
  },
  completePassword(
    email: string,
    temporaryPassword: string,
    newPassword: string,
  ): Promise<{ message: string }> {
    return request("/auth/staff/complete-password", {
      method: "POST",
      body: JSON.stringify({ email, temporary_password: temporaryPassword, new_password: newPassword }),
    });
  },
};

export function staffLogin(email: string, password: string): Promise<{ message: string }> {
  return staffApi.login(email, password);
}

export function completeStaffPassword(
  email: string,
  temporaryPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  return staffApi.completePassword(email, temporaryPassword, newPassword);
}

export type UserSummary = {
  readonly id: string;
  readonly email: string;
  readonly role: "customer" | "advisor" | "admin";
  readonly state: "pending_verification" | "temporary_password" | "active" | "disabled";
  readonly created_at: string;
  readonly last_activity_at: string | null;
};

export type UserPage = {
  readonly items: readonly UserSummary[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
};

type ListUsersParams = {
  readonly role?: UserSummary["role"];
  readonly state?: UserSummary["state"];
  readonly q?: string;
  readonly page?: number;
  readonly pageSize?: number;
};

type StaffRole = Extract<UserSummary["role"], "advisor" | "admin">;

type ApiMessage = {
  readonly message: string;
};

export function listUsers(params: ListUsersParams = {}): Promise<UserPage> {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.role) query.set("role", params.role);
  if (params.state) query.set("state", params.state);
  if (params.q) query.set("q", params.q);
  return request<UserPage>(`/auth/admin/users?${query.toString()}`, { method: "GET" });
}

export function createStaff(email: string, role: StaffRole): Promise<ApiMessage> {
  return request<ApiMessage>(
    "/auth/staff",
    withCsrfHeader({ method: "POST", body: JSON.stringify({ email, role }) }),
  );
}

export function changeUserRole(userId: string, role: StaffRole): Promise<ApiMessage> {
  return request<ApiMessage>(
    `/auth/admin/users/${userId}/role`,
    withCsrfHeader({ method: "PATCH", body: JSON.stringify({ role }) }),
  );
}

export function disableUser(userId: string): Promise<ApiMessage> {
  return request<ApiMessage>(`/auth/admin/users/${userId}/disable`, withCsrfHeader({ method: "POST" }));
}

export function enableUser(userId: string): Promise<ApiMessage> {
  return request<ApiMessage>(`/auth/admin/users/${userId}/enable`, withCsrfHeader({ method: "POST" }));
}

export function activateUser(userId: string): Promise<ApiMessage> {
  return request<ApiMessage>(`/auth/admin/users/${userId}/activate`, withCsrfHeader({ method: "POST" }));
}

export function logout(): Promise<{ message: string }> {
  return request("/auth/logout", withCsrfHeader({ method: "POST" }));
}

export async function me(): Promise<AuthUser | null> {
  try {
    return await request<AuthUser>("/auth/me", { method: "GET" });
  } catch (error) {
    if (error instanceof AuthApiError && error.status === 401) return null;
    throw error;
  }
}

export type UserProfile = {
  id: string;
  email: string;
  role: string;
  full_name: string | null;
  phone_number: string | null;
  address: string | null;
  showroom_name: string | null;
  avatar_url: string | null;
  vehicle_preference: string | null;
  budget_preference: string | null;
  seats_preference: string | null;
  home_charging: boolean | null;
  title: string | null;
  bio: string | null;
};

export type UpdateProfilePayload = {
  full_name?: string | null;
  phone_number?: string | null;
  address?: string | null;
  showroom_name?: string | null;
  avatar_url?: string | null;
  vehicle_preference?: string | null;
  budget_preference?: string | null;
  seats_preference?: string | null;
  home_charging?: boolean | null;
  title?: string | null;
  bio?: string | null;
};

export async function getProfile(): Promise<UserProfile | null> {
  try {
    return await request<UserProfile>("/auth/profile", { method: "GET" });
  } catch (error) {
    if (error instanceof AuthApiError && error.status === 401) return null;
    throw error;
  }
}

export function updateProfile(payload: UpdateProfilePayload): Promise<UserProfile> {
  return request<UserProfile>(
    "/auth/profile",
    withCsrfHeader({
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  );
}
