"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import { RotateCw, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { cn, getErrorMessage } from "@/lib/utils";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { KnowledgeGraphVisualization } from "@/components/kg-visualization";

export default function KGPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const kgGraph = useProjectStore((s) => s.kgGraph);
  const notes = useProjectStore((s) => s.notes);
  const members = useProjectStore((s) => s.members);
  const extractNoteKg = useProjectStore((s) => s.extractNoteKg);
  const rebuildKg = useProjectStore((s) => s.rebuildKg);
  const loadKGTabData = useProjectStore((s) => s.loadKGTabData);
  const busy = useProjectStore((s) => s.busy);
  const [error, setError] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [relationFilter, setRelationFilter] = useState("");
  const [entityKeyword, setEntityKeyword] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [extractingNoteId, setExtractingNoteId] = useState<number | null>(null);
  const feedback = useActionFeedback();
  const membership = members.find((member) => member.user_id === user?.id);
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;

  useEffect(() => {
    if (token) loadKGTabData(token, projectId);
  }, [token, projectId, loadKGTabData]);

  const entityTypes = useMemo(() =>
    Array.from(new Set((kgGraph?.entities || []).map((e) => e.entity_type))).sort(),
  [kgGraph]);

  const entityLabels = useMemo(() =>
    new Map((kgGraph?.entities || []).map((e) => [e.id, e.label] as const)),
  [kgGraph]);

  const relationTypes = useMemo(() =>
    Array.from(new Set((kgGraph?.relations || []).map((r) => r.relation_type))).sort(),
  [kgGraph]);

  const filteredEntities = useMemo(() => {
    const keyword = entityKeyword.trim().toLowerCase();
    if (!entityFilter && !relationFilter && !keyword) return kgGraph?.entities || [];
    const relatedIds = new Set<number>();
    (kgGraph?.relations || []).forEach((r) => {
      if (relationFilter && r.relation_type !== relationFilter) return;
      relatedIds.add(r.source_entity_id);
      relatedIds.add(r.target_entity_id);
    });
    return (kgGraph?.entities || []).filter((e) =>
      (!entityFilter || e.entity_type === entityFilter)
      && (!relationFilter || relatedIds.has(e.id))
      && (!keyword || e.label.toLowerCase().includes(keyword))
    );
  }, [kgGraph, entityFilter, relationFilter, entityKeyword]);

  const handleExtract = async (noteId: number) => {
    if (!token) return;
    setExtractingNoteId(noteId); setError("");
    try { await extractNoteKg(token, noteId); useProjectStore.getState().invalidateCache(); loadKGTabData(token, projectId); feedback.success("实体已提取"); }
    catch (e) {
      const msg = getErrorMessage(e, "提取失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setExtractingNoteId(null); }
  };

  const handleRebuild = async () => {
    if (!token) return;
    setRebuilding(true); setError("");
    try { await rebuildKg(token, projectId); feedback.success("图谱已重建"); }
    catch (e) {
      const msg = getErrorMessage(e, "重建失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setRebuilding(false); }
  };

  if (busy) return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-28" />
      </div>
      <div className="flex gap-2"><Skeleton className="h-9 w-36" /><Skeleton className="h-9 w-36" /></div>
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
      </div>
    </div>
  );

  const entities = filteredEntities;
  const relations = (kgGraph?.relations || []).filter((r) => {
    if (relationFilter && r.relation_type !== relationFilter) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{kgGraph?.entities.length || 0} 实体 · {kgGraph?.relations.length || 0} 关系</p>
        {canWrite && <Button size="sm" variant="outline" onClick={handleRebuild} disabled={rebuilding}>
          <RotateCw className={`mr-2 h-4 w-4 ${rebuilding ? "animate-spin" : ""}`} />重建图谱
        </Button>}
      </div>

      {/* 过滤器 */}
      <div className="flex gap-2">
        <Select value={entityFilter || "all"} onValueChange={(value) => setEntityFilter(value === "all" ? "" : value)}>
          <SelectTrigger className="w-36"><SelectValue placeholder="实体类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            {entityTypes.map((t) => (<SelectItem key={t} value={t}>{kgEntityTypeText[t] || t}</SelectItem>))}
          </SelectContent>
        </Select>
        <Select value={relationFilter || "all"} onValueChange={(value) => setRelationFilter(value === "all" ? "" : value)}>
          <SelectTrigger className="w-36"><SelectValue placeholder="关系类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            {relationTypes.map((t) => (<SelectItem key={t} value={t}>{kgRelationTypeText[t] || t}</SelectItem>))}
          </SelectContent>
        </Select>
        <Input value={entityKeyword} onChange={(e) => setEntityKeyword(e.target.value)}
          placeholder="按实体关键词过滤..." className="flex-1" />
      </div>

      {/* 图谱可视化 */}
      {kgGraph && kgGraph.entities.length > 0 && (
        <KnowledgeGraphVisualization
          entities={kgGraph.entities}
          relations={kgGraph.relations}
          selectedEntityId={selectedEntityId}
          onEntitySelect={setSelectedEntityId}
        />
      )}

      {/* 实体列表 */}
      <Card>
        <CardHeader><CardTitle className="text-base">实体 ({entities.length})</CardTitle></CardHeader>
        <CardContent>
          {entities.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无实体</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {entities.map((e) => {
                const selected = selectedEntityId === e.id;
                return (
                  <button key={e.id} type="button"
                    onClick={() => setSelectedEntityId(selected ? null : e.id)}
                    title={selected ? "取消高亮其关联关系" : "点击高亮其关联关系"}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      selected
                        ? "border-transparent bg-primary text-primary-foreground"
                        : "hover:bg-muted"
                    )}>
                    {kgEntityTypeText[e.entity_type] || e.entity_type}: {e.label}
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 关系列表 */}
      <Card>
        <CardHeader><CardTitle className="text-base">关系 ({relations.length})</CardTitle></CardHeader>
        <CardContent>
          {relations.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无关系</p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {relations.map((r, i) => {
                const highlighted = selectedEntityId !== null
                  && (r.source_entity_id === selectedEntityId || r.target_entity_id === selectedEntityId);
                return (
                  <p key={r.id || i} className={cn("rounded px-1 py-0.5 text-sm", highlighted && "bg-primary/10")}>
                    <span className="font-medium">{entityLabels.get(r.source_entity_id) || `实体 #${r.source_entity_id}`}</span>
                    <span className="text-muted-foreground">{` (#${r.source_entity_id})`}</span>
                    {" → "}
                    <span className="font-medium text-primary">{kgRelationTypeText[r.relation_type] || r.relation_type}</span>
                    {" → "}
                    <span className="font-medium">{entityLabels.get(r.target_entity_id) || `实体 #${r.target_entity_id}`}</span>
                    <span className="text-muted-foreground">{` (#${r.target_entity_id})`}</span>
                    <span className="ml-2 text-xs text-muted-foreground">置信度 {r.confidence.toFixed(2)}</span>
                  </p>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 从笔记提取 */}
      {canWrite && notes.some((note) => note.status === "approved") && (
        <Card>
          <CardHeader><CardTitle className="text-base">从笔记提取实体</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {notes.filter((note) => note.status === "approved").map((note) => (
              <div key={note.id} className="flex items-center justify-between rounded-md border p-2 text-sm">
                <span className="truncate">{note.title}</span>
                <Button size="sm" variant="outline" onClick={() => handleExtract(note.id)}
                  disabled={extractingNoteId === note.id}>
                  <FileText className="mr-1 h-3 w-3" />
                  {extractingNoteId === note.id ? "提取中..." : "提取"}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
