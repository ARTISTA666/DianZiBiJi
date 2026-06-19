"use client";

import { FormEvent } from "react";
import { Database, Users } from "lucide-react";
import type { Project, User, ProjectMember } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { projectRoleOptions } from "../constants";

interface MembersPanelProps {
  selectedProject: Project | null;
  selectedProjectId: number | null;
  members: ProjectMember[];
  users: User[];
  usersById: Map<number, User>;
  projectEdit: { name: string; description: string; is_sensitive: boolean; approval_enabled: boolean; owner_user_id: string; status: string };
  onProjectEditChange: (edit: MembersPanelProps["projectEdit"]) => void;
  memberDraft: { user_id: string; project_role: string; can_read: boolean; can_write: boolean; can_review: boolean; can_manage: boolean };
  onMemberDraftChange: (draft: MembersPanelProps["memberDraft"]) => void;
  canManageSelectedProject: boolean;
  onUpdateProject: (e: FormEvent<HTMLFormElement>) => void;
  onAddMember: (e: FormEvent<HTMLFormElement>) => void;
  onUpdateMember: (member: ProjectMember, payload: Partial<ProjectMember>) => void;
  onRemoveMember: (member: ProjectMember) => void;
  onAddReviewer: (member: ProjectMember) => void;
}

export function MembersPanel({
  selectedProject: _selectedProject,
  selectedProjectId,
  members,
  users,
  usersById,
  projectEdit,
  onProjectEditChange,
  memberDraft,
  onMemberDraftChange,
  canManageSelectedProject,
  onUpdateProject,
  onAddMember,
  onUpdateMember,
  onRemoveMember,
  onAddReviewer,
}: MembersPanelProps) {
  return (
    <div>
      {/* Project Settings (only visible to managers) */}
      {canManageSelectedProject && selectedProjectId && (
        <form onSubmit={onUpdateProject} className={cardClass("p-5 mb-4")}>
          <h2 className="flex items-center gap-2 font-semibold"><Database size={18} />项目设置</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <input
              className="rounded-md border border-border px-3 py-2"
              value={projectEdit.name}
              onChange={(e) => onProjectEditChange({ ...projectEdit, name: e.target.value })}
              required
            />
            <select
              className="rounded-md border border-border px-3 py-2"
              value={projectEdit.owner_user_id}
              onChange={(e) => onProjectEditChange({ ...projectEdit, owner_user_id: e.target.value })}
            >
              <option value="">项目负责人</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
            <select
              className="rounded-md border border-border px-3 py-2"
              value={projectEdit.status}
              onChange={(e) => onProjectEditChange({ ...projectEdit, status: e.target.value })}
            >
              <option value="active">active</option>
              <option value="archived">archived</option>
            </select>
            <textarea
              className="rounded-md border border-border px-3 py-2 md:col-span-2 xl:col-span-3"
              value={projectEdit.description}
              onChange={(e) => onProjectEditChange({ ...projectEdit, description: e.target.value })}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={projectEdit.is_sensitive}
                onChange={(e) => onProjectEditChange({ ...projectEdit, is_sensitive: e.target.checked })}
              />敏感项目
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={projectEdit.approval_enabled}
                onChange={(e) => onProjectEditChange({ ...projectEdit, approval_enabled: e.target.checked })}
              />启用审批
            </label>
            <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存项目</button>
          </div>
        </form>
      )}

      {/* Members */}
      <div className={cardClass("p-5")}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">成员权限</h2>
        </div>
        {selectedProjectId && canManageSelectedProject && (
          <form onSubmit={onAddMember} className="mb-5 grid gap-3 rounded-md border border-border bg-surface p-4 md:grid-cols-[1fr_1fr_auto]">
            <select
              className="rounded-md border border-border px-3 py-2"
              value={memberDraft.user_id}
              onChange={(e) => onMemberDraftChange({ ...memberDraft, user_id: e.target.value })}
              required
            >
              <option value="">选择授权用户</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name} · {u.role}</option>)}
            </select>
            <select
              className="rounded-md border border-border px-3 py-2"
              value={memberDraft.project_role}
              onChange={(e) => onMemberDraftChange({ ...memberDraft, project_role: e.target.value })}
            >
              {projectRoleOptions.map((role) => <option key={role}>{role}</option>)}
            </select>
            <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">添加成员</button>
            <div className="flex flex-wrap gap-4 text-sm md:col-span-3">
              {(["can_read", "can_write", "can_review", "can_manage"] as const).map((key) => (
                <label key={key} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={memberDraft[key]}
                    onChange={(e) => onMemberDraftChange({ ...memberDraft, [key]: e.target.checked })}
                  />
                  {key}
                </label>
              ))}
            </div>
          </form>
        )}
        <div className="flex flex-wrap gap-2">
          {members.map((member) => (
            <div key={member.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-xs">
              <span className="min-w-24 font-medium">
                {usersById.get(member.user_id)?.display_name || `用户 ${member.user_id}`}
              </span>
              <select
                disabled={!canManageSelectedProject}
                className="rounded-md border border-border px-2 py-1 disabled:opacity-60"
                value={member.project_role}
                onChange={(e) => onUpdateMember(member, { project_role: e.target.value })}
              >
                {projectRoleOptions.map((role) => <option key={role}>{role}</option>)}
              </select>
              {(["can_read", "can_write", "can_review", "can_manage"] as const).map((key) => (
                <label key={key} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    disabled={!canManageSelectedProject}
                    checked={member[key]}
                    onChange={(e) => onUpdateMember(member, { [key]: e.target.checked })}
                  />
                  {key.replace("can_", "")}
                </label>
              ))}
              {canManageSelectedProject && (
                <>
                  <button
                    type="button"
                    onClick={() => onAddReviewer(member)}
                    className="rounded-md border border-border px-2 py-1"
                  >
                    设为审核人
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemoveMember(member)}
                    className="rounded-md border border-red-200 px-2 py-1 text-red-700"
                  >
                    移除
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
