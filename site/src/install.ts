// Using the site outside an app store: in-app browsers (Threads, Instagram, KakaoTalk, …), adding it to the
// home screen, offline support and a copy fallback for sharing.

export interface Env {
  inApp: string | null; // name of the app whose built-in browser shows the page
  ios: boolean;
  android: boolean;
  standalone: boolean; // opened from the home screen
}

// Best effort: an unknown in-app browser simply gets no banner.
const IN_APP: [string, RegExp][] = [
  ["Threads", /Barcelona/i],
  ["Instagram", /Instagram/i],
  ["Facebook", /FBAN|FBAV|FB_IAB/],
  ["KakaoTalk", /KAKAOTALK/i],
  ["LINE", /\bLine\//],
  ["NAVER", /NAVER\(inapp/i],
];

export function detectEnv(ua = navigator.userAgent): Env {
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  return {
    inApp: IN_APP.find(([, re]) => re.test(ua))?.[0] ?? null,
    ios,
    android: /Android/.test(ua),
    standalone: matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true,
  };
}

function dismissed(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function dismiss(key: string): void {
  try {
    localStorage.setItem(key, "1");
  } catch {
    /* private mode: hidden until reload */
  }
}

/** Banner for in-app browsers: they cannot add to the home screen and often block sharing. */
export function bannerHtml(env: Env): string {
  if (!env.inApp || dismissed("banner-dismissed")) return "";
  const url = location.href.split("#")[0];
  const open = env.android
    ? `<a class="b-btn" href="intent://${url.replace(/^https?:\/\//, "")}#Intent;scheme=https;package=com.android.chrome;end">Chrome으로 열기</a>`
    : `<span class="b-how">오른쪽 위 <b>···</b> → <b>외부 브라우저로 열기</b></span>`;
  return `<div class="banner" role="note">
    <p>📱 <b>${env.inApp}</b> 안에서 보고 있어요. 브라우저로 열면 홈 화면에 추가해 앱처럼 쓸 수 있어요.</p>
    <div class="b-row">${open}<button type="button" class="b-btn ghost" data-copy-link>링크 복사</button>
      <button type="button" class="b-x" data-dismiss="banner-dismissed" aria-label="닫기">✕</button></div>
  </div>`;
}

/** Home-screen hint: Chrome/Edge offer an install prompt; iOS Safari needs the share menu. */
export function hintHtml(env: Env, canPrompt: boolean): string {
  if (env.standalone || env.inApp || dismissed("hint-dismissed")) return "";
  const body = canPrompt
    ? `<p><b>📲 홈 화면에 추가</b>하면 앱처럼 바로 열려요. 설치도 로그인도 필요 없어요.</p>
       <button type="button" class="b-btn" data-install>추가하기</button>`
    : env.ios
      ? `<p><b>📲 홈 화면에 추가</b>하면 앱처럼 바로 열려요.<br>Safari 아래 <b>공유 버튼</b> → <b>홈 화면에 추가</b></p>`
      : "";
  if (!body) return "";
  return `<div class="hint card">${body}<button type="button" class="b-x" data-dismiss="hint-dismissed" aria-label="닫기">✕</button></div>`;
}

/** Clipboard API, then the old execCommand path (some in-app browsers only allow that). */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = Object.assign(document.createElement("textarea"), { value: text, readOnly: true });
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.append(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}

/** Offline + home-screen support. Skipped under automation so screenshots never see a stale cache. */
export function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator) || navigator.webdriver) return;
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
