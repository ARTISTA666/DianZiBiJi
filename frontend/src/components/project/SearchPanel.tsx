"use client";

import { FileSearch } from "lucide-react";
import { FormEvent } from "react";
import type { SearchResult } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface SearchPanelProps {
  searchQuery: string;
  onSearchQueryChange: (v: string) => void;
  searchResults: SearchResult[];
  searchBusy: boolean;
  selectedProjectId: number | null;
  onSearch: (e: FormEvent<HTMLFormElement>) => void;
}

export function SearchPanel({
  searchQuery,
  onSearchQueryChange,
  searchResults,
  searchBusy,
  selectedProjectId,
  onSearch,
}: SearchPanelProps) {
  if (!selectedProjectId) return null;

  return (
    <div className="grid gap-4">
      <div className={cardClass("p-5")}>
        <h2 className="flex items-center gap-2 font-semibold"><FileSearch size={18} />全文搜索</h2>
        <p className="mt-1 text-sm text-muted">在当前项目中搜索实验笔记的内容。</p>
        <form onSubmit={onSearch} className="mt-4 flex flex-wrap gap-2">
          <input
            className="min-w-[260px] flex-1 rounded-md border border-border px-3 py-2 text-sm"
            placeholder="输入搜索关键词"
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
          />
          <button disabled={searchBusy} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60">
            {searchBusy ? "搜索中..." : "搜索"}
          </button>
        </form>
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-sm text-muted">共找到 {searchResults.length} 条结果</p>
            {searchResults.map((result) => (
              <div key={result.document_id} className="rounded-md border border-border px-3 py-2 text-sm">
                <p className="font-medium">{result.title}</p>
                <p className="mt-1 text-muted line-clamp-2">{result.snippet}</p>
                <p className="mt-1 text-xs text-muted">实验笔记 ID: {result.note_id}</p>
              </div>
            ))}
          </div>
        )}
        {searchResults.length === 0 && searchQuery && !searchBusy && (
          <p className="mt-4 text-sm text-muted">未找到匹配结果。</p>
        )}
      </div>
    </div>
  );
}
