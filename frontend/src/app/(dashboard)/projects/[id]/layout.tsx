"use client";

import { useEffect, useMemo, useTransition } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
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
  const pendingNotes = useProjectStore((s) => s.pendingNotes);

  const projectId = Number(params.id);
  const project = selectedProject?.id === projectId ? selectedProject : null;
  const membership = members.find((member) => member.user_id === user?.id);
  const evaluationOnly = membership?.can_evaluate === true && membership.can_read === false;
  const isSuperAdmin = user?.role === "super_admin";
  const isOwner = project?.owner_user_id != null && project.owner_user_id === user?.id;
  const isPiWithGeneralAccess = user?.role === "pi" && project?.is_sensitive === false;
  const hasWorkspaceAccess = isSuperAdmin
    || isOwner
    || isPiWithGeneralAccess
    || membership?.can_read === true
    // 评价-only 盲评成员无读权限（can_read=false），仅允许进入盲评页，
    // 下方 evaluationOnly 重定向逻辑会将其限定在盲评页内。
    || evaluationOnly;
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
  // 待审批角标：pendingNotes 由 loadBaseProjectData 统一加载，此处只统计当前项目。
  const pendingApprovalCount = pendingNotes.filter((n) => n.project_id === projectId).length;
  const blindReviewPath = `/projects/${projectId}/blind-review`;
  const isBlindReviewPath = pathname === blindReviewPath;

  const [isPending, startTransition] = useTransition();

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

  // The project endpoint proves that the ID exists, but the member payload is
  // what tells the UI which workspace features this account may see. Fail
  // closed while that authorization basis is absent; API guards remain the
  // final enforcement layer for every operation.
  if (!hasWorkspaceAccess) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16" role="alert">
        <p className="text-sm text-destructive">无法确认当前账号的项目权限，已停止加载项目内容。</p>
        <button className="text-sm text-primary underline" onClick={() => router.push("/projects")}>返回项目列表</button>
      </div>
    );
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

      {/* 标题区：项目名为视觉主体；Dropdown 触发器仅作切换入口，chevron 弱化提示 */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="group flex items-center gap-1.5 text-2xl font-bold tracking-tight text-foreground hover:text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-lg px-1.5 py-0.5 -mx-1.5 hover:bg-muted/60">
                  <span>{project.name}</span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200 group-hover:text-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64 shadow-elevate">
                <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">切换项目</DropdownMenuLabel>
                {projects
                  .filter((p) => p.id !== projectId)
                  .slice(0, 10)
                  .map((p) => (
                    <DropdownMenuItem key={p.id} onClick={() => router.push(`/projects/${p.id}`)} className="cursor-pointer">
                      <span className="truncate">{p.name}</span>
                    </DropdownMenuItem>
                  ))}
                {projects.length > 1 && <DropdownMenuSeparator />}
                <DropdownMenuItem onClick={() => router.push("/projects")} className="cursor-pointer text-primary font-medium">
                  查看所有项目...
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          {project.description && <p className="text-sm text-muted-foreground max-w-3xl leading-relaxed">{project.description}</p>}
        </div>
      </div>

      {!evaluationOnly && projectDataErrors.length > 0 && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-warning shadow-subtle flex items-center gap-2" role="alert">
          <span className="font-medium">部分项目数据加载失败：</span>
          <span>{projectDataErrors.join("、")}。请刷新后重试。</span>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={(v) => {
        startTransition(() => {
          const target = v === "notes" ? `/projects/${projectId}` : `/projects/${projectId}/${v}`;
          router.push(target);
        });
      }}>
        {/* 精美下划线风格：保持 role/文案/角标 aria-hidden 完全不变 */}
        <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-none border-b border-border/80 bg-transparent p-0 gap-1 sm:gap-2">
          {tabs.map((t) => (
            <TabsTrigger
              key={t.value}
              value={t.value}
              className="rounded-none border-b-2 border-transparent bg-transparent px-3.5 py-2.5 text-sm font-medium text-muted-foreground shadow-none transition-all hover:text-foreground hover:border-border/60 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:font-semibold data-[state=active]:shadow-none"
            >
              {t.label}
              {t.value === "approvals" && pendingApprovalCount > 0 && (
                // aria-hidden 保证角标不进入 tab 的 accessible name（E2E 按精确名称匹配）。
                <Badge
                  aria-hidden="true"
                  variant="destructive"
                  className="ml-1.5 h-4 min-w-4 justify-center rounded-full px-1.5 text-[10px] leading-none"
                >
                  {pendingApprovalCount}
                </Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className={`mt-6 transition-all duration-200 ${isPending ? "opacity-40 translate-y-1" : "opacity-100 translate-y-0"}`}>{children}</div>
    </div>
  );
}
