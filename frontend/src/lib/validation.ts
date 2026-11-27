/**
 * Client-side rules that mirror the API so a form never sends a request the server is
 * guaranteed to reject. The server stays the authority; this only shortens the loop.
 */

export const PASSWORD_MIN_LENGTH = 12;

const PASSWORD_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/~`";

// The browser's type="email" check accepts "name@host" with no dot. The API (RFC-style
// validation) does not, so require a dotted domain here too.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/;

export function normalizeEmail(value: string): string {
  return value.trim();
}

export function emailProblem(value: string): string | null {
  const email = normalizeEmail(value);
  if (!email) return "Enter your email address.";
  if (!EMAIL_PATTERN.test(email)) {
    return "Enter a full email address, including the domain, e.g. name@example.com.";
  }
  return null;
}

export const PASSWORD_RULES = [
  { id: "length", label: `At least ${PASSWORD_MIN_LENGTH} characters`, test: (v: string) => v.length >= PASSWORD_MIN_LENGTH },
  { id: "lowercase", label: "A lowercase letter", test: (v: string) => /[a-z]/.test(v) },
  { id: "uppercase", label: "An uppercase letter", test: (v: string) => /[A-Z]/.test(v) },
  { id: "number", label: "A number", test: (v: string) => /[0-9]/.test(v) },
  {
    id: "symbol",
    label: "A symbol (for example ! ? # $)",
    test: (v: string) => [...PASSWORD_SYMBOLS].some((c) => v.includes(c)),
  },
] as const;

export const PASSWORD_HINT = `At least ${PASSWORD_MIN_LENGTH} characters, with upper and lower case, a number and a symbol.`;

export function passwordIssues(value: string): string[] {
  return PASSWORD_RULES.filter((rule) => !rule.test(value)).map((rule) => rule.label);
}
