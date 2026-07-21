export function compactIdentifier(value: string, visible = 12): string {
  if (!value) return "Chưa có";
  return value.length > visible ? `${value.slice(0, visible)}…` : value;
}

export function pluralizeCount(count: number, noun: string): string {
  return `${new Intl.NumberFormat("vi-VN").format(count)} ${noun}`;
}

export function formatVndCompact(value: number, currency = "VND"): string {
  if (!Number.isFinite(value)) return "Chưa xác định";
  if (currency.toUpperCase() !== "VND") {
    return `${new Intl.NumberFormat("vi-VN").format(value)} ${currency}`;
  }
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value / 1_000_000_000)} tỷ ₫`;
  }
  if (absolute >= 1_000_000) {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value / 1_000_000)} triệu ₫`;
  }
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}
