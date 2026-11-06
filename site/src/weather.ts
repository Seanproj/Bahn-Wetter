// Probability → weather level, using the thresholds from config/weather.yaml (via meta.json).

import type { Forecast, Meta, WeatherLevel } from "./data";

export const UNKNOWN: WeatherLevel = { icon: "❔", name: "unknown", label: "데이터 부족", text: "표본이 적어 예보를 숨겼어요", fortune: "미정", fortune_text: "기록이 부족해 운세를 볼 수 없어요." };

export function weatherOf(f: Forecast | null | undefined, meta: Meta): WeatherLevel {
  if (!f || f.p6 === null) return UNKNOWN;
  const w = meta.weather;
  if (f.pc !== null && f.pc >= w.tornado_cancel_rate) return w.tornado;
  return w.levels.find((l) => f.p6! >= (l.min_p ?? 0)) ?? w.levels[w.levels.length - 1];
}

export function pct(p: number | null | undefined, digits = 0): string {
  return p === null || p === undefined ? "–" : `${(p * 100).toFixed(digits)}%`;
}

/**
 * 0.25 → "4대 중 1대", 0.4 → "10대 중 4대": natural frequencies read faster than percentages.
 * "N대 중 1대" only when it stays within 3 points of p (0.4 is not "3대 중 1대").
 */
export function freqText(p: number): string {
  if (p < 0.005) return "100대 중 0대";
  if (p < 0.1) return `${Math.round(1 / p)}대 중 1대`;
  const n = Math.round(1 / p);
  return Math.abs(1 / n - p) <= 0.03 ? `${n}대 중 1대` : `10대 중 ${Math.round(p * 10)}대`;
}

export function sampleNote(f: Forecast): string {
  return `n=${f.n.toLocaleString("ko-KR")}회 기준`;
}
