import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getErrorMessage(e: unknown, fallback = "操作失败"): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return fallback;
}
