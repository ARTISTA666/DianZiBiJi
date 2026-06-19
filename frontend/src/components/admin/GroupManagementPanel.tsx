"use client";

import { FormEvent } from "react";
import { FolderPlus } from "lucide-react";
import type { Group, GroupMember, User } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface GroupManagementPanelProps {
  groups: Group[];
  selectedGroup: Group | null;
  selectedGroupId: number | null;
  groupMembers: GroupMember[];
  groupDraft: { user_id: string; group_role: string };
  onGroupDraftChange: (draft: { user_id: string; group_role: string }) => void;
  newGroup: { name: string; description: string; leader_user_id: string };
  onNewGroupChange: (g: { name: string; description: string; leader_user_id: string }) => void;
  users: User[];
  usersById: Map<number, User>;
  onSetSelectedGroupId: (id: number | null) => void;
  onSelectedGroupChange: (group: Group) => void;
  onCreateGroup: (e: FormEvent<HTMLFormElement>) => void;
  onUpdateGroup: () => void;
  onAddGroupMember: (e: FormEvent<HTMLFormElement>) => void;
  onRemoveGroupMember: (groupId: number, userId: number) => void;
}

export function GroupManagementPanel({
  groups,
  selectedGroup,
  selectedGroupId,
  groupMembers,
  groupDraft,
  onGroupDraftChange,
  newGroup,
  onNewGroupChange,
  users,
  usersById,
  onSetSelectedGroupId,
  onSelectedGroupChange,
  onCreateGroup,
  onUpdateGroup,
  onAddGroupMember,
  onRemoveGroupMember,
}: GroupManagementPanelProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {/* Create Group */}
      <form onSubmit={onCreateGroup} className={cardClass("p-5")}>
        <h2 className="flex items-center gap-2 font-semibold"><FolderPlus size={18} />小组管理</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <input
            className="rounded-md border border-border px-3 py-2"
            placeholder="小组名称"
            value={newGroup.name}
            onChange={(e) => onNewGroupChange({ ...newGroup, name: e.target.value })}
            required
          />
          <select
            className="rounded-md border border-border px-3 py-2"
            value={newGroup.leader_user_id}
            onChange={(e) => onNewGroupChange({ ...newGroup, leader_user_id: e.target.value })}
          >
            <option value="">小组负责人</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
          <textarea
            className="rounded-md border border-border px-3 py-2 md:col-span-2"
            placeholder="小组说明"
            value={newGroup.description}
            onChange={(e) => onNewGroupChange({ ...newGroup, description: e.target.value })}
          />
        </div>
        <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">
          <span>+</span>创建小组
        </button>
        <div className="mt-4 flex flex-wrap gap-2">
          {groups.map((g) => (
            <button
              type="button"
              key={g.id}
              onClick={() => onSetSelectedGroupId(g.id)}
              className={`rounded-md border px-3 py-2 text-sm ${selectedGroupId === g.id ? "border-brand bg-[#eef8f6]" : "border-border"}`}
            >
              {g.name}
            </button>
          ))}
        </div>
      </form>

      {/* Group Details */}
      {selectedGroup && (
        <div className={cardClass("p-5")}>
          <h2 className="font-semibold">小组详情</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <input
              className="rounded-md border border-border px-3 py-2"
              value={selectedGroup.name}
              onChange={(e) => onSelectedGroupChange({ ...selectedGroup, name: e.target.value })}
            />
            <select
              className="rounded-md border border-border px-3 py-2"
              value={selectedGroup.leader_user_id || ""}
              onChange={(e) =>
                onSelectedGroupChange({
                  ...selectedGroup,
                  leader_user_id: e.target.value ? Number(e.target.value) : null,
                })
              }
            >
              <option value="">小组负责人</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
            <textarea
              className="rounded-md border border-border px-3 py-2 md:col-span-2"
              value={selectedGroup.description || ""}
              onChange={(e) => onSelectedGroupChange({ ...selectedGroup, description: e.target.value })}
            />
          </div>
          <button type="button" onClick={onUpdateGroup} className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存小组</button>
          <div className="mt-4 border-t border-border pt-4">
            <form onSubmit={onAddGroupMember} className="flex flex-wrap gap-2">
              <select
                className="rounded-md border border-border px-3 py-2 text-sm"
                value={groupDraft.user_id}
                onChange={(e) => onGroupDraftChange({ ...groupDraft, user_id: e.target.value })}
                required
              >
                <option value="">选择成员</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
              </select>
              <input
                className="rounded-md border border-border px-3 py-2 text-sm"
                value={groupDraft.group_role}
                onChange={(e) => onGroupDraftChange({ ...groupDraft, group_role: e.target.value })}
              />
              <button className="rounded-md border border-border px-3 py-2 text-sm">添加/更新</button>
            </form>
            <div className="mt-3 flex flex-wrap gap-2">
              {groupMembers.map((member) => (
                <span key={member.id} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-1 text-xs">
                  {usersById.get(member.user_id)?.display_name || `用户 ${member.user_id}`} · {member.group_role}
                  <button
                    type="button"
                    onClick={() => onRemoveGroupMember(member.group_id, member.user_id)}
                    className="text-red-700"
                  >
                    移除
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
