"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Plus, FolderOpen, ClipboardCheck, Layers, Activity, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardDescription, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ErrorBanner } from "@/components/shared/error-banner";
import { EmptyState } from "@/components/shared/empty-state";
import { PagePagination } from "@/components/shared/page-pagination";
import { useAuthStore, useProjectStore } from "@/stores";
import { getPendingApprovals, type Note } from "@/lib/api";
import { getErrorMessage, handleCardKeyDown } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { ProjectCardSkeleton } from "@/components/skeletons";

const PAGE_SIZE = 20;
const statusMap: Record<string, string> = { active: "进行中", archived: "已归档", pending: "待启动" };
const statusBadgeVariant: Record<string, "success" | "info" | "secondary"> = {
  active: "success",
  pending: "info",
  archived: "secondary",
};

export default function ProjectsPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const projects = useProjectStore((s) => s.projects);
  const projectTotal = useProjectStore((s) => s.projectTotal);
  const projectSkip = useProjectStore((s) => s.projectSkip);
  const loadProjects = useProjectStore((s) => s.loadProjects);
  const loadNextProjectsPage = useProjectStore((s) => s.loadNextProjectsPage);
  const loadPrevProjectsPage = useProjectStore((s) => s.loadPrevProjectsPage);
  const createProject = useProjectStore((s) => s.createProject);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [nameError, setNameError] = useState("");
  const [pendingNotes, setPendingNotes] = useState<Note[]>([]);
  const feedback = useActionFeedback();
  const canCreateProject = user?.role === "super_admin";

  useEffect(() => {
    if (token) {
      setLoading(true);
      loadProjects(token, 0, PAGE_SIZE)
        .catch((e) => {
          setError(getErrorMessage(e, "加载项目失败"));
          feedback.error(getErrorMessage(e, "加载项目失败"));
        })
        .finally(() => setLoading(false));
    }
  }, [token, loadProjects, feedback]);

  // 待审批待办横幅：请求失败静默降级，不打断项目列表使用。
  useEffect(() => {
    if (!token) return;
    getPendingApprovals(token)
      .then(setPendingNotes)
      .catch(() => setPendingNotes([]));
  }, [token]);

  const pendingGroups = useMemo(() => {
    const byProject = new Map<number, number>();
    pendingNotes.forEach((note) => {
      byProject.set(note.project_id, (byProject.get(note.project_id) || 0) + 1);
    });
    return [...byProject.entries()].map(([projectId, count]) => ({
      projectId,
      count,
      name: projects.find((p) => p.id === projectId)?.name || `项目 #${projectId}`,
    }));
  }, [pendingNotes, projects]);

  const activeCount = useMemo(() => projects.filter((p) => p.status === "active").length, [projects]);

  const handleNameBlur = () => {
    if (!name.trim()) {
      setNameError("项目名称不能为空");
    } else {
      setNameError("");
    }
  };

  const handleCreate = async () => {
    if (!canCreateProject || !token || !name.trim()) return;
    setBusy(true);
    try {
      const project = await createProject(token, { name: name.trim(), description: description.trim() || null });
      setOpen(false);
      setName("");
      setDescription("");
      router.push(`/projects/${project.id}`);
      feedback.success("项目创建成功");
    } catch (e) {
      const msg = getErrorMessage(e, "创建失败");
      setError(msg);
      feedback.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const startItem = projectSkip + 1;
  const endItem = Math.min(projectSkip + projects.length, projectTotal);
  const hasNext = projectSkip + PAGE_SIZE < projectTotal;
  const hasPrev = projectSkip > 0;

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      {/* PageHeader */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">项目</h1>
          <p className="text-sm text-muted-foreground mt-1">管理你的实验课题、科研笔记与多模态数据分析</p>
        </div>
        {canCreateProject && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="shadow-subtle hover:shadow-glow-primary">
                <Plus className="mr-2 h-4 w-4" />
                新建项目
              </Button>
            </DialogTrigger>
            <DialogContent className="shadow-elevate">
              <DialogHeader>
                <DialogTitle>新建项目</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="pname">项目名称</Label>
                  <Input
                    id="pname"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onBlur={handleNameBlur}
                    placeholder="例如：PCR 实验优化"
                    className={nameError ? "border-destructive" : ""}
                  />
                  {nameError && <p className="text-sm text-destructive">{nameError}</p>}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pdesc">项目描述</Label>
                  <Textarea
                    id="pdesc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="可选，简要概述课题目标与范围"
                    rows={3}
                  />
                </div>
                <Button
                  onClick={handleCreate}
                  disabled={busy || !name.trim()}
                  isLoading={busy}
                  className="w-full"
                >
                  {busy ? "创建中..." : "创建"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {/* Overview Stats Strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="flex items-center gap-4 rounded-xl border border-border/70 bg-card p-4 shadow-card">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">课题总数</p>
            <p className="text-xl font-bold tracking-tight text-foreground">{projectTotal}</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-xl border border-border/70 bg-card p-4 shadow-card">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">进行中项目</p>
            <p className="text-xl font-bold tracking-tight text-foreground">{activeCount}</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-xl border border-border/70 bg-card p-4 shadow-card">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <ClipboardCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">待审批事项</p>
            <p className="text-xl font-bold tracking-tight text-foreground">{pendingNotes.length}</p>
          </div>
        </div>
      </div>

      {/* 待审批横幅 */}
      {pendingNotes.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-info/30 bg-info/10 p-4 text-sm text-info shadow-subtle">
          <span className="inline-flex items-center gap-2 font-medium">
            <ClipboardCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
            你有 {pendingNotes.length} 条待审批笔记
          </span>
          <div className="flex flex-wrap items-center gap-2">
            {pendingGroups.map((g) => (
              <Link
                key={g.projectId}
                href={`/projects/${g.projectId}/approvals`}
                className="inline-flex items-center gap-1 rounded-md bg-info/20 px-2.5 py-1 text-xs font-semibold text-info hover:bg-info/30 transition-colors"
              >
                <span>{g.name}</span>
                <span className="rounded-full bg-info/30 px-1.5 py-0.2 text-[10px]">{g.count}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <ProjectCardSkeleton key={i} />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="暂无项目"
          description={canCreateProject ? "点击「新建项目」创建你的第一个实验项目" : "当前账号暂无可访问的项目，请联系系统管理员"}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Card
                key={p.id}
                role="button"
                tabIndex={0}
                className="group cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover border-border/75 hover:border-primary/40 flex flex-col justify-between"
                onClick={() => router.push(`/projects/${p.id}`)}
                onKeyDown={(e) => handleCardKeyDown(e, () => router.push(`/projects/${p.id}`))}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base font-semibold group-hover:text-primary transition-colors line-clamp-1">
                      {p.name}
                    </CardTitle>
                    <Badge variant={statusBadgeVariant[p.status] || "secondary"} className="text-xs shrink-0">
                      {statusMap[p.status] || p.status}
                    </Badge>
                  </div>
                  {p.description ? (
                    <CardDescription className="line-clamp-2 mt-2 text-xs leading-relaxed">
                      {p.description}
                    </CardDescription>
                  ) : (
                    <p className="text-xs text-muted-foreground/60 italic mt-2">暂无项目描述</p>
                  )}
                </CardHeader>
                <CardContent className="pt-0 flex items-center justify-between text-xs text-muted-foreground border-t border-border/40 py-3 mt-auto">
                  <span className="font-mono text-[11px] text-muted-foreground/80">ID: #{p.id}</span>
                  <span className="inline-flex items-center gap-1 font-medium text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                    进入工作台 <ArrowRight size={12} />
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {projectTotal > PAGE_SIZE && (
            <PagePagination
              startItem={startItem}
              endItem={endItem}
              total={projectTotal}
              hasPrev={hasPrev}
              hasNext={hasNext}
              onPrev={() => token && loadPrevProjectsPage(token)}
              onNext={() => token && loadNextProjectsPage(token)}
              className="pt-4"
            />
          )}
        </>
      )}
    </div>
  );
}
