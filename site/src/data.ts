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

export type Direction = "ffm_da" | "da_ffm";

export interface Corridor {
  directions: Record<Direction, { from: string; to: string }>;
  lines: string[];
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

export interface Data {
  meta: Meta;
  hub: Hub;
  corridor: Corridor;
  ranking: Ranking;
}

async function getJson<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`);
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
  return { meta, hub, corridor, ranking };
}
