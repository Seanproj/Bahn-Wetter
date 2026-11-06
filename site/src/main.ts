import "./style.css";
import { loadData, loadLive, type Data, type DayType, type Direction, type Forecast } from "./data";
import { cardSky, renderCard } from "./card";
import { gachaBlock, spin } from "./fun";
import { renderRanking } from "./ranking";
import { berlinDay, berlinNow, dayTypeOf } from "./time";
import { commuteSky, conditionalTable, esc, homeSky, renderAbout, renderCommute, renderFooter, renderHome, type Ctx } from "./views";
import { pct, sampleNote, weatherOf } from "./weather";
import { bannerHtml, copyText, detectEnv, dismiss, hintHtml, registerServiceWorker } from "./install";

type Route = "home" | "commute" | "ranking" | "about" | "card";
const ROUTES: Route[] = ["home", "commute", "ranking", "about", "card"];

const app = document.querySelector<HTMLElement>("#app")!;
const footer = document.querySelector<HTMLElement>("#footer")!;
const sheet = document.querySelector<HTMLDialogElement>("#sheet")!;
const toast = document.querySelector<HTMLElement>("#toast")!;
const banner = document.querySelector<HTMLElement>("#banner")!;
const hint = document.querySelector<HTMLElement>("#hint")!;
const env = detectEnv();
let installPrompt: (Event & { prompt: () => Promise<void> }) | null = null;

function showToast(text: string) {
  toast.textContent = text;
  toast.classList.add("on");
  setTimeout(() => toast.classList.remove("on"), 2200);
}

const siteUrl = () => location.href.split("#")[0];

/**
 * Native share sheet where it works; otherwise copy text + link. In-app browsers often expose
 * navigator.share but fail, so a failure falls through to copying, and copying to a manual-copy sheet.
 */
async function share(text: string) {
  const url = siteUrl();
  if (navigator.share && !env.inApp) {
    try {
      return await navigator.share({ title: "Bahn-Wetter", text, url });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
    }
  }
  if (await copyText(`${text}\n${url}`)) return showToast("복사했어요! 붙여넣기로 공유하세요");
  sheet.innerHTML = `<form method="dialog"><p class="sheet-title">아래 내용을 길게 눌러 복사하세요</p>
    <textarea class="copy-box" readonly rows="5">${esc(`${text}\n${url}`)}</textarea><button class="close">닫기</button></form>`;
  sheet.showModal();
}

function store<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) ?? fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: ignore */
  }
}

let data: Data;
let liveFetchedAt = 0;
let dayType: DayType | null = null; // null = today
let direction: Direction = store<Direction>("direction", "");
let dexLine = store<string>("dexLine", "");

/** "#/card?date=2026-10-23" → { route: "card", params } */
function parseHash(): { route: Route; params: URLSearchParams } {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const route = (ROUTES as string[]).includes(path) ? (path as Route) : "home";
  return { route, params: new URLSearchParams(query) };
}

function render() {
  const { route: r, params } = parseHash();
  const now = berlinNow(); // per render, so a tab left open across hours or midnight stays correct
  // The share card can be rendered for any day (cards/make_card.py passes ?date=).
  const at = r === "card" ? (berlinDay(params.get("date") ?? "") ?? now) : now;
  const today = dayTypeOf(at, data.meta);
  const ctx: Ctx = { now: at, today, dayType: r === "card" ? today : (dayType ?? today), direction };
  document.body.classList.toggle("card-mode", r === "card");
  const view = {
    home: () => [renderHome(data, ctx), homeSky()],
    commute: () => [renderCommute(data, ctx), commuteSky(data, ctx)],
    ranking: () => [renderRanking(data, dexLine), "dex"],
    about: () => [renderAbout(data), "about"],
    card: () => [renderCard(data, ctx), cardSky()],
  }[r];
  const [html, sky] = view();
  app.innerHTML = html;
  banner.innerHTML = r === "card" ? "" : bannerHtml(env);
  hint.innerHTML = r === "home" ? hintHtml(env, installPrompt !== null) : "";
  document.body.dataset.sky = sky;
  document.querySelectorAll<HTMLAnchorElement>("nav.tabs a").forEach((a) => {
    a.setAttribute("aria-current", a.dataset.route === r ? "page" : "false");
  });
  // Bring the current hour into view in the strip / grid.
  app.querySelector<HTMLElement>(".hour.now")?.scrollIntoView({ inline: "center", block: "nearest" });
  const nowRow = app.querySelector<HTMLElement>("tr.now");
  const wrap = app.querySelector<HTMLElement>(".grid-wrap");
  if (nowRow && wrap) wrap.scrollTop = nowRow.offsetTop - wrap.clientHeight / 3;
}

