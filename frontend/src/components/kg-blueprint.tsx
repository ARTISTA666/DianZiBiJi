/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  CheckCircle2,
  CircleDashed,
  ClipboardList,
  FileText,
  Loader2,
  Sparkles,
  Focus,
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Tag,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
    <div className="flex h-[30rem] items-center justify-center text-sm text-muted-foreground">
      <div className="flex flex-col items-center gap-2">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span>加载知识蓝图可视化...</span>
      </div>
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
  evidenceCount: number;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

interface GraphLink {
  source: any;
  target: any;
  relationType: string;
  label: string;
  color: string;
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
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [showLinkLabels, setShowLinkLabels] = useState(false);
  const [graphSize, setGraphSize] = useState({ width: 0, height: 480 });

  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fitOnEngineStopRef = useRef(true);

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
    const updateSize = () => {
      setGraphSize({
        width: container.clientWidth,
        height: container.clientHeight,
      });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [blueprint, isFullscreen]);

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
      evidenceCount: n.evidence.entity_count,
      val: Math.max(4, Math.min(16, 4 + n.evidence.entity_count * 2.5)),
    }));

    const links: GraphLink[] = blueprint.edges
      .filter((e) => activeIds.has(e.source_node_id) && activeIds.has(e.target_node_id))
      .map((e) => ({
        source: e.source_node_id,
        target: e.target_node_id,
        relationType: e.relation_type,
        label: kgRelationTypeText[e.relation_type] || e.relation_type,
        color: getRelationColor(e.relation_type),
      }));

    return { nodes, links };
  }, [blueprint]);

  const uncoveredNodes = useMemo(
    () => (blueprint?.nodes || []).filter((n) => n.evidence.entity_count === 0),
    [blueprint]
  );

  const selectedNode = useMemo(
    () => (blueprint?.nodes || []).find((n) => n.id === selectedNodeId) || null,
    [blueprint, selectedNodeId]
  );

  // 力导引配置
  const configureGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.d3Force("charge")?.strength(-240);
    graph.d3Force("link")?.distance(90);
    graph.d3Force("center")?.strength(0.7);

    const d3 = (window as any).d3;
    if (d3?.forceCollide) {
      graph.d3Force(
        "collide",
        d3.forceCollide((n: any) => {
          const r = Math.sqrt(Math.max(n.val || 4, 1)) * 4.4;
          return r + 14;
        })
      );
    }
  }, []);

  const fitGraph = useCallback((duration = 400) => {
    graphRef.current?.zoomToFit?.(duration, 48);
  }, []);

  const handleEngineStop = useCallback(() => {
    if (!fitOnEngineStopRef.current) return;
    fitOnEngineStopRef.current = false;
    fitGraph(300);
  }, [fitGraph]);

  const zoomGraph = useCallback((factor: number) => {
    const graph = graphRef.current;
    if (!graph) return;
    const current = graph.zoom?.() || 1;
    graph.zoom?.(Math.max(0.2, Math.min(3.0, current * factor)), 200);
  }, []);

  const focusOnNode = useCallback(
    (nodeId: number) => {
      const targetNode = graphData.nodes.find((n) => n.id === nodeId);
      if (!targetNode || !graphRef.current) return;
      const x = targetNode.x;
      const y = targetNode.y;
      if (Number.isFinite(x) && Number.isFinite(y)) {
        graphRef.current.centerAt(x, y, 600);
        graphRef.current.zoom(1.4, 600);
      }
    },
    [graphData.nodes]
  );

  useEffect(() => {
    const timer = window.setTimeout(configureGraph, 100);
    return () => window.clearTimeout(timer);
  }, [configureGraph, graphSize.width, graphSize.height, graphData.nodes.length]);

  useEffect(() => {
    fitOnEngineStopRef.current = true;
  }, [graphData]);

  // 双态高保真 Canvas 节点绘制（创新点一：实证翡翠态 vs 计划虚线脉冲态）
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x;
      const y = node.y;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const r = Math.max(14, Math.min(28, 12 + Math.sqrt(Math.max(node.val || 4, 1)) * 3.8));
      const baseColor = getEntityColor(node.entityType);
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const covered = node.covered;

      // 1. 选中或悬停外环
      if (isSelected) {
        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r + 6 / globalScale);
        ctx.fillStyle = hexToRgba("#4f46e5", 0.2);
        ctx.fill();
        traceShapePath(ctx, node.shape, x, y, r + 3.5 / globalScale);
        ctx.strokeStyle = "#4f46e5";
        ctx.lineWidth = 2.2 / globalScale;
        ctx.stroke();
        ctx.restore();
      } else if (isHovered) {
        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r + 3 / globalScale);
        ctx.strokeStyle = hexToRgba(baseColor, 0.6);
        ctx.lineWidth = 1.8 / globalScale;
        ctx.stroke();
        ctx.restore();
      }

      // 2. 双态渲染：已实证 vs 待实证
      if (covered) {
        // 【已实证态】: 充盈翡翠/青碧波澜，立体宝石感
        traceShapePath(ctx, node.shape, x, y, r);
        ctx.fillStyle = hexToRgba(baseColor, 0.15);
        ctx.fill();

        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r);
        ctx.clip();

        // 饱满水波
        const grad = ctx.createLinearGradient(x, y - r * 0.4, x, y + r);
        grad.addColorStop(0, hexToRgba("#10b981", 0.82));
        grad.addColorStop(1, hexToRgba("#059669", 0.98));

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(x, y + r * 0.2, r * 1.3, 0, Math.PI * 2);
        ctx.fill();

        // 玻璃高光
        const sheen = ctx.createLinearGradient(x, y - r, x, y);
        sheen.addColorStop(0, "rgba(255, 255, 255, 0.4)");
        sheen.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = sheen;
        ctx.beginPath();
        ctx.arc(x, y - r * 0.4, r * 0.8, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // 外实线边框
        traceShapePath(ctx, node.shape, x, y, r);
        ctx.strokeStyle = isSelected ? "#4f46e5" : hexToRgba("#10b981", 0.95);
        ctx.lineWidth = (isSelected ? 2.5 : 1.5) / Math.max(globalScale, 0.6);
        ctx.stroke();

        // 中心对勾徽章 (✓)
        ctx.font = `bold ${Math.max(10, r * 0.7)}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#ffffff";
        ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
        ctx.shadowBlur = 3;
        ctx.fillText("✓", x, y);
        ctx.shadowBlur = 0;
      } else {
        // 【待实证态】: 空心科技虚线环，流光内核，提示"下一步缺口"
        traceShapePath(ctx, node.shape, x, y, r);
        ctx.fillStyle = hexToRgba(baseColor, 0.08);
        ctx.fill();

        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r);
        ctx.setLineDash([5 / Math.max(globalScale, 0.6), 3.5 / Math.max(globalScale, 0.6)]);
        ctx.strokeStyle = isSelected ? "#4f46e5" : hexToRgba(baseColor, 0.85);
        ctx.lineWidth = (isSelected ? 2.4 : 1.6) / Math.max(globalScale, 0.6);
        ctx.stroke();
        ctx.restore();

        // 中心提示点（星芒/感叹号）
        ctx.font = `bold ${Math.max(9, r * 0.65)}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = hexToRgba(baseColor, 0.95);
        ctx.fillText("✦", x, y);
      }

      // 3. 自适应文字药丸标签
      if (showLabels || isSelected || isHovered || globalScale >= 0.75) {
        const rawName = node.name || "";
        const maxLen = isSelected || isHovered ? 24 : 13;
        const displayName = rawName.length > maxLen ? `${rawName.slice(0, maxLen)}…` : rawName;

        const fontSize = Math.max(9, Math.min(12, 11 / Math.sqrt(Math.max(globalScale, 0.65))));
        ctx.font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        const textWidth = ctx.measureText(displayName).width;

        const pillHeight = fontSize + 6;
        const pillWidth = textWidth + 12;
        const pillY = y + r + 3 / globalScale;

        ctx.save();
        ctx.fillStyle = isSelected
          ? "rgba(30, 27, 75, 0.95)"
          : isHovered
          ? "rgba(15, 23, 42, 0.92)"
          : "rgba(15, 23, 42, 0.82)";
        ctx.beginPath();
        ctx.roundRect(x - pillWidth / 2, pillY, pillWidth, pillHeight, 4);
        ctx.fill();

        ctx.strokeStyle = isSelected
          ? "#818cf8"
          : covered
          ? "rgba(16, 185, 129, 0.5)"
          : "rgba(255, 255, 255, 0.16)";
        ctx.lineWidth = 1 / globalScale;
        ctx.stroke();

        ctx.fillStyle = isSelected || isHovered ? "#ffffff" : "#f1f5f9";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(displayName, x, pillY + pillHeight / 2);
        ctx.restore();
      }
    },
    [selectedNodeId, hoveredNodeId, showLabels]
  );

  // 连线关系标签
  const paintLinkCanvas = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source;
      const target = link.target;
      if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(target.x)) return;

      const isFocused =
        (selectedNodeId !== null && (source.id === selectedNodeId || target.id === selectedNodeId)) ||
        (hoveredNodeId !== null && (source.id === hoveredNodeId || target.id === hoveredNodeId));

      if (!showLinkLabels && !isFocused) return;

      const mx = (source.x + target.x) / 2;
      const my = (source.y + target.y) / 2;

      const label = link.label;
      const fontSize = Math.max(8, Math.min(11, 10 / Math.sqrt(Math.max(globalScale, 0.65))));
      ctx.font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      const tw = ctx.measureText(label).width;
      const pw = tw + 8;
      const ph = fontSize + 4;

      ctx.save();
      ctx.fillStyle = isFocused ? "rgba(15, 23, 42, 0.92)" : "rgba(15, 23, 42, 0.8)";
      ctx.beginPath();
      ctx.roundRect(mx - pw / 2, my - ph / 2, pw, ph, 3);
      ctx.fill();

      ctx.strokeStyle = isFocused ? hexToRgba(link.color, 0.9) : "rgba(255, 255, 255, 0.18)";
      ctx.lineWidth = 1 / globalScale;
      ctx.stroke();

      ctx.fillStyle = isFocused ? "#ffffff" : "#e2e8f0";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, mx, my);
      ctx.restore();
    },
    [selectedNodeId, hoveredNodeId, showLinkLabels]
  );

  const handleParse = async () => {
    if (!parseTitle.trim() || parseText.trim().length < 10) return;
    setParseBusy(true);
    setError("");
    try {
      const result = await parseProjectKnowledgeBlueprint(token, projectId, {
        title: parseTitle.trim(),
        source_kind: parseSourceKind,
        text: parseText.trim(),
      });
      const summary = `解析完成（${
        result.parse_mode === "llm" ? "AI 导师模型" : "规则兜底模式"
      }）：新增 ${result.nodes_added}、覆盖更新 ${result.nodes_updated}、新增关系 ${result.edges_added}`;
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
      await patchProjectKnowledgeBlueprintNode(token, projectId, nodeId, { status: "retired" });
      setSelectedNodeId(null);
      await loadBlueprint();
    } catch (e) {
      setError(getErrorMessage(e, "修正失败"));
    }
  };

  if (loading) {
    return (
      <Card className="border-border/75">
        <CardContent className="flex h-56 items-center justify-center text-sm text-muted-foreground">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span>加载项目知识蓝图与实证覆盖...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const completionPct = blueprint ? Math.round(blueprint.coverage.completion * 100) : 0;

  return (
    <div
      className={`space-y-3 transition-all duration-200 ${
        isFullscreen ? "fixed inset-0 z-50 h-screen w-screen overflow-y-auto bg-background p-4" : ""
      }`}
    >
      {error && (
        <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {error}
        </div>
      )}

      {/* 覆盖度总览与控制顶栏 */}
      <Card className="border-border/75 shadow-card bg-card">
        <CardHeader className="pb-3 border-b border-border/60 bg-muted/20">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <ClipboardList className="h-4 w-4 text-primary" />
                知识蓝图（计划态 vs 实证态）
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                依据项目计划书或组会纪要解析预期知识网络；实证记录自动覆盖，导引「下一步做什么」
              </p>
            </div>
            {canWrite && (
              <Button
                size="sm"
                variant={showParseForm ? "secondary" : "outline"}
                onClick={() => setShowParseForm((v) => !v)}
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5 text-primary" />
                {showParseForm ? "收起解析面板" : "解析计划书 / 组会纪要"}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight tabular-nums text-foreground">
                {completionPct}%
              </span>
              <span className="text-xs text-muted-foreground">
                实证覆盖 {blueprint?.coverage.covered_nodes ?? 0} /{" "}
                {blueprint?.coverage.total_nodes ?? 0} 个计划知识点
              </span>
            </div>
            <div className="h-2.5 min-w-48 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${completionPct}%` }}
              />
            </div>
          </div>

          {/* 解析表单折叠区 */}
          {showParseForm && canWrite && (
            <div className="space-y-2.5 rounded-xl border border-border/70 bg-muted/20 p-3.5">
              <div className="flex flex-wrap gap-2.5">
                <Input
                  aria-label="文档标题"
                  value={parseTitle}
                  onChange={(e) => setParseTitle(e.target.value)}
                  placeholder="来源标题（如：课题设计论证书 v1 / 09-06 组会决议）"
                  className="h-9 min-w-64 flex-1 bg-background"
                />
                <Select value={parseSourceKind} onValueChange={setParseSourceKind}>
                  <SelectTrigger aria-label="来源类型" className="h-9 w-44 bg-background">
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
                placeholder="粘贴项目大纲、实施方案或导师组会决议文本（至少 10 字）。系统解析后更新计划知识网络；组会纪要具备高来源优先级，可动态修正早期计划。"
                className="min-h-24 bg-background text-xs leading-relaxed"
              />
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <p className="text-[11px] text-muted-foreground">
                  优先由 LLM 语义大模型智能析取；若离线则自动无缝回退至规则提取器，全部变更入库审计。
                </p>
                <Button
                  size="sm"
                  onClick={handleParse}
                  disabled={parseBusy || parseText.trim().length < 10 || !parseTitle.trim()}
                >
                  {parseBusy ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  解析并更新蓝图
                </Button>
              </div>
            </div>
          )}

          {/* 图例说明栏 */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground border-t border-border/50 pt-2.5">
            <div className="flex flex-wrap items-center gap-4">
              <span className="inline-flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                实心水波 = 已获实验记录实证
              </span>
              <span className="inline-flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
                <CircleDashed className="h-3.5 w-3.5" />
                虚线流光 = 待实证知识缺口（下一步做）
              </span>
            </div>
            <div className="text-[10px]">
              形状=实体角色 · 颜色=实体类型 · 连线颜色=关系语义
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 蓝图核心画布 */}
      <Card className="overflow-hidden border-border/75 shadow-card bg-card">
        {/* 画布顶部操作条 */}
        <div className="flex items-center justify-between border-b border-border/60 bg-muted/20 px-3 py-1.5 text-xs">
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="text-[10px]">
              {graphData.nodes.length} 计划知识点 · {graphData.links.length} 逻辑关联
            </Badge>
          </div>
          <div className="flex items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs">
                  <Layers className="h-3 w-3" />
                  <span>显示</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuLabel className="text-xs">图层选项</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuCheckboxItem
                  checked={showLabels}
                  onCheckedChange={setShowLabels}
                  className="text-xs"
                >
                  <Tag className="mr-2 h-3.5 w-3.5" />
                  常显标签药丸
                </DropdownMenuCheckboxItem>
                <DropdownMenuCheckboxItem
                  checked={showLinkLabels}
                  onCheckedChange={setShowLinkLabels}
                  className="text-xs"
                >
                  <ArrowRight className="mr-2 h-3.5 w-3.5" />
                  显示关联名称
                </DropdownMenuCheckboxItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => zoomGraph(0.8)}
              title="缩小"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => zoomGraph(1.25)}
              title="放大"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => fitGraph(300)}
              title="重置视图居中"
            >
              <Focus className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => {
                graphRef.current?.d3ReheatSimulation?.();
              }}
              title="重新力场排列"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setIsFullscreen((v) => !v)}
              title={isFullscreen ? "退出全屏" : "全屏查看"}
            >
              {isFullscreen ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>

        <CardContent
          ref={containerRef}
          className={`relative overflow-hidden p-0 bg-dot-grid bg-muted/10 ${
            isFullscreen ? "h-[75vh]" : "h-[min(65vh,38rem)] min-h-[28rem]"
          }`}
        >
          {graphData.nodes.length > 0 ? (
            <ForceGraph2D
              ref={graphRef as any}
              graphData={graphData}
              width={graphSize.width}
              height={graphSize.height}
              nodeLabel={(node: any) => {
                const bp = (blueprint?.nodes || []).find((n) => n.id === node.id);
                return bp
                  ? `${blueprintEntityTypeText(bp.entity_type)}: ${bp.label} · ${
                      bp.evidence.entity_count > 0
                        ? `已实证 (${bp.evidence.entity_count} 笔记录)`
                        : "待实证知识点"
                    }`
                  : node.name;
              }}
              nodeCanvasObject={paintNode}
              nodeVal={(node: any) => node.val}
              linkCanvasObjectMode={() => "after"}
              linkCanvasObject={paintLinkCanvas}
              linkLabel={(link: any) => link.label}
              linkColor={(link: any) => hexToRgba(link.color, 0.7)}
              linkWidth={1.2}
              linkDirectionalArrowLength={6}
              linkDirectionalArrowRelPos={0.88}
              linkDirectionalArrowColor={(link: any) => link.color}
              linkCurvature={0.1}
              onNodeHover={(node: any) => setHoveredNodeId(node ? node.id : null)}
              onNodeClick={(node: any) =>
                setSelectedNodeId(node.id === selectedNodeId ? null : node.id)
              }
              onBackgroundClick={() => setSelectedNodeId(null)}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              enablePointerInteraction={true}
              onEngineStop={handleEngineStop}
              cooldownTicks={100}
              cooldownTime={1200}
              warmupTicks={40}
              autoPauseRedraw
              minZoom={0.2}
              maxZoom={3.5}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center py-16 text-center">
              <FileText className="mb-3 h-10 w-10 text-muted-foreground/60" />
              <p className="text-base font-medium text-foreground">暂无项目知识蓝图</p>
              <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                {canWrite
                  ? "点击上方「解析计划书 / 组会纪要」，从项目文本自动提取预期的知识脉络"
                  : "请项目负责人或导师录入并解析项目计划大纲以生成知识蓝图"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 下方联动区域：下一步指引 与 节点检视 */}
      <div className="grid gap-3 lg:grid-cols-2">
        {/* 下一步指引：未覆盖清单（点击聚焦到图） */}
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2 border-b border-border/60 bg-muted/20">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-1.5 text-sm font-semibold">
                <AlertCircle className="h-4 w-4 text-amber-500" />
                下一步指引（待实证知识缺口）
              </CardTitle>
              <Badge variant="outline" className="text-[10px]">
                剩余 {uncoveredNodes.length} 个缺口
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            {uncoveredNodes.length === 0 ? (
              <div className="flex items-center gap-2 py-4 text-xs text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
                <span>
                  {blueprint && blueprint.coverage.total_nodes > 0
                    ? "恭喜！全部计划知识点均已被实验记录所覆盖证实。"
                    : "暂无待实证节点。解析计划文本后将在此生成下一步科研建议清单。"}
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto pr-1">
                {uncoveredNodes.map((node) => (
                  <Badge
                    key={node.id}
                    variant="outline"
                    className={`cursor-pointer gap-1 border-dashed py-1 text-[11px] transition-colors ${
                      selectedNodeId === node.id
                        ? "border-primary bg-primary/10 text-primary font-medium"
                        : "hover:border-primary/50 hover:bg-muted"
                    }`}
                    onClick={() => {
                      setSelectedNodeId(node.id);
                      focusOnNode(node.id);
                    }}
                  >
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: getEntityColor(node.entity_type) }}
                    />
                    <span>{node.label}</span>
                    <span className="text-[9px] text-muted-foreground">
                      ({blueprintEntityTypeText(node.entity_type)})
                    </span>
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 节点详情与解析文档历史 */}
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2 border-b border-border/60 bg-muted/20">
            <CardTitle className="flex items-center gap-1.5 text-sm font-semibold">
              <ShieldCheck className="h-4 w-4 text-primary" />
              节点属性与来源追溯
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-3">
            {selectedNode ? (
              <div className="space-y-2 rounded-xl border border-border/70 bg-muted/20 p-3 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: getEntityColor(selectedNode.entity_type) }}
                    />
                    <p className="font-semibold text-foreground text-sm">{selectedNode.label}</p>
                    <Badge variant="outline" className="text-[10px] py-0">
                      {blueprintEntityTypeText(selectedNode.entity_type)}
                    </Badge>
                  </div>
                  {selectedNode.evidence.entity_count > 0 ? (
                    <Badge className="bg-emerald-600 text-white text-[10px] py-0">
                      已实证 · {selectedNode.evidence.entity_count} 处
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="border-dashed text-amber-600 text-[10px] py-0">
                      待实证缺口
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 text-muted-foreground pt-1">
                  <p>
                    来源类型：
                    <span className="text-foreground">
                      {SOURCE_KIND_TEXT[selectedNode.source_kind] || selectedNode.source_kind}
                    </span>
                  </p>
                  <p>
                    来源权重：
                    <span className="text-foreground font-medium">
                      优先级 {selectedNode.priority}
                    </span>
                  </p>
                </div>

                {selectedNode.description && (
                  <p className="text-muted-foreground">
                    规划描述：<span className="text-foreground">{selectedNode.description}</span>
                  </p>
                )}

                {selectedNode.evidence.last_evidence_at && (
                  <p className="text-muted-foreground">
                    最近实证记录：
                    <span className="text-foreground">
                      {new Date(selectedNode.evidence.last_evidence_at).toLocaleString()}
                    </span>
                  </p>
                )}

                <div className="flex items-center justify-between pt-1 border-t border-border/50">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => focusOnNode(selectedNode.id)}
                  >
                    <Focus className="mr-1 h-3 w-3" />
                    定位在蓝图中
                  </Button>
                  {canWrite && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-destructive hover:bg-destructive/10"
                      onClick={() => handleRetire(selectedNode.id)}
                    >
                      作废此计划节点
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground py-2">
                点击蓝图中的任一节点或上方「待实证知识缺口」标签，在此查看实体规格与证据映射。
              </p>
            )}

            {/* 来源解析文档清单 */}
            <div className="space-y-1.5 border-t border-border/50 pt-2">
              <p className="text-[11px] font-medium text-foreground">来源文档解析历史</p>
              {(blueprint?.documents || []).length === 0 ? (
                <p className="text-[10px] text-muted-foreground">暂无解析文档记录</p>
              ) : (
                (blueprint?.documents || []).slice(0, 3).map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between rounded border border-border/50 bg-background/50 px-2 py-1 text-[11px] text-muted-foreground"
                  >
                    <span className="truncate max-w-[16rem]">
                      <FileText className="mr-1.5 inline h-3 w-3 text-primary" />
                      {doc.title}
                    </span>
                    <span className="text-[10px]">
                      {SOURCE_KIND_TEXT[doc.source_kind] || doc.source_kind} · {doc.parse_mode === "llm" ? "AI" : "规则"}
                    </span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export type { BlueprintNode, KnowledgeBlueprint };
