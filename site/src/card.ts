// 📸 Share card: today's fortune slip (1080×1350 when captured at 2× from 540×675). Route: #/card?date=YYYY-MM-DD

import type { Data, Forecast } from "./data";
import { DAYTYPE_LABEL, formatDate } from "./time";
import { bestTrain, directionOverall, dirText, DISCLAIMER, esc, luckyHours, type Ctx } from "./views";
import { freqText, pct, weatherOf } from "./weather";

/** One fun line from the weekly ranking: the biggest single delay in the last 7 days of data. */
function weekly(data: Data): string {
  const big = data.ranking.hub.biggest;
  const h = Math.floor(big.delay / 60);
  const text = h ? `${h}시간 ${big.delay % 60}분` : `${big.delay}분`;
  const md = (iso: string) => iso.split("-").slice(1).map(Number).join("/");
  const w = data.ranking.window;
  return `<p class="weekly">📉 ${md(w.from)}–${md(w.to)} 최대 지연 <b>${esc(big.label)} +${text}</b></p>`;
}

export function cardSky(): string {
  return "fortune";
}

export function renderCard(data: Data, ctx: Ctx): string {
  const { meta, hub } = data;
  const day = hub.daytypes[ctx.dayType];
  const main_route = data.corridor.routes[0]; // the card's commute: first route in config
  const am = bestTrain(data, main_route.out, ctx.dayType, [6, 7, 8, 9]);
  const pm = bestTrain(data, main_route.in, ctx.dayType, [16, 17, 18, 19]);
  const luck = luckyHours(data, main_route.out, ctx.dayType, [6, 7, 8, 9]);
  const grade = (f: Forecast) => weatherOf(f, meta);

  const main = am ? grade(am.f) : null;
  const tile = (label: string, g: ReturnType<typeof grade>, line: string, sub: string) =>
    `<div class="c-tile"><small>${label}</small><p><span class="g-word g-${g.name}">${esc(g.fortune ?? g.label)}</span> ${line}</p><span>${sub}</span></div>`;

  return `<article class="share-card fortune-card">
    <header><p class="kicker">BAHN-WETTER</p><p class="when">${formatDate(ctx.now, meta)} · ${DAYTYPE_LABEL[ctx.dayType]}</p></header>
    <h1>🔮 오늘의 출근 운세</h1>
    ${am && main ? `<div class="c-slip">
      <div class="c-grade"><div class="stamp g-${main.name}">${esc(main.fortune ?? main.label)}</div>
        <div><b>${am.hour}시대 ${esc(am.line)} 타는 당신</b><span>${esc(dirText(data, main_route.out))} · 늦을 확률 ${pct(am.f.p6)}</span></div></div>
      <p class="c-msg">${esc(main.fortune_text ?? main.text)}</p>
      ${luck ? `<div class="c-lucky"><div>🍀 행운의 시간 <b>${luck.lucky.h}시</b></div><div>⚠️ 조심할 시간 <b>${luck.careful.h}시</b></div></div>` : ""}
    </div>` : ""}
    <p class="c-routes-title">오늘의 노선 운세 <small>Frankfurt 출발 · 하루 평균</small></p>
    <div class="c-routes">${data.corridor.routes
      .map((r) => ({ r, f: directionOverall(data, r.out, ctx.dayType) }))
      .filter((o): o is { r: typeof o.r; f: Forecast } => !!o.f)
      .map(({ r, f }) => `<div><span>${esc(r.label)}</span><b class="g-${grade(f).name}">${esc(grade(f).fortune ?? "")}</b></div>`)
      .join("")}</div>
    <div class="c-tiles">
      ${pm ? tile(`퇴근길 ${esc(dirText(data, main_route.in))}`, grade(pm.f), `${pm.hour}시대 ${esc(pm.line)}`, `늦을 확률 ${pct(pm.f.p6)}`) : ""}
      ${tile("Frankfurt Hbf 오늘의 총운", grade(day.overall), "", `열차 ${freqText(day.overall.p6 ?? 0)}가 늦어요`)}
    </div>
    ${weekly(data)}
    <footer>
      <p>${esc(DISCLAIMER)}. 6분 이상 지연 기준.</p>
      <p>${esc(meta.attribution.text)} · 확률로 가공됨 · 비공식 서비스</p>
    </footer>
  </article>`;
}
