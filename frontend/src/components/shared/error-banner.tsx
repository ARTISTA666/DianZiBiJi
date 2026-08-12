import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface ErrorBannerProps {
  /** 错误文案；提供 children 时以 children 为准。 */
  message?: string;
  /** 特殊结构（如附带关闭/重试按钮）时传入完整内容。 */
  children?: ReactNode;
  className?: string;
}

/**
 * 统一的页面级错误提示条。
 * 样式沿用原各页面复制的内联错误段落样式，附带 role="alert" 便于无障碍定位。
 */
export function ErrorBanner({ message, children, className }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive",
        className
      )}
    >
      {children ?? message}
    </div>
  );
}
