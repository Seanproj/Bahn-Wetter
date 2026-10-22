// "Now" in Europe/Berlin (the data's time zone), independent of the viewer's time zone.

import type { DayType, Meta } from "./data";

export interface BerlinNow {
  date: string; // YYYY-MM-DD
  month: number;
  day: number;
  weekday: number; // 0 = Sunday
  hour: number;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"];

export function berlinNow(at: Date = new Date()): BerlinNow {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Europe/Berlin",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
      hour: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(at)
      .map((p) => [p.type, p.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    month: Number(parts.month),
    day: Number(parts.day),
    weekday: WEEKDAYS.indexOf(parts.weekday),
    hour: Number(parts.hour),
  };
}

/** A fixed day (YYYY-MM-DD) as seen in Berlin, at the given hour. Used by the share card. */
export function berlinDay(date: string, hour = 12): BerlinNow | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const at = new Date(`${date}T12:00:00Z`); // noon UTC is the same calendar day in Berlin
  if (Number.isNaN(at.getTime())) return null;
  return { ...berlinNow(at), hour };
}

export function dayTypeOf(now: BerlinNow, meta: Meta): DayType {
  if (now.weekday === 0 || meta.holidays_he[now.date]) return "sun_hol";
  if (now.weekday === 6) return "sat";
  return "weekday";
}

export const DAYTYPE_LABEL: Record<DayType, string> = {
  weekday: "평일",
  sat: "토요일",
  sun_hol: "일·공휴일",
};

export function formatDate(now: BerlinNow, meta: Meta): string {
  const holiday = meta.holidays_he[now.date];
  return `${now.month}월 ${now.day}일 (${WEEKDAY_KO[now.weekday]})${holiday ? ` · ${holiday}` : ""}`;
}
