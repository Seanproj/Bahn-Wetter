// Playful views built on observed numbers: train characters (랭킹) and the delay gacha (detail sheet).

import type { Data, Direction, Forecast } from "./data";
import { esc } from "./views";
import { pct } from "./weather";

type Profile = Data["corridor"]["characters"][string];

// ── Character cards ─────────────────────────────────────────────────────

interface Persona {
  emoji: string;
  name: string;
  quote: string;
  color: string;
}

/** Persona from the line's own record, compared with the other corridor lines. First rule that fits wins. */
export function persona(line: string, data: Data): Persona {
  const all = Object.values(data.corridor.characters);
  const s = data.corridor.characters[line];
  const max = (k: keyof Profile) => Math.max(...all.map((x) => x[k]));
  const min = (k: keyof Profile) => Math.min(...all.map((x) => x[k]));
  if (s.cancel === max("cancel") && s.cancel >= 0.05)
    return { emoji: "👻", name: "잠수왕", quote: `${Math.round(1 / s.cancel)}번 중 1번은 홀연히 사라져요`, color: "var(--dex-ghost)" };
  if (s.p6 === max("p6"))
    return { emoji: "🦥", name: "지각대장", quote: `${Math.round(1 / s.p6)}번 중 1번은 6분 넘게 늦어요. 그래도 결국 와요`, color: "var(--dex-sloth)" };
  if (s.p6 === min("p6"))
    return { emoji: "🐕", name: "성실한 모범생", quote: `95%는 ${s.p95}분 안에 도착. 믿고 타는 열차`, color: "var(--dex-dog)" };
  if (s.early >= 0.04)
    return { emoji: "🐇", name: "성격 급한 토끼", quote: `${Math.round(1 / s.early)}번 중 1번은 일찍 와 있어요`, color: "var(--dex-rabbit)" };
  return { emoji: "🐢", name: "느긋한 거북이", quote: `평균 ${s.mean}분 늦어요. 서두르지 않는 타입`, color: "var(--dex-turtle)" };
}

function statBar(label: string, value: number, max: number, text: string): string {
  return `<div class="stat"><span>${label}</span><span class="sbar"><i style="width:${Math.min(100, Math.round((value / max) * 100))}%"></i></span><span>${text}</span></div>`;
}

export function characterCard(line: string, data: Data): string {
  const s = data.corridor.characters[line];
  const p = persona(line, data);
  return `<article class="dex-card" style="--c:${p.color}">
    <div class="dex-head"><div class="ava" aria-hidden="true">${p.emoji}</div>
      <div><small>${esc(line)}</small><b>${p.name}</b><i>Frankfurt ↔ Darmstadt · ${s.n.toLocaleString("ko-KR")}회 관찰</i></div></div>
    <div class="stats-rpg">
      ${statBar("성실함", 1 - s.p6, 1, pct(1 - s.p6))}
      ${statBar("느긋함", s.mean, 8, `평균 ${s.mean}분`)}
      ${statBar("잠수력", s.cancel, 0.12, `취소 ${pct(s.cancel)}`)}
      ${statBar("폭주력", s.p30, 0.06, `30분↑ ${pct(s.p30)}`)}
    </div>
    <p class="quote">💬 ${p.quote}</p>
    <p class="dex-foot">최악의 기록 +${s.max}분 · 6분↑ ${pct(s.p6)}</p>
  </article>`;
}

/** Character dex: one large card for the selected line, small tiles for the others. */
export function renderDex(data: Data, selected: string): string {
  const lines = data.corridor.lines.filter((l) => data.corridor.characters[l]);
  const sel = lines.includes(selected) ? selected : lines[0];
  return `<section class="dex">
    <h1>🚆 열차 캐릭터 도감</h1>
    <p class="sub">Frankfurt ↔ Darmstadt를 달리는 열차들의 성격 · 실제 기록 ${esc(data.meta.data_from)} ~ ${esc(data.meta.data_until)}</p>
    <div class="dex-tabs" role="tablist">${lines.map((l) => `<button role="tab" data-line="${esc(l)}" aria-selected="${l === sel}" class="${l === sel ? "on" : ""}">${esc(l)}</button>`).join("")}</div>
    ${characterCard(sel, data)}
    <div class="dex-mini">${lines
      .filter((l) => l !== sel)
      .map((l) => {
        const p = persona(l, data);
        return `<button class="m" data-line="${esc(l)}" style="--c:${p.color}"><span aria-hidden="true">${p.emoji}</span><b>${esc(l)}</b><small>${p.name}</small></button>`;
      })
      .join("")}</div>
  </section>`;
}

// ── Delay gacha + "100번 타면" ──────────────────────────────────────────

