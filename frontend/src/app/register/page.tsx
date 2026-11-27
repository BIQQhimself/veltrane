import type { Metadata } from "next";
import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
import { AuthRoot } from "@/components/app/gate";
import { RegisterForm } from "./register-form";

export const metadata: Metadata = { title: "Create your account" };

export default function RegisterPage() {
  return (
    <AuthShell
      eyebrow="New account"
      title="Open a workspace"
      description="Free tier, read-only connections and simulated execution from the first minute. No card, no custody, no live orders."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="link-underline text-paper">
            Sign in
          </Link>
        </>
      }
    >
      <AuthRoot>
        <RegisterForm />
      </AuthRoot>
    </AuthShell>
  );
}
