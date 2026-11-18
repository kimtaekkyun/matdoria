// Dependency-free Chromium (CDP) driver for mobile layout checks.
//
// Usage (dev server must already be running on BASE_URL, default http://localhost:3000):
//   node scripts/mobile-e2e.mjs capture <outDir>   # screenshots + geometry JSON per viewport/state
//   node scripts/mobile-e2e.mjs test               # functional/geometry assertions
//
// Env: BASE_URL, CHROME_BIN (default /usr/bin/google-chrome)

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";
const CHROME_BIN = process.env.CHROME_BIN ?? "/usr/bin/google-chrome";
const VIEWPORTS = [
  { name: "320x568", width: 320, height: 568 },
  { name: "375x667", width: 375, height: 667 },
  { name: "390x844", width: 390, height: 844 },
  { name: "430x932", width: 430, height: 932 },
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0;
    this.pending = new Map();
    this.ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) rej(new Error(JSON.stringify(msg.error)));
        else res(msg.result);
      }
    };
  }
  open() {
    return new Promise((res, rej) => {
      this.ws.onopen = () => res();
      this.ws.onerror = (e) => rej(e);
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
  async eval(expression) {
    const r = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? "eval failed");
    return r.result.value;
  }
}

async function launchChrome() {
  const port = 9400 + Math.floor(Math.random() * 400);
  const profile = mkdtempSync(join(tmpdir(), "matdoria-e2e-"));
  const proc = spawn(CHROME_BIN, [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
    `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return { proc, cdp: new Cdp(page.webSocketDebuggerUrl) };
    } catch { /* not ready */ }
    await sleep(100);
  }
  proc.kill();
  throw new Error("Chrome did not expose DevTools");
}

async function openApp(cdp, vp) {
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: vp.width, height: vp.height, deviceScaleFactor: 2, mobile: true,
  });
  await cdp.send("Page.navigate", { url: BASE_URL });
  for (let i = 0; i < 150; i++) {
    const ready = await cdp.eval(`document.readyState === "complete" && !!document.querySelector(".list-item")`).catch(() => false);
    if (ready) break;
    await sleep(200);
  }
  await sleep(600);
}

async function rect(cdp, selector) {
  return cdp.eval(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height, top: r.top, bottom: r.bottom, left: r.left, right: r.right };
  })()`);
}

async function mouse(cdp, x, y, type = "click") {
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  if (type === "click") {
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
  }
  await sleep(320);
}

async function clickSel(cdp, selector) {
  const r = await rect(cdp, selector);
  if (!r) throw new Error(`missing ${selector}`);
  await mouse(cdp, r.x + r.w / 2, r.y + r.h / 2);
}

async function dragSel(cdp, selector, toY) {
  const r = await rect(cdp, selector);
  const x = r.x + r.w / 2;
  const y = r.y + r.h / 2;
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
  const steps = 12;
  for (let i = 1; i <= steps; i++) {
    const ny = y + ((toY - y) * i) / steps;
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y: ny, button: "left", buttons: 1 });
    await sleep(16);
  }
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y: toY, button: "left", buttons: 0, clickCount: 1 });
  await sleep(450);
}

// Real touch input: Input.dispatchTouchEvent with touch emulation, so the browser
// produces pointerType="touch" pointer events (unlike dispatchMouseEvent drags).
async function enableTouch(cdp) {
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
}

async function touchDragSel(cdp, selector, toY, steps = 12, fromEdge = "center") {
  const r = await rect(cdp, selector);
  if (!r) throw new Error(`missing ${selector}`);
  const x = r.x + r.w / 2;
  const y = fromEdge === "top" ? r.y + 1 : r.y + r.h / 2;
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  for (let i = 1; i <= steps; i++) {
    const ny = y + ((toY - y) * i) / steps;
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: ny, id: 1 }] });
    await sleep(16);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(450);
}

async function touchTapSel(cdp, selector) {
  const r = await rect(cdp, selector);
  if (!r) throw new Error(`missing ${selector}`);
  const x = r.x + r.w / 2;
  const y = r.y + r.h / 2;
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(350);
}

