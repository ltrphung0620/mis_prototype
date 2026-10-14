import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PreviewApp from "./PreviewApp";
import { parsePreviewRoute } from "./navigation";

function route(path: string) {
  act(() => {
    window.history.replaceState({}, "", `/#${path}`);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
}
beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("Preview must not call the backend"))),
  );
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  window.history.replaceState({}, "", "/#/dashboard");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("isolated executive preview", () => {
  it("opens a contract from a non-link cell without changing the approval scope", async () => {
    render(<PreviewApp />);
    route("/contracts");
    const row = screen.getByText("CON-004").closest("tr")!;
    expect(within(row).getByText("Negotiation")).toBeInTheDocument();
    expect(within(row).getByText("Chờ duyệt quyết định")).toBeInTheDocument();
    fireEvent.click(within(row).getByText("Đang đàm phán"));
    await screen.findByRole("heading", {
      name: "Triển khai nền tảng quản trị doanh nghiệp",
    });
    expect(window.location.hash).toBe("#/contracts/CON-004");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("keeps native contract links and ignores modified row clicks", () => {
    render(<PreviewApp />);
    route("/contracts");
    const row = screen.getByText("CON-004").closest("tr")!;
    fireEvent.click(within(row).getByText("Đang đàm phán"), { ctrlKey: true });
    expect(window.location.hash).toBe("#/contracts");
    expect(
      screen.getByRole("link", { name: /CON-004.*An Việt/ }),
    ).toHaveAttribute("href", "#/contracts/CON-004");
    expect(
      screen.getByRole("link", { name: "Mở hợp đồng CON-004" }),
    ).toHaveAttribute("href", "#/contracts/CON-004");
  });
  it("searches contract rows and reports an empty filter result", () => {
    render(<PreviewApp />);
    route("/contracts");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm hợp đồng" }), {
      target: { value: "An Việt" },
    });
    expect(screen.getByText("CON-004")).toBeInTheDocument();
    expect(screen.queryByText("CON-002")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm hợp đồng" }), {
      target: { value: "no match" },
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      "Không có hợp đồng khớp bộ lọc",
    );
  });
  it("validates the demo input without patching or resuming a workflow", async () => {
    render(<PreviewApp />);
    route("/contracts/CON-002?request=UI-INPUT-CON-002");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Kiểm tra form minh họa" }),
    );
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "Nhập số tiền lớn hơn 0",
    );
    fireEvent.change(
      within(dialog).getByRole("spinbutton", { name: "Số tiền yêu cầu (VND)" }),
      { target: { value: "1000000" } },
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Kiểm tra form minh họa" }),
    );
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "Không tạo patch, không resume workflow",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("keeps URL scope and rejects unknown paths", () => {
    expect(
      parsePreviewRoute("#/contracts/CON-004?view=evidence&request=UI-X"),
    ).toMatchObject({
      page: "contracts",
      contractId: "CON-004",
      view: "evidence",
      request: "UI-X",
    });
    expect(
      parsePreviewRoute("#/company?section=finance&status=Open&period=recent"),
    ).toMatchObject({
      page: "company",
      section: "finance",
      status: "Open",
      period: "recent",
    });
    expect(parsePreviewRoute("#/company?section=unknown").section).toBe(
      "overview",
    );
    expect(parsePreviewRoute("#/unsafe").page).toBe("not-found");
  });
  it("renders action-first home and filters actions without financial filtering", () => {
    render(<PreviewApp />);
    fireEvent.click(screen.getByRole("button", { name: "Phê duyệt" }));
    expect(screen.getByText("Xem xét quyết định hợp đồng")).toBeInTheDocument();
    expect(
      screen.queryByText("Bổ sung số tiền yêu cầu precheck"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Hóa đơn ghi nguồn Open")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("offers native links to every contract from the dashboard header", () => {
    render(<PreviewApp />);
    const summary = screen.getByText("Đi tới hợp đồng");
    const menu = summary.closest("details")!;
    const links = within(menu).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "#/contracts/CON-004",
      "#/contracts/CON-002",
      "#/contracts/CON-001",
      "#/contracts/CON-005",
      "#/contracts/CON-003",
      "#/contracts",
    ]);

    menu.open = true;
    fireEvent.keyDown(links[0], { key: "Escape" });
    expect(menu.open).toBe(false);
    expect(summary).toHaveFocus();

    menu.open = true;
    fireEvent.pointerDown(document.body);
    expect(menu.open).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("drills down into invoice scope and filters the table", async () => {
    render(<PreviewApp />);
    route("/company?section=invoices&status=Open");
    expect(screen.getByText("INV-002")).toBeInTheDocument();
    expect(screen.queryByText("INV-001")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm hóa đơn" }), {
      target: { value: "nothing" },
    });
    expect(
      screen.getByText(/Không có hóa đơn khớp bộ lọc/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ lọc" }));
    await waitFor(() =>
      expect(screen.getByText("INV-001")).toBeInTheDocument(),
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("provides chart table, series controls and a missing-period state", async () => {
    render(<PreviewApp />);
    fireEvent.click(screen.getByRole("button", { name: "Bảng dữ liệu" }));
    expect(screen.getByRole("table")).toHaveTextContent("1.700.000.000");
    fireEvent.click(screen.getByRole("button", { name: "Thu dự kiến" }));
    expect(screen.getByRole("table")).not.toHaveTextContent("1.700.000.000");
    fireEvent.change(
      screen.getByRole("combobox", { name: "Kỳ biểu đồ dòng tiền" }),
      { target: { value: "empty" } },
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Chưa có dữ liệu dự kiến cho kỳ này/),
      ).toBeInTheDocument(),
    );
  });
  it("shows only the selected contract and reports an unknown ID", () => {
    render(<PreviewApp />);
    route("/contracts/CON-004?view=overview");
    expect(
      screen.getByRole("heading", { name: "Đề xuất chấp nhận hợp đồng" }),
    ).toBeInTheDocument();
    route("/contracts/NO-SUCH-ID");
    expect(
      screen.getByRole("heading", { name: "Không tìm thấy hợp đồng" }),
    ).toBeInTheDocument();
  });
  it("reviews exact ID/version and locks stale or resolved requests", async () => {
    render(<PreviewApp />);
    route("/contracts/CON-004?view=overview&request=UI-APPROVAL-CON-004");
    const modal = await screen.findByRole("dialog");
    expect(modal).toHaveTextContent("UI-CARD-CON-004 · v1");
    expect(
      within(modal).getByRole("button", { name: "Phê duyệt" }),
    ).toBeEnabled();
    fireEvent.change(
      within(modal).getByRole("combobox", {
        name: "Trạng thái review minh họa",
      }),
      { target: { value: "stale" } },
    );
    expect(
      within(modal).queryByRole("button", { name: "Phê duyệt" }),
    ).not.toBeInTheDocument();
    fireEvent.change(
      within(modal).getByRole("combobox", {
        name: "Trạng thái review minh họa",
      }),
      { target: { value: "resolved" } },
    );
    expect(
      within(modal).queryByRole("button", { name: "Phê duyệt" }),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("demo submit never mutates and prevents duplicate submission", async () => {
    render(<PreviewApp />);
    route("/contracts/CON-004?request=UI-APPROVAL-CON-004");
    const modal = await screen.findByRole("dialog");
    fireEvent.click(within(modal).getByRole("button", { name: "Phê duyệt" }));
    expect(modal).toHaveTextContent(
      "Không gửi request và không thay đổi quyết định backend",
    );
    expect(
      within(modal).getByRole("button", { name: "Phê duyệt" }),
    ).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not borrow another contract's request or artifacts", () => {
    render(<PreviewApp />);
    route("/contracts/CON-005?request=UI-APPROVAL-CON-004");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "không mở review của request khác",
    );
    route("/contracts/CON-003?view=evidence");
    expect(
      screen.getByRole("heading", { name: "Chưa có artifact để đối chiếu" }),
    ).toBeInTheDocument();
  });
  it("keeps NOT_EVALUABLE read-only", async () => {
    render(<PreviewApp />);
    route("/contracts/CON-001");
    fireEvent.click(
      screen.getByRole("button", { name: "Xem giới hạn Decision Card" }),
    );
    const modal = await screen.findByRole("dialog");
    expect(
      within(modal).queryByRole("button", { name: "Phê duyệt" }),
    ).not.toBeInTheDocument();
  });
  it("preserves risk artifact lineage after evidence search", async () => {
    render(<PreviewApp />);
    route("/contracts/CON-004?view=evidence");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm bằng chứng" }), {
      target: { value: "RISK" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Xem bằng chứng" }));
    const modal = await screen.findByRole("dialog");
    expect(modal).toHaveTextContent("UI-RISK-CON-004");
    expect(modal).toHaveTextContent("UI-FINANCE-CON-004");
    expect(modal).toHaveTextContent("UI-OPERATIONS-CON-004");
  });
  it("supports explicit loading, empty, error and retry without backend calls", () => {
    render(<PreviewApp />);
    const selector = screen.getByRole("combobox", {
      name: "Trạng thái preview",
    });
    fireEvent.change(selector, { target: { value: "loading" } });
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải");
    fireEvent.change(selector, { target: { value: "empty" } });
    expect(
      screen.getByRole("heading", {
        name: "Chưa có dữ liệu trong phạm vi này",
      }),
    ).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: "error" } });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Lỗi kết nối được mô phỏng",
    );
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(
      screen.getByRole("heading", { name: "Bảng điều hành" }),
    ).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
