"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getAuditLogs,
  getGroupMembers,
  getGroups,
  getUsers,
  type AuditLog as AuditLogType,
  type Group,
  type GroupMember,
  type User,
} from "@/lib/api";
import { useAuthStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { UserManagement } from "./user-management";
import { GroupManagement } from "./group-management";
import { AuditLog } from "./audit-log";

export default function AdminPage() {
  const token = useAuthStore((state) => state.token);
  const currentUser = useAuthStore((state) => state.user);
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogType[]>([]);
  const [groupMembers, setGroupMembers] = useState<GroupMember[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
  );

  const refresh = useCallback(async () => {
    if (!token || currentUser?.role !== "super_admin") return;
    const [nextUsers, nextGroups, nextLogs] = await Promise.all([
      getUsers(token),
      getGroups(token),
      getAuditLogs(token),
    ]);
    setUsers(nextUsers);
    setGroups(nextGroups);
    setAuditLogs(nextLogs);
    setSelectedGroupId((current) => current || (nextGroups[0] ? String(nextGroups[0].id) : ""));
  }, [token, currentUser?.role]);

  const refreshSelectedGroup = useCallback(async () => {
    if (!token || !selectedGroupId) {
      setGroupMembers([]);
      return;
    }
    setGroupMembers(await getGroupMembers(token, Number(selectedGroupId)));
  }, [token, selectedGroupId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    refresh()
      .catch((cause) => {
        if (active) setError(getErrorMessage(cause, "管理数据加载失败"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    refreshSelectedGroup().catch((cause) => {
      setError(getErrorMessage(cause, "小组成员加载失败"));
    });
  }, [refreshSelectedGroup]);

  const runAction = async (action: () => Promise<unknown>, success: string): Promise<boolean> => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      await refresh();
      await refreshSelectedGroup();
      setMessage(success);
      return true;
    } catch (cause) {
      setError(getErrorMessage(cause, "操作失败"));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (currentUser?.role !== "super_admin") {
    return <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">只有系统管理员可以访问此页面。</p>;
  }
  if (loading) return <p className="py-12 text-center text-sm text-muted-foreground">管理数据加载中...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">系统管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">维护账号、小组和全局审计记录</p>
      </div>
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive" role="alert">{error}</p>}
      {message && <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700" role="status">{message}</p>}

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">账号</TabsTrigger>
          <TabsTrigger value="groups">小组</TabsTrigger>
          <TabsTrigger value="audit">审计</TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="space-y-4">
          {token && (
            <UserManagement
              token={token}
              currentUser={currentUser}
              users={users}
              busy={busy}
              runAction={runAction}
            />
          )}
        </TabsContent>

        <TabsContent value="groups" className="space-y-4">
          {token && (
            <GroupManagement
              token={token}
              users={users}
              groups={groups}
              groupMembers={groupMembers}
              selectedGroupId={selectedGroupId}
              usersById={usersById}
              busy={busy}
              onSelectGroup={setSelectedGroupId}
              runAction={runAction}
            />
          )}
        </TabsContent>

        <TabsContent value="audit">
          {token && (
            <AuditLog
              token={token}
              auditLogs={auditLogs}
              usersById={usersById}
              busy={busy}
              onLogsUpdate={setAuditLogs}
              onError={setError}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