const GEOMETRY_JS = `(() => {
  const r = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), display: getComputedStyle(el).display };
  };
  const list = document.querySelector(".list");
  return {
    viewport: { w: innerWidth, h: innerHeight },
    docScrollWidth: document.documentElement.scrollWidth,
    app: r(".app"),
    map: r(".map-wrap"),
    sidebar: r(".sidebar"),
    handle: r(".mobile-panel-toggle"),
    peek: r(".mobile-map-peek"),
    head: r(".sidebar-head"),
    search: r(".search"),
    sourceTrigger: r(".source-trigger"),
    chips: r(".chips"),
    toolbar: r(".list-toolbar"),
    sort: r(".sort-select"),
    list: r(".list"),
    listClientHeight: list ? list.clientHeight : null,
    listScrollTop: list ? Math.round(list.scrollTop) : null,
    detail: r(".detail-inline"),
    close: r(".detail-inline .close"),
    panelClass: document.querySelector(".app")?.className ?? null,
  };
})()`;

async function captureViewport(cdp, vp, outDir) {
  const dir = join(outDir, vp.name);
  mkdirSync(dir, { recursive: true });
  const shot = async (name) => {
    const { data } = await cdp.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(dir, `${name}.png`), Buffer.from(data, "base64"));
    return cdp.eval(GEOMETRY_JS);
  };
  const out = {};
  await openApp(cdp, vp);
  out.split = await shot("1-split-default");
  await clickSel(cdp, ".mobile-panel-toggle");
  out.expanded = await shot("2-expanded");
  await clickSel(cdp, ".mobile-panel-toggle");
  await openApp(cdp, vp);
  await dragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
  out.peek = await shot("3-peek");
  await openApp(cdp, vp);
  await clickSel(cdp, ".list-item");
  out.detailSplit = await shot("4-detail-split");
  await dragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
  out.detailPeek = await shot("5-detail-peek");
  writeFileSync(join(dir, "geometry.json"), JSON.stringify(out, null, 2));
  return out;
}

// ---- assertions -------------------------------------------------------------

function makeAsserter() {
  const results = [];
  return {
    results,
    check(name, cond, detail = "") {
      results.push({ name, ok: !!cond, detail });
      console.log(`${cond ? "PASS" : "FAIL"} ${name}${detail ? ` :: ${detail}` : ""}`);
    },
  };
}

