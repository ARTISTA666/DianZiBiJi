"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const hydrated = useAuthStore((s) => s.hydrated);
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!hydrated) {
      // Try to restore the session from the HttpOnly auth cookie
      refreshUser().finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, [hydrated, refreshUser]);

  useEffect(() => {
    if (!checking && !token) {
      window.location.replace("/login");
    }
  }, [checking, token]);

  if (checking || !token) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  return <>{children}</>;
}
