"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores";
import { FullScreenLoadingSkeleton } from "@/components/skeletons";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const hydrated = useAuthStore((s) => s.hydrated);
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const login = useAuthStore((s) => s.login);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;

    const initAuth = async () => {
      // 1. 尝试从既有 Cookie 恢复会话
      if (!hydrated) {
        try {
          await refreshUser();
        } catch {
          // 忽略初次未登录异常
        }
      }

      if (!active) return;

      const currentToken = useAuthStore.getState().token;
      if (currentToken) {
        setChecking(false);
        return;
      }

      // 2. 支持直达免密预览模式（?demo=true / ?preview=true / ?autologin=true）
      if (typeof window !== "undefined") {
        const search = window.location.search;
        const params = new URLSearchParams(search);
        const isDemo =
          params.get("demo") === "true" ||
          params.get("preview") === "true" ||
          params.get("autologin") === "true";

        if (isDemo) {
          try {
            await login("admin", "admin123");
            if (active) {
              setChecking(false);
              return;
            }
          } catch (e) {
            console.error("Demo auto login failed:", e);
          }
        }
      }

      if (active) {
        setChecking(false);
      }
    };

    void initAuth();

    return () => {
      active = false;
    };
  }, [hydrated, refreshUser, login]);

  useEffect(() => {
    if (!checking && !token) {
      const currentPath =
        typeof window !== "undefined"
          ? window.location.pathname + window.location.search
          : "";
      const redirectUrl = currentPath
        ? `/login?redirect=${encodeURIComponent(currentPath)}`
        : "/login";
      window.location.replace(redirectUrl);
    }
  }, [checking, token]);

  if (checking || !token) {
    return <FullScreenLoadingSkeleton />;
  }

  return <>{children}</>;
}
