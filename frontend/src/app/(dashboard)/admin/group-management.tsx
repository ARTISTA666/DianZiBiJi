"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  addGroupMember,
  createGroup,
  removeGroupMember,
  type Group,
  type GroupMember,
  type User,
} from "@/lib/api";

interface Props {
  token: string;
  users: User[];
  groups: Group[];
  groupMembers: GroupMember[];
  selectedGroupId: string;
  usersById: Map<number, User>;
  busy: boolean;
  onSelectGroup: (id: string) => void;
  runAction: (action: () => Promise<unknown>, success: string) => Promise<boolean>;
}

export function GroupManagement({
  token,
  users,
  groups,
  groupMembers,
  selectedGroupId,
  usersById,
  busy,
  onSelectGroup,
  runAction,
}: Props) {
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [newGroupLeader, setNewGroupLeader] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState("member");

  const handleCreateGroup = async (event: FormEvent) => {
    event.preventDefault();
    let createdId: number | null = null;
    const succeeded = await runAction(async () => {
      const group = await createGroup(token, {
        name: newGroupName.trim(),
        description: newGroupDescription.trim() || undefined,
        leader_user_id: newGroupLeader ? Number(newGroupLeader) : null,
      });
      createdId = group.id;
    }, `小组 ${newGroupName.trim()} 已创建`);
    if (!succeeded) return;
    if (createdId !== null) onSelectGroup(String(createdId));
    setNewGroupName("");
    setNewGroupDescription("");
    setNewGroupLeader("");
  };

  return (
    <>
      <Card>
        <CardHeader><CardTitle className="text-base">创建小组</CardTitle></CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-3" onSubmit={handleCreateGroup}>
            <div className="space-y-1"><Label htmlFor="group-name">小组名称</Label><Input id="group-name" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} required /></div>
            <div className="space-y-1"><Label htmlFor="group-description">说明</Label><Input id="group-description" value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor="group-leader">负责人</Label><select id="group-leader" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={newGroupLeader} onChange={(event) => setNewGroupLeader(event.target.value)}><option value="">暂不指定</option>{users.filter((user) => user.status === "active").map((user) => <option key={user.id} value={user.id}>{user.display_name}（{user.username}）</option>)}</select></div>
            <Button className="md:col-span-3" type="submit" disabled={busy}>创建小组</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">小组成员</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1"><Label htmlFor="managed-group">管理小组</Label><select id="managed-group" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={selectedGroupId} onChange={(event) => onSelectGroup(event.target.value)}><option value="">请选择</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></div>
            <div className="space-y-1"><Label htmlFor="group-member-user">添加成员</Label><select id="group-member-user" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={memberUserId} onChange={(event) => setMemberUserId(event.target.value)}><option value="">请选择账号</option>{users.filter((user) => user.status === "active").map((user) => <option key={user.id} value={user.id}>{user.display_name}（{user.username}）</option>)}</select></div>
            <div className="space-y-1"><Label htmlFor="group-member-role">组内角色</Label><select id="group-member-role" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={memberRole} onChange={(event) => setMemberRole(event.target.value)}><option value="member">成员</option><option value="leader">负责人</option></select></div>
          </div>
          <Button disabled={busy || !selectedGroupId || !memberUserId} onClick={() => runAction(() => addGroupMember(token, Number(selectedGroupId), { user_id: Number(memberUserId), group_role: memberRole }), "小组成员已保存")}>添加或更新成员</Button>
          <div className="space-y-2">{groupMembers.map((member) => {
            const account = usersById.get(member.user_id);
            return <div key={member.id} data-testid={`group-member-${member.user_id}`} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"><span>{account?.display_name || `用户 #${member.user_id}`} · {member.group_role}</span><Button size="sm" variant="ghost" disabled={busy} onClick={() => runAction(() => removeGroupMember(token, member.group_id, member.user_id), "小组成员已移除")}>移除</Button></div>;
          })}{selectedGroupId && groupMembers.length === 0 && <p className="text-sm text-muted-foreground">该小组暂无成员。</p>}</div>
        </CardContent>
      </Card>
    </>
  );
}
