import type { Metadata } from "next";
import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
import { AuthRoot } from "@/components/app/gate";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in"
      description="Your workspace, your balances, your open contracts — exactly where you left them."
      width="sm"
      footer={
        <>
          New here?{" "}
          <Link href="/register" className="link-underline text-paper">
            Open an account
          </Link>
        </>
      }
    >
      <AuthRoot>
        <LoginForm />
      </AuthRoot>
    </AuthShell>
  );
}
