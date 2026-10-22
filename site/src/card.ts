// 📸 Share card: today's fortune slip (1080×1350 when captured at 2× from 540×675). Route: #/card?date=YYYY-MM-DD

import type { Data, Forecast } from "./data";
import { DAYTYPE_LABEL, formatDate } from "./time";
import { bestTrain, DISCLAIMER, esc, type Ctx } from "./views";
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
  const am = bestTrain(data, "ffm_da", ctx.dayType, [6, 7, 8, 9]);
  const pm = bestTrain(data, "da_ffm", ctx.dayType, [16, 17, 18, 19]);
  const hours = Object.entries(day.hours).map(([h, f]) => ({ h: Number(h), f })).filter(({ h, f }) => h >= 6 && f.p6 !== null);
  const lucky = hours.reduce((m, x) => (x.f.p6! < m.f.p6! ? x : m));
  const careful = hours.reduce((m, x) => (x.f.p6! > m.f.p6! ? x : m));
  const grade = (f: Forecast) => weatherOf(f, meta);

  const main = am ? grade(am.f) : null;
  const tile = (label: string, g: ReturnType<typeof grade>, line: string, sub: string) =>
    `<div class="c-tile"><small>${label}</small><p><span class="g-word g-${g.name}">${esc(g.fortune ?? g.label)}</span> ${line}</p><span>${sub}</span></div>`;

  return `<article class="share-card fortune-card">
    <header><p class="kicker">BAHN-WETTER</p><p class="when">${formatDate(ctx.now, meta)} · ${DAYTYPE_LABEL[ctx.dayType]}</p></header>
    <h1>🔮 오늘의 출근 운세</h1>
    ${am && main ? `<div class="c-slip">
      <div class="c-grade"><div class="stamp g-${main.name}">${esc(main.fortune ?? main.label)}</div>
        <div><b>${am.hour}시대 ${esc(am.line)} 타는 당신</b><span>Frankfurt → Darmstadt · 늦을 확률 ${pct(am.f.p6)}</span></div></div>
      <p class="c-msg">${esc(main.fortune_text ?? main.text)}</p>
      <div class="c-lucky"><div>🍀 행운의 시간 <b>${lucky.h}시</b></div><div>⚠️ 조심할 시간 <b>${careful.h}시</b></div></div>
    </div>` : ""}
    ${am ? `<div class="c-others">${data.corridor.lines
      .filter((l) => l !== am.line)
      .map((l) => ({ l, f: data.corridor.cells.ffm_da[ctx.dayType][l]?.hours[String(am.hour)] }))
      .filter((o): o is { l: string; f: Forecast } => !!o.f && o.f.p6 !== null)
      .slice(0, 3)
      .map(({ l, f }) => `<div>${esc(l)} <b class="g-${grade(f).name}">${esc(grade(f).fortune ?? "")}</b></div>`)
      .join("")}</div>` : ""}
    <div class="c-tiles">
      ${pm ? tile("퇴근길 Darmstadt → Frankfurt", grade(pm.f), `${pm.hour}시대 ${esc(pm.line)}`, `늦을 확률 ${pct(pm.f.p6)}`) : ""}
      ${tile("Frankfurt Hbf 오늘의 총운", grade(day.overall), "", `열차 ${freqText(day.overall.p6 ?? 0)}가 늦어요`)}
    </div>
    ${weekly(data)}
    <footer>
      <p>${esc(DISCLAIMER)}. 6분 이상 지연 기준.</p>
      <p>${esc(meta.attribution.text)} · 확률로 가공됨 · 비공식 서비스</p>
    </footer>
  </article>`;
}
