"use client";

import { AuthGuard } from "@/components/shared/AuthGuard";
import { TopNav } from "@/components/shared/TopNav";
import { MainNav } from "@/components/shared/MainNav";
import { ErrorBoundary } from "@/components/error-boundary";
import { AgentAssistant } from "@/components/shared/AgentAssistant";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen flex-col bg-background bg-dot-grid">
        <TopNav />
        <div className="border-b border-border/60 bg-background/60 backdrop-blur-sm">
          <div className="mx-auto flex max-w-7xl items-center px-4 py-2 sm:px-6 lg:px-8">
            <MainNav />
          </div>
        </div>
        <main className="flex-1 py-6 sm:py-8">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </main>
        <AgentAssistant />
      </div>
    </AuthGuard>
  );
}