async function runTests() {
  const { proc, cdp } = await launchChrome();
  const a = makeAsserter();
  try {
    await cdp.open();
    for (const vp of VIEWPORTS) {
      const tag = vp.name;
      await openApp(cdp, vp);
      const g = await cdp.eval(GEOMETRY_JS);
      a.check(`${tag} no horizontal overflow`, g.docScrollWidth <= vp.width, `scrollWidth=${g.docScrollWidth}`);
      a.check(`${tag} map canvas is full viewport`, g.map && g.map.x === 0 && g.map.y === 0 && g.map.w === vp.width && g.map.h === vp.height, JSON.stringify(g.map));
      a.check(`${tag} header fully inside viewport`, g.head && g.head.top >= 0 && g.head.bottom <= vp.height, JSON.stringify(g.head));
      a.check(`${tag} search visible in header`, g.search && g.search.right <= vp.width && g.search.left >= 0 && g.search.w > 120, JSON.stringify(g.search));
      a.check(`${tag} source trigger visible`, g.sourceTrigger && g.sourceTrigger.display !== "none" && g.sourceTrigger.right <= vp.width, JSON.stringify(g.sourceTrigger));
      a.check(`${tag} split sheet below header`, g.sidebar && g.sidebar.top >= g.head.bottom, `sheetTop=${g.sidebar?.top} headBottom=${g.head?.bottom}`);
      a.check(`${tag} split list is usable (>=120px)`, g.listClientHeight >= 120, `listClientHeight=${g.listClientHeight}`);
      a.check(`${tag} split toolbar (count+sort) visible`, g.toolbar && g.toolbar.bottom <= vp.height && g.sort && g.sort.bottom <= vp.height, `toolbar=${JSON.stringify(g.toolbar)}`);

      // expanded: sheet must not cover header
      await clickSel(cdp, ".mobile-panel-toggle");
      const ex = await cdp.eval(GEOMETRY_JS);
      a.check(`${tag} expanded keeps header visible`, ex.sidebar.top >= ex.head.bottom && ex.head.top >= 0, `sheetTop=${ex.sidebar.top} headBottom=${ex.head.bottom}`);
      a.check(`${tag} expanded map still full viewport`, ex.map.h === vp.height, `mapH=${ex.map.h}`);
      await clickSel(cdp, ".mobile-panel-toggle");

      // peek shows count
      await openApp(cdp, vp);
      await dragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
      const pk = await cdp.eval(GEOMETRY_JS);
      const peekText = await cdp.eval(`document.querySelector(".mobile-map-peek")?.textContent ?? ""`);
      a.check(`${tag} peek shows list count`, /곳 · 목록 보기/.test(peekText), peekText);
      a.check(`${tag} peek map still full viewport`, pk.map.h === vp.height, `mapH=${pk.map.h}`);
      a.check(`${tag} peek header still visible`, pk.head && pk.head.bottom <= vp.height && pk.head.top >= 0, JSON.stringify(pk.head));
      a.check(`${tag} peek sheet is bottom bar`, pk.sidebar.top > vp.height * 0.8, `sheetTop=${pk.sidebar.top}`);

      // peek with a selected place shows its name; tapping it opens the lower detail (split)
      await openApp(cdp, vp);
      await clickSel(cdp, ".list-item");
      await dragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
      const peekName = await cdp.eval(`document.querySelector(".mobile-map-peek")?.textContent ?? ""`);
      const selName = await cdp.eval(`document.querySelector(".list-item-name")?.textContent ?? ""`);
      a.check(`${tag} peek shows selected name`, selName && peekName.includes(selName), peekName);
      await clickSel(cdp, ".mobile-map-peek");
      const fromPeek = await cdp.eval(GEOMETRY_JS);
      a.check(`${tag} peek->select opens split detail`, fromPeek.detail && fromPeek.detail.h > 80 && fromPeek.sidebar.top < vp.height * 0.6, `detail=${JSON.stringify(fromPeek.detail)} sheetTop=${fromPeek.sidebar?.top}`);
    }

    // Functional tests at 390x844
    const vp = { name: "390x844", width: 390, height: 844 };
    await openApp(cdp, vp);

    // source menu
    await clickSel(cdp, ".source-trigger");
    const menuOpen = await cdp.eval(`document.querySelector(".source-trigger")?.getAttribute("aria-expanded")`);
    a.check("source menu opens from trigger", menuOpen === "true", `aria-expanded=${menuOpen}`);
    await cdp.eval(`[...document.querySelectorAll(".chips .chip")].find(b => b.textContent.includes("미쉐린"))?.click()`);
    await sleep(200);
    const afterPick = await cdp.eval(`({ menu: document.querySelector(".source-trigger")?.getAttribute("aria-expanded"), label: document.querySelector(".source-trigger")?.textContent ?? "", pressed: [...document.querySelectorAll(".chips .chip")].find(b => b.textContent.includes("미쉐린"))?.getAttribute("aria-pressed") })`);
    a.check("selecting a source closes menu and updates trigger", afterPick.menu === "false" && afterPick.label.includes("미쉐린") && afterPick.pressed === "true", JSON.stringify(afterPick));
    await clickSel(cdp, ".source-trigger");
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await sleep(200);
    const escState = await cdp.eval(`document.querySelector(".source-trigger")?.getAttribute("aria-expanded")`);
    a.check("Escape closes source menu", escState === "false", `aria-expanded=${escState}`);

    // Pick stays prominent by default
    await openApp(cdp, vp);
    const pickPressed = await cdp.eval(`document.querySelector(".curation-card")?.getAttribute("aria-pressed")`);
    a.check("Matdoria Pick is default active curation", pickPressed === "true", `aria-pressed=${pickPressed}`);

    // scroll + search + detail preservation
    await cdp.eval(`(() => { const b = [...document.querySelectorAll(".chips .chip")].find(b => b.textContent.includes("전체")); b?.click(); })()`);
    await sleep(300);
    await cdp.eval(`document.querySelector(".list").scrollTop = 400`);
    await sleep(150);
    const scrolledBefore = await cdp.eval(`document.querySelector(".list").scrollTop`);
    await cdp.eval(`(() => { const i = document.querySelectorAll(".list-item")[8]; i.click(); })()`);
    await sleep(400);
    const det = await cdp.eval(GEOMETRY_JS);
    a.check("detail opens inline in sheet on mobile", det.detail && det.detail.h > 100, JSON.stringify(det.detail));
    await clickSel(cdp, ".detail-inline .close");
    await sleep(300);
    const scrolledAfter = await cdp.eval(`document.querySelector(".list").scrollTop`);
    a.check("list scroll survives detail open/close", Math.abs(scrolledAfter - scrolledBefore) <= 2, `before=${scrolledBefore} after=${scrolledAfter}`);

    // search stays usable while a detail is open (query keeps the selected place visible)
    await cdp.eval(`(() => { const i = document.querySelectorAll(".list-item")[8]; i.click(); })()`);
    await sleep(400);
    const prefix = await cdp.eval(`document.querySelectorAll(".list-item")[8]?.querySelector(".list-item-name")?.textContent?.slice(0, 2) ?? ""`);
    await cdp.eval(`document.querySelector(".search").focus()`);
    await cdp.send("Input.insertText", { text: prefix });
    await sleep(300);
    const qv = await cdp.eval(`document.querySelector(".search").value`);
    const stillOpen = await cdp.eval(`!!document.querySelector(".detail-inline")`);
    a.check("search stays usable while detail is open", qv === prefix && stillOpen, `value=${qv} detailOpen=${stillOpen}`);

    // Desktop regression
    await openApp(cdp, { name: "1280x800", width: 1280, height: 800 });
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
    await sleep(400);
    const dg = await cdp.eval(GEOMETRY_JS);
    a.check("desktop sidebar is left column with list", dg.sidebar && dg.sidebar.left === 0 && dg.sidebar.w >= 340 && dg.sidebar.w <= 390, JSON.stringify(dg.sidebar));
    a.check("desktop map is right of sidebar", dg.map && dg.map.left >= dg.sidebar.right - 1, JSON.stringify(dg.map));
    a.check("desktop list visible and scrollable", dg.listClientHeight > 200, `listH=${dg.listClientHeight}`);
    a.check("desktop source trigger hidden", !dg.sourceTrigger || dg.sourceTrigger.display === "none", JSON.stringify(dg.sourceTrigger));
    a.check("desktop chips visible", dg.chips && dg.chips.display !== "none" && dg.chips.h > 0, JSON.stringify(dg.chips));
  } finally {
    cdp.ws.close();
    proc.kill();
  }
  const failed = a.results.filter((r) => !r.ok);
  console.log(`\n${a.results.length - failed.length}/${a.results.length} passed`);
  process.exitCode = failed.length ? 1 : 0;
}

