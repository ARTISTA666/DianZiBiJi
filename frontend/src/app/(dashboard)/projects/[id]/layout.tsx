"use client";

import { useEffect, useMemo } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore, useProjectStore } from "@/stores";

const regularTabs = [
  { value: "notes", label: "笔记" },
  { value: "approvals", label: "审批" },
  { value: "data", label: "资料" },
  { value: "ai", label: "AI 问答" },
  { value: "kg", label: "图谱" },
  { value: "reports", label: "报告" },
  { value: "settings", label: "设置" },
] as const;
const evaluatorTabs = [{ value: "blind-review", label: "独立盲评" }] as const;

type TabValue = (typeof regularTabs)[number]["value"] | "blind-review";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const members = useProjectStore((s) => s.members);
  const busy = useProjectStore((s) => s.busy);
  const projectLoadError = useProjectStore((s) => s.projectLoadError);
  const projectDataErrors = useProjectStore((s) => s.projectDataErrors);
  const loadProjects = useProjectStore((s) => s.loadProjects);
  const loadProject = useProjectStore((s) => s.loadProject);
  const loadBaseProjectData = useProjectStore((s) => s.loadBaseProjectData);
  const selectProject = useProjectStore((s) => s.selectProject);
  const projects = useProjectStore((s) => s.projects);

  const projectId = Number(params.id);
  const project = selectedProject?.id === projectId ? selectedProject : null;
  const membership = members.find((member) => member.user_id === user?.id);
  const evaluationOnly = membership?.can_evaluate === true && membership.can_read === false;
  const tabs = evaluationOnly ? evaluatorTabs : regularTabs;
  const blindReviewPath = `/projects/${projectId}/blind-review`;
  const isBlindReviewPath = pathname === blindReviewPath;

  const activeTab = useMemo<TabValue>(() => {
    const segments = pathname.split("/");
    const last = segments[segments.length - 1];
    if (last === String(projectId)) return "notes";
    const found = [...regularTabs, ...evaluatorTabs].find((t) => t.value === last);
    return found ? found.value : "notes";
  }, [pathname, projectId]);

  useEffect(() => {
    if (token && projects.length === 0) loadProjects(token);
  }, [token, loadProjects, projects.length]);

  useEffect(() => {
    if (token && projectId) {
      selectProject(projectId);
      loadProject(token, projectId);
      loadBaseProjectData(token, projectId);
    }
  }, [token, projectId, selectProject, loadProject, loadBaseProjectData]);

  useEffect(() => {
    if (busy || !project || !membership) return;
    if (evaluationOnly && !isBlindReviewPath) {
      router.replace(blindReviewPath);
    } else if (!evaluationOnly && isBlindReviewPath) {
      router.replace(`/projects/${projectId}`);
    }
  }, [
    busy,
    project,
    membership,
    evaluationOnly,
    isBlindReviewPath,
    blindReviewPath,
    projectId,
    router,
  ]);

  if (projectLoadError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16" role="alert">
        <p className="text-sm text-destructive">{projectLoadError}</p>
        <button className="text-sm text-primary underline" onClick={() => router.push("/projects")}>返回项目列表</button>
      </div>
    );
  }

  if (!project || busy) {
    return <div className="flex items-center justify-center py-16"><p className="text-sm text-muted-foreground">加载中...</p></div>;
  }

  if (
    membership
    && ((evaluationOnly && !isBlindReviewPath) || (!evaluationOnly && isBlindReviewPath))
  ) {
    return <div className="flex items-center justify-center py-16"><p className="text-sm text-muted-foreground">正在进入授权工作区...</p></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
        {project.description && <p className="mt-1 text-sm text-muted-foreground">{project.description}</p>}
      </div>

      {!evaluationOnly && projectDataErrors.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
          部分项目数据加载失败：{projectDataErrors.join("、")}。请刷新后重试。
        </div>
      )}

      <Tabs value={activeTab} onValueChange={(v) => {
        const target = v === "notes" ? `/projects/${projectId}` : `/projects/${projectId}/${v}`;
        router.push(target);
      }}>
        <TabsList className="w-full justify-start overflow-x-auto">
          {tabs.map((t) => (<TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>))}
        </TabsList>
      </Tabs>

      <div className="mt-4">{children}</div>
    </div>
  );
}
