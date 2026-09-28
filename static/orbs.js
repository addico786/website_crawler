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
// Solid ink: every dot is drawn in the text colour (black on the light Slush
// paper, white on dark) and depth is shown by opacity alone, from 1 for the
// nearest dots down to INK_FLOOR for the farthest. The engine's own painter
// fades far dots toward the paper colour, which reads as pale grey here.
const INK_FLOOR = 0.45;
// With solid ink the globe's un-scanned dots (dimBase 0.45) read as grey; lift them.
const SOLID_EXTRA = { searching: { dimBase: 0.85 } };
const DPR_CAP = 2; // same cap as the React component

/** Job status (from /api/jobs) -> orb state per size, or no orb.
 *  The engine has no "done" or "error" animation, so finished, stopped and
 *  failed jobs show their status sticker and word without an orb.
 *  Card (24 px): "solving", a dotted globe whose bands turn in quarter turns;
 *  it stays black and visibly moving at small sizes, where "searching" dims
 *  most of its dots to grey. Detail (96 px): "searching", a dotted globe with
 *  a scan sweep, which reads as an ordered sphere at that size ("solving"
 *  looks like scattered dots mid-turn). Both are dotted globes. */
export const JOB_STATUS_ORB = { running: { card: "solving", detail: "searching" } };

const reducedMq = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
const darkMq = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
const isReduced = () => !!(reducedMq && reducedMq.matches);

/** The tuned preset to draw with: the largest one that fits the display size
 *  (20 for anything smaller). Larger sizes, such as 96, scale the 64 preset. */
function presetFor(size) {
  return SIZES.filter((s) => s <= size).pop() || SIZES[0];
}

function paintInk(ctx, frame, dark, floor = INK_FLOOR, dotScale = 1) {
  const rgb = dark ? "255,255,255" : "0,0,0";
  const style = (white, a = 1) => `rgba(${rgb},${(a * (1 - (1 - floor) * Math.min(1, Math.max(0, white)))).toFixed(3)})`;
  for (const l of frame.lines) {
    ctx.strokeStyle = style(l.white, l.a);
    ctx.lineWidth = l.w;
    ctx.beginPath();
    ctx.moveTo(l.x1, l.y1);
    ctx.lineTo(l.x2, l.y2);
    ctx.stroke();
  }
  for (const d of frame.dots) {
    ctx.fillStyle = style(d.white, d.a);
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.r * dotScale, 0, Math.PI * 2);
    ctx.fill();
  }
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
 * @param {{state?: string, size?: number, ink?: "solid"|"engine"}} options
 *        state: one of the engine's states (working, searching, solving,
 *        listening, connecting, weaving, composing, breathing, shaping);
 *        an empty/unknown state hides the orb. size: CSS px; 20, 32 and 64
 *        are the engine's tuned presets, other sizes scale the nearest one
 *        below. ink: "solid" (default, text-coloured dots) or "engine" (the
 *        package's grey depth ramp).
 * @returns {{setState(state: string): void, destroy(): void}}
 */
export function mountOrb(el, { state = "working", size = 20, ink = "solid" } = {}) {
  const px = Math.max(12, Math.round(Number(size) || 20)); // display size
  const preset = presetFor(px); // geometry size
  const zoom = px / preset;
  const small = px <= 32;
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
    ctx.setTransform(dpr * zoom, 0, 0, dpr * zoom, 0, 0);
    const frame = frameFn(preset, tSec, opts);
    if (ink === "engine") paintFrame(ctx, frame, dark);
    else if (small) paintInk(ctx, frame, dark, 0.6, 1.3); // bolder at card size so it reads at a glance
    else paintInk(ctx, frame, dark);
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
      const resolved = resolvePreset(s, preset);
      frameFn = MODE_FRAMES[resolved.mode];
      opts = ink === "engine" ? resolved.opts : { ...resolved.opts, ...SOLID_EXTRA[s] };
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
  mounted.set(host, mountOrb(host, {
    state,
    size: host.getAttribute("data-orb-size") || 20,
    ink: host.getAttribute("data-orb-ink") || "solid",
  }));
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
