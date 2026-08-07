"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getAuditLogs,
  getGroupMembers,
  getGroups,
  getProjectsPaginated,
  getUsers,
  type AuditLog as AuditLogType,
  type Group,
  type GroupMember,
  type Project,
  type User,
} from "@/lib/api";
import { useAuthStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { UserManagement } from "./user-management";
import { GroupManagement } from "./group-management";
import { AuditLog } from "./audit-log";

export default function AdminPage() {
  const token = useAuthStore((state) => state.token);
  const currentUser = useAuthStore((state) => state.user);
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogType[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [groupMembers, setGroupMembers] = useState<GroupMember[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const feedback = useActionFeedback();

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
  );

  const refresh = useCallback(async () => {
    if (!token || currentUser?.role !== "super_admin") return;
    // 审计筛选用项目下拉；后端单页上限 100，逐页拉取全量避免一次拉取过大。
    const fetchAllProjects = async () => {
      const all: Project[] = [];
      let skip = 0;
      const limit = 100;
      for (;;) {
        const page = await getProjectsPaginated(token, skip, limit);
        all.push(...page.items);
        skip += limit;
        if (page.items.length < limit || skip >= page.total) break;
      }
      return all;
    };
    const [nextUsers, nextGroups, nextLogs, nextProjects] = await Promise.all([
      getUsers(token),
      getGroups(token),
      getAuditLogs(token),
      fetchAllProjects(),
    ]);
    setUsers(nextUsers.items);
    setGroups(nextGroups);
    setAuditLogs(nextLogs.items);
    setAuditTotal(nextLogs.total);
    setProjects(nextProjects);
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
    try {
      await action();
      await refresh();
      await refreshSelectedGroup();
      feedback.success(success);
      return true;
    } catch (cause) {
      const msg = getErrorMessage(cause, "操作失败");
      setError(msg);
      feedback.error(msg);
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (currentUser?.role !== "super_admin") {
    return <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">只有系统管理员可以访问此页面。</p>;
  }
  if (loading) return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-60" />
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">系统管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">维护账号、小组和全局审计记录</p>
      </div>
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive" role="alert">{error}</p>}

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
              auditTotal={auditTotal}
              usersById={usersById}
              projects={projects}
              busy={busy}
              onLogsUpdate={(logs, total) => {
                setAuditLogs(logs);
                setAuditTotal(total);
              }}
              onError={setError}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
