// Page renderers. Each returns an HTML string; main.ts wires up events after rendering.

import type { Data, DayType, Direction, Forecast } from "./data";
import { DAYTYPES } from "./data";
import { DAYTYPE_LABEL, formatDate, type BerlinNow } from "./time";
import { pct, sampleNote, weatherOf } from "./weather";

export interface Ctx {
  now: BerlinNow;
  today: DayType;
  dayType: DayType; // selected
  direction: Direction;
}

export const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export const DISCLAIMER = "과거 패턴 기반 예보이며 파업·사고 등 돌발 상황은 반영되지 않습니다";

function dayChips(ctx: Ctx): string {
  return `<div class="chips" role="group" aria-label="요일 구분">${DAYTYPES.map(
    (d) => `<button class="chip${d === ctx.dayType ? " on" : ""}" data-daytype="${d}" aria-pressed="${d === ctx.dayType}">
      ${DAYTYPE_LABEL[d]}${d === ctx.today ? " · 오늘" : ""}</button>`,
  ).join("")}</div>`;
}

function icon(f: Forecast | null | undefined, data: Data, cls = ""): string {
  const w = weatherOf(f, data.meta);
  return `<span class="wx ${cls}" role="img" aria-label="${esc(w.label)}">${w.icon}</span>`;
}

/** Data attributes so a tap can open the detail sheet. */
function detailAttrs(title: string, f: Forecast): string {
  return `data-detail='${esc(JSON.stringify({ title, f }))}'`;
}

// ── Home: today's forecast for Frankfurt Hbf ─────────────────────────────

export function homeSky(data: Data, ctx: Ctx): string {
  return weatherOf(data.hub.daytypes[ctx.dayType].overall, data.meta).name;
}

export function renderHome(data: Data, ctx: Ctx): string {
  const { meta, hub } = data;
  const day = hub.daytypes[ctx.dayType];
  const f = day.overall;
  const w = weatherOf(f, meta);
  const isToday = ctx.dayType === ctx.today;
  const nowF = isToday ? day.hours[String(ctx.now.hour)] : undefined;

  const hours = Array.from({ length: 18 }, (_, i) => i + 6); // 06–23
  const strip = hours
    .map((h) => {
      const hf = day.hours[String(h)];
      const current = isToday && h === ctx.now.hour;
      return `<li class="hour${current ? " now" : ""}" ${hf ? detailAttrs(`${h}시 · 전체 노선`, hf) : ""} tabindex="0">
        <span class="h">${current ? "지금" : `${h}시`}</span>
        ${icon(hf, data)}
        <span class="p">${pct(hf?.p6)}</span>
      </li>`;
    })
    .join("");

  const lines = day.lines
    .slice(0, 12)
    .map(
      (l) => `<li class="line-row" ${detailAttrs(`${l.line} · ${DAYTYPE_LABEL[ctx.dayType]} 전체`, l)} tabindex="0">
        <span class="badge">${esc(l.line)}</span>
        <span class="bar"><span style="width:${Math.round((l.p6 ?? 0) * 100)}%"></span></span>
        <span class="p">${pct(l.p6)}</span>
        ${icon(l, data)}
      </li>`,
    )
    .join("");

  return `
  <section class="hero">
    <p class="date">${isToday ? formatDate(ctx.now, meta) : `${DAYTYPE_LABEL[ctx.dayType]} 예보`}</p>
    <h1>${esc(meta.stations[hub.station])}</h1>
    <div class="big" role="img" aria-label="${esc(w.label)}">${w.icon}</div>
    <p class="headline"><strong>${pct(f.p6)}</strong> 지연 확률</p>
    <p class="condition">${esc(w.label)} — ${esc(w.text)}</p>
    <dl class="stats">
      <div><dt>15분↑</dt><dd>${pct(f.p15)}</dd></div>
      <div><dt>30분↑</dt><dd>${pct(f.p30)}</dd></div>
      <div><dt>취소</dt><dd>${pct(f.pc, 1)}</dd></div>
    </dl>
    <p class="note">6분 이상 지연 기준 · ${sampleNote(f)}</p>
  </section>

  ${dayChips(ctx)}

  ${nowF ? `<section class="card now-card">
    <h2>지금 (${ctx.now.hour}시대)</h2>
    <p>${icon(nowF, data, "md")} <strong>${pct(nowF.p6)}</strong> · ${esc(weatherOf(nowF, meta).text)}</p>
  </section>` : ""}

  <section class="card">
    <h2>시간대별 예보</h2>
    <ol class="strip" aria-label="시간대별 지연 확률">${strip}</ol>
  </section>

  <section class="card">
    <h2>노선별 예보 <small>${DAYTYPE_LABEL[ctx.dayType]} 하루 전체</small></h2>
    <ol class="lines">${lines}</ol>
  </section>`;
}

// ── Commute: Frankfurt ↔ Darmstadt ──────────────────────────────────────

