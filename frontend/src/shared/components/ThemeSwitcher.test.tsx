import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEME_STORAGE_KEY } from "../theme";
import { ThemeSwitcher } from "./ThemeSwitcher";

type Listener = () => void;

function stubSystemTheme(initialDark: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: initialDark,
    addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    listeners,
    change(dark: boolean) {
      query.matches = dark;
      listeners.forEach((listener) => listener());
    },
  };
}

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("follows the system theme by default and tracks OS changes", () => {
    const system = stubSystemTheme(true);
    render(<ThemeSwitcher />);

    expect(screen.getByRole("group", { name: "Giao diện" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theo hệ thống" })).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");

    act(() => system.change(false));
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("stores an explicit choice and stops following the system", () => {
    const system = stubSystemTheme(false);
    render(<ThemeSwitcher />);

    fireEvent.click(screen.getByRole("button", { name: "Tối" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Tối" })).toHaveAttribute("aria-pressed", "true");
    expect(system.listeners.size).toBe(0);

    act(() => system.change(false));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("restores a stored choice and clears it when returning to system", () => {
    stubSystemTheme(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeSwitcher />);

    expect(screen.getByRole("button", { name: "Tối" })).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");

    fireEvent.click(screen.getByRole("button", { name: "Theo hệ thống" }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("falls back to light when matchMedia and storage are unavailable", () => {
    vi.stubGlobal("matchMedia", undefined);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<ThemeSwitcher />);

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(screen.getByRole("button", { name: "Theo hệ thống" })).toHaveAttribute("aria-pressed", "true");
  });
});
