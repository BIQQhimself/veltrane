import { describe, expect, it } from "vitest";
import { ApiError, fieldErrors } from "./api";
import { PASSWORD_RULES, emailProblem, normalizeEmail, passwordIssues } from "./validation";

describe("fieldErrors", () => {
  it("keys messages by the failing input and drops the framework prefix", () => {
    const error = new ApiError(422, "validation_error", "Request validation failed.", {
      errors: [
        { loc: ["body", "email"], msg: "value is not a valid email address: The part after the @-sign is not valid." },
        { loc: ["body", "accept_terms"], msg: "Value error, You must accept the terms to create an account." },
      ],
    });

    expect(fieldErrors(error)).toEqual({
      email: "value is not a valid email address: The part after the @-sign is not valid.",
      accept_terms: "You must accept the terms to create an account.",
    });
  });

  it("keeps only the first message per field and ignores non-string locations", () => {
    const error = new ApiError(422, "validation_error", "Request validation failed.", {
      errors: [
        { loc: ["body", "password"], msg: "String should have at least 12 characters" },
        { loc: ["body", "password"], msg: "second message" },
        { loc: ["body", 0, "email"], msg: "nested" },
        { loc: "not-a-list", msg: "ignored" },
      ],
    });

    expect(fieldErrors(error)).toEqual({
      password: "String should have at least 12 characters",
      email: "nested",
    });
  });

  it("returns nothing for errors that carry no field detail", () => {
    expect(fieldErrors(new ApiError(500, "internal_error", "An unexpected error occurred."))).toEqual({});
    expect(fieldErrors(new Error("boom"))).toEqual({});
  });
});

describe("emailProblem", () => {
  it("rejects the addresses the browser accepts but the API refuses", () => {
    expect(emailProblem("trader@corvex")).toMatch(/including the domain/);
    expect(emailProblem("trader@localhost")).toMatch(/including the domain/);
    expect(emailProblem("trader@example..com")).not.toBeNull();
  });

  it("accepts ordinary addresses, with surrounding space ignored", () => {
    expect(emailProblem("  trader@example.com  ")).toBeNull();
    expect(emailProblem("first.last+tag@sub.example.co.uk")).toBeNull();
  });

  it("asks for an address when the field is empty", () => {
    expect(emailProblem("   ")).toMatch(/Enter your email/);
  });
});

describe("normalizeEmail", () => {
  it("trims without changing case", () => {
    expect(normalizeEmail("  Trader@Example.COM ")).toBe("Trader@Example.COM");
  });
});

describe("passwordIssues", () => {
  it("lists every unmet rule in the same order the API reports them", () => {
    expect(passwordIssues("short")).toEqual([
      "At least 12 characters",
      "An uppercase letter",
      "A number",
      "A symbol (for example ! ? # $)",
    ]);
  });

  it("is empty for a password that satisfies the policy", () => {
    expect(passwordIssues("Veltrane!Test2026")).toEqual([]);
    expect(PASSWORD_RULES.every((rule) => rule.test("Veltrane!Test2026"))).toBe(true);
  });
});
