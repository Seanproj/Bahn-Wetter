// Probability → weather level, using the thresholds from config/weather.yaml (via meta.json).

import type { Forecast, Meta, WeatherLevel } from "./data";

export const UNKNOWN: WeatherLevel = { icon: "❔", name: "unknown", label: "데이터 부족", text: "표본이 적어 예보를 숨겼어요" };

export function weatherOf(f: Forecast | null | undefined, meta: Meta): WeatherLevel {
  if (!f || f.p6 === null) return UNKNOWN;
  const w = meta.weather;
  if (f.pc !== null && f.pc >= w.tornado_cancel_rate) return w.tornado;
  return w.levels.find((l) => f.p6! >= (l.min_p ?? 0)) ?? w.levels[w.levels.length - 1];
}

export function pct(p: number | null | undefined, digits = 0): string {
  return p === null || p === undefined ? "–" : `${(p * 100).toFixed(digits)}%`;
}

export function sampleNote(f: Forecast): string {
  return `n=${f.n.toLocaleString("ko-KR")}회 기준`;
}