// Touch-emulation suite: handle drags (split->peek, peek->split, split->expanded, peek->expanded)
// and the source popover must not intercept the sheet handle.
async function runTouch() {
  const { proc, cdp } = await launchChrome();
  const a = makeAsserter();
  const SPLIT_TOP = `parseFloat(getComputedStyle(document.querySelector(".app")).getPropertyValue("--split-top"))`;
  const EXPANDED_TOP = `parseFloat(getComputedStyle(document.querySelector(".app")).getPropertyValue("--expanded-top"))`;
  const PEEK_TOP = `parseFloat(getComputedStyle(document.querySelector(".app")).getPropertyValue("--peek-top"))`;
  const SHEET_TOP = `document.querySelector(".sidebar").getBoundingClientRect().top`;
  const recordPointerTypes = `(() => {
    const h = document.querySelector(".mobile-panel-toggle");
    window.__pointerTypes = [];
    h.addEventListener("pointerdown", (e) => window.__pointerTypes.push(e.pointerType));
  })()`;
  try {
    await cdp.open();
    for (const vp of VIEWPORTS) {
      const tag = vp.name;
      // split -> peek
      await openApp(cdp, vp);
      await enableTouch(cdp);
      await cdp.eval(recordPointerTypes);
      await touchDragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
      const types1 = await cdp.eval(`window.__pointerTypes`);
      const peekNow = await cdp.eval(`({ top: ${SHEET_TOP}, peekTop: ${PEEK_TOP}, text: document.querySelector(".mobile-map-peek")?.textContent ?? "" })`);
      a.check(`${tag} touch split->peek`, Math.abs(peekNow.top - peekNow.peekTop) <= 2 && /목록 보기/.test(peekNow.text), JSON.stringify(peekNow));
      a.check(`${tag} touch drag uses pointerType=touch`, types1.length > 0 && types1.every((t) => t === "touch"), JSON.stringify(types1));

      // peek -> split (drag up to mid-screen; should snap to split)
      await touchDragSel(cdp, ".mobile-panel-toggle", vp.height * 0.5);
      const splitNow = await cdp.eval(`({ top: ${SHEET_TOP}, splitTop: ${SPLIT_TOP} })`);
      a.check(`${tag} touch peek->split`, Math.abs(splitNow.top - splitNow.splitTop) <= 2, JSON.stringify(splitNow));

      // split -> expanded (drag to top; snaps to expanded, header stays visible)
      await touchDragSel(cdp, ".mobile-panel-toggle", 10);
      const expNow = await cdp.eval(`({ top: ${SHEET_TOP}, expandedTop: ${EXPANDED_TOP}, headBottom: document.querySelector(".sidebar-head").getBoundingClientRect().bottom })`);
      a.check(`${tag} touch split->expanded keeps header visible`, Math.abs(expNow.top - expNow.expandedTop) <= 2 && expNow.top >= expNow.headBottom, JSON.stringify(expNow));

      // expanded -> peek (drag to bottom)
      await touchDragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
      const peek2 = await cdp.eval(`({ top: ${SHEET_TOP}, peekTop: ${PEEK_TOP} })`);
      a.check(`${tag} touch expanded->peek`, Math.abs(peek2.top - peek2.peekTop) <= 2, JSON.stringify(peek2));

      // source popover must not intercept the handle
      await openApp(cdp, vp);
      await enableTouch(cdp);
      await clickSel(cdp, ".source-trigger");
      const hit = await cdp.eval(`(() => {
        const h = document.querySelector(".mobile-panel-toggle").getBoundingClientRect();
        const x = h.x + h.width / 2;
        const probe = (y) => { const el = document.elementFromPoint(x, y); return { inHandle: !!el?.closest(".mobile-panel-toggle"), inMenu: !!el?.closest(".chips") }; };
        const c = document.querySelector(".chips").getBoundingClientRect();
        return { center: probe(h.top + h.height / 2), topEdge: probe(h.top + 1), bottomEdge: probe(h.bottom - 1), menuRect: { top: Math.round(c.top), bottom: Math.round(c.bottom) }, handleRect: { top: Math.round(h.top), bottom: Math.round(h.bottom) } };
      })()`);
      a.check(`${tag} source popover does not intercept handle center`, hit.center.inHandle && !hit.center.inMenu, JSON.stringify(hit));
      a.check(`${tag} source popover does not intercept handle edges`, hit.topEdge.inHandle && !hit.topEdge.inMenu && hit.bottomEdge.inHandle, JSON.stringify(hit));
      const geo = await cdp.eval(`(() => {
        const c = document.querySelector(".chips").getBoundingClientRect();
        const h = document.querySelector(".mobile-panel-toggle").getBoundingClientRect();
        const s = document.querySelector(".sidebar").getBoundingClientRect();
        return { chipsBottom: Math.round(c.bottom), handleTop: Math.round(h.top), sheetTop: Math.round(s.top), headerBottom: Math.round(document.querySelector(".sidebar-head").getBoundingClientRect().bottom) };
      })()`);
      a.check(`${tag} popover bottom is above handle and sheet top (menu open)`, geo.chipsBottom <= geo.handleTop && geo.chipsBottom <= geo.sheetTop - 4, JSON.stringify(geo));
      // Touch starting on the handle's top edge with the menu open must still move the panel.
      await touchDragSel(cdp, ".mobile-panel-toggle", vp.height - 20, 12, "top");
      const edgeDrag = await cdp.eval(`({ top: ${SHEET_TOP}, peekTop: ${PEEK_TOP}, menuOpen: document.querySelector(".source-trigger")?.getAttribute("aria-expanded") })`);
      a.check(`${tag} touch on handle top edge with menu open moves panel`, Math.abs(edgeDrag.top - edgeDrag.peekTop) <= 2, JSON.stringify(edgeDrag));
      await openApp(cdp, vp);
      await enableTouch(cdp);
      await clickSel(cdp, ".source-trigger");
      await touchDragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
      const withMenu = await cdp.eval(`({ top: ${SHEET_TOP}, peekTop: ${PEEK_TOP}, pickPressed: document.querySelector(".curation-card")?.getAttribute("aria-pressed"), chipPressed: [...document.querySelectorAll(".chips .chip")].some(b => b.getAttribute("aria-pressed") === "true" && !b.textContent.includes("Pick")) })`);
      a.check(`${tag} touch drag on handle works while source menu open`, Math.abs(withMenu.top - withMenu.peekTop) <= 2 && withMenu.pickPressed === "true", JSON.stringify(withMenu));
    }
    // 320x568, expanded: source menu open must not cover the handle; handle drag must change mode.
    const v320 = VIEWPORTS[0];
    await openApp(cdp, v320);
    await enableTouch(cdp);
    await touchDragSel(cdp, ".mobile-panel-toggle", 10);
    const expanded = await cdp.eval(`({ top: ${SHEET_TOP}, expandedTop: ${EXPANDED_TOP} })`);
    a.check("320x568 expanded reached by touch", Math.abs(expanded.top - expanded.expandedTop) <= 2, JSON.stringify(expanded));
    await touchTapSel(cdp, ".source-trigger");
    const menu = await cdp.eval(`(() => {
      const h = document.querySelector(".mobile-panel-toggle").getBoundingClientRect();
      const c = document.querySelector(".chips");
      const cr = c.getBoundingClientRect();
      const x = h.x + h.width / 2;
      const at = (y) => { const el = document.elementFromPoint(x, y); return !!el?.closest(".mobile-panel-toggle"); };
      return {
        open: document.querySelector(".source-trigger").getAttribute("aria-expanded"),
        chipsDisplay: getComputedStyle(c).display,
        chipsRect: { top: Math.round(cr.top), bottom: Math.round(cr.bottom) },
        handleRect: { top: Math.round(h.top), bottom: Math.round(h.bottom) },
        hitHandleTopEdge: at(h.top + 1),
        hitHandleCenter: at(h.top + h.height / 2),
        viewportH: innerHeight,
      };
    })()`);
    a.check("320x568 expanded: source menu opens by touch", menu.open === "true" && menu.chipsDisplay !== "none", JSON.stringify(menu));
    a.check("320x568 expanded+menu: elementFromPoint on handle top edge is the handle", menu.hitHandleTopEdge, JSON.stringify(menu));
    a.check("320x568 expanded+menu: elementFromPoint on handle center is the handle", menu.hitHandleCenter, JSON.stringify(menu));
    a.check("320x568 expanded+menu: popover starts below the handle", menu.chipsRect.top >= menu.handleRect.bottom, JSON.stringify(menu));
    a.check("320x568 expanded+menu: popover fits viewport", menu.chipsRect.bottom <= menu.viewportH, JSON.stringify(menu));

    const scrollInfo = async (label) => {
      const info = await cdp.eval(`(() => {
        const c = document.querySelector(".chips");
        const exceeds = c.scrollHeight > c.clientHeight + 1;
        if (exceeds) c.scrollTop = c.scrollHeight;
        return { exceeds, overflowY: getComputedStyle(c).overflowY, clientH: c.clientHeight, scrollH: c.scrollHeight, scrollTop: Math.round(c.scrollTop) };
      })()`);
      return info;
    };
    const expScroll = await scrollInfo("expanded");
    a.check("320x568 expanded+menu: popover is internally scrollable when chips exceed cap", !expScroll.exceeds || (expScroll.overflowY === "auto" && expScroll.scrollTop > 0), JSON.stringify(expScroll));

    // Drag the handle from its top edge with the menu open -> sheet changes mode (expanded -> peek) and menu closes.
    await touchDragSel(cdp, ".mobile-panel-toggle", v320.height - 20, 12, "top");
    const afterDrag = await cdp.eval(`({ top: ${SHEET_TOP}, peekTop: ${PEEK_TOP}, open: document.querySelector(".source-trigger").getAttribute("aria-expanded") })`);
    a.check("320x568 expanded+menu: handle top-edge drag changes mode to peek", Math.abs(afterDrag.top - afterDrag.peekTop) <= 2 && afterDrag.open === "false", JSON.stringify(afterDrag));

    // Split with menu open: chips cap is smaller, so the list must scroll inside the popover.
    await openApp(cdp, v320);
    await enableTouch(cdp);
    await touchTapSel(cdp, ".source-trigger");
    const splitScroll = await scrollInfo("split");
    a.check("320x568 split+menu: chips exceed cap and popover scrolls internally", splitScroll.exceeds && splitScroll.overflowY === "auto" && splitScroll.scrollTop > 0, JSON.stringify(splitScroll));
  } finally {
    cdp.ws.close();
    proc.kill();
  }
  const failed = a.results.filter((r) => !r.ok);
  console.log(`\n${a.results.length - failed.length}/${a.results.length} passed`);
  process.exitCode = failed.length ? 1 : 0;
}

