import "./style.css";
import { loadData, type Data, type DayType, type Direction, type Forecast } from "./data";
import { berlinNow, dayTypeOf } from "./time";
import { commuteSky, esc, homeSky, renderAbout, renderCommute, renderFooter, renderHome, type Ctx } from "./views";
import { pct, sampleNote, weatherOf } from "./weather";

type Route = "home" | "commute" | "about";

const app = document.querySelector<HTMLElement>("#app")!;
const footer = document.querySelector<HTMLElement>("#footer")!;
const sheet = document.querySelector<HTMLDialogElement>("#sheet")!;

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
const now = berlinNow();
let dayType: DayType | null = null; // null = today
let direction: Direction = store<Direction>("direction", "ffm_da");

function route(): Route {
  const r = location.hash.replace(/^#\/?/, "");
  return r === "commute" || r === "about" ? r : "home";
}

function render() {
  const today = dayTypeOf(now, data.meta);
  const ctx: Ctx = { now, today, dayType: dayType ?? today, direction };
  const r = route();
  app.innerHTML = r === "commute" ? renderCommute(data, ctx) : r === "about" ? renderAbout(data) : renderHome(data, ctx);
  document.body.dataset.sky = r === "commute" ? commuteSky(data, ctx) : r === "about" ? "about" : homeSky(data, ctx);
  document.querySelectorAll<HTMLAnchorElement>("nav.tabs a").forEach((a) => {
    a.setAttribute("aria-current", a.dataset.route === r ? "page" : "false");
  });
  // Bring the current hour into view in the strip / grid.
  app.querySelector<HTMLElement>(".hour.now")?.scrollIntoView({ inline: "center", block: "nearest" });
  const nowRow = app.querySelector<HTMLElement>("tr.now");
  const wrap = app.querySelector<HTMLElement>(".grid-wrap");
  if (nowRow && wrap) wrap.scrollTop = nowRow.offsetTop - wrap.clientHeight / 3;
}

function openDetail(title: string, f: Forecast) {
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
    <button class="close">닫기</button>
  </form>`;
  sheet.showModal();
}

app.addEventListener("click", (e) => {
  const t = e.target as HTMLElement;
  const chip = t.closest<HTMLElement>("[data-daytype]");
  if (chip) {
    const d = chip.dataset.daytype as DayType;
    dayType = d === dayTypeOf(now, data.meta) ? null : d;
    return render();
  }
  const dir = t.closest<HTMLElement>("[data-direction]");
  if (dir) {
    direction = dir.dataset.direction as Direction;
    save("direction", direction);
    return render();
  }
  const detail = t.closest<HTMLElement>("[data-detail]");
  if (detail) {
    const { title, f } = JSON.parse(detail.dataset.detail!);
    openDetail(title, f);
  }
});
app.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && (e.target as HTMLElement).dataset.detail) {
    e.preventDefault();
    (e.target as HTMLElement).click();
  }
});
sheet.addEventListener("click", (e) => {
  if (e.target === sheet) sheet.close(); // tap on backdrop
});
window.addEventListener("hashchange", () => {
  render();
  window.scrollTo(0, 0);
});

loadData()
  .then((d) => {
    data = d;
    footer.innerHTML = renderFooter(d);
    render();
  })
  .catch((err) => {
    app.innerHTML = `<section class="card"><h2>예보를 불러오지 못했어요</h2><p class="note">${String(err)}</p></section>`;
  });
