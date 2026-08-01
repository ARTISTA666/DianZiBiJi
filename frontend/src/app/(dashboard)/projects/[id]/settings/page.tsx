"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { UserPlus, UserMinus, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { useConfirmDialog } from "@/hooks/use-confirm-dialog";
import { SettingsSkeleton } from "@/components/skeletons";

const rt: Record<string, string> = { owner: "拥有者", reviewer: "审核人", member: "成员", viewer: "观察者" };
const roleOpts = ["member", "reviewer", "owner", "viewer"];
const permissionOptions = [
  ["can_read", "读"],
  ["can_write", "写"],
  ["can_review", "审"],
  ["can_evaluate", "评"],
  ["can_manage", "管"],
] as const;

export default function SettingsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const members = useProjectStore((s) => s.members);
  const updateProject = useProjectStore((s) => s.updateProject);
  const addMember = useProjectStore((s) => s.addMember);
  const updateMember = useProjectStore((s) => s.updateMember);
  const removeMember = useProjectStore((s) => s.removeMember);
  const addReviewer = useProjectStore((s) => s.addReviewer);
  const busy = useProjectStore((s) => s.busy);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [memberBusyId, setMemberBusyId] = useState<number | null>(null);
  const feedback = useActionFeedback();
  const { confirm, ConfirmDialog } = useConfirmDialog();

  // Add member
  const [userId, setUserId] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [canRead, setCanRead] = useState(true);
  const [canWrite, setCanWrite] = useState(true);
  const [canReview, setCanReview] = useState(false);
  const [canEval, setCanEval] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [independentReview, setIndependentReview] = useState(false);
  const [addBusy, setAddBusy] = useState(false);

  // Edit project
  const project = selectedProject?.id === projectId ? selectedProject : null;
  const [editName, setEditName] = useState(project?.name || "");
  const [editDesc, setEditDesc] = useState(project?.description || "");

  useEffect(() => {
    if (project) {
      setEditName(project.name);
      setEditDesc(project.description || "");
    }
  }, [project]);

  const resetAdd = () => { setUserId(""); setMemberRole("member"); setCanRead(true); setCanWrite(true); setCanReview(false); setCanEval(false); setCanManage(false); setIndependentReview(false); };

  const handleAddMember = async () => {
    if (!token || !userId) return;
    setAddBusy(true); setError("");
    try {
      if (independentReview) {
        await addReviewer(token, projectId, Number(userId));
      } else {
        await addMember(token, projectId, {
          user_id: Number(userId),
          project_role: memberRole,
          can_read: canRead,
          can_write: canWrite,
          can_review: canReview,
          can_evaluate: canEval,
          can_manage: canManage,
        });
      }
      setAddOpen(false);
      resetAdd();
      feedback.success("成员已添加");
    } catch (e) {
      const msg = getErrorMessage(e, "添加失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setAddBusy(false); }
  };

  const handleRemoveMember = async (memberId: number) => {
    if (!token) return;
    setMemberBusyId(memberId); setError("");
    try {
      await removeMember(token, projectId, memberId);
      feedback.success("成员已移除");
    } catch (e) {
      const msg = getErrorMessage(e, "移除失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setMemberBusyId(null); }
  };

  const handleRemoveMemberConfirm = (memberId: number, userId: number) => {
    confirm("确认移除", `确定要移除用户 #${userId} 吗？该用户将失去项目访问权限。`, () => {
      handleRemoveMember(memberId);
    });
  };

  const handleUpdateRole = async (memberId: number, newRole: string) => {
    if (!token) return;
    setMemberBusyId(memberId); setError("");
    try {
      await updateMember(token, projectId, memberId, { project_role: newRole });
      feedback.success("角色已更新");
    } catch (e) {
      const msg = getErrorMessage(e, "更新失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setMemberBusyId(null); }
  };

  const handleUpdatePermission = async (
    memberId: number,
    permission: (typeof permissionOptions)[number][0],
    enabled: boolean,
  ) => {
    if (!token) return;
    setMemberBusyId(memberId); setError("");
    try {
      await updateMember(token, projectId, memberId, { [permission]: enabled });
    } catch (e) {
      const msg = getErrorMessage(e, "权限更新失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setMemberBusyId(null); }
  };

  const handleUpdateProject = async () => {
    if (!token || !editName.trim()) return;
    try {
      await updateProject(token, projectId, { name: editName.trim(), description: editDesc.trim() || null });
      feedback.success("项目设置已保存");
    } catch (e) {
      const msg = getErrorMessage(e, "更新失败");
      setError(msg);
      feedback.error(msg);
    }
  };

  if (busy) return <SettingsSkeleton />;

  const membership = members.find((m) => m.user_id === user?.id);
  const canManageProject = user?.role === "super_admin"
    || (project?.owner_user_id != null && project.owner_user_id === user?.id)
    || membership?.can_manage === true
    || membership?.project_role === "owner";
  if (!canManageProject) {
    return <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">只有项目管理员可以访问项目设置。</p>;
  }

  return (
    <div className="space-y-6">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      {/* 项目信息 */}
      <Card>
        <CardHeader><CardTitle className="text-base">项目设置</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sname">项目名称</Label>
            <Input id="sname" value={editName} onChange={(e) => setEditName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sdesc">项目描述</Label>
            <Input id="sdesc" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
          </div>
          <Button onClick={handleUpdateProject} disabled={!editName.trim()}>
            <Save className="mr-2 h-4 w-4" />保存
          </Button>
        </CardContent>
      </Card>

      {/* 成员管理 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">项目成员 ({members.length})</CardTitle>
            <Dialog open={addOpen} onOpenChange={(o) => { if (!o) resetAdd(); setAddOpen(o); }}>
              <DialogTrigger asChild>
                <Button size="sm"><UserPlus className="mr-2 h-4 w-4" />添加成员</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>添加成员</DialogTitle></DialogHeader>
                <div className="space-y-4 pt-2">
                  <div className="space-y-2">
                    <Label>用户 ID</Label>
                    <Input type="number" value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="输入用户ID" />
                  </div>
                  <label className="flex items-start gap-2 rounded-md border p-3 text-sm">
                    <input
                      aria-label="设为独立盲评人"
                      className="mt-1"
                      type="checkbox"
                      checked={independentReview}
                      onChange={(event) => setIndependentReview(event.target.checked)}
                    />
                    <span><span className="block font-medium">独立盲评人</span><span className="text-xs text-muted-foreground">只能查看方法隐藏后的评价材料，不能读取项目原始内容。</span></span>
                  </label>
                  <div className="space-y-2">
                    <Label>角色</Label>
                    <Select value={memberRole} onValueChange={setMemberRole} disabled={independentReview}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{roleOpts.map((r) => (<SelectItem key={r} value={r}>{rt[r] || r}</SelectItem>))}</SelectContent>
                    </Select>
                  </div>
                  <fieldset className="grid grid-cols-2 gap-2 text-sm" disabled={independentReview}>
                    {[
                      { k: "can_read", l: "读取", v: canRead, s: setCanRead },
                      { k: "can_write", l: "写入", v: canWrite, s: setCanWrite },
                      { k: "can_review", l: "审核", v: canReview, s: setCanReview },
                      { k: "can_evaluate", l: "评价", v: canEval, s: setCanEval },
                      { k: "can_manage", l: "管理", v: canManage, s: setCanManage },
                    ].map(({ k, l, v, s }) => (
                      <label key={k} className="flex items-center gap-2 rounded border p-2 cursor-pointer hover:bg-muted/50">
                        <input type="checkbox" checked={v} onChange={() => s(!v)} />
                        {l}
                      </label>
                    ))}
                  </fieldset>
                  <Button onClick={handleAddMember} disabled={addBusy || !userId} className="w-full">
                    {addBusy ? "添加中..." : independentReview ? "添加独立盲评人" : "添加成员"}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {members.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无成员</p>
          ) : (
            <div className="space-y-2">
              {members.map((m) => (
                <div key={m.id} className="flex items-start justify-between gap-3 rounded-md border p-3">
                  <div>
                    <p className="text-sm font-medium">用户 #{m.user_id}</p>
                    <div className="flex gap-1 mt-1">
                      <Badge variant="secondary" className="text-xs">{rt[m.project_role] || m.project_role}</Badge>
                      {m.can_read && <Badge variant="outline" className="text-xs">读</Badge>}
                      {m.can_write && <Badge variant="outline" className="text-xs">写</Badge>}
                      {m.can_review && <Badge variant="outline" className="text-xs">审</Badge>}
                      {m.can_evaluate && <Badge variant="outline" className="text-xs">评</Badge>}
                      {m.can_manage && <Badge variant="outline" className="text-xs">管</Badge>}
                      {m.is_independent_reviewer && <Badge variant="outline" className="text-xs">独立盲评</Badge>}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {permissionOptions.map(([permission, label]) => (
                        <label key={permission} className="flex items-center gap-1 text-xs text-muted-foreground">
                          <input
                            aria-label={`用户 ${m.user_id} ${label}权限`}
                            type="checkbox"
                            checked={m[permission]}
                            disabled={memberBusyId === m.id || m.is_independent_reviewer}
                            onChange={(event) => handleUpdatePermission(m.id, permission, event.target.checked)}
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Select value={m.project_role} disabled={memberBusyId === m.id || m.is_independent_reviewer} onValueChange={(v) => handleUpdateRole(m.id, v)}>
                      <SelectTrigger className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>{roleOpts.map((r) => (<SelectItem key={r} value={r}>{rt[r] || r}</SelectItem>))}</SelectContent>
                    </Select>
                    <Button
                      aria-label={`${m.is_independent_reviewer ? "移除独立盲评人" : "移除成员"} ${m.user_id}`}
                      size="sm"
                      variant="ghost"
                      className="text-destructive h-8 w-8 p-0"
                      disabled={memberBusyId === m.id}
                      onClick={() => handleRemoveMemberConfirm(m.id, m.user_id)}
                    >
                      <UserMinus className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      {ConfirmDialog}

      {/* 系统测试入口 — 隐藏在日常界面之外 */}
      <div className="border-t pt-4 text-center">
        <Link
          href={`/projects/${projectId}/system-test`}
          target="_blank"
          className="text-xs text-muted-foreground/40 hover:text-muted-foreground/60 transition-colors"
        >
          系统测试 · 可信性验证
        </Link>
      </div>
    </div>
  );
}
