"use client";

import { AuthGuard } from "@/components/shared/AuthGuard";
import { TopNav } from "@/components/shared/TopNav";
import { MainNav } from "@/components/shared/MainNav";
import { ErrorBoundary } from "@/components/error-boundary";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen flex-col">
        <TopNav />
        <div className="border-b bg-background">
          <div className="mx-auto flex max-w-6xl items-center px-4 py-2 lg:px-6">
            <MainNav />
          </div>
        </div>
        <main className="flex-1 py-6">
          <div className="mx-auto max-w-6xl px-4 lg:px-6">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
