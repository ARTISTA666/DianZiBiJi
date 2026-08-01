"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ChevronDown } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { useAuthStore, useProjectStore } from "@/stores";
import { ProjectDetailSkeleton } from "@/components/skeletons";

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
  const isSuperAdmin = user?.role === "super_admin";
  const isOwner = project?.owner_user_id != null && project.owner_user_id === user?.id;
  const canManage = isSuperAdmin || isOwner || membership?.can_manage === true || membership?.project_role === "owner";
  const canReview = canManage || membership?.can_review === true;
  const visibleRegularTabs = useMemo(
    () => regularTabs.filter((t) => {
      if (t.value === "settings") return canManage;
      if (t.value === "approvals") return canReview;
      return true;
    }),
    [canManage, canReview],
  );
  const tabs = evaluationOnly ? evaluatorTabs : visibleRegularTabs;
  const blindReviewPath = `/projects/${projectId}/blind-review`;
  const isBlindReviewPath = pathname === blindReviewPath;

  const [isPending, startTransition] = useTransition();
  const [contentVisible, setContentVisible] = useState(true);

  const activeTab = useMemo<TabValue>(() => {
    const segments = pathname.split("/");
    const last = segments[segments.length - 1];
    if (last === String(projectId)) return "notes";
    const found = [...regularTabs, ...evaluatorTabs].find((t) => t.value === last);
    return found ? found.value : "notes";
  }, [pathname, projectId]);

  const activeTabLabel = useMemo(() => {
    const allTabs = [...regularTabs, ...evaluatorTabs] as readonly { value: string; label: string }[];
    return allTabs.find((t) => t.value === activeTab)?.label ?? "笔记";
  }, [activeTab]);

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
    return <ProjectDetailSkeleton />;
  }

  if (
    membership
    && ((evaluationOnly && !isBlindReviewPath) || (!evaluationOnly && isBlindReviewPath))
  ) {
    return <div className="flex items-center justify-center py-16"><p className="text-sm text-muted-foreground">正在进入授权工作区...</p></div>;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/projects">项目列表</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href={`/projects/${projectId}`}>{project.name}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{activeTabLabel}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-1 text-2xl font-bold tracking-tight hover:text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md px-1 -mx-1">
                {project.name}
                <ChevronDown className="h-5 w-5 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              {projects
                .filter((p) => p.id !== projectId)
                .slice(0, 10)
                .map((p) => (
                  <DropdownMenuItem key={p.id} onClick={() => router.push(`/projects/${p.id}`)}>
                    {p.name}
                  </DropdownMenuItem>
                ))}
              {projects.length > 1 && <DropdownMenuSeparator />}
              <DropdownMenuItem onClick={() => router.push("/projects")}>
                查看所有项目...
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {project.description && <p className="mt-1 text-sm text-muted-foreground">{project.description}</p>}
      </div>

      {!evaluationOnly && projectDataErrors.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
          部分项目数据加载失败：{projectDataErrors.join("、")}。请刷新后重试。
        </div>
      )}

      <Tabs value={activeTab} onValueChange={(v) => {
        setContentVisible(false);
        startTransition(() => {
          const target = v === "notes" ? `/projects/${projectId}` : `/projects/${projectId}/${v}`;
          router.push(target);
        });
        setTimeout(() => setContentVisible(true), 50);
      }}>
        <TabsList className="w-full justify-start overflow-x-auto">
          {tabs.map((t) => (<TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>))}
        </TabsList>
      </Tabs>

      <div className={`mt-4 transition-opacity duration-200 ${isPending || !contentVisible ? "opacity-0" : "opacity-100"}`}>{children}</div>
    </div>
  );
}
