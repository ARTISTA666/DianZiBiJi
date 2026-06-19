"use client";

import { BookOpen, RefreshCw, LogOut } from "lucide-react";
import type { CurrentUser } from "@/lib/api";

interface TopHeaderProps {
  user: CurrentUser;
  token: string;
  onRefresh: () => void;
  onLogout: () => void;
}

export function TopHeader({ user, token, onRefresh, onLogout }: TopHeaderProps) {
  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6 lg:grid-cols-[1fr_auto]">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-brand text-white">
            <BookOpen size={22} />
          </div>
          <div>
            <h1 className="text-lg font-semibold">智能 ELN 工作台</h1>
            <p className="text-sm text-muted">{user.display_name} · {user.role}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRefresh}
            className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface"
          >
            <RefreshCw size={16} />
            刷新
          </button>
          <button
            onClick={onLogout}
            className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface"
          >
            <LogOut size={16} />
            退出
          </button>
        </div>
      </div>
    </header>
  );
}
