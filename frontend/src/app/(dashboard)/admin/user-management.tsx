"use client";

import { FormEvent, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createUser, updateUser, type User, type CurrentUser } from "@/lib/api";

const roles = ["super_admin", "pi", "group_leader", "project_owner", "reviewer", "member"];
const roleNames: Record<string, string> = {
  super_admin: "系统管理员",
  pi: "课题负责人",
  group_leader: "小组负责人",
  project_owner: "项目负责人",
  reviewer: "审核人员",
  member: "普通成员",
};

interface Props {
  token: string;
  currentUser: CurrentUser;
  users: User[];
  busy: boolean;
  runAction: (action: () => Promise<unknown>, success: string) => Promise<boolean>;
}

export function UserManagement({ token, currentUser, users, busy, runAction }: Props) {
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("member");

  const handleCreateUser = async (event: FormEvent) => {
    event.preventDefault();
    const succeeded = await runAction(
      () => createUser(token, {
        username: newUsername.trim(),
        password: newPassword,
        display_name: newDisplayName.trim(),
        email: newEmail.trim() || undefined,
        role: newRole,
      }),
      `账号 ${newUsername.trim()} 已创建`,
    );
    if (!succeeded) return;
    setNewUsername("");
    setNewDisplayName("");
    setNewEmail("");
    setNewPassword("");
    setNewRole("member");
  };

  return (
    <>
      <Card>
        <CardHeader><CardTitle className="text-base">创建账号</CardTitle></CardHeader>
        <CardContent>
          <form className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-5" onSubmit={handleCreateUser}>
            <div className="space-y-1"><Label htmlFor="new-username">账号</Label><Input id="new-username" value={newUsername} onChange={(event) => setNewUsername(event.target.value)} required /></div>
            <div className="space-y-1"><Label htmlFor="new-display-name">显示名</Label><Input id="new-display-name" value={newDisplayName} onChange={(event) => setNewDisplayName(event.target.value)} required /></div>
            <div className="space-y-1"><Label htmlFor="new-email">邮箱</Label><Input id="new-email" type="email" value={newEmail} onChange={(event) => setNewEmail(event.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor="new-password">初始密码</Label><Input id="new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={8} required /></div>
            <div className="space-y-1"><Label htmlFor="new-role">系统角色</Label><Select value={newRole} onValueChange={setNewRole}><SelectTrigger id="new-role"><SelectValue /></SelectTrigger><SelectContent>{roles.map((role) => <SelectItem key={role} value={role}>{roleNames[role]}</SelectItem>)}</SelectContent></Select></div>
            <Button className="col-span-1 md:col-span-2 lg:col-span-5" type="submit" disabled={busy}>创建账号</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">账号列表（{users.length}）</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>账号</TableHead><TableHead>显示名</TableHead><TableHead>角色</TableHead><TableHead>状态</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
            <TableBody>{users.map((user) => {
              const self = user.id === currentUser.id;
              return (
                <TableRow key={user.id} data-testid={`admin-user-${user.id}`}>
                  <TableCell>{user.username}<div className="text-xs text-muted-foreground">#{user.id} {user.email || ""}</div></TableCell>
                  <TableCell>{user.display_name}</TableCell>
                  <TableCell><Select value={user.role} disabled={busy || self} onValueChange={(value) => runAction(() => updateUser(token, user.id, { role: value }), `${user.username} 的角色已更新`)}><SelectTrigger aria-label={`${user.username} 系统角色`} className="h-9 w-auto min-w-[120px]"><SelectValue /></SelectTrigger><SelectContent>{roles.map((role) => <SelectItem key={role} value={role}>{roleNames[role]}</SelectItem>)}</SelectContent></Select></TableCell>
                  <TableCell><Badge variant={user.status === "active" ? "secondary" : "destructive"}>{user.status === "active" ? "启用" : "停用"}</Badge></TableCell>
                  <TableCell className="text-right"><Button size="sm" variant="outline" disabled={busy || self} onClick={() => runAction(() => updateUser(token, user.id, { status: user.status === "active" ? "disabled" : "active" }), `${user.username} 已${user.status === "active" ? "停用" : "启用"}`)}>{user.status === "active" ? `停用 ${user.username}` : `启用 ${user.username}`}</Button></TableCell>
                </TableRow>
              );
            })}</TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
