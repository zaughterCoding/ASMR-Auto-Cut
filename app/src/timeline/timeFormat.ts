/**
 * 秒数格式化成 mm:ss，超过一小时就是 h:mm:ss。
 *
 * 从 SummaryPanel 里搬过来的，概览的视口提示也要用同一套格式——同一个界面上
 * 两处时间写法不一致会让人以为是两个东西。
 */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const clock = `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return hours > 0 ? `${hours}:${clock}` : clock;
}

/**
 * 视口两端的标签。
 *
 * 跨度不到一分钟时给一位小数：概览放大到几秒的范围时，整秒会把 12.3–13.7
 * 显示成 00:12–00:14，看不出视口到底停在哪一小段上。
 */
export function formatRangeLabel(start: number, end: number): string {
  if (end - start < 60) {
    return `${start.toFixed(1)}s – ${end.toFixed(1)}s`;
  }
  return `${formatClock(start)} – ${formatClock(end)}`;
}
