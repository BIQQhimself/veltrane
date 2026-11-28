/**
 * Real-browser journeys for VELTRANE.
 *
 * These run against a live stack (web on :3000, API on :8000 by default) and drive the
 * product the way a customer does: register, verify, sign in, look at the dashboard, try to
 * trade, hit the plan gate, and check the admin boundary. They assert observable UI state and
 * cross-check the API, so a screenshot-only regression cannot pass.
 *
 * Usage:
 *   node e2e/journeys.mjs
 *   E2E_WEB=http://localhost:3000 E2E_API=http://localhost:8000 node e2e/journeys.mjs
 *
 * The API must run with the mock payment provider enabled (development configuration) so a
 * Basic account can be created without a real card. No live order is ever submitted: every
 * journey stays in paper/demo mode.
 */
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const WEB = (process.env.E2E_WEB ?? "http://localhost:3000").replace(/\/$/, "");
const API = (process.env.E2E_API ?? "http://localhost:8000").replace(/\/$/, "");
const API_V1 = `${API}/api/v1`;
const PASSWORD = "Veltrane!Journey2026";
// Registration is limited to 5 per hour per IP on purpose. Journeys reuse the accounts they
// created on earlier runs instead of consuming that budget every time.
const ACCOUNTS_FILE = new URL("./.accounts.json", import.meta.url);

const results = [];