/** Chance the trip goes badly: canceled, or runs and arrives ≥6 min late. */
const badTrip = (f: Forecast) => (f.pc ?? 0) + (1 - (f.pc ?? 0)) * f.p6!;

/**
 * Ranking score: badTrip plus a penalty for small samples (≈ upper 75% bound of a binomial
 * estimate), so a rarely-run train cannot win on a lucky handful of trips.
 */
const pickScore = (f: Forecast) => {
  const b = badTrip(f);
  return b + 0.67 * Math.sqrt((b * (1 - b)) / Math.max(f.n, 1));
};

export function bestTrain(data: Data, direction: Direction, dayType: DayType, hours: number[]) {
  const cells = data.corridor.cells[direction][dayType];
  let best: { line: string; hour: number; f: Forecast } | null = null;
  for (const line of data.corridor.lines) {
    for (const h of hours) {
      const f = cells[line]?.hours[String(h)];
      if (!f || f.p6 === null) continue;
      if (weatherOf(f, data.meta).name === data.meta.weather.tornado.name) continue; // never recommend 🌪️
      if (!best || pickScore(f) < pickScore(best.f)) best = { line, hour: h, f };
    }
  }
  return best;
}

/** Which hours the recommendation covers: morning or evening rush, skipping hours already past today. */
function bestWindow(ctx: Ctx): { label: string; hours: number[] } {
  const range = (a: number, b: number) => Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
  if (ctx.dayType !== ctx.today) return { label: `${DAYTYPE_LABEL[ctx.dayType]} 아침`, hours: range(6, 9) };
  const h = ctx.now.hour;
  if (h < 10) return { label: "오늘 아침", hours: range(Math.max(6, h), 9) };
  if (h < 20) return { label: "오늘 저녁", hours: range(Math.max(16, h), 19) };
  return { label: "지금부터", hours: range(h, 23) };
}

export function commuteSky(data: Data, ctx: Ctx): string {
  const cells = data.corridor.cells[ctx.direction][ctx.dayType];
  const main = data.corridor.lines.map((l) => cells[l]?.overall).filter((f): f is Forecast => !!f && f.p6 !== null);
  const n = main.reduce((a, f) => a + f.n, 0);
  const p6 = n ? main.reduce((a, f) => a + f.p6! * f.n, 0) / n : null;
  return weatherOf({ n, p6, p15: null, p30: null, pc: null }, data.meta).name;
}

export function renderCommute(data: Data, ctx: Ctx): string {
  const { corridor } = data;
  const dir = corridor.directions[ctx.direction];
  const cells = corridor.cells[ctx.direction][ctx.dayType];
  const isToday = ctx.dayType === ctx.today;

  const window = bestWindow(ctx);
  const best = bestTrain(data, ctx.direction, ctx.dayType, window.hours);

  const hours = [...new Set(corridor.lines.flatMap((l) => Object.keys(cells[l]?.hours ?? {}).map(Number)))].sort((a, b) => a - b);
  const head = corridor.lines.map((l) => `<th scope="col"><span class="badge">${esc(l)}</span></th>`).join("");
  const rows = hours
    .map((h) => {
      const current = isToday && h === ctx.now.hour;
      const tds = corridor.lines
        .map((l) => {
          const f = cells[l]?.hours[String(h)];
          if (!f) return `<td class="empty" aria-label="운행 없음"></td>`;
          if (f.p6 === null) return `<td class="thin" ${detailAttrs(`${l} · ${h}시 출발`, f)} tabindex="0"><span>부족</span></td>`;
          return `<td ${detailAttrs(`${l} · ${h}시 출발`, f)} tabindex="0">${icon(f, data)}<span>${pct(f.p6)}</span></td>`;
        })
        .join("");
      return `<tr class="${current ? "now" : ""}"><th scope="row">${String(h).padStart(2, "0")}시</th>${tds}</tr>`;
    })
    .join("");

  return `
  <section class="hero compact">
    <p class="date">${isToday ? formatDate(ctx.now, data.meta) : `${DAYTYPE_LABEL[ctx.dayType]} 예보`}</p>
    <h1>출퇴근 예보</h1>
    <div class="toggle" role="group" aria-label="방향">
      <button data-direction="ffm_da" class="${ctx.direction === "ffm_da" ? "on" : ""}" aria-pressed="${ctx.direction === "ffm_da"}">Frankfurt → Darmstadt</button>
      <button data-direction="da_ffm" class="${ctx.direction === "da_ffm" ? "on" : ""}" aria-pressed="${ctx.direction === "da_ffm"}">Darmstadt → Frankfurt</button>
    </div>
  </section>

  ${dayChips(ctx)}

  <section class="card best">
    <h2>${window.label} 가장 맑은 열차</h2>
    ${best ? `<p class="best-line" ${detailAttrs(`${best.line} · ${best.hour}시 출발`, best.f)} tabindex="0">
        ${icon(best.f, data, "md")}
        <span><strong>${best.hour}시대 ${esc(best.line)}</strong><br>
        <small>${esc(dir.to)} 도착 지연 ${pct(best.f.p6)} · 취소 ${pct(best.f.pc, 1)} · ${sampleNote(best.f)}</small></span>
      </p>` : `<p>이 시간대에는 예보할 데이터가 부족해요.</p>`}
  </section>

  <section class="card">
    <h2>시간대 × 노선 <small>${esc(dir.from)} 출발 시각 기준</small></h2>
    <p class="note">${esc(dir.to)} <b>도착</b>이 6분 이상 늦을 확률. 칸을 누르면 자세히 볼 수 있어요.</p>
    <div class="grid-wrap">
      <table class="grid">
        <thead><tr><th scope="col"><span class="sr">출발</span></th>${head}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </section>`;
}

