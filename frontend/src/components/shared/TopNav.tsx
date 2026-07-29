"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, LogOut, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";

export function TopNav() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const authBusy = useAuthStore((s) => s.busy);
  const changePassword = useAuthStore((s) => s.changePassword);

  const roleText: Record<string, string> = {
    super_admin: "超级管理员", pi: "PI", group_leader: "组长",
    project_owner: "项目负责人", reviewer: "审核人", member: "成员",
  };

  const [pwOpen, setPwOpen] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwBusy, setPwBusy] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch (error) {
      toast.error("退出失败，会话仍保持有效，请重试", {
        description: getErrorMessage(error),
      });
    }
  };

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setPwError("");
    setPwBusy(true);
    try {
      await changePassword(currentPw, newPw);
      setPwOpen(false);
      setCurrentPw("");
      setNewPw("");
    } catch (err) {
      setPwError(getErrorMessage(err, "修改密码失败"));
    } finally {
      setPwBusy(false);
    }
  };

  if (!user) return null;

  const initials = user.display_name.slice(0, 2);

  return (
    <>
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-14 items-center justify-between px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <BookOpen size={18} />
            </div>
            <span className="font-semibold text-sm">智能 ELN</span>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label="账户菜单" variant="ghost" size="sm" className="gap-2">
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="text-xs">{initials}</AvatarFallback>
                </Avatar>
                <span className="hidden sm:inline text-sm">{user.display_name}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>
                <p className="text-sm font-medium">{user.display_name}</p>
                <p className="text-xs text-muted-foreground">{roleText[user.role] || user.role}</p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setPwOpen(true)}>
                <KeyRound className="mr-2 h-4 w-4" />
                修改密码
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled={authBusy} onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                {authBusy ? "退出中..." : "退出登录"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <Dialog open={pwOpen} onOpenChange={setPwOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>修改密码</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleChangePassword} className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label htmlFor="current-pw">当前密码</Label>
              <Input id="current-pw" type="password" required value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)} placeholder="请输入当前密码" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-pw">新密码</Label>
              <Input id="new-pw" type="password" required minLength={8} value={newPw}
                onChange={(e) => setNewPw(e.target.value)} placeholder="至少 8 位" />
            </div>
            {pwError && <p className="text-sm text-destructive">{pwError}</p>}
            <Button type="submit" disabled={pwBusy} className="w-full">
              {pwBusy ? "更新中..." : "更新密码"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
