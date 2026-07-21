interface LoadingBlockProps {
  label?: string;
  rows?: number;
}

export function LoadingBlock({ label = "Đang tải dữ liệu", rows = 3 }: LoadingBlockProps) {
  return (
    <div className="loading-block" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} style={{ width: `${92 - index * 11}%` }} />
      ))}
    </div>
  );
}
