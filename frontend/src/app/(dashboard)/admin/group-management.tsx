"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
  const [newGroupLeader, setNewGroupLeader] = useState("__none__");
  const [memberUserId, setMemberUserId] = useState("__none_user__");
  const [memberRole, setMemberRole] = useState("member");

  const handleSelectGroupChange = (value: string) => {
    onSelectGroup(value === "__none_group__" ? "" : value);
  };

  const handleCreateGroup = async (event: FormEvent) => {
    event.preventDefault();
    let createdId: number | null = null;
    const succeeded = await runAction(async () => {
      const group = await createGroup(token, {
        name: newGroupName.trim(),
        description: newGroupDescription.trim() || undefined,
        leader_user_id: newGroupLeader && newGroupLeader !== "__none__" ? Number(newGroupLeader) : null,
      });
      createdId = group.id;
    }, `小组 ${newGroupName.trim()} 已创建`);
    if (!succeeded) return;
    if (createdId !== null) onSelectGroup(String(createdId));
    setNewGroupName("");
    setNewGroupDescription("");
    setNewGroupLeader("__none__");
  };

  return (
    <>
      <Card>
        <CardHeader><CardTitle className="text-base">创建小组</CardTitle></CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-3" onSubmit={handleCreateGroup}>
            <div className="space-y-1"><Label htmlFor="group-name">小组名称</Label><Input id="group-name" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} required /></div>
            <div className="space-y-1"><Label htmlFor="group-description">说明</Label><Input id="group-description" value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor="group-leader">负责人</Label><Select value={newGroupLeader} onValueChange={setNewGroupLeader}><SelectTrigger id="group-leader"><SelectValue placeholder="暂不指定" /></SelectTrigger><SelectContent><SelectItem value="__none__">暂不指定</SelectItem>{users.filter((user) => user.status === "active").map((user) => <SelectItem key={user.id} value={String(user.id)}>{user.display_name}（{user.username}）</SelectItem>)}</SelectContent></Select></div>
            <Button className="md:col-span-3" type="submit" disabled={busy}>创建小组</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">小组成员</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1"><Label htmlFor="managed-group">管理小组</Label><Select value={selectedGroupId || "__none_group__"} onValueChange={handleSelectGroupChange}><SelectTrigger id="managed-group"><SelectValue placeholder="请选择" /></SelectTrigger><SelectContent><SelectItem value="__none_group__">请选择</SelectItem>{groups.map((group) => <SelectItem key={group.id} value={String(group.id)}>{group.name}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1"><Label htmlFor="group-member-user">添加成员</Label><Select value={memberUserId} onValueChange={setMemberUserId}><SelectTrigger id="group-member-user"><SelectValue placeholder="请选择账号" /></SelectTrigger><SelectContent><SelectItem value="__none_user__">请选择账号</SelectItem>{users.filter((user) => user.status === "active").map((user) => <SelectItem key={user.id} value={String(user.id)}>{user.display_name}（{user.username}）</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1"><Label htmlFor="group-member-role">组内角色</Label><Select value={memberRole} onValueChange={setMemberRole}><SelectTrigger id="group-member-role"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="member">成员</SelectItem><SelectItem value="leader">负责人</SelectItem></SelectContent></Select></div>
          </div>
          <Button disabled={busy || !selectedGroupId || selectedGroupId === "__none_group__" || !memberUserId || memberUserId === "__none_user__"} onClick={() => runAction(() => addGroupMember(token, Number(selectedGroupId), { user_id: Number(memberUserId), group_role: memberRole }), "小组成员已保存")}>添加或更新成员</Button>
          <div className="space-y-2">{groupMembers.map((member) => {
            const account = usersById.get(member.user_id);
            return <div key={member.id} data-testid={`group-member-${member.user_id}`} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"><span>{account?.display_name || `用户 #${member.user_id}`} · {member.group_role}</span><Button size="sm" variant="ghost" disabled={busy} onClick={() => runAction(() => removeGroupMember(token, member.group_id, member.user_id), "小组成员已移除")}>移除</Button></div>;
          })}{selectedGroupId && groupMembers.length === 0 && <p className="text-sm text-muted-foreground">该小组暂无成员。</p>}</div>
        </CardContent>
      </Card>
    </>
  );
}
