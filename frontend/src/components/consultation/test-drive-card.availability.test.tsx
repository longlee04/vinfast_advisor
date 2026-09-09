// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestDriveCard } from "@/components/consultation/test-drive-card";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

/**
 * Nạp ô giờ khi khách bấm sang ngày khác.
 *
 * Bước nạp lười cắt `options` xuống còn ô của ngày mặc định (126 → 18 ô). Thẻ
 * vẫn bày đủ bảy ngày, nhưng client không xin ô của sáu ngày còn lại — nên bấm
 * sang ngày thứ tư thì MỌI khung đều mờ. Payload nhẹ đi, chức năng thì gãy, và
 * đó là thứ chặn deploy chứ không phải một tối ưu để dành.
 */

const { fetchTestDriveAvailability } = vi.hoisted(() => ({
  fetchTestDriveAvailability: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchTestDriveAvailability };
});

const HOM_NAY = "2026-08-28";
const NGAY_KIA = "2026-08-30";

const CARD: TestDriveCardData = {
  vehicle_id: "veh-vf5",
  vehicle_name: "VinFast VF 5 All New",
  showrooms: [{ showroom_id: "sr-lb", name: "Long Biên", address: "Số 1 Nguyễn Văn Cừ", distance_label: "2,1 km" }],
  days: [
    {
      date: HOM_NAY,
      label: "Hôm nay 28/08",
      times: [{ scheduled_at: `${HOM_NAY}T09:00:00+07:00`, label: "09:00" }],
    },
    {
      date: NGAY_KIA,
      label: "Thứ 7 30/08",
      times: [
        { scheduled_at: `${NGAY_KIA}T09:00:00+07:00`, label: "09:00" },
        { scheduled_at: `${NGAY_KIA}T14:00:00+07:00`, label: "14:00" },
      ],
    },
  ],
  // Lượt chat CHỈ chở ô của ngày mặc định — đúng như backend gửi sau nạp lười.
  options: [
    { showroom_id: "sr-lb", scheduled_at: `${HOM_NAY}T09:00:00+07:00`, value: "__lichlaithu__|hom-nay-9h" },
  ],
  default_showroom_id: "sr-lb",
  default_date: HOM_NAY,
};

const NGAY_NUA = "2026-08-31";

//: Ba ngày, để bấm nhanh qua hai ngày chưa nạp.
const BA_NGAY: TestDriveCardData = {
  ...CARD,
  days: [
    ...CARD.days,
    {
      date: NGAY_NUA,
      label: "CN 31/08",
      times: [{ scheduled_at: `${NGAY_NUA}T09:00:00+07:00`, label: "09:00" }],
    },
  ],
};

function _render(onConfirm = vi.fn()) {
  return render(<TestDriveCard card={CARD} onConfirm={onConfirm} sessionId="session-1" />);
}

async function _bamSangNgayKia(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Xem ngày khác" }));
  await user.click(screen.getByRole("button", { name: "Thứ 7 30/08" }));
}

describe("TestDriveCard nạp ô giờ của ngày khác", () => {
  beforeEach(() => {
    fetchTestDriveAvailability.mockResolvedValue({
      date: NGAY_KIA,
      options: [
        { showroom_id: "sr-lb", scheduled_at: `${NGAY_KIA}T14:00:00+07:00`, value: "__lichlaithu__|ngay-kia-14h" },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("bấm sang ngày khác thì hỏi server ô giờ của đúng ngày đó", async () => {
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);

    await waitFor(() =>
      expect(fetchTestDriveAvailability).toHaveBeenCalledWith({ sessionId: "session-1", date: NGAY_KIA }),
    );
  });

  it("ô server trả về thì bấm được, ô không trả về vẫn mờ", async () => {
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);

    // 14:00 có trong danh sách server trả -> bấm được.
    await waitFor(() => expect(screen.getByRole("button", { name: "14:00" })).toBeEnabled());
    // 09:00 của ngày kia KHÔNG có trong danh sách -> vẫn mờ.
    expect(screen.getByRole("button", { name: "09:00" })).toBeDisabled();
  });

  it("bấm giờ đã nạp thì gửi đúng mã của server, không phải mã tự ghép", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    _render(onConfirm);

    await _bamSangNgayKia(user);
    await waitFor(() => expect(screen.getByRole("button", { name: "14:00" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "14:00" }));
    await user.click(screen.getByRole("button", { name: "Đặt lịch" }));

    expect(onConfirm).toHaveBeenCalledWith("__lichlaithu__|ngay-kia-14h");
  });

  it("quay lại ngày đã nạp thì không hỏi server lần nữa", async () => {
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);
    await waitFor(() => expect(fetchTestDriveAvailability).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Hôm nay 28/08" }));
    await user.click(screen.getByRole("button", { name: "Thứ 7 30/08" }));

    expect(fetchTestDriveAvailability).toHaveBeenCalledTimes(1);
  });

  it("ngày mặc định đã có sẵn ô nên không gọi server", async () => {
    _render();

    await waitFor(() => expect(screen.getByRole("button", { name: "09:00" })).toBeEnabled());
    expect(fetchTestDriveAvailability).not.toHaveBeenCalled();
  });

  it("server lỗi thì nói ra, không để khách nhìn lưới mờ mà không hiểu vì sao", async () => {
    fetchTestDriveAvailability.mockRejectedValueOnce(new Error("mạng hỏng"));
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);

    expect(await screen.findByRole("status")).toHaveTextContent(/chưa tải được/i);
  });
});

describe("TestDriveCard — hai ca biên", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("ngày mặc định kín chỗ vẫn KHÔNG hỏi lại server", async () => {
    // Ngày mặc định là ngày đã gửi kể cả khi nó không còn ô nào. Suy "đã gửi"
    // từ "có option" thì đúng ca này client hỏi lại một câu đã có câu trả lời.
    const KIN_CHO: TestDriveCardData = { ...CARD, options: [] };
    render(<TestDriveCard card={KIN_CHO} onConfirm={vi.fn()} sessionId="session-1" />);

    await waitFor(() => expect(screen.getByRole("button", { name: "09:00" })).toBeDisabled());
    expect(fetchTestDriveAvailability).not.toHaveBeenCalled();
  });

  it("bấm nhanh qua hai ngày thì chữ 'đang tải' theo ngày đang chờ", async () => {
    const user = userEvent.setup();
    let giaiPhongNgayKia!: (value: unknown) => void;
    fetchTestDriveAvailability
      .mockImplementationOnce(
        () => new Promise((resolve) => {
          giaiPhongNgayKia = resolve;
        }),
      )
      // Ngày 31 vẫn ĐANG chạy khi ngày 30 trả về — đó là cả nội dung của ca này.
      .mockImplementationOnce(() => new Promise(() => {}));

    render(<TestDriveCard card={BA_NGAY} onConfirm={vi.fn()} sessionId="session-1" />);
    await user.click(screen.getByRole("button", { name: "Xem ngày khác" }));
    await user.click(screen.getByRole("button", { name: "Thứ 7 30/08" }));
    await user.click(screen.getByRole("button", { name: "CN 31/08" }));

    // Yêu cầu của ngày 30 về TRƯỚC, trong khi ngày 31 còn đang chạy.
    giaiPhongNgayKia({ date: NGAY_KIA, options: [] });

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/đang tải/i));
  });
});

