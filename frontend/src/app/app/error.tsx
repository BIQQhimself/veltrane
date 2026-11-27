"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";

/**
 * Without a boundary here a render error anywhere in the workspace replaced the whole
 * document with Next's built-in page, losing the shell and the reason. This keeps the
 * user inside the product and shows the digest support can trace.
 */
export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl px-6 py-20" role="alert">
      <p className="text-3xs uppercase tracking-label text-paper-faint">Something broke</p>
      <h1 className="mt-2 text-xl font-medium text-paper">This screen could not be rendered</h1>
      <p className="mt-3 text-sm leading-relaxed text-paper-muted">
        Nothing was submitted and no order was sent — this is a display failure. Try again, and if it
        keeps happening send the reference below to support.
      </p>
      <p className="mt-4 break-words rounded-lg border border-line-soft bg-obsidian-900/60 p-3 font-mono text-2xs text-paper-faint">
        {error.message || "Unknown error"}
        {error.digest ? ` · ${error.digest}` : null}
      </p>
      <div className="mt-5 flex gap-2">
        <Button onClick={reset}>Try again</Button>
        <Button variant="ghost" onClick={() => window.location.reload()}>
          Reload the page
        </Button>
      </div>
    </div>
  );
}
