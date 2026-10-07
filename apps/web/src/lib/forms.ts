"use client";

import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { toast } from "sonner";

import { ApiError, fieldErrors, problemMessage } from "@/lib/problem";

/**
 * Apply an API error to a form: field errors go to their fields, anything else becomes a toast.
 * Returns true if at least one field error was set.
 */
export function applyApiError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): boolean {
  if (!(error instanceof ApiError)) {
    toast.error("Something went wrong. Try again.");
    return false;
  }
  const errors = fieldErrors(error.problem);
  let matched = false;
  for (const [name, message] of Object.entries(errors)) {
    if (fields.includes(name)) {
      setError(name as Path<T>, { type: "server", message });
      matched = true;
    }
  }
  if (!matched) toast.error(problemMessage(error.problem));
  return matched;
}
