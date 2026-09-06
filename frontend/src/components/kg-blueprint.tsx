/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { CheckCircle2, CircleDashed, ClipboardList, FileText, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getErrorMessage } from "@/lib/utils";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";
import {
  getEntityColor,
  getRelationColor,
  hexToRgba,
  traceShapePath,
  ENTITY_SHAPES,
  type NodeShape,
} from "@/components/kg-visualization";
import {
  getProjectKnowledgeBlueprint,
  parseProjectKnowledgeBlueprint,
  patchProjectKnowledgeBlueprintNode,
  type BlueprintNode,
  type KnowledgeBlueprint,
} from "@/lib/api";

// react-force-graph-2d 不支持 SSR，需动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((mod) => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex h-80 items-center justify-center text-sm text-muted-foreground">
      加载知识蓝图...
    </div>
  ),
});

interface GraphNode {
  id: number;
  name: string;
  entityType: string;
  shape: NodeShape;
  covered: boolean;
  val: number;
}

interface GraphLink {
  source: number;
  target: number;
  relationType: string;
  label: string;
}

const SOURCE_KIND_TEXT: Record<string, string> = {
  plan_document: "项目计划书",
  meeting_note: "组会纪要",
};

function blueprintEntityTypeText(entityType: string): string {
  return kgEntityTypeText[entityType] || entityType;
}

