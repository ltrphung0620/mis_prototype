import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { useDialogFocus } from "./useDialogFocus";

function DialogExample() {
  const [open, setOpen] = useState(false);
  useDialogFocus(open, () => setOpen(false));
  return (
    <>
      <button onClick={() => setOpen(true)}>Mở</button>
      {open && (
        <div role="dialog">
          <button>Đầu</button>
          <button>Cuối</button>
        </div>
      )}
    </>
  );
}
describe("dialog keyboard focus", () => {
  it("traps Tab and Shift+Tab, closes with Escape and restores the trigger", () => {
    render(<DialogExample />);
    const trigger = screen.getByRole("button", { name: "Mở" });
    trigger.focus();
    fireEvent.click(trigger);
    const first = screen.getByRole("button", { name: "Đầu" });
    const last = screen.getByRole("button", { name: "Cuối" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