describe("TestDriveCard — lỗi bám dai", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lỗi của ngày B biến mất khi quay lại ngày đã có sẵn", async () => {
    // `loadFailed` là cờ CHUNG thì dòng lỗi của ngày hỏng còn đứng nguyên sau
    // khi khách quay về ngày mặc định — effect thoát sớm nên không ai xoá nó.
    fetchTestDriveAvailability.mockRejectedValueOnce(new Error("mạng hỏng"));
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);
    await screen.findByRole("status");

    await user.click(screen.getByRole("button", { name: "Hôm nay 28/08" }));

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });
});

describe("TestDriveCard — cache không phụ thuộc identity của prop", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("cha render lại với thẻ BẰNG NHAU thì không nạp lại ngày đã có", async () => {
    // `useEffect(..., [card])` so bằng identity. Một cha dựng object thẻ mới mỗi
    // lần render sẽ xoá sạch cache sau mỗi lần render, và mỗi lần đổi ngày lại
    // là một vòng chờ mạng nữa. Khoá theo GIÁ TRỊ của thẻ thì không dính.
    const user = userEvent.setup();
    const { rerender } = render(<TestDriveCard card={CARD} onConfirm={vi.fn()} sessionId="session-1" />);

    await _bamSangNgayKia(user);
    await waitFor(() => expect(fetchTestDriveAvailability).toHaveBeenCalledTimes(1));

    // Cùng nội dung, KHÁC object — đúng thứ một cha vô tình dựng lại mỗi render.
    rerender(<TestDriveCard card={{ ...CARD }} onConfirm={vi.fn()} sessionId="session-1" />);

    // Kiểm thứ THẬT SỰ mất khi cache bị xoá: ngày đang chọn và ô đã nạp.
    // Chỉ đếm số lần gọi ngay sau `rerender` thì vẫn ra 1 kể cả khi cache đã bị
    // xoá sạch — vì thẻ lúc đó vừa nhảy về ngày mặc định, vốn không cần hỏi.
    expect(await screen.findByRole("button", { name: "14:00" })).toBeEnabled();
    expect(fetchTestDriveAvailability).toHaveBeenCalledTimes(1);
  });
});

describe("TestDriveCard — 'đang tải' không được treo", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("bỏ ngày đang chờ giữa chừng thì chữ 'đang tải' biến mất", async () => {
    // Yêu cầu của ngày B bị cleanup khi khách quay về ngày mặc định, nên
    // `.finally()` của nó không bao giờ chạy — `loadingDate` kẹt ở B và dòng
    // "Đang tải…" đứng đó mãi trên một ngày đã có sẵn đủ ô.
    fetchTestDriveAvailability.mockImplementationOnce(() => new Promise(() => {}));
    const user = userEvent.setup();
    _render();

    await _bamSangNgayKia(user);
    expect(await screen.findByRole("status")).toHaveTextContent(/đang tải/i);

    await user.click(screen.getByRole("button", { name: "Hôm nay 28/08" }));

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });
});
