export function ConsultationProgress({ current, total }: Readonly<{ current: number; total: number }>) {
  const progress = Math.min(100, Math.max(0, (current / total) * 100));
  return (
    <div className="consultation-progress" aria-label={`Bước ${Math.min(current + 1, total)} trên ${total}`}>
      <div><span>Bước {Math.min(current + 1, total)}/{total}</span><strong>{Math.round(progress)}% hoàn tất</strong></div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
    </div>
  );
}
