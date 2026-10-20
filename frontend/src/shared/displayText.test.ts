import { describe, expect, it } from "vitest";
import { displayText } from "./displayText";

describe("display copy from existing responses", () => {
  it("adapts existing labels without changing source objects or identifiers", () => {
    const source = {
      label: "Chờ Founder duyệt Decision Card",
      status: "WAITING_FOR_APPROVAL",
      id: "FINANCE_ASSESSMENT",
    };
    expect(displayText(source.label)).toBe(
      "Chờ phê duyệt Phiếu đề xuất quyết định",
    );
    expect(source.label).toBe("Chờ Founder duyệt Decision Card");
    expect(displayText(source.id)).toBe(source.id);
    expect(displayText(source.status)).toBe(source.status);
  });
  it("does not partially translate names embedded inside technical identifiers", () => {
    expect(displayText("FinanceFacts / DocumentPreparationRequest")).toBe(
      "FinanceFacts / DocumentPreparationRequest",
    );
    expect(displayText("Trạng thái workflow")).toBe("Trạng thái xử lý");
    expect(displayText("Lượt chạy hiện tại")).toBe("Lần xử lý hiện tại");
  });
});
