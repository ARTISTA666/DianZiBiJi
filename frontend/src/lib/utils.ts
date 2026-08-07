import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import { withPermissionHint } from "./permission-hints";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getErrorMessage(e: unknown, fallback = "操作失败"): string {
  const base = e instanceof Error ? e.message : typeof e === "string" ? e : fallback;
  // 全局接入权限/状态指引，保证各调用点无需重复处理。
  return withPermissionHint(e, base);
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unitIndex]}`;
}
