"use client";

import "./globals.css";

/**
 * Last-resort boundary for errors in the root layout itself (shell, providers, sign-in gate).
 * It replaces the root layout, so it renders its own html and body.
 */
export default function GlobalError({ error, retry }: { error: unknown; retry: () => void }) {
  const message = error instanceof Error ? error.message : "An unexpected error occurred.";
  return (
    <html lang="en" className="dark">
      <body className="flex min-h-dvh items-center justify-center bg-background p-6 text-foreground">
        <main role="alert" className="max-w-md rounded-lg border border-critical/40 bg-hull p-6">
          <h1 className="font-heading text-xl font-semibold">ASTRA-MED could not start this view</h1>
          <p className="mt-2 text-sm text-ink-2">{message}</p>
          <p className="mt-2 text-sm text-ink-2">
            Live monitoring continues on the server. Try again; if it keeps failing, check that the API is running.
          </p>
          <button
            type="button"
            onClick={() => retry()}
            className="mt-4 rounded-md bg-telemetry px-3 py-1.5 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
