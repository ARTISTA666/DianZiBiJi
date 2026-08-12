"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import { RotateCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { KnowledgeGraphVisualization } from "@/components/kg-visualization";
import { ErrorBanner } from "@/components/shared/error-banner";

export default function KGPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const kgGraph = useProjectStore((s) => s.kgGraph);
  const members = useProjectStore((s) => s.members);
  const rebuildKg = useProjectStore((s) => s.rebuildKg);
  const loadKGTabData = useProjectStore((s) => s.loadKGTabData);
  const busy = useProjectStore((s) => s.busy);
  const [error, setError] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [relationFilter, setRelationFilter] = useState("");
  const [entityKeyword, setEntityKeyword] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const feedback = useActionFeedback();
  const membership = members.find((member) => member.user_id === user?.id);
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;

  useEffect(() => {
    if (token) loadKGTabData(token, projectId);
  }, [token, projectId, loadKGTabData]);

  const entityTypes = useMemo(() =>
    Array.from(new Set((kgGraph?.entities || []).map((e) => e.entity_type))).sort(),
  [kgGraph]);

  const relationTypes = useMemo(() =>
    Array.from(new Set((kgGraph?.relations || []).map((r) => r.relation_type))).sort(),
  [kgGraph]);

  const graphEntities = useMemo(() => {
    if (!kgGraph) return [];
    const keyword = entityKeyword.trim().toLowerCase();
    const matchedIds = new Set(kgGraph.entities.filter((entity) =>
      (!entityFilter || entity.entity_type === entityFilter)
      && (!keyword || entity.label.toLowerCase().includes(keyword))
    ).map((entity) => entity.id));

    // 筛选时保留一跳关联实体，避免图谱只剩孤立节点。
    const visibleIds = new Set(matchedIds);
    kgGraph.relations.forEach((relation) => {
      if (relationFilter && relation.relation_type !== relationFilter) return;
      if (matchedIds.has(relation.source_entity_id) || matchedIds.has(relation.target_entity_id)) {
        visibleIds.add(relation.source_entity_id);
        visibleIds.add(relation.target_entity_id);
      }
    });
    return kgGraph.entities.filter((entity) => visibleIds.has(entity.id));
  }, [kgGraph, entityFilter, relationFilter, entityKeyword]);

  const graphEntityIds = useMemo(() => new Set(graphEntities.map((entity) => entity.id)), [graphEntities]);
  const graphRelations = useMemo(() =>
    (kgGraph?.relations || []).filter((relation) =>
      (!relationFilter || relation.relation_type === relationFilter)
      && graphEntityIds.has(relation.source_entity_id)
      && graphEntityIds.has(relation.target_entity_id),
    ),
  [kgGraph, relationFilter, graphEntityIds]);

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
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-28" />
      </div>
      <div className="flex gap-2"><Skeleton className="h-9 w-36" /><Skeleton className="h-9 w-36" /></div>
      <Skeleton className="h-[32rem] w-full" />
    </div>
  );

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}

      <div className="flex justify-end">
        {canWrite && <Button size="sm" variant="outline" onClick={handleRebuild} disabled={rebuilding}>
          <RotateCw className={`mr-2 h-4 w-4 ${rebuilding ? "animate-spin" : ""}`} />重建图谱
        </Button>}
      </div>

      {/* 过滤器 */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={entityFilter || "all"} onValueChange={(value) => setEntityFilter(value === "all" ? "" : value)}>
          <SelectTrigger aria-label="实体类型筛选" className="h-9 w-44"><SelectValue placeholder="筛选实体类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部实体类型</SelectItem>
            {entityTypes.map((t) => (<SelectItem key={t} value={t}>{kgEntityTypeText[t] || t}</SelectItem>))}
          </SelectContent>
        </Select>
        <Select value={relationFilter || "all"} onValueChange={(value) => setRelationFilter(value === "all" ? "" : value)}>
          <SelectTrigger aria-label="关系类型筛选" className="h-9 w-44"><SelectValue placeholder="筛选关系类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部关系类型</SelectItem>
            {relationTypes.map((t) => (<SelectItem key={t} value={t}>{kgRelationTypeText[t] || t}</SelectItem>))}
          </SelectContent>
        </Select>
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input aria-label="搜索实体" value={entityKeyword} onChange={(e) => setEntityKeyword(e.target.value)}
            placeholder="" className="h-9 border-slate-400 pl-9" />
        </div>
      </div>

      {/* 图谱可视化 */}
      {kgGraph && kgGraph.entities.length > 0 && (
        <KnowledgeGraphVisualization
          entities={graphEntities}
          relations={graphRelations}
          selectedEntityId={selectedEntityId}
          onEntitySelect={setSelectedEntityId}
        />
      )}
    </div>
  );
}