// ── About ───────────────────────────────────────────────────────────────

export function renderAbout(data: Data): string {
  const { meta } = data;
  const levels = [...meta.weather.levels]
    .reverse()
    .map((l, i, arr) => {
      const hi = arr[i + 1]?.min_p;
      const range = hi === undefined ? `${pct(l.min_p)} 이상` : `${pct(l.min_p)}–${pct(hi)}`;
      return `<li><span class="wx">${l.icon}</span> <b>${esc(l.label)}</b> ${range} — ${esc(l.text)}</li>`;
    })
    .join("");
  return `
  <section class="hero compact"><h1>Bahn-Wetter 소개</h1></section>
  <section class="card prose">
    <h2>이게 뭔가요?</h2>
    <p>Frankfurt (Main) Hbf와 Frankfurt ↔ Darmstadt 출퇴근 구간의 열차 지연 확률을 날씨 예보처럼 보여주는 비공식 재미용 서비스예요.</p>
    <p><b>${esc(DISCLAIMER)}.</b></p>

    <h2>날씨 읽는 법</h2>
    <ul class="legend">${levels}
      <li><span class="wx">${meta.weather.tornado.icon}</span> <b>${esc(meta.weather.tornado.label)}</b> 취소율 ${pct(meta.weather.tornado_cancel_rate)} 이상 — ${esc(meta.weather.tornado.text)}</li>
    </ul>
    <p>지연은 Deutsche Bahn 공식 기준과 같이 <b>6분 이상</b>이에요. 정차역은 도착 기준, 출발역은 출발 기준이고, 출퇴근 예보는 목적지 도착 기준이에요.</p>

    <h2>어떻게 계산하나요?</h2>
    <p>${meta.data_from} ~ ${meta.data_until} 실제 운행 기록을 역 × 노선 × 요일(평일/토/일·공휴일) × 시간대별로 모아 지연 비율을 구했어요.
       표본이 적은 칸은 상위 묶음(노선 전체, 역 전체)의 비율 쪽으로 당겨 보정하고(Beta-Binomial 축소), 최근 기록에 조금 더 무게를 줘요.
       표본이 ${meta.weather.min_samples}회 미만인 칸은 "데이터 부족"으로 표시해요.</p>
    <p>정확도는 시간 순서대로 나눈 백테스트로 확인했어요. 지난 달까지의 데이터로 다음 한 달을 예측했을 때, 역 평균이나 노선 평균만 쓰는 것보다 지연 예보가 더 잘 맞았어요. 취소는 파업·공사 영향이 커서 예측력이 거의 없어요.</p>

    <h2>데이터 출처</h2>
    <p>${esc(meta.attribution.text.split(",")[0])}, via <a href="${meta.attribution.source_url}" rel="noopener">piebro/deutsche-bahn-data</a>.
       라이선스: <a href="${meta.attribution.license_url}" rel="noopener">CC BY 4.0</a>.
       원본 운행 기록을 이 서비스에서 확률로 집계·가공했어요.</p>
    <p>이 사이트는 Deutsche Bahn과 관련 없는 비공식 서비스이며, Deutsche Bahn이 내용을 보증하지 않아요.</p>
    <h2>공유 카드</h2>
    <p>매일 아침 그날의 예보 카드(1080×1350)가 자동으로 만들어져요: <a href="cards/latest.png">오늘의 카드 PNG</a></p>
    <p class="note">데이터 기준일 ${meta.data_until} · 생성 ${meta.generated_at.slice(0, 10)} · 예보 표는 매달 3일에 갱신돼요</p>
  </section>`;
}

export function renderFooter(data: Data): string {
  const a = data.meta.attribution;
  return `<p>${esc(DISCLAIMER)}.</p>
    <p><a href="${a.source_url}" rel="noopener">${esc(a.text)}</a> · 확률로 가공됨 · <a href="${a.license_url}" rel="noopener">라이선스</a></p>
    <p>비공식 서비스 — Deutsche Bahn과 관련 없음 · 데이터 기준일 ${data.meta.data_until}</p>`;
}
