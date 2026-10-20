import { describe, expect, it } from "vitest";
import { sourceStatusLabel } from "./sourceLabels";

describe("source status display labels", () => {
  it.each([
    ["Paid", "Đã thanh toán"],
    ["Open", "Đang mở"],
    ["Not issued", "Chưa phát hành"],
    ["Pending approval", "Chờ phê duyệt"],
    ["At risk", "Có rủi ro"],
  ])("labels %s without changing the original value", (value, label) => {
    expect(sourceStatusLabel(value)).toBe(label);
    expect(value).not.toBe(label);
  });
  it("preserves unfamiliar statuses rather than guessing their meaning", () => {
    expect(sourceStatusLabel("PARTIALLY_PAID")).toBe("PARTIALLY_PAID");
  });
});
