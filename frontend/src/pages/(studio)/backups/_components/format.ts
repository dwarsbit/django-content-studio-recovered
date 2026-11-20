/** Bytes as "512 B", "3.4 MB" or "1.2 GB". */
export function formatBytes(bytes: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Math.round(bytes);
  let unit = 0;

  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }

  return unit === 0
    ? `${value} ${units[unit]}`
    : `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

/** A run's time: "42 s" or "3 min". */
export function formatSeconds(seconds: number) {
  return seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}
