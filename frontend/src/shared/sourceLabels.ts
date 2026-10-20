/** Display labels only. Keep source values unchanged for filtering and API calls. */
const SOURCE_STATUS_LABELS: Readonly<Record<string, string>> = {
  Paid: "Đã thanh toán",
  Open: "Đang mở",
  "Not issued": "Chưa phát hành",
  Negotiation: "Đang đàm phán",
  Active: "Đang hoạt động",
  "Pending expansion": "Chờ mở rộng",
  "In progress": "Đang triển khai",
  Delivered: "Đã bàn giao",
  Planned: "Đã lên kế hoạch",
  "At risk": "Có rủi ro",
  "Pending approval": "Chờ phê duyệt",
};

export function sourceStatusLabel(value: string): string {
  return SOURCE_STATUS_LABELS[value] ?? value;
}
