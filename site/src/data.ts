// Shapes of the JSON written by pipeline/export.py, plus loading.

export type DayType = "weekday" | "sat" | "sun_hol";
export const DAYTYPES: DayType[] = ["weekday", "sat", "sun_hol"];

/** One forecast. p* are null when n < min_samples ("데이터 부족"). */
export interface Forecast {
  n: number;
  p6: number | null;
  p15: number | null;
  p30: number | null;
  pc: number | null;
}

export interface WeatherLevel {
  icon: string;
  name: string;
  label: string;
  text: string;
  min_p?: number;
  fortune?: string;
  fortune_text?: string;
}

export interface Meta {
  generated_at: string;
  data_from: string;
  data_until: string;
  weather: {
    delay_threshold_min: number;
    min_samples: number;
    tornado_cancel_rate: number;
    levels: WeatherLevel[];
    tornado: WeatherLevel;
  };
  holidays_he: Record<string, string>;
  stations: Record<string, string>;
  live: { url: string; max_age_min: number };
  attribution: { text: string; license_url: string; source_url: string };
}

export interface Hub {
  station: string;
  overall: Forecast;
  daytypes: Record<DayType, {
    overall: Forecast;
    hours: Record<string, Forecast>;
    lines: (Forecast & { line: string })[];
  }>;
}

/** Route direction key: "ffm_<code>" (from Frankfurt Hbf) or "<code>_ffm" (to Frankfurt Hbf). */
export type Direction = string;

export interface Route {
  code: string;
  label: string; // short UI name, e.g. "공항"
  name: string; // endpoint station name from the data
  out: Direction;
  in: Direction;
}

/** Arrival-delay probability given the delay at the origin (pipeline/conditional.py). */
export interface Conditional {
  bins: string[];
  edges: number[];
  cells: Record<Direction, Record<string, ({ n: number; p6: number; p15: number } | null)[]>>;
}

export interface Corridor {
  routes: Route[];
  directions: Record<Direction, { route: string; from: string; to: string; lines: string[] }>;
  conditional: Conditional;
  /** Observed per-line profile, both directions (pipeline/profiles.py) — drives the character cards. */
  characters: Record<string, { n: number; p6: number; p15: number; p30: number; cancel: number; mean: number; p95: number; max: number; early: number }>;
  /** 101 quantiles of arrival delay among trains that ran, per direction × line — drives the delay gacha. */
  dist: Record<Direction, Record<string, number[]>>;
  cells: Record<Direction, Record<DayType, Record<string, {
    overall: Forecast | null;
    hours: Record<string, Forecast>;
  }>>>;
}

/** Observed results in the last 7 days of data (pipeline/ranking.py). */
export interface RankedTrain {
  label: string;
  line: string;
  train_number: string;
  time: string;
  destination?: string;
  direction?: Direction;
  p6: number;
  mean_delay: number;
  max_delay: number;
  runs: number;
  cancels: number;
}

export interface RankedLine {
  line: string;
  runs: number;
  p6: number;
  mean_delay: number;
  cancel_rate: number;
}

export interface Ranking {
  window: { from: string; to: string };
  station: string;
  hub: {
    lines_worst: RankedLine[];
    lines_best: RankedLine[];
    trains_worst: RankedTrain[];
    trains_best: RankedTrain[];
    biggest: { label: string; line: string; date: string; time: string; destination: string; delay: number };
  };
  corridor: { trains_worst: RankedTrain[]; trains_best: RankedTrain[] };
}

/** Live snapshot written by pipeline/live.py (every 15 min once an API key is configured). */
export interface LiveTrain {
  line: string;
  train_type: string;
  number: string;
  dep_planned: string;
  dep_expected: string;
  arr_planned: string;
  delay_now: number;
  departed: boolean;
  canceled: boolean;
  p6: number | null;
  p15: number | null;
  n: number | null;
}

export interface Live {
  generated_at: string;
  snapshot: string;
  source: "api" | "fixtures";
  hub: { window_min: number; n: number; delayed6: number; canceled: number; p6: number | null };
  corridor: Record<Direction, LiveTrain[]>;
}

export interface Data {
  meta: Meta;
  hub: Hub;
  corridor: Corridor;
  ranking: Ranking;
  live: Live | null; // filled in after first render, if a fresh snapshot exists
}

async function getJson<T>(name: string): Promise<T> {
  // no-cache: revalidate (ETag) every load, so fresh JS never meets JSON cached from the previous deploy
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export async function loadData(): Promise<Data> {
  const [meta, hub, corridor, ranking] = await Promise.all([
    getJson<Meta>("meta.json"),
    getJson<Hub>("hub.json"),
    getJson<Corridor>("corridor.json"),
    getJson<Ranking>("ranking.json"),
  ]);
  return { meta, hub, corridor, ranking, live: null };
}

/** Fresh live snapshot or null (no URL configured, unreachable, too old, or replayed fixtures). */
export async function loadLive(meta: Meta): Promise<Live | null> {
  if (!meta.live?.url) return null;
  try {
    const bucket = Math.floor(Date.now() / 300_000); // follow the ~5 min CDN cache, not every request
    const res = await fetch(`${meta.live.url}?t=${bucket}`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    const live = (await res.json()) as Live;
    const ageMin = (Date.now() - new Date(live.generated_at).getTime()) / 60_000;
    if (live.source !== "api" || !(ageMin >= -5 && ageMin <= meta.live.max_age_min)) return null;
    return live;
  } catch {
    return null;
  }
}
