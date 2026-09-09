// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sendTurn } from "@/lib/api/agent";
import { me } from "@/lib/api/auth";
import { refreshSession, resetSessionRefreshState, withSessionRetry } from "@/lib/api/session";

const SESSION = "11111111-1111-1111-1111-111111111111";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// jsdom từ chối cookie tiền tố `__Host-` trên trang http (prefix đó đòi
// `Secure`), nên gán thẳng `document.cookie` sẽ im lặng không có tác dụng và
// mọi test dưới đây chạy như chưa đăng nhập. Kiểm soát bằng một hũ cookie giả.
let cookieJar = "";

Object.defineProperty(document, "cookie", {
  configurable: true,
  get: () => cookieJar,
});

function signIn(csrf = "csrf-1"): void {
  cookieJar = `__Host-p150_csrf=${csrf}`;
}

function signOut(): void {
  cookieJar = "";
}

beforeEach(() => {
  resetSessionRefreshState();
  signOut();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("refreshSession", () => {
  it("không gọi mạng khi trình duyệt chưa từng đăng nhập", async () => {
    // Không có cookie CSRF nghĩa là không có phiên nào để làm mới; gọi refresh
    // lúc đó chỉ tạo thêm một 401 vô nghĩa trong log.
    const fetchMock = vi.fn(async () => json({ message: "refreshed" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(refreshSession()).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("gộp nhiều lời gọi song song thành ĐÚNG một lần refresh", async () => {
    // Refresh token xoay vòng sau mỗi lần dùng: hai lần refresh song song thì
    // lần sau cầm token đã bị tiêu và giết luôn cả phiên. Gom lại là điều kiện
    // đúng đắn, không phải tối ưu tốc độ.
    signIn();
    const fetchMock = vi.fn(async () => json({ message: "refreshed" }));
    vi.stubGlobal("fetch", fetchMock);

    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);

    expect(results).toEqual([true, true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("coi như thất bại khi mất mạng, không ném lỗi ra ngoài", async () => {
    signIn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(refreshSession()).resolves.toBe(false);
  });
});

describe("withSessionRetry", () => {
  it("chỉ thử lại đúng một lần khi 401 vẫn còn sau khi làm mới", async () => {
    // 401 còn nguyên sau một lần refresh thành công nghĩa là refresh token cũng
    // hết hạn, hoặc tài khoản bị vô hiệu hoá. Thử tiếp chỉ quay vòng vô ích.
    signIn();
    vi.stubGlobal("fetch", vi.fn(async () => json({ message: "refreshed" })));
    const attempt = vi.fn(async () => json({ error: "unauthorized" }, 401));

    const response = await withSessionRetry(attempt);

    expect(response.status).toBe(401);
    expect(attempt).toHaveBeenCalledTimes(2);
  });

  it("không thử lại khi lỗi không phải 401", async () => {
    signIn();
    const attempt = vi.fn(async () => json({ error: "server_error" }, 500));

    const response = await withSessionRetry(attempt);

    expect(response.status).toBe(500);
    expect(attempt).toHaveBeenCalledTimes(1);
  });
});

describe("một lượt chat sau khi access token hết hạn", () => {
  it("tự làm mới phiên rồi gửi lại, khách không thấy lỗi nào", async () => {
    // Đây là bug gốc: access token sống 15 phút, refresh token sống 30 ngày,
    // nhưng không chỗ nào gọi `/auth/refresh` — nên đúng 15 phút sau khi đăng
    // nhập, khách đọc được "Phiên đăng nhập đã hết hạn".
    signIn("csrf-cu");
    const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
      void init;
      const target = String(url);
      if (target.includes("/auth/refresh")) {
        signIn("csrf-moi"); // backend phát CSRF mới cùng cặp token mới
        return json({ message: "refreshed" });
      }
      return fetchMock.mock.calls.filter((call) => String(call[0]).includes("/agent/turn"))
        .length === 1
        ? json({ detail: "authentication required" }, 401)
        : json({
            answer: "VinFast VF 3 All New: giá niêm yết từ 270.750.000 đồng.",
            pending_question: null,
            lookup_facts: [],
            terminal_reason: null,
            awaiting_review: false,
          });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await sendTurn(
      SESSION,
      "22222222-2222-2222-2222-222222222222",
      "vf3 giá bao nhiêu",
    );

    expect(result.answer).toContain("270.750.000");
    const targets = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(targets.filter((target) => target.includes("/auth/refresh"))).toHaveLength(1);
    expect(targets.filter((target) => target.includes("/agent/turn"))).toHaveLength(2);
    const turnBodies = fetchMock.mock.calls
      .filter((call) => String(call[0]).includes("/agent/turn"))
      .map((call) => call[1]?.body);
    expect(turnBodies[1]).toBe(turnBodies[0]);
    // Lần gửi lại phải mang CSRF token MỚI: mang token cũ thì bị từ chối lần
    // thứ hai và trông y hệt như refresh đã thất bại.
    const retryInit = fetchMock.mock.calls.at(-1)?.[1];
    expect((retryInit?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-moi");
  });

  it("vẫn báo 401 khi refresh token cũng đã hết hạn", async () => {
    signIn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: unknown) =>
        String(url).includes("/auth/refresh")
          ? json({ error: "invalid_refresh" }, 401)
          : json({ detail: "authentication required" }, 401),
      ),
    );

    await expect(sendTurn(SESSION, "22222222-2222-2222-2222-222222222222", "xin chao")).rejects.toMatchObject({
      name: "AgentApiError",
      status: 401,
    });
  });
});

describe("endpoint không được thử lại", () => {
  it("đăng nhập sai mật khẩu không kích hoạt refresh", async () => {
    // `/auth/login` trả 401 để nói "sai mật khẩu". Làm mới phiên rồi gửi lại
    // đúng bộ thông tin sai đó chỉ đổi một lỗi rõ ràng thành hai lần thất bại.
    signIn();
    const fetchMock = vi.fn(async () => json({ error: "invalid_credentials" }, 401));
    vi.stubGlobal("fetch", fetchMock);
    const { login } = await import("@/lib/api/auth");

    await expect(login("a@b.com", "sai")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("`me()` chưa đăng nhập vẫn trả null mà không gọi refresh", async () => {
    const fetchMock = vi.fn(async (url: unknown) => {
      void url;
      return json({ error: "unauthorized" }, 401);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(me()).resolves.toBeNull();
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("/auth/refresh")),
    ).toHaveLength(0);
  });
});
