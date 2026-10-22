// 📸 Share card (1080×1350 when captured at 2× from a 540×675 layout). Route: #/card?date=YYYY-MM-DD

import type { Data } from "./data";
import { DAYTYPE_LABEL, formatDate } from "./time";
import { bestTrain, DISCLAIMER, esc, type Ctx } from "./views";
import { pct, weatherOf } from "./weather";

const HOURS = [6, 8, 10, 12, 14, 16, 18, 20, 22];

/** One fun line from the weekly ranking: the biggest single delay in the last 7 days of data. */
function weekly(data: Data): string {
  const big = data.ranking.hub.biggest;
  const h = Math.floor(big.delay / 60);
  const text = h ? `${h}시간 ${big.delay % 60}분` : `${big.delay}분`;
  const md = (iso: string) => iso.split("-").slice(1).map(Number).join("/");
  const w = data.ranking.window;
  return `<p class="weekly">📉 ${md(w.from)}–${md(w.to)} 최대 지연 <b>${esc(big.label)} +${text}</b> <small>(${md(big.date)} ${big.time} · ${esc(big.destination)}행)</small></p>`;
}

export function cardSky(data: Data, ctx: Ctx): string {
  return weatherOf(data.hub.daytypes[ctx.dayType].overall, data.meta).name;
}

export function renderCard(data: Data, ctx: Ctx): string {
  const { meta, hub, corridor } = data;
  const day = hub.daytypes[ctx.dayType];
  const f = day.overall;
  const w = weatherOf(f, meta);
  const am = bestTrain(data, "ffm_da", ctx.dayType, [6, 7, 8, 9]);
  const pm = bestTrain(data, "da_ffm", ctx.dayType, [16, 17, 18, 19]);
  const short = (s: string) => s.replace(" (Main)", "").replace(" Hbf", "");

  const strip = HOURS.map((h) => {
    const hf = day.hours[String(h)];
    const hw = weatherOf(hf, meta);
    return `<li><span>${h}시</span><b>${hw.icon}</b><span>${pct(hf?.p6)}</span></li>`;
  }).join("");

  const pick = (label: string, dir: "ffm_da" | "da_ffm", b: ReturnType<typeof bestTrain>) => {
    const d = corridor.directions[dir];
    if (!b) return "";
    return `<div class="pick"><p class="pick-label">${label}</p>
      <p class="pick-main">${weatherOf(b.f, meta).icon} <b>${b.hour}시대 ${esc(b.line)}</b></p>
      <p class="pick-sub">${esc(short(d.from))} → ${esc(short(d.to))} · 지연 ${pct(b.f.p6)}</p></div>`;
  };

  return `<article class="share-card" data-sky="${w.name}">
    <header>
      <p class="kicker">🌦️ 오늘의 Bahn-Wetter 예보</p>
      <p class="when">${formatDate(ctx.now, meta)} · ${DAYTYPE_LABEL[ctx.dayType]}</p>
    </header>
    <section class="main">
      <p class="station">${esc(meta.stations[hub.station])}</p>
      <div class="icon">${w.icon}</div>
      <p class="pct">${pct(f.p6)}</p>
      <p class="cond">지연 확률 · ${esc(w.label)} — ${esc(w.text)}</p>
    </section>
    <ol class="hours">${strip}</ol>
    <section class="picks">
      ${pick("출근길 가장 맑은 열차", "ffm_da", am)}
      ${pick("퇴근길 가장 맑은 열차", "da_ffm", pm)}
    </section>
    ${weekly(data)}
    <footer>
      <p>${esc(DISCLAIMER)}. 6분 이상 지연 기준.</p>
      <p>${esc(meta.attribution.text)} · 확률로 가공됨 · 비공식 서비스</p>
    </footer>
  </article>`;
}
