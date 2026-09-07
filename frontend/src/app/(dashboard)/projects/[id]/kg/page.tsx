"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import {
  RotateCw,
  Search,
  X,
  Network,
  Share2,
  Boxes,
  Activity,
  FilterX,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { KnowledgeGraphVisualization } from "@/components/kg-visualization";
import { KnowledgeBlueprintView } from "@/components/kg-blueprint";
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

  const totalEntities = kgGraph?.entities?.length || 0;
  const totalRelations = kgGraph?.relations?.length || 0;

  const entityTypes = useMemo(
    () => Array.from(new Set((kgGraph?.entities || []).map((e) => e.entity_type))).sort(),
    [kgGraph]
  );

  const relationTypes = useMemo(
    () => Array.from(new Set((kgGraph?.relations || []).map((r) => r.relation_type))).sort(),
    [kgGraph]
  );

  const graphEntities = useMemo(() => {
    if (!kgGraph) return [];
    const keyword = entityKeyword.trim().toLowerCase();
    const matchedIds = new Set(
      kgGraph.entities
        .filter(
          (entity) =>
            (!entityFilter || entity.entity_type === entityFilter) &&
            (!keyword || entity.label.toLowerCase().includes(keyword))
        )
        .map((entity) => entity.id)
    );

    // 筛选时保留一跳关联实体，避免图谱只剩孤立节点
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

  const graphEntityIds = useMemo(
    () => new Set(graphEntities.map((entity) => entity.id)),
    [graphEntities]
  );

  const graphRelations = useMemo(
    () =>
      (kgGraph?.relations || []).filter(
        (relation) =>
          (!relationFilter || relation.relation_type === relationFilter) &&
          graphEntityIds.has(relation.source_entity_id) &&
          graphEntityIds.has(relation.target_entity_id)
      ),
    [kgGraph, relationFilter, graphEntityIds]
  );

  const avgDegree = useMemo(() => {
    if (!totalEntities) return "0.0";
    return ((totalRelations * 2) / totalEntities).toFixed(1);
  }, [totalEntities, totalRelations]);

  const isFiltered = entityFilter !== "" || relationFilter !== "" || entityKeyword.trim() !== "";

  const handleResetFilters = () => {
    setEntityFilter("");
    setRelationFilter("");
    setEntityKeyword("");
  };

  const handleRebuild = async () => {
    if (!token) return;
    setRebuilding(true);
    setError("");
    try {
      await rebuildKg(token, projectId);
      feedback.success("图谱已根据最新实验审核记录重新构建");
    } catch (e) {
      const msg = getErrorMessage(e, "重建失败");
      setError(msg);
      feedback.error(msg);
    } finally {
      setRebuilding(false);
    }
  };

  if (busy) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-28" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-36" />
          <Skeleton className="h-9 w-36" />
        </div>
        <Skeleton className="h-[36rem] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}

      {/* 顶部宏观统计面板 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Network className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">实证节点总数</p>
            <p className="text-lg font-bold tabular-nums text-foreground">{totalEntities}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Share2 className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">拓扑关系总数</p>
            <p className="text-lg font-bold tabular-nums text-foreground">{totalRelations}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <Boxes className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">实体类别覆盖</p>
            <p className="text-lg font-bold tabular-nums text-foreground">{entityTypes.length} 类</p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <Activity className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">平均节点度数</p>
            <p className="text-lg font-bold tabular-nums text-foreground">{avgDegree}</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="evidence" className="w-full">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList className="h-9 bg-muted/60 p-0.5">
            <TabsTrigger value="evidence" className="text-xs px-3">
              实证图谱（五通道可视化）
            </TabsTrigger>
            <TabsTrigger value="blueprint" className="text-xs px-3">
              知识蓝图（计划态 vs 实证态）
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            {canWrite && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleRebuild}
                disabled={rebuilding}
                className="h-8 text-xs"
              >
                <RotateCw className={`mr-1.5 h-3.5 w-3.5 ${rebuilding ? "animate-spin" : ""}`} />
                重新提取并构建图谱
              </Button>
            )}
          </div>
        </div>

        {/* 实证图谱页签 */}
        <TabsContent value="evidence" className="space-y-3 pt-2">
          {/* 筛选与检索过滤条 */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/70 bg-card p-2 shadow-xs">
            <Select
              value={entityFilter || "all"}
              onValueChange={(value) => setEntityFilter(value === "all" ? "" : value)}
            >
              <SelectTrigger aria-label="实体类型筛选" className="h-8 w-40 text-xs bg-background">
                <SelectValue placeholder="全部实体类型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部实体类型 ({totalEntities})</SelectItem>
                {entityTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {kgEntityTypeText[t] || t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={relationFilter || "all"}
              onValueChange={(value) => setRelationFilter(value === "all" ? "" : value)}
            >
              <SelectTrigger aria-label="关系类型筛选" className="h-8 w-40 text-xs bg-background">
                <SelectValue placeholder="全部关系类型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部关系类型 ({totalRelations})</SelectItem>
                {relationTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {kgRelationTypeText[t] || t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="relative min-w-56 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="搜索实体"
                value={entityKeyword}
                onChange={(e) => setEntityKeyword(e.target.value)}
                placeholder="搜索实体名称、标签或编号..."
                className="h-8 pl-8 pr-7 text-xs bg-background"
              />
              {entityKeyword && (
                <button
                  type="button"
                  onClick={() => setEntityKeyword("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {isFiltered && (
              <div className="flex items-center gap-1.5 pl-1">
                <Badge variant="secondary" className="text-[10px] font-normal py-0.5">
                  显示 {graphEntities.length} / {totalEntities} 个节点
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleResetFilters}
                  className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                >
                  <FilterX className="mr-1 h-3 w-3" />
                  重置筛选
                </Button>
              </div>
            )}
          </div>

          {/* 图谱主可视化组件 */}
          {kgGraph && kgGraph.entities.length > 0 ? (
            <KnowledgeGraphVisualization
              entities={graphEntities}
              relations={graphRelations}
              selectedEntityId={selectedEntityId}
              onEntitySelect={setSelectedEntityId}
            />
          ) : (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground">
              <Network className="mb-2 h-8 w-8 text-muted-foreground/60" />
              <p className="text-sm">项目当前尚未生成知识图谱</p>
              <p className="mt-1 text-xs">录入实验笔记并通过审核后，系统将自动基于科研规则抽取实体与关系</p>
            </div>
          )}
        </TabsContent>

        {/* 知识蓝图页签 */}
        <TabsContent value="blueprint" className="pt-2">
          {token && (
            <KnowledgeBlueprintView projectId={projectId} token={token} canWrite={canWrite} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
