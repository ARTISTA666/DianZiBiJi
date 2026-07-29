"use client";

import { useEffect, useState, KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Plus, FolderOpen, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";

const PAGE_SIZE = 20;
const statusMap: Record<string, string> = { active: "进行中", archived: "已归档", pending: "待启动" };

const handleCardKeyDown = (e: KeyboardEvent, callback: () => void) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    callback();
  }
};

export default function ProjectsPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
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

  useEffect(() => {
    if (token) {
      setLoading(true);
      loadProjects(token, 0, PAGE_SIZE)
        .catch((e) => setError(getErrorMessage(e, "加载项目失败")))
        .finally(() => setLoading(false));
    }
  }, [token, loadProjects]);

  const handleCreate = async () => {
    if (!token || !name.trim()) return;
    setBusy(true);
    try {
      const project = await createProject(token, { name: name.trim(), description: description.trim() || null });
      setOpen(false);
      setName("");
      setDescription("");
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(getErrorMessage(e, "创建失败"));
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
      {error && <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</p>}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">项目</h1>
          <p className="text-sm text-muted-foreground mt-1">管理你的实验项目和科研课题</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="mr-2 h-4 w-4" />新建项目</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>新建项目</DialogTitle></DialogHeader>
            <div className="space-y-4 pt-2">
              <div className="space-y-2">
                <Label htmlFor="pname">项目名称</Label>
                <Input id="pname" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：PCR 实验优化" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pdesc">项目描述</Label>
                <Textarea id="pdesc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="可选" rows={3} />
              </div>
              <Button onClick={handleCreate} disabled={busy || !name.trim()} className="w-full">
                {busy ? "创建中..." : "创建"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <p className="text-sm text-muted-foreground">加载中...</p>
        </div>
      ) : projects.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <FolderOpen className="h-12 w-12 text-muted-foreground/50" />
            <h3 className="mt-4 text-lg font-medium">暂无项目</h3>
            <p className="mt-1 text-sm text-muted-foreground">点击「新建项目」创建你的第一个实验项目</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Card key={p.id} role="button" tabIndex={0} className="cursor-pointer transition-shadow hover:shadow-md" onClick={() => router.push(`/projects/${p.id}`)} onKeyDown={(e) => handleCardKeyDown(e, () => router.push(`/projects/${p.id}`))}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-base">{p.name}</CardTitle>
                    <Badge variant="secondary" className="text-xs">{statusMap[p.status] || p.status}</Badge>
                  </div>
                  {p.description && <CardDescription className="line-clamp-2 mt-1">{p.description}</CardDescription>}
                </CardHeader>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {projectTotal > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-sm text-muted-foreground">
                第 {startItem}–{endItem} 条，共 {projectTotal} 条
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasPrev}
                  onClick={() => token && loadPrevProjectsPage(token)}
                >
                  <ChevronLeft className="mr-1 h-4 w-4" />
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasNext}
                  onClick={() => token && loadNextProjectsPage(token)}
                >
                  下一页
                  <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
