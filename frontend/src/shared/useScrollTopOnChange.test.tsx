import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useScrollTopOnChange } from "./useScrollTopOnChange";

describe("useScrollTopOnChange", () => {
  let scrollTo: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.spyOn(window, "scrollY", "get").mockReturnValue(640);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not scroll on the first render or when the key is unchanged", () => {
    const { rerender } = renderHook(({ view }) => useScrollTopOnChange(view), {
      initialProps: { view: "decision" },
    });
    rerender({ view: "decision" });
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("returns to the top of the page when the view changes", () => {
    const { rerender } = renderHook(({ view }) => useScrollTopOnChange(view), {
      initialProps: { view: "decision" },
    });
    rerender({ view: "workflow" });
    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0 });
  });

  it("leaves focus where it was", () => {
    const button = document.createElement("button");
    document.body.append(button);
    button.focus();
    const { rerender } = renderHook(({ view }) => useScrollTopOnChange(view), {
      initialProps: { view: "decision" },
    });
    rerender({ view: "input" });
    expect(document.activeElement).toBe(button);
    button.remove();
  });

  it("skips the call when the page is already at the top", () => {
    vi.spyOn(window, "scrollY", "get").mockReturnValue(0);
    const { rerender } = renderHook(({ view }) => useScrollTopOnChange(view), {
      initialProps: { view: "decision" },
    });
    rerender({ view: "evidence" });
    expect(scrollTo).not.toHaveBeenCalled();
  });
});
