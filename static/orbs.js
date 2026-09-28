/**
 * Thinking-orb loaders for the dashboard (ES module).
 *
 * A small wrapper around the vendored, React-free thinking-orbs engine. It
 * mirrors what the package's React <ThinkingOrb> does: a devicePixelRatio
 * canvas, one requestAnimationFrame loop per orb driven by performance.now(),
 * paused while the tab is hidden or the orb is off-screen, and nothing drawn
 * under prefers-reduced-motion.
 *
 * The canvas is decorative (aria-hidden); callers always put the state in
 * words next to it ("Running", "Checking…"), so reduced-motion users and
 * screen readers get the words only.
 *
 * Two ways to use it:
 *   import { mountOrb } from "/orbs.js";
 *   const orb = mountOrb(el, { state: "working", size: 20 });
 *   orb.setState("searching"); orb.destroy();
 *
 *   Or declaratively: <span class="orb" data-orb="working" data-orb-size="20"></span>
 *   Any such element is mounted automatically when it appears in the page,
 *   updated when data-orb changes (an empty value hides the orb) and
 *   destroyed when it is removed. app.js uses this form, so it needs no
 *   imports and keeps working if this module fails to load.
 */
import { MODE_FRAMES, paintFrame, resolvePreset, STATE_TO_MODE } from "./vendor/thinking-orbs/engine.es.js";

const SIZES = [20, 32, 64]; // the engine's tuned presets
const DPR_CAP = 2; // same cap as the React component

/** Job status (from /api/jobs) -> orb state, or "" for no orb.
 *  The engine has no "done" or "error" animation, so finished, stopped and
 *  failed jobs show their status sticker and word without an orb. */
export const JOB_STATUS_ORB = { running: "working" };

const reducedMq = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
const darkMq = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
const isReduced = () => !!(reducedMq && reducedMq.matches);

function snapSize(size) {
  const n = Number(size) || 20;
  return SIZES.reduce((best, s) => (Math.abs(s - n) < Math.abs(best - n) ? s : best), SIZES[0]);
}

function validState(state) {
  return typeof state === "string" && Object.prototype.hasOwnProperty.call(STATE_TO_MODE, state) ? state : "";
}

/** Dark ink or light ink? An ancestor's data-theme / .dark / .light wins;
 *  otherwise follow the OS only if the page declares a dark colour scheme. */
function resolveDark(el) {
  for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
    const attr = node.getAttribute("data-theme");
    if (attr === "dark") return true;
    if (attr === "light") return false;
    if (node.classList.contains("dark")) return true;
    if (node.classList.contains("light")) return false;
  }
  const scheme = getComputedStyle(document.documentElement).colorScheme || "";
  return /dark/.test(scheme) && !!(darkMq && darkMq.matches);
}

/**
 * Mount an orb inside `el`.
 * @param {HTMLElement} el   host element (the canvas is appended to it)
 * @param {{state?: string, size?: number}} options
 *        state: one of the engine's states (working, searching, solving,
 *        listening, connecting, weaving, composing, breathing, shaping);
 *        an empty/unknown state hides the orb. size: 20, 32 or 64 CSS px.
 * @returns {{setState(state: string): void, destroy(): void}}
 */
