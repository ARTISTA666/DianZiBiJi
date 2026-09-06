/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Focus, Info, Map as MapIcon, ZoomIn, ZoomOut, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";

// react-force-graph-2d 不支持 SSR，需动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((mod) => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex h-80 items-center justify-center text-sm text-muted-foreground">
      加载图谱可视化...
    </div>
  ),
});

export interface KgEntity {
  id: number;
  project_id: number;
  entity_type: string;
  label: string;
  updated_at?: string;
}

export interface KgRelation {
  id: number;
  project_id: number;
  source_entity_id: number;
  target_entity_id: number;
  relation_type: string;
  confidence: number;
}

interface GraphNode {
  id: number;
  name: string;
  entityType: string;
  val: number;
  color: string;
  shape: NodeShape;
  freshness: number;
}

interface GraphLink {
  source: number;
  target: number;
  label: string;
  relationType: string;
  confidence: number;
  color: string;
}

export type NodeShape = "circle" | "square" | "diamond" | "hexagon" | "triangle";

// 实体类型 → 颜色映射（颜色通道 = 实体类型）
const ENTITY_COLORS: Record<string, string> = {
  note: "#6366f1",
  project: "#3b82f6",
  user: "#8b5cf6",
  file: "#06b6d4",
  reagent: "#f59e0b",
  instrument: "#10b981",
  sample: "#ef4444",
  result: "#ec4899",
  cell_type: "#14b8a6",
  cell_line: "#0ea5e9",
  group: "#a855f7",
  perturbation: "#f97316",
  treatment: "#84cc16",
  culture: "#22d3ee",
  biosample: "#e11d48",
  geo_accession: "#7c3aed",
  software: "#64748b",
  experiment_type: "#0284c7",
};

export function getEntityColor(entityType: string): string {
  return ENTITY_COLORS[entityType] || "#94a3b8";
}

// 形状通道 = 实体角色：研究对象(圆)/记录与组织(方)/材料与工具(菱)/方法与过程(六边)/产出(三角)
export const ENTITY_SHAPES: Record<string, NodeShape> = {
  project: "square",
  note: "square",
  file: "square",
  user: "square",
  sample: "circle",
  biosample: "circle",
  cell_type: "circle",
  cell_line: "circle",
  geo_accession: "circle",
  reagent: "diamond",
  instrument: "diamond",
  software: "diamond",
  experiment_type: "hexagon",
  treatment: "hexagon",
  perturbation: "hexagon",
  culture: "hexagon",
  group: "hexagon",
  result: "triangle",
};

export const SHAPE_LABELS: Array<{ shape: NodeShape; label: string }> = [
  { shape: "circle", label: "研究对象" },
  { shape: "square", label: "记录/组织" },
  { shape: "diamond", label: "材料/工具" },
  { shape: "hexagon", label: "方法/过程" },
  { shape: "triangle", label: "产出" },
];

// 边颜色通道 = 关系语义组：结构(蓝)/使用(琥珀)/产出(绿)
export const RELATION_GROUPS: Record<string, { color: string; label: string }> = {
  has_note: { color: "#3b82f6", label: "结构关系" },
  has_attachment: { color: "#3b82f6", label: "结构关系" },
  created_by: { color: "#3b82f6", label: "结构关系" },
  has_experiment_type: { color: "#3b82f6", label: "结构关系" },
  uses_reagent: { color: "#d97706", label: "使用关系" },
  uses_instrument: { color: "#d97706", label: "使用关系" },
  uses_sample: { color: "#d97706", label: "使用关系" },
  produces_result: { color: "#059669", label: "产出关系" },
};

export const RELATION_GROUP_LEGEND = [
  { color: "#3b82f6", label: "结构关系" },
  { color: "#d97706", label: "使用关系" },
  { color: "#059669", label: "产出关系" },
];

export function getRelationColor(relationType: string): string {
  return RELATION_GROUPS[relationType]?.color || "#94a3b8";
}

