import { translateText } from "../../shared/translate";

const TECHNICAL_TERM_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bprojected_closing_cash\b/gi, "dự báo dòng tiền hiện có"],
  [/\bclosing_cash\b/gi, "dòng tiền cuối kỳ riêng của hợp đồng"],
  [/\bdelivery_delay_days\b/gi, "số ngày chậm giao thực tế"],
  [/\bORDER_REVENUE_TOTAL\b/g, "tổng giá trị đơn hàng liên kết"],
  [/\bUNCOVERED_CONTRACT_VALUE\b/g, "phần giá trị hợp đồng chưa được đơn hàng liên kết làm rõ"],
  [/\bORDER_COVERAGE_RATIO\b/g, "tỷ lệ giá trị hợp đồng được đơn hàng liên kết làm rõ"],
  [/\bCONTRACT_VALUE\b/g, "giá trị hợp đồng"],
  [/\bWORST_RESERVE_GAP_MONTH\b/g, "tháng có áp lực dòng tiền lớn nhất"],
  [/\bWORST_RESERVE_GAP\b/g, "mức áp lực dòng tiền lớn nhất"],
  [/\bNEGATIVE_NET_CASHFLOW_MONTH_COUNT\b/g, "số tháng có dòng tiền âm"],
  [/\bOPC_GLOBAL\b/g, "bức tranh chung của OPC"],
  [/\breason_codes?\b/gi, "lý do đánh giá"],
  [/\bevidence_ids?\b/gi, "bằng chứng"],
  [/\bsource_reference_ids?\b/gi, "tham chiếu nguồn"],
];

export function founderScenarioText(text?: string | null): string {
  if (!text) return "";

  let output = translateText(text);
  for (const [pattern, replacement] of TECHNICAL_TERM_REPLACEMENTS) {
    output = output.replace(pattern, replacement);
  }

  return output
    .replace(/[`_]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
