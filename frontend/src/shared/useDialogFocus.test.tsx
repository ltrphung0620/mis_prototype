import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { focusableWithin, useDialogFocus } from "./useDialogFocus";

function DialogExample({ escapeDisabled = false }: { escapeDisabled?: boolean }) {
  const [open, setOpen] = useState<"first" | "second" | null>(null);
  useDialogFocus(open !== null, () => setOpen(null), { escapeDisabled });
  return (
    <>
      <main>
        <button onClick={() => setOpen("first")}>Mở</button>
      </main>
      {open === "first" && (
        <div role="dialog" aria-modal="true" aria-label="Thứ nhất">
          <button>Đầu</button>
          <button onClick={() => setOpen("second")}>Chuyển</button>
          <button>Cuối</button>
        </div>
      )}
      {open === "second" && (
        <div role="dialog" aria-modal="true" aria-label="Thứ hai">
          <input aria-label="Ô nhập" data-autofocus />
          <button>Xong</button>
        </div>
      )}
    </>
  );
}

describe("dialog keyboard focus", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("focuses the dialog, traps Tab and Shift+Tab, closes with Escape and restores the trigger", () => {
    render(<DialogExample />);
    const trigger = screen.getByRole("button", { name: "Mở" });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Thứ nhất" });
    const first = screen.getByRole("button", { name: "Đầu" });
    const last = screen.getByRole("button", { name: "Cuối" });

    expect(dialog).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("makes the background inert only while a dialog is open", () => {
    const { container } = render(<DialogExample />);
    const main = container.querySelector("main")!;
    fireEvent.click(screen.getByRole("button", { name: "Mở" }));
    expect(main).toHaveAttribute("inert");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(main).not.toHaveAttribute("inert");
  });

  it("follows a dialog that replaces the open one", async () => {
    render(<DialogExample />);
    const trigger = screen.getByRole("button", { name: "Mở" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển" }));

    const input = screen.getByRole("textbox", { name: "Ô nhập" });
    await waitFor(() => expect(input).toHaveFocus());
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: "Xong" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveFocus();
  });

  it("keeps the dialog open on Escape while a submission is in flight", () => {
    render(<DialogExample escapeDisabled />);
    fireEvent.click(screen.getByRole("button", { name: "Mở" }));
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.getByRole("dialog", { name: "Thứ nhất" })).toBeInTheDocument();
  });

  it("skips disabled, hidden and negative-tabindex controls", () => {
    render(
      <div role="dialog" aria-modal="true" data-testid="scope">
        <button>Hiện</button>
        <button disabled>Tắt</button>
        <fieldset disabled>
          <input aria-label="Trong fieldset tắt" />
        </fieldset>
        <div hidden>
          <button>Ẩn</button>
        </div>
        <span tabIndex={-1}>Không tab</span>
      </div>,
    );
    expect(focusableWithin(screen.getByTestId("scope")).map((element) => element.textContent)).toEqual(["Hiện"]);
  });

  it("returns focus to the fallback target when the dialog opened without a trigger", () => {
    function AutoOpened() {
      const [open, setOpen] = useState(true);
      useDialogFocus(open, () => setOpen(false), { fallbackFocusId: "content" });
      return (
        <>
          <main id="content" tabIndex={-1}>Nội dung</main>
          {open && (
            <div role="dialog" aria-modal="true" aria-label="Tự mở">
              <button>Đóng</button>
            </div>
          )}
        </>
      );
    }
    render(<AutoOpened />);
    expect(screen.getByRole("dialog", { name: "Tự mở" })).toHaveFocus();
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("main")).toHaveFocus();
    expect(focusSpy).toHaveBeenLastCalledWith({ preventScroll: true });
  });

  it("restores the trigger without scrolling the page", () => {
    render(<DialogExample />);
    const trigger = screen.getByRole("button", { name: "Mở" });
    trigger.focus();
    fireEvent.click(trigger);
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveFocus();
    expect(focusSpy.mock.instances.at(-1)).toBe(trigger);
    expect(focusSpy).toHaveBeenLastCalledWith({ preventScroll: true });
  });
});