function openDetail(title: string, f: Forecast, trip?: { line: string; direction: Direction }) {
  const w = weatherOf(f, data.meta);
  sheet.innerHTML = `<form method="dialog">
    <p class="sheet-title">${esc(title)}</p>
    <div class="sheet-main"><span class="wx lg">${w.icon}</span>
      <div><strong>${pct(f.p6)}</strong> 지연 확률<br><small>${esc(w.label)} — ${esc(w.text)}</small></div></div>
    <dl class="stats">
      <div><dt>15분↑</dt><dd>${pct(f.p15)}</dd></div>
      <div><dt>30분↑</dt><dd>${pct(f.p30)}</dd></div>
      <div><dt>취소</dt><dd>${pct(f.pc, 1)}</dd></div>
    </dl>
    <p class="note">${sampleNote(f)}${f.p6 === null ? ` · 표본이 ${data.meta.weather.min_samples}회 미만이라 확률을 숨겼어요` : ""}</p>
    ${gachaBlock(data, f, trip)}
    ${trip ? conditionalTable(data, trip) : ""}
    <button class="close">닫기</button>
  </form>`;
  sheet.showModal();
}

app.addEventListener("click", (e) => {
  const t = e.target as HTMLElement;
  const shareBtn = t.closest<HTMLElement>("[data-share]");
  if (shareBtn) return void share(shareBtn.dataset.share!);
  const chip = t.closest<HTMLElement>("[data-daytype]");
  if (chip) {
    const d = chip.dataset.daytype as DayType;
    dayType = d === dayTypeOf(berlinNow(), data.meta) ? null : d;
    return render();
  }
  const routeChip = t.closest<HTMLElement>("[data-route]");
  if (routeChip) {
    // Switch route, keep the travel direction (towards or away from Frankfurt).
    const r = data.corridor.routes.find((x) => x.code === routeChip.dataset.route)!;
    const inbound = data.corridor.routes.some((x) => x.in === direction);
    direction = inbound ? r.in : r.out;
    save("direction", direction);
    return render();
  }
  const dir = t.closest<HTMLElement>("[data-direction]");
  if (dir) {
    direction = dir.dataset.direction as Direction;
    save("direction", direction);
    return render();
  }
  const line = t.closest<HTMLElement>("[data-line]");
  if (line) {
    dexLine = line.dataset.line!;
    save("dexLine", dexLine);
    render();
    app.querySelector(".dex-card")?.scrollIntoView({ block: "nearest" });
    return;
  }
  const detail = t.closest<HTMLElement>("[data-detail]");
  if (detail) {
    const { title, f, trip } = JSON.parse(detail.dataset.detail!);
    openDetail(title, f, trip);
  }
});
app.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && (e.target as HTMLElement).dataset.detail) {
    e.preventDefault();
    (e.target as HTMLElement).click();
  }
});
sheet.addEventListener("click", (e) => {
  const spinBtn = (e.target as HTMLElement).closest("[data-spin]");
  if (spinBtn) {
    e.preventDefault();
    spin(spinBtn.closest<HTMLElement>(".gacha")!);
    spinBtn.textContent = "🎲 한 번 더 타기";
    return;
  }
  if (e.target === sheet) sheet.close(); // tap on backdrop
});
// Banner / home-screen hint buttons (outside #app).
document.addEventListener("click", async (e) => {
  const t = e.target as HTMLElement;
  const close = t.closest<HTMLElement>("[data-dismiss]");
  if (close) {
    dismiss(close.dataset.dismiss!);
    close.closest(".banner, .hint")?.remove();
  } else if (t.closest("[data-copy-link]")) {
    showToast((await copyText(siteUrl())) ? "링크를 복사했어요. 브라우저 주소창에 붙여넣으세요" : siteUrl());
  } else if (t.closest("[data-install]") && installPrompt) {
    await installPrompt.prompt();
    installPrompt = null;
    hint.innerHTML = "";
  }
});
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault(); // show our own button on the home tab instead of the browser's mini-bar
  installPrompt = e as typeof installPrompt;
  if (data && parseHash().route === "home") hint.innerHTML = hintHtml(env, true);
});
window.addEventListener("appinstalled", () => {
  installPrompt = null;
  hint.innerHTML = "";
});
registerServiceWorker();

window.addEventListener("hashchange", () => {
  render();
  window.scrollTo(0, 0);
});

/** Live data is optional: render first, then add it if a fresh snapshot exists (not on the card). */
function refreshLive() {
  liveFetchedAt = Date.now();
  loadLive(data.meta).then((live) => {
    const had = data.live !== null;
    data.live = live; // null drops a snapshot that went stale while the tab was open
    if ((live || had) && parseHash().route !== "card") render();
  });
}

// Coming back to a tab left open: re-render for the current hour and fetch a newer live snapshot.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || !data || sheet.open) return;
  if (Date.now() - liveFetchedAt > 5 * 60_000) refreshLive();
  else render();
});

loadData()
  .then((d) => {
    data = d;
    if (!d.corridor.directions[direction]) direction = d.corridor.routes[0].out; // first visit or a removed route
    footer.innerHTML = renderFooter(d);
    render();
    refreshLive();
  })
  .catch((err) => {
    app.innerHTML = `<section class="card"><h2>예보를 불러오지 못했어요</h2><p class="note">${String(err)}</p></section>`;
  });
