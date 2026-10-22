// 🏆 Ranking tab: train character dex on top, then observed results in the last 7 days of data.

import type { Data, RankedLine, RankedTrain } from "./data";
import { renderDex } from "./fun";
import { esc } from "./views";
import { pct } from "./weather";

const md = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${m}/${d}`;
};

const delayText = (min: number) => (min < 0 ? `평균 ${Math.abs(min)}분 일찍` : `평균 +${min}분`);

function trainRow(t: RankedTrain, data: Data, rank: number, worst: boolean): string {
  const dir = t.direction ? data.corridor.directions[t.direction] : null;
  const where = dir
    ? `${esc(dir.from.replace(" (Main)", ""))} ${t.time} 발 → ${esc(dir.to.replace(" (Main)", ""))}`
    : t.destination === data.ranking.station
      ? `${t.time} 도착 (종착)`
      : `${t.time} · ${esc(t.destination ?? "")}행`;
  const medal = worst ? ["💀", "⛈️", "🌧️", "☁️", "☁️"][rank] : ["🥇", "🥈", "🥉", "☀️", "☀️"][rank];
  return `<li class="rank-row">
    <span class="medal" aria-hidden="true">${medal}</span>
    <span class="who"><span class="badge">${esc(t.label)}</span><small>${where}</small></span>
    <span class="score"><b>${pct(t.p6)}</b><small>${delayText(t.mean_delay)} · ${t.runs}회${t.cancels ? ` · 취소 ${t.cancels}` : ""}</small></span>
  </li>`;
}

function lineRow(l: RankedLine, worst: boolean, i: number): string {
  const medal = worst ? ["💀", "⛈️", "🌧️"][i] : ["🥇", "🥈", "🥉"][i];
  return `<li class="rank-row">
    <span class="medal" aria-hidden="true">${medal}</span>
    <span class="who"><span class="badge">${esc(l.line)}</span><small>${l.runs}회 운행 · 취소 ${pct(l.cancel_rate, 1)}</small></span>
    <span class="score"><b>${pct(l.p6)}</b><small>${delayText(l.mean_delay)}</small></span>
  </li>`;
}

export function renderRanking(data: Data, dexLine: string): string {
  const r = data.ranking;
  const big = r.hub.biggest;
  const h = Math.floor(big.delay / 60);
  const bigText = h ? `${h}시간 ${big.delay % 60}분` : `${big.delay}분`;
  return `
  ${renderDex(data, dexLine)}

  <section class="week-head">
    <h2>🏆 주간 기록</h2>
    <p>${md(r.window.from)} – ${md(r.window.to)} · 데이터 마지막 7일 동안 실제로 얼마나 늦었는지</p>
  </section>

  <section class="card biggest">
    <h2>이 기간 최대 지연</h2>
    <p><span class="badge">${esc(big.label)}</span> ${md(big.date)} ${big.time} · ${esc(big.destination)}행</p>
    <p class="big-delay">+${bigText}</p>
  </section>

  <section class="card">
    <h2>출퇴근 구간 최악의 열차 <small>Frankfurt ↔ Darmstadt 도착 기준</small></h2>
    <ol class="ranks">${r.corridor.trains_worst.map((t, i) => trainRow(t, data, i, true)).join("")}</ol>
  </section>
  <section class="card">
    <h2>출퇴근 구간 가장 성실한 열차 <small>취소 없이 5회 이상</small></h2>
    <ol class="ranks">${r.corridor.trains_best.map((t, i) => trainRow(t, data, i, false)).join("")}</ol>
  </section>

  <section class="card">
    <h2>${esc(r.station)} 최악의 열차</h2>
    <ol class="ranks">${r.hub.trains_worst.map((t, i) => trainRow(t, data, i, true)).join("")}</ol>
  </section>
  <section class="card">
    <h2>${esc(r.station)} 가장 성실한 열차 <small>취소 없이 5회 이상</small></h2>
    <ol class="ranks">${r.hub.trains_best.map((t, i) => trainRow(t, data, i, false)).join("")}</ol>
  </section>

  <section class="card">
    <h2>노선 랭킹 <small>${esc(r.station)}, 50회 이상 운행</small></h2>
    <p class="sub">가장 흐린 노선</p>
    <ol class="ranks">${r.hub.lines_worst.map((l, i) => lineRow(l, true, i)).join("")}</ol>
    <p class="sub">가장 맑은 노선</p>
    <ol class="ranks">${r.hub.lines_best.map((l, i) => lineRow(l, false, i)).join("")}</ol>
  </section>`;
}