function record(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

async function api(path, { method = "GET", body, token } = {}) {
  const response = await fetch(`${API_V1}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  return { status: response.status, json, text };
}

function readAccounts() {
  try {
    return JSON.parse(readFileSync(ACCOUNTS_FILE, "utf8"));
  } catch {
    return {};
  }
}

function writeAccounts(accounts) {
  writeFileSync(ACCOUNTS_FILE, JSON.stringify(accounts, null, 2));
}

/** Reuses a saved account when it still signs in, otherwise registers a fresh one. */
async function createAccount(tag) {
  const accounts = readAccounts();
  const saved = accounts[tag];
  if (saved?.email) {
    const session = await api("/auth/login", { method: "POST", body: { email: saved.email, password: PASSWORD } });
    if (session.status === 200) {
      return { email: saved.email, token: session.json.access_token, csrf: session.json.csrf_token ?? null };
    }
  }
  const created = await registerAccount(tag);
  accounts[tag] = { email: created.email };
  writeAccounts(accounts);
  return created;
}

/** Registers through the public API, verifies the address, and returns a usable session. */
async function registerAccount(tag) {
  const email = `journey-${tag}-${Date.now()}@example.com`;
  const registered = await api("/auth/register", {
    method: "POST",
    body: {
      email,
      password: PASSWORD,
      full_name: `Journey ${tag}`,
      country: "GB",
      accept_terms: true,
    },
  });
  if (registered.status === 429) {
    throw new Error(
      "register rate limit reached (5 per hour per IP). Clear the rl:register bucket or wait; " +
        "the harness reuses accounts from e2e/.accounts.json when they exist.",
    );
  }
  if (registered.status !== 200 && registered.status !== 201) {
    throw new Error(`register failed: ${registered.status} ${registered.text}`);
  }
  const debugToken = registered.json?.debug_verification_token;
  if (debugToken) {
    await api("/auth/verify-email", { method: "POST", body: { token: debugToken } });
  }
  const session = await signIn(email);
  return { email, ...session };
}

async function signIn(email) {
  const login = await api("/auth/login", { method: "POST", body: { email, password: PASSWORD } });
  if (login.status !== 200) throw new Error(`login failed: ${login.status} ${login.text}`);
  return { token: login.json.access_token, csrf: login.json.csrf_token ?? null };
}

async function subscribe(token, planCode) {
  const checkout = await api("/billing/checkout", {
    method: "POST",
    body: { plan_code: planCode },
    token,
  });
  if (checkout.status !== 200) throw new Error(`checkout failed: ${checkout.status} ${checkout.text}`);
  const done = await api("/billing/mock/complete", {
    method: "POST",
    body: { checkout_token: checkout.json.checkout_token },
    token,
  });
  if (done.status !== 200) throw new Error(`mock payment failed: ${done.status} ${done.text}`);
}

async function seedSession(context, account) {
  await context.addInitScript(
    ([access, csrf]) => {
      sessionStorage.setItem("veltrane.access", access);
      if (csrf) sessionStorage.setItem("veltrane.csrf", csrf);
    },
    [account.token, account.csrf],
  );
}

/** The app polls live data, so "networkidle" never fires: wait for paint instead. */
async function settle(page, ms = 1500) {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(ms);
}

/**
 * Ticking the terms box before hydration flips the DOM but not React state, leaving the
 * submit button disabled. Retry until React has taken the input and enabled the button.
 */
async function acceptTerms(page) {
  const button = page.getByRole("button", { name: /create account/i });
  const box = page.locator('input[type="checkbox"]').first();
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (!(await button.isDisabled())) return;
    if (await box.isChecked()) await box.uncheck();
    await box.check();
    await page.waitForTimeout(250);
  }
  throw new Error("the terms checkbox never enabled the submit button");
}

/** Desktop uses Call/Put buttons; the phone ticket uses Up/Down. Pick whichever is mounted. */
async function pickDirection(page, direction) {
  const patterns =
    direction === "call"
      ? [/^up · /i, /^call\b/i]
      : [/^down · /i, /^put\b/i];
  for (const pattern of patterns) {
    const locator = page.getByRole("button", { name: pattern });
    if ((await locator.count()) > 0) {
      await locator.first().click();
      return;
    }
  }
  throw new Error(`no ${direction} control on the terminal`);
}

async function bodyText(page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ");
}

async function main() {
  const browser = await chromium.launch();

  // ---------------------------------------------------------------- journey 1
  // Registration through the UI, then the Free dashboard.
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    const email = `ui-register-${Date.now()}@example.com`;

    await page.goto(`${WEB}/register`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500); // let React hydrate before typing into controlled inputs
    await page.fill("#full_name", "Journey Customer");
    await page.fill("#email", email);
    await page.selectOption("#country", "GB");
    await page.fill("#password", PASSWORD);
    await acceptTerms(page);
    await page.getByRole("button", { name: /create account/i }).click();
    await settle(page);

    const registered = (await bodyText(page)).toLowerCase();
    record(
      "registration creates an account and moves to verification",
      /verify|check your inbox|verification/.test(registered),
      page.url(),
    );

    const blockedLogin = await api("/auth/login", { method: "POST", body: { email, password: PASSWORD } });
    record(
      "an unverified address cannot sign in",
      blockedLogin.status === 403,
      `status ${blockedLogin.status}`,
    );

    const fatal = consoleErrors.filter((line) => !/favicon|Failed to load resource/i.test(line));
    record("the registration page logs no console errors", fatal.length === 0, fatal.slice(0, 2).join(" | "));
    await context.close();
  }

  // ---------------------------------------------------------------- journey 2
  // Free customer: dashboard, and the terminal refusing to execute.
  const free = await createAccount("free");
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await seedSession(context, free);
    const page = await context.newPage();

    await page.goto(`${WEB}/app`, { waitUntil: "domcontentloaded" });
    await settle(page);
    const dashboard = (await bodyText(page)).toLowerCase();
    record("the dashboard renders for a Free customer", dashboard.includes("executions today"), page.url());
    record(
      "the dashboard states that the plan does not include execution",
      dashboard.includes("does not include execution") || dashboard.includes("0 / 0"),
    );

    await page.goto(`${WEB}/app/terminal`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await pickDirection(page, "call");
    await page.getByRole("button", { name: /confirm (call|put)/i }).click();
    await page.waitForTimeout(1500);

    const afterAttempt = (await bodyText(page)).toLowerCase();
    record(
      "the terminal surfaces the plan refusal instead of opening a contract",
      /rejected|does not include trade execution|upgrade/.test(afterAttempt),
    );

    const contracts = await api("/binary/contracts", { token: free.token });
    const opened = (contracts.json?.contracts ?? []).filter((c) => c.status === "open");
    record("no contract was opened for a Free customer", opened.length === 0, `${opened.length} open`);
    await context.close();
  }

  // ---------------------------------------------------------------- journey 3
  // Basic customer: a simulated contract actually opens and appears in the book.
  const basic = await createAccount("basic");
  await subscribe(basic.token, "basic");
  const basicSession = await signIn(basic.email);
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await seedSession(context, basicSession);
    const page = await context.newPage();

    await page.goto(`${WEB}/app/terminal`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await pickDirection(page, "call");
    await page.getByRole("button", { name: /confirm call/i }).click();
    await page.waitForTimeout(2000);

    const contracts = await api("/binary/contracts", { token: basicSession.token });
    const open = (contracts.json?.contracts ?? []).filter((c) => c.status === "open");
    record("a Basic customer can open a simulated contract", open.length === 1, `${open.length} open`);
    record(
      "the opened contract is labelled as simulated",
      open[0]?.is_demo === true && open[0]?.mode === "paper",
      `mode=${open[0]?.mode} is_demo=${open[0]?.is_demo}`,
    );

    const text = (await bodyText(page)).toLowerCase();
    record("the terminal shows the open position", /open|contract/.test(text));
    await context.close();
  }

  // ---------------------------------------------------------------- journey 4
  // Mobile layout: the one-tap ticket stays reachable without horizontal overflow.
  {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      deviceScaleFactor: 3,
    });
    await seedSession(context, basicSession);
    const page = await context.newPage();
    await page.goto(`${WEB}/app/terminal`, { waitUntil: "domcontentloaded" });
    await settle(page);

    const up = page.getByRole("button", { name: /^up · /i });
    const down = page.getByRole("button", { name: /^down · /i });
    record("mobile ticket exposes both directions", (await up.count()) > 0 && (await down.count()) > 0);
    record("mobile Up button is inside the viewport", await up.first().isVisible());

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    record("the terminal does not scroll horizontally on a phone", overflow <= 1, `${overflow}px`);
    await context.close();
  }

  // ---------------------------------------------------------------- journey 5
  // A subscriber must not reach the admin command centre.
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await seedSession(context, basicSession);
    const page = await context.newPage();
    await page.goto(`${WEB}/admin`, { waitUntil: "domcontentloaded" });
    await settle(page);
    const text = (await bodyText(page)).toLowerCase();
    const denied = !/user management|revenue|audit log/.test(text);
    record("a subscriber cannot open the admin command centre", denied, page.url());
    await context.close();
  }

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} journeys passed`);
  if (failed.length) {
    console.log("Failed:");
    for (const item of failed) console.log(` - ${item.name}${item.detail ? ` (${item.detail})` : ""}`);
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error("Journey run aborted:", error);
  process.exitCode = 1;
});
