"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";
import { toast, Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, problemMessage } from "@/lib/problem";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
          },
          mutations: {
            // Forms show field errors themselves; everything else surfaces as a toast.
            onError: (error) => {
              if (error instanceof ApiError && error.code === "validation_error") return;
              toast.error(error instanceof ApiError ? problemMessage(error.problem) : "Something went wrong. Try again.");
            },
          },
        },
      }),
  );
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <TooltipProvider>{children}</TooltipProvider>
        {/* Our own colours: Sonner's "rich colours" green fails WCAG AA contrast (4.25:1). */}
        <Toaster
          position="top-center"
          toastOptions={{
            classNames: {
              toast: "!border !border-border !bg-card !text-card-foreground !font-sans !text-base",
              success: "[&_[data-icon]]:!text-primary",
              error: "!border-destructive/50 [&_[data-icon]]:!text-destructive",
            },
          }}
        />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
