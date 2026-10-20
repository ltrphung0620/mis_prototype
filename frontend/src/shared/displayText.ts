/** Presentation copy only. Never use this function on IDs, enums or request payloads. */
export function displayText(value: string): string {
  return value
    .replace(/Cổng phê duyệt của Founder/g, "Xem xét và phê duyệt")
    .replace(/Founder (?:phê duyệt|duyệt)/g, "phê duyệt")
    .replace(/\bFounder\b/g, "người phê duyệt")
    .replace(/\bDecision Card\b/g, "Phiếu đề xuất quyết định")
    .replace(/\bFinance\b/g, "Tài chính")
    .replace(/\bOperations\b/g, "Vận hành")
    .replace(/\bRisk\b/g, "Rủi ro")
    .replace(/\bBanking\b/g, "Ngân hàng")
    .replace(/\bDocument\b/g, "Hồ sơ")
    .replace(/\b[Ww]orkflow\b/g, "quy trình")
    .replace(/\b[Pp]recheck\b/g, "kiểm tra sơ bộ")
    .replace(/Giá trị nguồn/g, "Giá trị ghi nhận")
    .replace(/Snapshot công ty/g, "Tổng quan công ty")
    .replace(/Trạng thái quy trình/g, "Trạng thái xử lý")
    .replace(/[Ll]ượt (?:chạy|xử lý|đánh giá)/g, (match) =>
      match[0] === "L" ? "Lần xử lý" : "lần xử lý",
    )
    .replace(
      /^(người phê duyệt|phê duyệt|quy trình|kiểm tra sơ bộ)/,
      (match) => match[0].toLocaleUpperCase("vi") + match.slice(1),
    );
}
