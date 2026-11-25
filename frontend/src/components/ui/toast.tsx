"use client";

import * as React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/cn";

type ToastTone = "success" | "error" | "info" | "warn";
type Toast = { id: number; tone: ToastTone; title: string; description?: string };

type ToastContextValue = {
  push: (toast: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

const icons: Record<ToastTone, React.ReactNode> = {
  success: <CheckCircle2 className="h-4 w-4 text-gain" />,
  error: <XCircle className="h-4 w-4 text-loss" />,
  info: <Info className="h-4 w-4 text-info" />,
  warn: <AlertTriangle className="h-4 w-4 text-warn" />,
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const counter = React.useRef(0);

  const remove = React.useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = React.useCallback(
    (toast: Omit<Toast, "id">) => {
      counter.current += 1;
      const id = counter.current;
      setToasts((current) => [...current.slice(-3), { ...toast, id }]);
      window.setTimeout(() => remove(id), toast.tone === "error" ? 7000 : 4500);
    },
    [remove],
  );

  const value = React.useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, description) => push({ tone: "success", title, description }),
      error: (title, description) => push({ tone: "error", title, description }),
      info: (title, description) => push({ tone: "info", title, description }),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto flex animate-fade-up items-start gap-3 rounded-lg border bg-ink-850 px-4 py-3 shadow-lift",
              toast.tone === "success" && "border-gain/30",
              toast.tone === "error" && "border-loss/30",
              toast.tone === "warn" && "border-warn/30",
              toast.tone === "info" && "border-line-strong",
            )}
            role={toast.tone === "error" ? "alert" : "status"}
          >
            <span className="mt-0.5 shrink-0">{icons[toast.tone]}</span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-paper">{toast.title}</p>
              {toast.description ? <p className="mt-0.5 text-xs text-paper-faint">{toast.description}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => remove(toast.id)}
              className="shrink-0 text-paper-faint transition hover:text-paper"
              aria-label="Dismiss notification"
            >
              <XCircle className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
