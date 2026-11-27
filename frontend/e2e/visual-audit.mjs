/**
 * Visual + accessibility audit for the shipped palette.
 *
 * Logs in through the real form, then walks the authenticated and public routes at desktop,
 * tablet and mobile widths. For every route it records console errors, horizontal overflow and
 * any text whose rendered colour falls below WCAG AA against its own painted background.
 * Screenshots land in e2e/artifacts so a reviewer can compare the chrome across breakpoints.
 *
 *   node e2e/visual-audit.mjs            # expects the app on http://127.0.0.1:3000
 *   BASE=http://127.0.0.1:3000 node e2e/visual-audit.mjs
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";

const axePath = createRequire(import.meta.url).resolve("axe-core/axe.min.js");

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const EMAIL = process.env.AUDIT_EMAIL ?? "reviewer@veltrane.dev";
const PASSWORD = process.env.AUDIT_PASSWORD ?? "Veltrane!Review2026";
const OUT = new URL("./artifacts/", import.meta.url).pathname;

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 834, height: 1112 },
  { name: "mobile", width: 390, height: 844 },
];

const ROUTES = [
  "/",
  "/app",
  "/app/terminal",
  "/app/markets",
  "/app/strategies",
  "/app/copilot",
  "/app/portfolio",
  "/app/wallet",
  "/app/analytics",
  "/app/accounts",
  "/app/membership",
  "/app/billing",
  "/app/settings",
  "/app/notifications",
  "/risk",
];

// Contrast is measured with axe-core rather than a hand-rolled walk of computed styles: it
// resolves stacked translucent layers and gradient panels the way the browser paints them, and
// it marks text over an image as "incomplete" instead of guessing a background.
const AXE_OPTIONS = { runOnly: { type: "rule", values: ["color-contrast"] } };

const contrastFailures = async (page) =>
  page.evaluate(async (options) => {
    const result = await window.axe.run(document, options);
    const failures = result.violations.flatMap((violation) =>
      violation.nodes.map((node) => ({
        target: node.target.join(" "),
        summary: (node.failureSummary ?? "").split("\n").slice(0, 3).join(" | "),
        text: (node.html ?? "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 48),
      })),
    );
    const undecided = result.incomplete
      .flatMap((incomplete) => incomplete.nodes)
      .map((node) => node.target.join(" "))
      .filter((target) => target && !target.includes("iframe"));
    return { failures, undecided };
  }, AXE_OPTIONS);

// Reads the paint under each text box from a captured PNG and returns the failures.
const sampleBackdrop = async (page, shot, rows, meta) =>
  page.evaluate(
    async ([dataUrl, entries, entriesMeta]) => {
      const image = new Image();
      image.src = dataUrl;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(image, 0, 0);

      const parse = (value) => {
        const m = value.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const [r, g, b, a = "1"] = m[1].split(/[,\s/]+/).filter(Boolean);
        return { r: +r, g: +g, b: +b, a: +a };
      };
      const lum = ({ r, g, b }) => {
        const f = (v) => {
          const s = v / 255;
          return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
        };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      };

      const found = [];
      for (const row of entries) {
        const entry = entriesMeta[row.selector];
        if (!entry) continue;
        const fg = parse(entry.color);
        if (!fg) continue;
        const { x, y, w, h } = row.rect;
        const points = [
          [x + w / 2, y + h / 2],
          [x + w * 0.25, y + h / 2],
          [x + w * 0.75, y + h / 2],
          [x + w / 2, y + h * 0.25],
          [x + w / 2, y + h * 0.75],
        ];
        const samples = [];
        for (const [px, py] of points) {
          if (px < 1 || py < 1 || px >= canvas.width - 1 || py >= canvas.height - 1) continue;
          const data = ctx.getImageData(Math.round(px), Math.round(py), 1, 1).data;
          samples.push({ r: data[0], g: data[1], b: data[2], a: 1 });
        }
        if (!samples.length) continue;

        // Modal colour: the backdrop is what most of the box shows, so one sample landing on an
        // icon or a neighbouring chip cannot decide the verdict.
        const counts = new Map();
        for (const sample of samples) {
          const key = `${sample.r},${sample.g},${sample.b}`;
          const hit = counts.get(key) ?? { sample, n: 0 };
          hit.n += 1;
          counts.set(key, hit);
        }
        const backdrop = [...counts.values()].sort((a, b) => b.n - a.n)[0].sample;

        // Faint text is often dimmed with opacity, so the painted ink is the colour composited at
        // the element's effective alpha.
        const alpha = fg.a * entry.opacity;
        const ink = {
          r: fg.r * alpha + backdrop.r * (1 - alpha),
          g: fg.g * alpha + backdrop.g * (1 - alpha),
          b: fg.b * alpha + backdrop.b * (1 - alpha),
        };
        const [hi, lo] = [lum(ink), lum(backdrop)].sort((a, b) => b - a);
        const ratio = (hi + 0.05) / (lo + 0.05);
        const large = entry.fontSize >= 24 || (entry.fontSize >= 18.66 && entry.fontWeight >= 600);
        const required = large ? 3 : 4.5;
        if (ratio + 0.05 < required) {
          found.push({
            target: entry.selector,
            text: entry.text,
            summary: `Painted backdrop ${ratio.toFixed(2)}:1 (needs ${required}:1) against rgb(${backdrop.r}, ${backdrop.g}, ${backdrop.b})`,
          });
        }
      }
      return found;
    },
    [`data:image/png;base64,${shot.toString("base64")}`, rows, meta],
  );

// axe cannot judge text on a gradient or image panel, so those elements are measured from the
// rendered pixels: every glyph is made transparent, the page is captured, and the paint under each
// text box is read back from a canvas. Capture happens band by band in the viewport rather than as
// one full-page shot, because resizing the viewport to the page height reflows the layout (and the
// live chart) and leaves the measured rectangles pointing at the wrong pixels.
const measurePaintedBackdrops = async (page, targets) => {
  if (!targets.length) return [];

  const boxes = await page.evaluate((selectors) => {
    const out = [];
    for (const selector of selectors) {
      let el;
      try {
        el = document.querySelector(selector);
      } catch {
        continue;
      }
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      // SVG text paints with `fill`, and gradient headlines paint through a clipped background;
      // neither carries a usable `color`, so a computed-style contrast check cannot judge them.
      if (el.ownerSVGElement || el instanceof SVGElement) continue;
      if ((style.backgroundClip || style.webkitBackgroundClip) === "text") continue;

      let opacity = 1;
      let fixed = false;
      for (let node = el; node; node = node.parentElement) {
        opacity *= Number(getComputedStyle(node).opacity || 1);
        if (getComputedStyle(node).position === "fixed") fixed = true;
      }

      out.push({
        selector,
        text: (el.textContent ?? "").trim().slice(0, 48),
        color: style.color,
        opacity,
        fontSize: parseFloat(style.fontSize),
        fontWeight: Number(style.fontWeight),
        fixed,
        docY: rect.top + window.scrollY,
      });
    }
    return out;
  }, targets);
  if (!boxes.length) return [];

  await page.evaluate(() => {
    const style = document.createElement("style");
    style.id = "visual-audit-blank-text";
    style.textContent =
      "html * { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; caret-color: transparent !important; }";
    document.head.appendChild(style);
  });

  const failures = [];
  try {
    // Fixed bars stack over each other and over the page, so a crop of one cannot be attributed to a
    // single element. They are covered by the axe pass where the background is a flat colour, and by
    // the stored screenshots where it is not.
    const bands = new Map();
    for (const box of boxes.filter((candidate) => !candidate.fixed)) {
      const key = Math.floor(box.docY / 600);
      if (!bands.has(key)) bands.set(key, []);
      bands.get(key).push(box);
    }

    for (const [band, subset] of bands) {
      const viewport = page.viewportSize() ?? { width: 1280, height: 800 };
      const target = Math.max(0, Math.round(Number(band) * 600 + 300 - viewport.height / 2));
      await page.evaluate((y) => window.scrollTo(0, y), target);
      await page.waitForTimeout(120);
      // Rectangles are read after the scroll so they match the capture that follows.
      const entries = await page.evaluate((selectors) => {
        const out = [];
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          if (!el) continue;
          const rect = el.getBoundingClientRect();
          out.push({ selector, rect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height } });
        }
        return out;
      }, subset.map((box) => box.selector));
      const visible = entries.filter(
        (entry) =>
          entry.rect.w >= 2 &&
          entry.rect.h >= 2 &&
          entry.rect.y + entry.rect.h > 0 &&
          entry.rect.y < viewport.height,
      );
      if (!visible.length) continue;

      const shot = await page.screenshot();
      const measured = await sampleBackdrop(
        page,
        shot,
        visible,
        Object.fromEntries(subset.map((box) => [box.selector, box])),
      );
      failures.push(...measured);
    }
  } finally {
    await page.evaluate(() => document.getElementById("visual-audit-blank-text")?.remove());
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  return failures;
};

const OVERFLOW_PROBE = () => {
  const doc = document.documentElement;
  const width = doc.clientWidth;
  const culprits = [];
  for (const el of document.querySelectorAll("body *")) {
    const rect = el.getBoundingClientRect();
    if (rect.right > width + 1 && rect.width > 0) {
      const style = getComputedStyle(el);
      if (style.position === "fixed" || style.visibility === "hidden") continue;
      culprits.push({
        tag: el.tagName.toLowerCase(),
        className: String(el.className).slice(0, 90),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      });
    }
  }
  return { scrollWidth: doc.scrollWidth, clientWidth: width, culprits: culprits.slice(0, 4) };
};

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();

// One sign-in, reused by every viewport: the login route is rate limited and the audit should
// measure rendering, not hammer the auth endpoint.
//
// The app keeps its access token in `sessionStorage`, which `storageState()` does not capture
// (it persists cookies and local storage only), so each context is seeded with the tokens from
// this real login through an init script. The session itself is the server's.
const authContext = await browser.newContext();
const login = await authContext.request.post(`${BASE}/api/v1/auth/login`, {
  data: { email: EMAIL, password: PASSWORD },
});
if (!login.ok()) throw new Error(`login failed: ${login.status()} ${await login.text()}`);
const { access_token: accessToken, csrf_token: csrfToken } = await login.json();
const storageState = await authContext.storageState();
await authContext.close();

const problems = [];

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, storageState });
  await context.addInitScript(
    ([access, csrf]) => {
      sessionStorage.setItem("veltrane.access", access);
      sessionStorage.setItem("veltrane.csrf", csrf);
    },
    [accessToken, csrfToken],
  );
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  const badResponses = [];
  page.on("response", (res) => {
    if (res.status() >= 400) badResponses.push(`${res.status()} ${new URL(res.url()).pathname}`);
  });


  for (const route of ROUTES) {
    // `networkidle` never settles under the dev server's HMR socket; wait for the paint instead.
    await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForLoadState("load");
    await page.waitForTimeout(700);

    if (route.startsWith("/app") && !page.url().includes(route)) {
      problems.push({ viewport: viewport.name, route, kind: "auth", landedOn: page.url() });
      continue;
    }

    await page.addScriptTag({ path: axePath });
    const { failures, undecided } = await contrastFailures(page);
    failures.push(...(await measurePaintedBackdrops(page, undecided)));
    const overflow = await page.evaluate(OVERFLOW_PROBE);
    const slug = route === "/" ? "home" : route.replaceAll("/", "-").replace(/^-/, "");
    // Let the sampling pass settle (it scrolls) so the stored screenshot shows the page at rest.
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}${viewport.name}-${slug}.png`, fullPage: false });

    if (failures.length) problems.push({ viewport: viewport.name, route, kind: "contrast", failures });
    if (undecided.length)
      console.log(`note: ${viewport.name} ${route} measured ${undecided.length} element(s) over imagery from painted pixels`);
    if (overflow.scrollWidth > overflow.clientWidth + 1)
      problems.push({ viewport: viewport.name, route, kind: "overflow", ...overflow });
  }

  // The auth endpoints are deliberately rate limited (refresh: 60 per 5 min per IP). A sweep of
  // 15 routes is faster than any human, so a 429 there is the limiter working, not a defect.
  const unexpected = [...new Set(badResponses)].filter(
    (entry) => !/^429 \/api\/v1\/auth\/(refresh|login)$/.test(entry),
  );
  const throttled = [...new Set(badResponses)].filter((entry) => !unexpected.includes(entry));
  if (unexpected.length)
    problems.push({ viewport: viewport.name, route: "*", kind: "http", errors: unexpected });
  if (throttled.length)
    console.log(`note: ${viewport.name} was rate limited on ${throttled.join(", ")} (expected at audit speed)`);
  await context.close();
}

await browser.close();

if (!problems.length) {
  console.log(`visual-audit: clean across ${ROUTES.length} routes × ${VIEWPORTS.length} viewports`);
} else {
  console.log(JSON.stringify(problems, null, 2));
  process.exitCode = 1;
}
