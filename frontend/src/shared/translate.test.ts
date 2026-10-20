import { describe, expect, it } from "vitest";
import { translateText } from "./translate";

describe("source statements and display wording", () => {
  it("still matches original governance messages after localizing their display text", () => {
    expect(translateText("If the protected action is later proposed, Governance must evaluate this registered checkpoint before execution."))
      .toBe("Nếu có đề xuất thực hiện hành động này, hệ thống phải kiểm tra yêu cầu phê duyệt đã đăng ký trước khi thực hiện.");
    expect(translateText("One or more explicit case-specific CRITICAL findings remain open; a later Governance/Decision phase must not silently bypass them."))
      .toContain("không được bỏ qua");
    expect(translateText("The masked Document package is an internal candidate only; a separate evidence-bound proposal and Governance authorization are required before external release."))
      .toContain("được phê duyệt riêng trước khi gửi ra ngoài");
  });
});
