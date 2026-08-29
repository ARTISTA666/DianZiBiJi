"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, ShieldCheck, Network, Sparkles, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { SESSION_EXPIRED_FLAG } from "@/lib/permission-hints";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const token = useAuthStore((s) => s.token);
  const hydrated = useAuthStore((s) => s.hydrated);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sessionExpired, setSessionExpired] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (hydrated && token) router.replace("/projects");
  }, [hydrated, token, router]);

  // 会话过期被踢回登录页时展示一次性提示，读后即清除。
  useEffect(() => {
    try {
      if (sessionStorage.getItem(SESSION_EXPIRED_FLAG)) {
        sessionStorage.removeItem(SESSION_EXPIRED_FLAG);
        setSessionExpired(true);
      }
    } catch {
      // sessionStorage 不可用时忽略过期提示。
    }
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSessionExpired(false);
    setBusy(true);
    try {
      await login(username, password);
      router.push("/projects");
    } catch (err) {
      setError(getErrorMessage(err, "登录失败"));
    } finally {
      setBusy(false);
    }
  };

  if (hydrated && token) return null;

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-background bg-dot-grid p-4 sm:p-8 overflow-hidden">
      {/* Background radial gradient glow */}
      <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[500px] w-[500px] rounded-full bg-primary/10 blur-[120px] dark:bg-primary/15" />

      <div className="relative z-10 grid w-full max-w-4xl grid-cols-1 lg:grid-cols-12 gap-8 items-center">
        {/* Left branding banner */}
        <div className="lg:col-span-7 space-y-6 text-left p-2 sm:p-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            <Sparkles size={13} />
            下一代智能科研工作台 ELN v2.0
          </div>
          
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/25">
                <BookOpen size={26} className="stroke-[2.25]" />
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                智能电子实验笔记系统
              </h1>
            </div>
            <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
              融合知识图谱与 RAG 智能问答，实现实验数据可追溯、研究记录链上可存证的全流程科研管理平台。
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            <div className="flex items-start gap-2.5 rounded-xl border border-border/60 bg-card/60 p-3 backdrop-blur-sm">
              <ShieldCheck className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-foreground">双重存证与评审</p>
                <p className="text-[11px] text-muted-foreground">哈希校验与盲审机制</p>
              </div>
            </div>
            <div className="flex items-start gap-2.5 rounded-xl border border-border/60 bg-card/60 p-3 backdrop-blur-sm">
              <Network className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-foreground">知识图谱提取</p>
                <p className="text-[11px] text-muted-foreground">自动构建实体关系网</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 size={13} className="text-primary" /> 合规审计追溯
            </span>
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 size={13} className="text-primary" /> 多模态数据解析
            </span>
          </div>
        </div>

        {/* Right login form card */}
        <div className="lg:col-span-5 w-full">
          <Card className="w-full border-border/80 shadow-elevate backdrop-blur-md bg-card/90">
            <CardHeader className="space-y-1 pb-4">
              <CardTitle className="text-xl font-bold">用户登录</CardTitle>
              <CardDescription className="text-xs">
                输入您的账号和密码进入工作台
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sessionExpired && (
                <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-xs text-warning font-medium flex items-center gap-2" role="status">
                  <span>会话已过期，请重新登录</span>
                </div>
              )}
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="username" className="text-xs font-medium">账号</Label>
                  <Input
                    id="username"
                    required
                    autoFocus
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="请输入账号"
                    className="h-10 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password" className="text-xs font-medium">密码</Label>
                  <Input
                    id="password"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="请输入密码"
                    className="h-10 text-sm"
                  />
                </div>
                {error && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive font-medium">
                    {error}
                  </div>
                )}
                <Button type="submit" className="w-full h-10 font-semibold shadow-sm" disabled={busy} isLoading={busy}>
                  {busy ? "登录中..." : "登录"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
