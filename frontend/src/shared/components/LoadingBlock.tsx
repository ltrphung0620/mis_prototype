interface LoadingBlockProps {
  label?: string;
  rows?: number;
}

export function LoadingBlock({ label = "Đang tải dữ liệu", rows = 3 }: LoadingBlockProps) {
  return (
    <div className="loading-block" role="status" aria-busy="true" aria-label={label}>
      <p className="loading-block__label">{label}…</p>
      {Array.from({ length: rows }, (_, index) => (
        <span className="loading-block__line" aria-hidden="true" key={index} />
      ))}
    </div>
  );
}