export function hexToRgba(hex: string, alpha: number): string {
  const value = hex.replace("#", "");
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// 按角色画形状路径（以 x,y 为中心、r 为外接半径）
export function traceShapePath(ctx: CanvasRenderingContext2D, shape: NodeShape, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (shape) {
    case "circle":
      ctx.arc(x, y, r, 0, Math.PI * 2);
      break;
    case "square": {
      const k = r * 0.92;
      const corner = r * 0.22;
      ctx.roundRect(x - k, y - k, k * 2, k * 2, corner);
      break;
    }
    case "diamond":
      ctx.moveTo(x, y - r * 1.1);
      ctx.lineTo(x + r * 1.05, y);
      ctx.lineTo(x, y + r * 1.1);
      ctx.lineTo(x - r * 1.05, y);
      ctx.closePath();
      break;
    case "triangle":
      ctx.moveTo(x, y - r * 1.12);
      ctx.lineTo(x + r * 1.05, y + r * 0.78);
      ctx.lineTo(x - r * 1.05, y + r * 0.78);
      ctx.closePath();
      break;
    case "hexagon": {
      for (let i = 0; i < 6; i += 1) {
        const angle = Math.PI / 6 + (i * Math.PI) / 3;
        const px = x + r * Math.cos(angle);
        const py = y + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      break;
    }
  }
}

export function KnowledgeGraphVisualization({
  entities,
  relations,
  selectedEntityId,
  onEntitySelect,
}: {
  entities: KgEntity[];
  relations: KgRelation[];
  selectedEntityId: number | null;
  onEntitySelect: (id: number | null) => void;
}) {
  const graphRef = useRef<any>(null);
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const fitOnEngineStopRef = useRef(true);
  const [graphSize, setGraphSize] = useState({ width: 0, height: 320 });
  const [legendOpen, setLegendOpen] = useState(true);

  // 构建图数据
  const { nodes, links } = useMemo(() => {
    // 只展示有关系的实体
    const relatedIds = new Set<number>();
    relations.forEach((r) => {
      relatedIds.add(r.source_entity_id);
      relatedIds.add(r.target_entity_id);
    });
    const visibleEntities = entities.filter((e) => relatedIds.has(e.id));

    // 水波通道 = 证据新鲜度：updated_at 在全图内归一化（最新=满波，最旧=0.15 底波）
    const times = visibleEntities
      .map((e) => (e.updated_at ? new Date(e.updated_at).getTime() : Number.NaN))
      .filter((t) => Number.isFinite(t));
    const minT = times.length ? Math.min(...times) : 0;
    const maxT = times.length ? Math.max(...times) : 0;
    const span = maxT - minT || 1;

    const graphNodes: GraphNode[] = visibleEntities.map((e) => {
      const degree = relations.filter(
        (r) => r.source_entity_id === e.id || r.target_entity_id === e.id
      ).length;
      const t = e.updated_at ? new Date(e.updated_at).getTime() : Number.NaN;
      const freshness = Number.isFinite(t) ? 0.15 + 0.85 * ((t - minT) / span) : 0.5;
      return {
        id: e.id,
        name: e.label,
        entityType: e.entity_type,
        val: Math.max(3, Math.min(12, degree * 2)),
        color: getEntityColor(e.entity_type),
        shape: ENTITY_SHAPES[e.entity_type] || "circle",
        freshness,
      };
    });

    const graphLinks: GraphLink[] = relations
      .filter((r) => relatedIds.has(r.source_entity_id) && relatedIds.has(r.target_entity_id))
      .map((r) => ({
        source: r.source_entity_id,
        target: r.target_entity_id,
        label: kgRelationTypeText[r.relation_type] || r.relation_type,
        relationType: r.relation_type,
        confidence: r.confidence,
        color: getRelationColor(r.relation_type),
      }));

    return { nodes: graphNodes, links: graphLinks };
  }, [entities, relations]);

  // 保持引用稳定：悬停、选中等 UI 状态变化不应让 ForceGraph 误以为整张图换了数据。
  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  // 让节点之间保持更宽松的间距，并在数据变化后重新适配到容器内。
  const configureGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.d3Force("charge")?.strength(-170);
    graph.d3Force("link")?.distance(56);
    graph.d3Force("center")?.strength(0.8);
  }, []);

  const fitGraph = useCallback(() => {
    graphRef.current?.zoomToFit?.(0, 36);
  }, []);

  const freezeLayout = useCallback(() => {
    const currentNodes = graphRef.current?.graphData?.().nodes || [];
    currentNodes.forEach((node: any) => {
      if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
        node.fx = node.x;
        node.fy = node.y;
      }
    });
  }, []);

  const handleEngineStop = useCallback(() => {
    if (!fitOnEngineStopRef.current) return;
    fitOnEngineStopRef.current = false;
    freezeLayout();
    fitGraph();
  }, [fitGraph, freezeLayout]);

  const zoomGraph = useCallback((factor: number) => {
    const graph = graphRef.current;
    if (!graph) return;
    const current = graph.zoom?.() || 1;
    graph.zoom?.(Math.max(0.3, Math.min(2.2, current * factor)), 180);
  }, []);

  useEffect(() => {
    const container = graphContainerRef.current;
    if (!container) return;
    const updateSize = () => setGraphSize({ width: container.clientWidth, height: container.clientHeight });
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(configureGraph, 120);
    return () => window.clearTimeout(timer);
  }, [configureGraph, graphSize.width, graphSize.height, nodes.length, links.length]);

  useEffect(() => {
    fitOnEngineStopRef.current = true;
  }, [graphData]);

  // 选中实体时高亮关联
  const highlightedIds = useMemo(() => {
    if (selectedEntityId === null) return new Set<number>();
    const ids = new Set<number>([selectedEntityId]);
    relations.forEach((r) => {
      if (r.source_entity_id === selectedEntityId) ids.add(r.target_entity_id);
      if (r.target_entity_id === selectedEntityId) ids.add(r.source_entity_id);
    });
    return ids;
  }, [selectedEntityId, relations]);

  const handleNodeClick = useCallback((node: any) => {
    onEntitySelect(node.id === selectedEntityId ? null : node.id);
  }, [selectedEntityId, onEntitySelect]);

  const handleNodeDragEnd = useCallback((node: any) => {
    node.fx = node.x;
    node.fy = node.y;
  }, []);

  // 自定义节点绘制：形状=角色、颜色=类型、大小=关联度、水波高度=证据新鲜度
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = Math.sqrt(Math.max(node.val, 1)) * 4.5;
    const x = node.x;
    const y = node.y;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    const dimmed = selectedEntityId !== null && !highlightedIds.has(node.id);
    const selected = node.id === selectedEntityId;
    const baseColor = dimmed ? "#cbd5e1" : node.color;

    // 底色（水波以上部分）
    traceShapePath(ctx, node.shape, x, y, r);
    ctx.fillStyle = dimmed ? "rgba(226, 232, 240, 0.85)" : hexToRgba(baseColor, 0.18);
    ctx.fill();

    // 水波填充：高度=证据新鲜度，波面带相位起伏
    ctx.save();
    traceShapePath(ctx, node.shape, x, y, r);
    ctx.clip();
    const level = y + r - 2 * r * Math.min(1, Math.max(0.06, node.freshness));
    ctx.beginPath();
    ctx.moveTo(x - r * 1.2, y + r * 1.2);
    ctx.lineTo(x - r * 1.2, level);
    for (let px = x - r; px <= x + r; px += 2) {
      ctx.lineTo(px, level + Math.sin((px - x) * 0.5 + node.id * 1.7) * r * 0.1);
    }
    ctx.lineTo(x + r * 1.2, y + r * 1.2);
    ctx.closePath();
    ctx.fillStyle = dimmed ? "rgba(203, 213, 225, 0.9)" : hexToRgba(baseColor, 0.88);
    ctx.fill();
    ctx.restore();

    // 轮廓：选中态加粗高亮
    traceShapePath(ctx, node.shape, x, y, r);
    ctx.strokeStyle = selected ? "#4f46e5" : dimmed ? "#cbd5e1" : baseColor;
    ctx.lineWidth = (selected ? 2.6 : 1.2) / Math.max(globalScale, 0.5);
    ctx.stroke();
  }, [selectedEntityId, highlightedIds]);

  // 统计实体类型分布
  const typeDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach((n) => {
      const label = kgEntityTypeText[n.entityType] || n.entityType;
      counts[label] = (counts[label] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <Info className="mb-2 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">暂无可视化的图谱数据</p>
          <p className="mt-1 text-xs text-muted-foreground">请先创建实验笔记并审核，系统会自动抽取实体和关系</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-border/75 shadow-card bg-card">
      <CardHeader className="pb-3 border-b border-border/60 bg-muted/20">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold">图谱可视化</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {nodes.length} 节点 · {links.length} 边 · 形状=角色 · 颜色=类型 · 大小=关联度 · 水波=证据新鲜度 · 边色=关系语义
            </p>
          </div>
          <div className="min-w-0 flex-1 items-center justify-end gap-2 sm:flex">
            {/* 图例 */}
            <div className="hidden min-w-0 flex-1 flex-wrap justify-end gap-1.5 sm:flex">
              {typeDistribution.slice(0, 6).map(([label, count]) => {
                const entityType = Object.entries(kgEntityTypeText).find(([, v]) => v === label)?.[0] || label;
                return (
                  <Badge key={label} variant="outline" className="gap-1.5 text-[10px] font-normal border-border/60 bg-background/80 py-0.5">
                    <span className="inline-block h-2 w-2 rounded-full ring-1 ring-black/10 dark:ring-white/10" style={{ backgroundColor: getEntityColor(entityType) }} />
                    {label} ({count})
                  </Badge>
                );
              })}
            </div>
            <div className="flex items-center rounded-lg border border-border/70 bg-background/90 shadow-subtle p-0.5">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 rounded-md"
                aria-label="切换语义图例"
                title="切换语义图例"
                onClick={() => setLegendOpen((v) => !v)}
              >
                <MapIcon className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md" aria-label="缩小图谱" title="缩小图谱" onClick={() => zoomGraph(0.8)}>
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md" aria-label="放大图谱" title="放大图谱" onClick={() => zoomGraph(1.25)}>
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md" aria-label="重置图谱视图" title="重置图谱视图" onClick={() => graphRef.current?.zoomToFit?.(250, 36)}>
                <Focus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent ref={graphContainerRef} className="relative h-[min(68vh,44rem)] min-h-[32rem] overflow-hidden p-0 bg-dot-grid bg-muted/10">
        {graphSize.width > 0 && <ForceGraph2D
          ref={graphRef as any}
          graphData={graphData}
          width={graphSize.width}
          height={graphSize.height}
          nodeLabel={(node: any) => `${kgEntityTypeText[node.entityType] || node.entityType}: ${node.name} · 证据新鲜度 ${(node.freshness * 100).toFixed(0)}%`}
          nodeVal={(node: any) => node.val}
          nodeCanvasObject={paintNode}
          linkLabel={(link: any) => `${link.label}（置信度 ${link.confidence.toFixed(2)}）`}
          linkColor={(link: any) => {
            if (selectedEntityId !== null) {
              const isHighlighted = link.source.id === selectedEntityId || link.target.id === selectedEntityId
                || link.source === selectedEntityId || link.target === selectedEntityId;
              return isHighlighted ? getRelationColor(link.relationType) : "#e2e8f0";
            }
            return getRelationColor(link.relationType);
          }}
          linkWidth={(link: any) => {
            if (selectedEntityId !== null) {
              const isHighlighted = link.source.id === selectedEntityId || link.target.id === selectedEntityId
                || link.source === selectedEntityId || link.target === selectedEntityId;
              return isHighlighted ? 2 : 0.5;
            }
            return 1.1;
          }}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.9}
          linkDirectionalArrowColor={(link: any) => getRelationColor(link.relationType)}
          linkCurvature={0.1}
          onNodeClick={handleNodeClick}
          onNodeDragEnd={handleNodeDragEnd}
          onBackgroundClick={() => onEntitySelect(null)}
          enableZoomInteraction={false}
          enablePointerInteraction
          onEngineStop={handleEngineStop}
          minZoom={0.3}
          maxZoom={2.2}
          cooldownTicks={90}
          cooldownTime={1200}
          d3AlphaDecay={0.08}
          d3VelocityDecay={0.45}
          warmupTicks={40}
          autoPauseRedraw
        />}
        {legendOpen && (
          <div className="absolute bottom-3 left-3 z-10 w-64 rounded-lg border border-border/70 bg-background/95 p-3 shadow-subtle backdrop-blur">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold">语义映射图例</p>
              <button
                type="button"
                aria-label="收起语义图例"
                className="rounded p-0.5 text-muted-foreground hover:bg-muted"
                onClick={() => setLegendOpen(false)}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
            <div className="space-y-2 text-[11px] leading-relaxed text-muted-foreground">
              <div>
                <p className="mb-1 font-medium text-foreground/80">形状 = 实体角色</p>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {SHAPE_LABELS.map(({ shape, label }) => (
                    <span key={shape} className="inline-flex items-center gap-1">
                      <svg width="12" height="12" viewBox="0 0 12 12">
                        {shape === "circle" && <circle cx="6" cy="6" r="5" fill="#94a3b8" />}
                        {shape === "square" && <rect x="1.5" y="1.5" width="9" height="9" rx="1.5" fill="#94a3b8" />}
                        {shape === "diamond" && <path d="M6 0.5 L11.5 6 L6 11.5 L0.5 6 Z" fill="#94a3b8" />}
                        {shape === "hexagon" && <path d="M8.9 1.2 L11.3 6 L8.9 10.8 L3.1 10.8 L0.7 6 L3.1 1.2 Z" fill="#94a3b8" />}
                        {shape === "triangle" && <path d="M6 1 L11.3 10.4 L0.7 10.4 Z" fill="#94a3b8" />}
                      </svg>
                      {label}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1 font-medium text-foreground/80">颜色 = 实体类型（见右上）</p>
                <p>大小 = 关联度（连接越多节点越大）</p>
                <p>水波 = 证据新鲜度（满波=最近更新，低波=待复核）</p>
              </div>
              <div>
                <p className="mb-1 font-medium text-foreground/80">边颜色 = 关系语义</p>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {RELATION_GROUP_LEGEND.map((g) => (
                    <span key={g.label} className="inline-flex items-center gap-1">
                      <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: g.color }} />
                      {g.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