// Opt-in: real Kakao markers on the authorized local dev server (needs the local map key).
// Not part of test:e2e. Refuses any other origin.
const MAP_ORIGIN = "http://localhost:3000";
const MARKERS_JS = `[...document.querySelectorAll(".map img[title][src^='data:image/svg']")].map((img) => {
  const r = img.getBoundingClientRect();
  return { title: img.title, x: r.x, y: r.y, w: r.width, h: r.height, top: r.top, bottom: r.bottom, cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
})`;
const BAND_JS = `(() => {
  const head = document.querySelector(".sidebar-head").getBoundingClientRect();
  const sheet = document.querySelector(".sidebar").getBoundingClientRect();
  return { bandTop: head.bottom + 8, bandBottom: sheet.top, sheetTop: sheet.top, vh: innerHeight };
})()`;

async function runMap() {
  if (BASE_URL !== MAP_ORIGIN) {
    console.error(`map mode refused: BASE_URL=${BASE_URL}. Only ${MAP_ORIGIN} (authorized local dev server with map key) is allowed.`);
    process.exitCode = 2;
    return;
  }
  const vp = { name: "390x844", width: 390, height: 844 };
  const { proc, cdp } = await launchChrome();
  const a = makeAsserter();
  const inBand = (m, band) => m.top >= band.bandTop - 1 && m.bottom <= band.bandBottom + 1;
  try {
    await cdp.open();
    await openApp(cdp, vp);
    await enableTouch(cdp);
    let markers = [];
    for (let i = 0; i < 60; i++) {
      markers = await cdp.eval(MARKERS_JS);
      if (markers.length > 0) break;
      await sleep(250);
    }
    if (markers.length === 0) {
      a.check("kakao markers rendered", false, "no img[title][src^=data:image/svg] inside .map: Kakao SDK not loaded, key/domain rejected, or markers not rendered");
      return;
    }
    a.check("kakao markers rendered", true, `count=${markers.length} titles=${markers.map((m) => m.title).join(", ")}`);
    await sleep(1500); // let fit-to-band animation settle

    let band = await cdp.eval(BAND_JS);
    markers = await cdp.eval(MARKERS_JS);
    const visibleMarkers = markers.filter((m) => inBand(m, band));
    a.check("at least two markers inside the split band", visibleMarkers.length >= 2, `band=${JSON.stringify(band)} inBand=${visibleMarkers.map((m) => m.title).join(", ")} all=${JSON.stringify(markers.map((m) => [m.title, Math.round(m.top), Math.round(m.bottom)]))}`);
    if (visibleMarkers.length === 0) return;

    // Tap a real marker (touch -> click) in the split band.
    const target = visibleMarkers[0];
    await touchTapAt(cdp, target.cx, target.cy);
    await sleep(700);
    const detail1 = await cdp.eval(`({ h2: document.querySelector(".detail-inline h2")?.textContent ?? null, sheetTop: document.querySelector(".sidebar").getBoundingClientRect().top, splitTop: parseFloat(getComputedStyle(document.querySelector(".app")).getPropertyValue("--split-top")) })`);
    a.check("marker tap opens lower detail with matching place", detail1.h2 === target.title, `tapped=${target.title} detailH2=${detail1.h2} (null means no detail rendered: tap missed marker or click not delivered)`);
    a.check("marker tap keeps split (lower sheet) mode", Math.abs(detail1.sheetTop - detail1.splitTop) <= 2, JSON.stringify(detail1));

    band = await cdp.eval(BAND_JS);
    let now = (await cdp.eval(MARKERS_JS)).find((m) => m.title === target.title);
    a.check("selected marker inside visible split band", !!now && inBand(now, band), `marker=${JSON.stringify(now)} band=${JSON.stringify(band)}`);
    if (now) {
      const center = (band.bandTop + band.bandBottom) / 2;
      console.log(`INFO split: marker center y=${Math.round(now.cy)} band center y=${Math.round(center)} delta=${Math.round(now.cy - center)}`);
    }

    // Drag to peek (touch); selected name must show in the bar, marker must stay in the peek band.
    await touchDragSel(cdp, ".mobile-panel-toggle", vp.height - 20);
    await sleep(900);
    const peekText = await cdp.eval(`document.querySelector(".mobile-map-peek")?.textContent ?? ""`);
    a.check("peek bar shows the selected marker's place", peekText.includes(target.title), `peekText=${peekText}`);
    band = await cdp.eval(BAND_JS);
    now = (await cdp.eval(MARKERS_JS)).find((m) => m.title === target.title);
    a.check("selected marker inside visible peek band", !!now && inBand(now, band), `marker=${JSON.stringify(now)} band=${JSON.stringify(band)}`);

    // Peek bar tap -> lower detail (split); marker stays in split band.
    await touchTapSel(cdp, ".mobile-map-peek");
    await sleep(900);
    const detail2 = await cdp.eval(`({ h2: document.querySelector(".detail-inline h2")?.textContent ?? null, sheetTop: document.querySelector(".sidebar").getBoundingClientRect().top, splitTop: parseFloat(getComputedStyle(document.querySelector(".app")).getPropertyValue("--split-top")) })`);
    a.check("peek tap opens lower detail for the same place", detail2.h2 === target.title && Math.abs(detail2.sheetTop - detail2.splitTop) <= 2, JSON.stringify(detail2));
    band = await cdp.eval(BAND_JS);
    now = (await cdp.eval(MARKERS_JS)).find((m) => m.title === target.title);
    a.check("selected marker inside visible split band after peek->split", !!now && inBand(now, band), `marker=${JSON.stringify(now)} band=${JSON.stringify(band)}`);

    // Second round on a fresh load: tap a different marker in the band; detail must match that place.
    await openApp(cdp, vp);
    await enableTouch(cdp);
    await sleep(1500);
    const band2 = await cdp.eval(BAND_JS);
    const fresh = (await cdp.eval(MARKERS_JS)).filter((m) => inBand(m, band2));
    const second = fresh[1];
    if (!second) {
      a.check("second marker available in split band (fresh load)", false, `inBand=${fresh.map((m) => m.title).join(", ") || "none"}`);
    } else {
      await touchTapAt(cdp, second.cx, second.cy);
      await sleep(700);
      const h2 = await cdp.eval(`document.querySelector(".detail-inline h2")?.textContent ?? null`);
      a.check("second marker tap opens detail for that place", h2 === second.title, `tapped=${second.title} detailH2=${h2}`);
      const band3 = await cdp.eval(BAND_JS);
      const moved = (await cdp.eval(MARKERS_JS)).find((m) => m.title === second.title);
      a.check("second selected marker inside visible split band", !!moved && inBand(moved, band3), `marker=${JSON.stringify(moved)} band=${JSON.stringify(band3)}`);
    }
  } finally {
    cdp.ws.close();
    proc.kill();
  }
  const failed = a.results.filter((r) => !r.ok);
  console.log(`\n${a.results.length - failed.length}/${a.results.length} passed`);
  process.exitCode = failed.length ? 1 : 0;
}

async function touchTapAt(cdp, x, y) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(350);
}

async function runCapture(outDir) {
  mkdirSync(outDir, { recursive: true });
  const { proc, cdp } = await launchChrome();
  const all = {};
  try {
    await cdp.open();
    for (const vp of VIEWPORTS) {
      all[vp.name] = await captureViewport(cdp, vp, outDir);
      console.log(`captured ${vp.name}`);
    }
    writeFileSync(join(outDir, "geometry-all.json"), JSON.stringify(all, null, 2));
  } finally {
    cdp.ws.close();
    proc.kill();
  }
}

const [mode, arg] = process.argv.slice(2);
if (mode === "capture") await runCapture(arg ?? "/tmp/opencode/shots/unknown");
else if (mode === "test") await runTests();
else if (mode === "touch") await runTouch();
else if (mode === "map") await runMap();
else {
  console.error("usage: mobile-e2e.mjs capture <outDir> | test | touch | map (opt-in, BASE_URL=http://localhost:3000 only)");
  process.exitCode = 2;
}