export function mountOrb(el, { state = "working", size = 20 } = {}) {
  const px = snapSize(size);
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.className = "orb-canvas";
  canvas.style.width = `${px}px`;
  canvas.style.height = `${px}px`;
  canvas.style.display = "block";
  el.appendChild(canvas);
  const ctx = canvas.getContext("2d");

  let current = "";
  let frameFn = null;
  let opts = null;
  let speed = 1;
  let dark = resolveDark(el);
  let dpr = 1;
  let raf = 0;
  let running = false;
  let onScreen = true;
  let destroyed = false;

  const sizeCanvas = () => {
    dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1);
    canvas.width = Math.round(px * dpr);
    canvas.height = Math.round(px * dpr);
  };

  const draw = (tSec) => {
    if (!ctx || !frameFn) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, px, px);
    paintFrame(ctx, frameFn(px, tSec, opts), dark);
  };

  const loop = () => {
    draw((performance.now() / 1e3) * speed);
    if (running) raf = requestAnimationFrame(loop);
  };

  const shouldRun = () => !destroyed && !!current && !isReduced() && onScreen && document.visibilityState !== "hidden";

  const sync = () => {
    const visible = !!current && !isReduced() && !destroyed;
    canvas.hidden = !visible;
    el.classList.toggle("orb-on", visible);
    if (shouldRun()) {
      if (!running) {
        running = true;
        raf = requestAnimationFrame(loop);
      }
    } else {
      running = false;
      cancelAnimationFrame(raf);
      if (ctx && !visible) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  };

  const setState = (next) => {
    const s = validState(next);
    if (s === current) return sync();
    current = s;
    if (s) {
      const resolved = resolvePreset(s, px);
      frameFn = MODE_FRAMES[resolved.mode];
      opts = resolved.opts;
      speed = resolved.speed;
      if (!isReduced()) draw((performance.now() / 1e3) * speed); // first frame now, no blank flash
    } else {
      frameFn = null;
    }
    sync();
  };

  const io = typeof IntersectionObserver === "function"
    ? new IntersectionObserver((entries) => {
        onScreen = entries[entries.length - 1].isIntersecting;
        sync();
      })
    : null;
  if (io) io.observe(canvas);

  const onVisibility = () => sync();
  const onReduced = () => sync();
  const onScheme = () => {
    dark = resolveDark(el);
    if (!running && current && !isReduced()) draw((performance.now() / 1e3) * speed);
  };
  document.addEventListener("visibilitychange", onVisibility);
  if (reducedMq) reducedMq.addEventListener("change", onReduced);
  if (darkMq) darkMq.addEventListener("change", onScheme);
  const themeMo = typeof MutationObserver === "function" ? new MutationObserver(onScheme) : null;
  if (themeMo) themeMo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });

  sizeCanvas();
  setState(state);

  return {
    setState,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      running = false;
      cancelAnimationFrame(raf);
      if (io) io.disconnect();
      if (themeMo) themeMo.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      if (reducedMq) reducedMq.removeEventListener("change", onReduced);
      if (darkMq) darkMq.removeEventListener("change", onScheme);
      el.classList.remove("orb-on");
      canvas.remove();
    },
  };
}

// --- Declarative mounting: <span class="orb" data-orb="working" data-orb-size="20"> ---

const mounted = new Map(); // host element -> orb handle

function mountHost(host) {
  const state = host.getAttribute("data-orb") || "";
  const existing = mounted.get(host);
  if (existing) return existing.setState(state);
  mounted.set(host, mountOrb(host, { state, size: host.getAttribute("data-orb-size") || 20 }));
}

function scan(root) {
  if (root.nodeType !== 1) return;
  if (root.hasAttribute("data-orb")) mountHost(root);
  root.querySelectorAll("[data-orb]").forEach(mountHost);
}

function sweepRemoved() {
  for (const [host, orb] of mounted) {
    if (!host.isConnected) {
      orb.destroy();
      mounted.delete(host);
    }
  }
}

function startAutoMount() {
  scan(document.body);
  new MutationObserver((records) => {
    let removed = false;
    for (const r of records) {
      if (r.type === "attributes") {
        if (r.target.isConnected) mountHost(r.target);
        continue;
      }
      if (r.removedNodes.length) removed = true;
      r.addedNodes.forEach(scan);
    }
    if (removed) sweepRemoved();
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-orb"] });
}

if (document.body) startAutoMount();
else document.addEventListener("DOMContentLoaded", startAutoMount, { once: true });

window.Orbs = { mountOrb, JOB_STATUS_ORB };