export function KnowledgeBlueprintView({
  projectId,
  token,
  canWrite,
}: {
  projectId: number;
  token: string;
  canWrite: boolean;
}) {
  const [blueprint, setBlueprint] = useState<KnowledgeBlueprint | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [parseBusy, setParseBusy] = useState(false);
  const [showParseForm, setShowParseForm] = useState(false);
  const [parseTitle, setParseTitle] = useState("");
  const [parseSourceKind, setParseSourceKind] = useState("plan_document");
  const [parseText, setParseText] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [graphSize, setGraphSize] = useState({ width: 0, height: 380 });
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadBlueprint = useCallback(async () => {
    setError("");
    try {
      const data = await getProjectKnowledgeBlueprint(token, projectId);
      setBlueprint(data);
    } catch (e) {
      setError(getErrorMessage(e, "蓝图加载失败"));
    } finally {
      setLoading(false);
    }
  }, [token, projectId]);

  useEffect(() => {
    void loadBlueprint();
  }, [loadBlueprint]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const updateSize = () => setGraphSize({ width: container.clientWidth, height: container.clientHeight });
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [blueprint]);

  const graphData = useMemo(() => {
    if (!blueprint) return { nodes: [] as GraphNode[], links: [] as GraphLink[] };
    const active = blueprint.nodes;
    const activeIds = new Set(active.map((n) => n.id));
    const nodes: GraphNode[] = active.map((n) => ({
      id: n.id,
      name: n.label,
      entityType: n.entity_type,
      shape: ENTITY_SHAPES[n.entity_type] || "circle",
      covered: n.evidence.entity_count > 0,
      val: Math.max(2.5, Math.min(10, 2.5 + n.evidence.entity_count * 2)),
    }));
    const links: GraphLink[] = blueprint.edges
      .filter((e) => activeIds.has(e.source_node_id) && activeIds.has(e.target_node_id))
      .map((e) => ({
        source: e.source_node_id,
        target: e.target_node_id,
        relationType: e.relation_type,
        label: kgRelationTypeText[e.relation_type] || e.relation_type,
      }));
    return { nodes, links };
  }, [blueprint]);

  const uncoveredNodes = useMemo(
    () => (blueprint?.nodes || []).filter((n) => n.evidence.entity_count === 0),
    [blueprint],
  );

  const selectedNode = useMemo(
    () => (blueprint?.nodes || []).find((n) => n.id === selectedNodeId) || null,
    [blueprint, selectedNodeId],
  );

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = Math.sqrt(Math.max(node.val, 1)) * 4.2;
    const x = node.x;
    const y = node.y;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const baseColor = getEntityColor(node.entityType);
    const selected = node.id === selectedNodeId;
    const covered = node.covered;

    if (covered) {
      // 已覆盖：实心 + 满水波
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.fillStyle = hexToRgba(baseColor, 0.9);
      ctx.fill();
    } else {
      // 计划中：空心虚线轮廓（虚线在缩放下保持可读）
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.fillStyle = hexToRgba(baseColor, 0.08);
      ctx.fill();
      ctx.setLineDash([4 / Math.max(globalScale, 0.5), 3 / Math.max(globalScale, 0.5)]);
      ctx.strokeStyle = hexToRgba(baseColor, 0.75);
      ctx.lineWidth = 1.4 / Math.max(globalScale, 0.5);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (selected) {
      traceShapePath(ctx, node.shape, x, y, r + 3 / Math.max(globalScale, 0.5));
      ctx.strokeStyle = "#4f46e5";
      ctx.lineWidth = 2 / Math.max(globalScale, 0.5);
      ctx.stroke();
    }
  }, [selectedNodeId]);

  const handleParse = async () => {
    if (!parseTitle.trim() || parseText.trim().length < 10) return;
    setParseBusy(true);
    setError("");
    try {
      const result = await parseProjectKnowledgeBlueprint(
        token,
        projectId,
        { title: parseTitle.trim(), source_kind: parseSourceKind, text: parseText.trim() },
      );
      const summary = `解析完成（${result.parse_mode === "llm" ? "AI 模式" : "规则模式"}）：新增 ${result.nodes_added}、覆盖更新 ${result.nodes_updated}、新增关系 ${result.edges_added}`;
      if (result.message) setError(`${summary}；${result.message}`);
      else setError("");
      setParseTitle("");
      setParseText("");
      setShowParseForm(false);
      await loadBlueprint();
    } catch (e) {
      setError(getErrorMessage(e, "蓝图解析失败"));
    } finally {
      setParseBusy(false);
    }
  };

  const handleRetire = async (nodeId: number) => {
    try {
      await patchProjectKnowledgeBlueprintNode(
        token,
        projectId,
        nodeId,
        { status: "retired" },
      );
      setSelectedNodeId(null);
      await loadBlueprint();
    } catch (e) {
      setError(getErrorMessage(e, "修正失败"));
    }
  };

  if (loading) {
    return (
      <Card className="border-border/75">
        <CardContent className="flex h-40 items-center justify-center text-sm text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />加载知识蓝图...
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {error}
        </div>
      )}

      {/* 覆盖度总览 */}
      <Card className="border-border/75 shadow-card bg-card">
        <CardHeader className="pb-3 border-b border-border/60 bg-muted/20">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <ClipboardList className="h-4 w-4" />知识蓝图
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                计划态知识点 vs 实验记录实证覆盖——蓝图指导「下一步做什么」
              </p>
            </div>
            {canWrite && (
              <Button size="sm" variant="outline" onClick={() => setShowParseForm((v) => !v)}>
                <Sparkles className="mr-2 h-3.5 w-3.5" />
                {showParseForm ? "收起解析" : "解析计划/纪要"}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold tabular-nums">
                {blueprint ? Math.round(blueprint.coverage.completion * 100) : 0}%
              </span>
              <span className="text-xs text-muted-foreground">
                实证覆盖 {blueprint?.coverage.covered_nodes ?? 0}/{blueprint?.coverage.total_nodes ?? 0} 个计划知识点
              </span>
            </div>
            <div className="h-2 min-w-40 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${Math.round((blueprint?.coverage.completion ?? 0) * 100)}%` }}
              />
            </div>
          </div>

          {showParseForm && canWrite && (
            <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
              <div className="flex flex-wrap gap-2">
                <Input
                  aria-label="文档标题"
                  value={parseTitle}
                  onChange={(e) => setParseTitle(e.target.value)}
                  placeholder="来源标题（如：课题计划书 v1 / 组会纪要 09-06）"
                  className="h-9 min-w-56 flex-1"
                />
                <Select value={parseSourceKind} onValueChange={setParseSourceKind}>
                  <SelectTrigger aria-label="来源类型" className="h-9 w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="plan_document">项目计划书</SelectItem>
                    <SelectItem value="meeting_note">组会纪要（高优先级）</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Textarea
                aria-label="计划文本"
                value={parseText}
                onChange={(e) => setParseText(e.target.value)}
                placeholder="粘贴项目计划书、大纲或组会纪要文本（至少 10 字）。系统解析后生成/更新计划态知识蓝图；组会纪要来源优先级更高，可覆盖计划书来源的定义。"
                className="min-h-24"
              />
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-muted-foreground">
                  AI 解析不可用时自动回落规则抽取，解析留痕可在解析记录中审计。
                </p>
                <Button size="sm" onClick={handleParse} disabled={parseBusy || parseText.trim().length < 10 || !parseTitle.trim()}>
                  {parseBusy ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-2 h-3.5 w-3.5" />}
                  解析并更新蓝图
                </Button>
              </div>
            </div>
          )}

          {/* 图例：实心=已覆盖，虚线空心=待实证 */}
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />实心 = 实验记录已覆盖
            </span>
            <span className="inline-flex items-center gap-1">
              <CircleDashed className="h-3.5 w-3.5 text-slate-400" />虚线空心 = 待实证（下一步指引）
            </span>
            <span>形状=实体角色 · 颜色=实体类型 · 边色=关系语义（同实证图谱）</span>
          </div>
        </CardContent>
      </Card>

      {/* 蓝图可视化 */}
      <Card className="overflow-hidden border-border/75 shadow-card bg-card">
        <CardContent ref={containerRef} className="relative h-[26rem] overflow-hidden p-0 bg-dot-grid bg-muted/10">
          {graphData.nodes.length > 0 ? (
            <ForceGraph2D
              ref={graphRef as any}
              graphData={graphData}
              width={graphSize.width}
              height={graphSize.height}
              nodeLabel={(node: any) => {
                const bp = (blueprint?.nodes || []).find((n) => n.id === node.id);
                return bp
                  ? `${blueprintEntityTypeText(bp.entity_type)}: ${bp.label} · ${bp.evidence.entity_count > 0 ? "已实证" : "待实证"}`
                  : node.name;
              }}
              nodeCanvasObject={paintNode}
              nodeVal={(node: any) => node.val}
              linkLabel={(link: any) => link.label}
              linkColor={(link: any) => getRelationColor(link.relationType)}
              linkWidth={1}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.9}
              linkDirectionalArrowColor={(link: any) => getRelationColor(link.relationType)}
              linkCurvature={0.08}
              onNodeClick={(node: any) => setSelectedNodeId(node.id === selectedNodeId ? null : node.id)}
              onBackgroundClick={() => setSelectedNodeId(null)}
              enableZoomInteraction={false}
              enablePointerInteraction
              cooldownTicks={90}
              cooldownTime={1200}
              warmupTicks={30}
              autoPauseRedraw
              minZoom={0.3}
              maxZoom={2.2}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <FileText className="mb-2 h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无知识蓝图</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {canWrite ? "点击右上角「解析计划/纪要」，从项目计划书生成计划态图谱" : "请项目负责人解析项目计划书以生成蓝图"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* 下一步指引：未覆盖清单 */}
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">下一步指引（待实证知识点）</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            {uncoveredNodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                {blueprint && blueprint.coverage.total_nodes > 0 ? "所有计划知识点均已被实验记录覆盖" : "解析计划书后，这里会列出尚未实证的知识点"}
              </p>
            ) : (
              uncoveredNodes.map((node) => (
                <Badge
                  key={node.id}
                  variant="outline"
                  className="cursor-pointer gap-1 border-dashed py-0.5 text-[11px] font-normal"
                  onClick={() => setSelectedNodeId(node.id)}
                >
                  <span className="inline-block h-2 w-2 rounded-full ring-1 ring-black/10 dark:ring-white/10" style={{ backgroundColor: getEntityColor(node.entity_type) }} />
                  {node.label}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>

        {/* 节点详情 + 解析记录 */}
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">节点详情与解析记录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {selectedNode ? (
              <div className="space-y-1.5 rounded-lg border border-border/70 bg-muted/20 p-3 text-xs">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{selectedNode.label}</p>
                  {selectedNode.evidence.entity_count > 0 ? (
                    <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">已实证</Badge>
                  ) : (
                    <Badge variant="outline" className="border-dashed">待实证</Badge>
                  )}
                </div>
                <p className="text-muted-foreground">
                  {blueprintEntityTypeText(selectedNode.entity_type)} · 来源：{SOURCE_KIND_TEXT[selectedNode.source_kind] || selectedNode.source_kind}
                  （{selectedNode.source_label}）· 优先级 {selectedNode.priority}
                </p>
                {selectedNode.description && (
                  <p className="text-muted-foreground">描述：{selectedNode.description}</p>
                )}
                {selectedNode.evidence.last_evidence_at && (
                  <p className="text-muted-foreground">
                    最近实证：{new Date(selectedNode.evidence.last_evidence_at).toLocaleString()}
                  </p>
                )}
                {canWrite && (
                  <div className="pt-1">
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleRetire(selectedNode.id)}>
                      作废该计划节点
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">点击蓝图节点或待实证标签查看详情。</p>
            )}
            <div className="space-y-1">
              {(blueprint?.documents || []).slice(0, 3).map((doc) => (
                <p key={doc.id} className="truncate text-[11px] text-muted-foreground">
                  <FileText className="mr-1 inline h-3 w-3" />
                  {doc.title}（{SOURCE_KIND_TEXT[doc.source_kind] || doc.source_kind} · {doc.parse_mode === "llm" ? "AI" : "规则"}模式）→ 节点 {doc.node_count} / 关系 {doc.edge_count}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export type { BlueprintNode, KnowledgeBlueprint };
