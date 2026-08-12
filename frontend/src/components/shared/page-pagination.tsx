"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface PagePaginationProps {
  /** 当前页起始条目序号（从 1 计）。 */
  startItem: number;
  /** 当前页结束条目序号。 */
  endItem: number;
  total: number;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  /** 可选页码信息，如「第 1 / 3 页」。 */
  pageInfo?: string;
  /** 起止数字间的分隔符，保持各调用点原有字符（– 或 -）。 */
  separator?: string;
  className?: string;
}

/**
 * 统一的「上一页/下一页」分页条，合并项目列表与笔记列表两套实现。
 */
export function PagePagination({
  startItem,
  endItem,
  total,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
  pageInfo,
  separator = "–",
  className,
}: PagePaginationProps) {
  return (
    <div className={cn("flex items-center justify-between", className)}>
      <p className="text-sm text-muted-foreground">
        第 {startItem}{separator}{endItem} 条，共 {total} 条
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrev}
          onClick={onPrev}
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          上一页
        </Button>
        {pageInfo && (
          <span className="text-sm text-muted-foreground">{pageInfo}</span>
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={onNext}
        >
          下一页
          <ChevronRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
