"use client";

import { FormEvent } from "react";
import { UserPlus, Users } from "lucide-react";
import type { User, CurrentUser } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { roleOptions } from "../constants";

interface UserManagementPanelProps {
  users: User[];
  currentUser: CurrentUser;
  userEdits: Record<number, { display_name: string; email: string; role: string; status: string; password: string }>;
  onUserEditChange: (userId: number, edit: { display_name: string; email: string; role: string; status: string; password: string }) => void;
  newUser: { username: string; password: string; display_name: string; email: string; role: string };
  onNewUserChange: (u: { username: string; password: string; display_name: string; email: string; role: string }) => void;
  token: string;
  onCreateUser: (e: FormEvent<HTMLFormElement>) => void;
  onUpdateUser: (user: User) => void;
  onDisableUser: (userId: number) => void;
}

export function UserManagementPanel({
  users,
  currentUser,
  userEdits,
  onUserEditChange,
  newUser,
  onNewUserChange,
  token: _token,
  onCreateUser,
  onUpdateUser,
  onDisableUser,
}: UserManagementPanelProps) {
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2">
        {/* Create User */}
        <form onSubmit={onCreateUser} className={cardClass("p-5")}>
          <h2 className="flex items-center gap-2 font-semibold"><UserPlus size={18} />创建用户</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <input
              className="rounded-md border border-border px-3 py-2"
              placeholder="账号"
              value={newUser.username}
              onChange={(e) => onNewUserChange({ ...newUser, username: e.target.value })}
              required
            />
            <input
              className="rounded-md border border-border px-3 py-2"
              placeholder="姓名"
              value={newUser.display_name}
              onChange={(e) => onNewUserChange({ ...newUser, display_name: e.target.value })}
              required
            />
            <input
              className="rounded-md border border-border px-3 py-2"
              placeholder="邮箱"
              value={newUser.email}
              onChange={(e) => onNewUserChange({ ...newUser, email: e.target.value })}
            />
            <select
              className="rounded-md border border-border px-3 py-2"
              value={newUser.role}
              onChange={(e) => onNewUserChange({ ...newUser, role: e.target.value })}
            >
              {roleOptions.map((role) => <option key={role}>{role}</option>)}
            </select>
            <input
              className="rounded-md border border-border px-3 py-2 md:col-span-2"
              placeholder="初始密码"
              value={newUser.password}
              onChange={(e) => onNewUserChange({ ...newUser, password: e.target.value })}
              required
            />
          </div>
          <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">
            <span>+</span>创建用户
          </button>
        </form>

        {/* Create Project (in admin) */}
        {/* Handled by AdminProjectPanel */}
      </div>

      {/* User List */}
      <div className={cardClass("p-5")}>
        <h2 className="flex items-center gap-2 font-semibold"><Users size={18} />用户管理</h2>
        <div className="mt-4 grid gap-3">
          {users.map((item) => {
            const draft = userEdits[item.id] || {
              display_name: item.display_name,
              email: item.email || "",
              role: item.role,
              status: item.status,
              password: "",
            };
            return (
              <div key={item.id} className="grid gap-2 rounded-md border border-border p-3 lg:grid-cols-[1fr_1fr_1fr_1fr_1fr_auto]">
                <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm">{item.username}</div>
                <input
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={draft.display_name}
                  onChange={(e) => onUserEditChange(item.id, { ...draft, display_name: e.target.value })}
                />
                <input
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="邮箱"
                  value={draft.email}
                  onChange={(e) => onUserEditChange(item.id, { ...draft, email: e.target.value })}
                />
                <select
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={draft.role}
                  onChange={(e) => onUserEditChange(item.id, { ...draft, role: e.target.value })}
                >
                  {roleOptions.map((role) => <option key={role}>{role}</option>)}
                </select>
                <input
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="新密码可留空"
                  value={draft.password}
                  onChange={(e) => onUserEditChange(item.id, { ...draft, password: e.target.value })}
                />
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => onUpdateUser(item)} className="rounded-md bg-brand px-3 py-2 text-xs font-medium text-white">保存</button>
                  <button
                    type="button"
                    onClick={() => onDisableUser(item.id)}
                    disabled={item.id === currentUser.id || item.status === "disabled"}
                    className="rounded-md border border-border px-3 py-2 text-xs disabled:opacity-40"
                  >
                    停用
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