type Bucket = "on" | "bit" | "late" | "big" | "gone";
const BUCKETS: { key: Bucket; label: string; lo: number; hi: number }[] = [
  { key: "on", label: "정시 (0–1분)", lo: -Infinity, hi: 2 },
  { key: "bit", label: "살짝 (2–5분)", lo: 2, hi: 6 },
  { key: "late", label: "지각 (6–14분)", lo: 6, hi: 15 },
  { key: "big", label: "대지각 (15분↑)", lo: 15, hi: Infinity },
  { key: "gone", label: "취소", lo: NaN, hi: NaN },
];

/**
 * Bucket shares for one cell. The cell's own probabilities fix "≥6", "≥15" and "canceled"; the split
 * below 6 minutes (0–1 vs 2–5) comes from the line's delay quantiles.
 */
function shares(f: Forecast, q: number[] | undefined): Record<Bucket, number> {
  const pc = f.pc ?? 0;
  const p6 = f.p6 ?? 0;
  const p15 = f.p15 ?? 0;
  const below6 = q ? q.filter((x) => x < 6) : [];
  const onShare = below6.length ? below6.filter((x) => x < 2).length / below6.length : 0.55;
  const ran = 1 - pc;
  return { on: ran * (1 - p6) * onShare, bit: ran * (1 - p6) * (1 - onShare), late: ran * (p6 - p15), big: ran * p15, gone: pc };
}

/** 100 cells by largest remainder, so the grid always adds up to exactly 100 rides. */
function hundred(sh: Record<Bucket, number>): Bucket[] {
  const keys = BUCKETS.map((b) => b.key);
  const raw = keys.map((k) => sh[k] * 100);
  const n = raw.map(Math.floor);
  let left = 100 - n.reduce((a, b) => a + b, 0);
  raw.map((r, i) => [r - Math.floor(r), i] as const).sort((a, b) => b[0] - a[0]).forEach(([, i]) => left-- > 0 && n[i]++);
  return keys.flatMap((k, i) => Array<Bucket>(n[i]).fill(k));
}

export function gachaBlock(data: Data, f: Forecast, trip?: { line: string; direction: Direction }): string {
  if (f.p6 === null) return "";
  const q = trip ? data.corridor.dist[trip.direction]?.[trip.line] : undefined;
  const sh = shares(f, q);
  const cells = hundred(sh);
  const count = (k: Bucket) => cells.filter((c) => c === k).length;
  const lateN = count("late") + count("big");
  const spin = trip && q
    ? `<div class="gacha" data-shares='${esc(JSON.stringify(sh))}' data-q='${esc(JSON.stringify(q))}'>
        <p class="g-result" aria-live="polite"><span class="g-num">?</span><span class="g-verdict">오늘 이 열차, 몇 분 늦을까?</span></p>
        <button type="button" class="g-btn" data-spin>🎲 한 번 타보기</button>
      </div>`
    : "";
  return `${spin}
    <div class="hund">
      <p><b>100번 타면?</b> ${lateN}번은 6분 넘게 늦고${count("gone") ? `, ${count("gone")}번은 사라져요` : "요"}</p>
      <div class="hgrid" role="img" aria-label="100번 중 정시 ${count("on")}, 살짝 ${count("bit")}, 지각 ${count("late")}, 대지각 ${count("big")}, 취소 ${count("gone")}">${cells.map((c) => `<i class="${c}"></i>`).join("")}</div>
      <p class="hlegend">${BUCKETS.map((b) => `<span><i class="${b.key}"></i>${b.label}</span>`).join("")}</p>
    </div>`;
}

const VERDICT: Record<Bucket, string> = {
  on: "🎉 정시 도착!",
  bit: "😌 살짝 늦었어요",
  late: "🐌 지각 확정",
  big: "💀 대형 지각",
  gone: "👻 열차가 사라졌어요",
};

/** One random ride: pick a bucket by the cell's shares, then a real minute value from the quantiles inside it. */
export function spin(el: HTMLElement): void {
  const sh = JSON.parse(el.dataset.shares!) as Record<Bucket, number>;
  const q = JSON.parse(el.dataset.q!) as number[];
  let u = Math.random();
  const bucket = BUCKETS.find((b) => (u -= sh[b.key]) < 0)?.key ?? "on";
  const num = el.querySelector<HTMLElement>(".g-num")!;
  const verdict = el.querySelector<HTMLElement>(".g-verdict")!;
  if (bucket === "gone") {
    num.textContent = "취소";
  } else {
    const b = BUCKETS.find((x) => x.key === bucket)!;
    const inside = q.filter((x) => x >= b.lo && x < b.hi);
    const minutes = inside.length ? inside[Math.floor(Math.random() * inside.length)] : Math.max(0, b.lo);
    num.textContent = minutes <= 0 ? "정시" : `+${minutes}분`;
  }
  verdict.textContent = VERDICT[bucket];
  el.dataset.bucket = bucket;
  el.classList.remove("pop");
  void el.offsetWidth; // restart the pop animation
  el.classList.add("pop");
}
