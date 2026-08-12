"use client";

import { useEffect, useState, type RefObject } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const statusFilterOptions = [
  { value: "all", label: "全部状态" },
  { value: "draft", label: "草稿" },
  { value: "submitted", label: "待审核" },
  { value: "approved", label: "已审核" },
  { value: "returned", label: "已退回" },
  { value: "archived", label: "已归档" },
  { value: "voided", label: "已作废" },
];

const sortOptions = [
  { value: "updated_desc", label: "最新更新" },
  { value: "updated_asc", label: "最早更新" },
  { value: "created_desc", label: "最新创建" },
];

interface NoteFiltersProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  statusFilter: string;
  onStatusChange: (value: string) => void;
  sortBy: string;
  onSortChange: (value: string) => void;
  onNewNote: () => void;
  canWrite: boolean;
  /** 搜索输入框 ref，供页面快捷键 "/" 聚焦 */
  searchInputRef?: RefObject<HTMLInputElement | null>;
}

export function NoteFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusChange,
  sortBy,
  onSortChange,
  onNewNote,
  canWrite,
  searchInputRef,
}: NoteFiltersProps) {
  // 本地输入态 + 300ms 防抖后回调，输入即时、过滤延迟，不改变 onSearchChange 语义。
  const [inputValue, setInputValue] = useState(searchQuery);

  useEffect(() => {
    setInputValue(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (inputValue !== searchQuery) onSearchChange(inputValue);
    }, 300);
    return () => clearTimeout(timer);
  }, [inputValue, searchQuery, onSearchChange]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select value={statusFilter} onValueChange={onStatusChange}>
        <SelectTrigger className="w-[130px]">
          <SelectValue placeholder="状态筛选" />
        </SelectTrigger>
        <SelectContent>
          {statusFilterOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="relative flex-1 min-w-[180px] max-w-sm">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={searchInputRef}
          placeholder="搜索笔记标题..."
          title="按 / 聚焦搜索框"
          className="pl-8"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground whitespace-nowrap">排序:</span>
        <Select value={sortBy} onValueChange={onSortChange}>
          <SelectTrigger className="w-[120px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sortOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {canWrite && (
        <div className="ml-auto flex items-center gap-2">
          {/* 页面主 CTA：使用默认 size，作为操作条唯一视觉焦点 */}
          <Button onClick={onNewNote} title="快捷键 N">
            <Plus className="mr-2 h-4 w-4" />
            新建笔记
          </Button>
          {/* kbd 提示置于按钮外部，避免污染按钮 accessible name（E2E 按精确名称匹配） */}
          <kbd aria-hidden="true" className="hidden items-center rounded border border-border bg-muted px-1.5 text-[10px] leading-5 text-muted-foreground sm:inline-flex">N</kbd>
        </div>
      )}
    </div>
  );
}
