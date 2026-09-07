/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Focus,
  Info,
  Layers,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  RotateCcw,
  Sparkles,
  Tag,
  X,
  ZoomIn,
  ZoomOut,
  ArrowRight,
  Clock,
  Network,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { kgEntityTypeText, kgRelationTypeText, kgEntityShortText } from "@/components/constants";

// react-force-graph-2d 不支持 SSR，需动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((mod) => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex h-[32rem] items-center justify-center text-sm text-muted-foreground">
      <div className="flex flex-col items-center gap-2">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span>加载科研图谱渲染引擎...</span>
      </div>
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
  degree: number;
  color: string;
  shape: NodeShape;
  freshness: number;
  updatedAt?: string;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

interface GraphLink {
  source: any;
  target: any;
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
  return ENTITY_COLORS[entityType] || "#64748b";
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
  uses_reagent: { color: "#f59e0b", label: "使用关系" },
  uses_instrument: { color: "#f59e0b", label: "使用关系" },
  uses_sample: { color: "#f59e0b", label: "使用关系" },
  produces_result: { color: "#10b981", label: "产出关系" },
};

export const RELATION_GROUP_LEGEND = [
  { color: "#3b82f6", label: "结构关系" },
  { color: "#f59e0b", label: "使用关系" },
  { color: "#10b981", label: "产出关系" },
];

export function getRelationColor(relationType: string): string {
  return RELATION_GROUPS[relationType]?.color || "#94a3b8";
}

export function hexToRgba(hex: string, alpha: number): string {
  const cleanHex = hex.replace("#", "");
  const r = parseInt(cleanHex.slice(0, 2), 16) || 0;
  const g = parseInt(cleanHex.slice(2, 4), 16) || 0;
  const b = parseInt(cleanHex.slice(4, 6), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

const EXTENDED_SHORT_TEXT: Record<string, string> = {
  ...kgEntityShortText,
  cell_type: "细",
  cell_line: "系",
  biosample: "样",
  perturbation: "扰",
  treatment: "处",
  culture: "培",
  group: "组",
  geo_accession: "登",
  software: "软",
};

// 按角色画形状路径（以 x,y 为中心、r 为外接半径，带平滑圆角设计）
export function traceShapePath(ctx: CanvasRenderingContext2D, shape: NodeShape, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (shape) {
    case "circle":
      ctx.arc(x, y, r, 0, Math.PI * 2);
      break;
    case "square": {
      const k = r * 0.92;
      const corner = Math.min(8, r * 0.3);
      ctx.roundRect(x - k, y - k, k * 2, k * 2, corner);
      break;
    }
    case "diamond": {
      const hr = r * 1.15;
      const wr = r * 1.12;
      ctx.moveTo(x, y - hr);
      ctx.lineTo(x + wr, y);
      ctx.lineTo(x, y + hr);
      ctx.lineTo(x - wr, y);
      ctx.closePath();
      break;
    }
    case "triangle": {
      const top = y - r * 1.18;
      const bottom = y + r * 0.82;
      const wr = r * 1.12;
      ctx.moveTo(x, top);
      ctx.lineTo(x + wr, bottom);
      ctx.lineTo(x - wr, bottom);
      ctx.closePath();
      break;
    }
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
  const containerRef = useRef<HTMLDivElement>(null);
  const fitOnEngineStopRef = useRef(true);

  const [graphSize, setGraphSize] = useState({ width: 0, height: 560 });
  const [legendOpen, setLegendOpen] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const [spotlightType, setSpotlightType] = useState<string | null>(null);

  // 显示控制选项
  const [showLabels, setShowLabels] = useState(true);
  const [showLinkLabels, setShowLinkLabels] = useState(false);
  const [subgraphOnly, setSubgraphOnly] = useState(false);

  // 构建图数据
  const { nodes, links, entityMap } = useMemo(() => {
    const map = new Map<number, KgEntity>();
    entities.forEach((e) => map.set(e.id, e));

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

      // 关联度决定基础尺寸：度数越多节点越宏伟
      const val = Math.max(4, Math.min(18, degree * 2.5));

      return {
        id: e.id,
        name: e.label,
        entityType: e.entity_type,
        val,
        degree,
        color: getEntityColor(e.entity_type),
        shape: ENTITY_SHAPES[e.entity_type] || "circle",
        freshness,
        updatedAt: e.updated_at,
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

    return { nodes: graphNodes, links: graphLinks, entityMap: map };
  }, [entities, relations]);

  // 保持引用稳定
  const graphData = useMemo(() => {
    if (!subgraphOnly || selectedEntityId === null) {
      return { nodes, links };
    }
    // 仅查看一跳子图
    const activeIds = new Set<number>([selectedEntityId]);
    relations.forEach((r) => {
      if (r.source_entity_id === selectedEntityId) activeIds.add(r.target_entity_id);
      if (r.target_entity_id === selectedEntityId) activeIds.add(r.source_entity_id);
    });
    return {
      nodes: nodes.filter((n) => activeIds.has(n.id)),
      links: links.filter(
        (l) =>
          activeIds.has(typeof l.source === "object" ? l.source.id : l.source) &&
          activeIds.has(typeof l.target === "object" ? l.target.id : l.target)
      ),
    };
  }, [nodes, links, subgraphOnly, selectedEntityId, relations]);

  // 计算当前高亮节点网络（选中的节点或悬停的节点）
  const focusEntityId = hoveredNodeId ?? selectedEntityId;
  const highlightedIds = useMemo(() => {
    if (focusEntityId === null) return new Set<number>();
    const ids = new Set<number>([focusEntityId]);
    relations.forEach((r) => {
      if (r.source_entity_id === focusEntityId) ids.add(r.target_entity_id);
      if (r.target_entity_id === focusEntityId) ids.add(r.source_entity_id);
    });
    return ids;
  }, [focusEntityId, relations]);

  // 选中的实体详情与关联明细
  const selectedDetails = useMemo(() => {
    if (selectedEntityId === null) return null;
    const node = nodes.find((n) => n.id === selectedEntityId);
    if (!node) return null;

    const connected = relations
      .filter((r) => r.source_entity_id === selectedEntityId || r.target_entity_id === selectedEntityId)
      .map((r) => {
        const isOutgoing = r.source_entity_id === selectedEntityId;
        const neighborId = isOutgoing ? r.target_entity_id : r.source_entity_id;
        const neighbor = entityMap.get(neighborId);
        const group = RELATION_GROUPS[r.relation_type] || { color: "#94a3b8", label: "其它" };
        return {
          id: r.id,
          relationType: r.relation_type,
          relationLabel: kgRelationTypeText[r.relation_type] || r.relation_type,
          confidence: r.confidence,
          isOutgoing,
          neighborId,
          neighborLabel: neighbor?.label || `实体 #${neighborId}`,
          neighborType: neighbor?.entity_type || "unknown",
          neighborColor: getEntityColor(neighbor?.entity_type || ""),
          groupColor: group.color,
          groupLabel: group.label,
        };
      });

    return {
      node,
      connected,
    };
  }, [selectedEntityId, nodes, relations, entityMap]);

  // 配置舒展、防重叠的物理力导引力场
  const configureGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;

    // 适中斥力与舒展连线张力
    graph.d3Force("charge")?.strength(-260);
    graph.d3Force("link")?.distance(95);
    graph.d3Force("center")?.strength(0.65);

    // 碰撞避免力，彻底杜绝节点重叠
    const d3 = (window as any).d3;
    if (d3?.forceCollide) {
      graph.d3Force(
        "collide",
        d3.forceCollide((n: any) => {
          const r = Math.sqrt(Math.max(n.val || 4, 1)) * 4.6;
          return r + 16;
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

  const focusOnNode = useCallback((nodeId: number) => {
    const targetNode = nodes.find((n) => n.id === nodeId);
    if (!targetNode || !graphRef.current) return;
    const x = targetNode.x;
    const y = targetNode.y;
    if (Number.isFinite(x) && Number.isFinite(y)) {
      graphRef.current.centerAt(x, y, 600);
      graphRef.current.zoom(1.4, 600);
    }
  }, [nodes]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((v) => !v);
    setTimeout(() => {
      fitGraph(200);
    }, 150);
  }, [fitGraph]);

  // 容器尺寸响应
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
  }, [isFullscreen]);

  useEffect(() => {
    const timer = window.setTimeout(configureGraph, 100);
    return () => window.clearTimeout(timer);
  }, [configureGraph, graphSize.width, graphSize.height, nodes.length, links.length]);

  useEffect(() => {
    fitOnEngineStopRef.current = true;
  }, [graphData]);

  // 键盘 Esc 退出全屏或取消选中
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (isFullscreen) setIsFullscreen(false);
        else if (selectedEntityId !== null) onEntitySelect(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen, selectedEntityId, onEntitySelect]);

  // 高保真 Canvas 节点绘制
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x;
      const y = node.y;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      // 半径基于度数：基线 15px ~ 30px
      const r = Math.max(14, Math.min(30, 12 + Math.sqrt(Math.max(node.val || 4, 1)) * 4.2));

      const isSelected = node.id === selectedEntityId;
      const isHovered = node.id === hoveredNodeId;
      const isInSpotlight = !spotlightType || node.entityType === spotlightType;
      const hasFocus = focusEntityId !== null;
      const isInFocusNetwork = highlightedIds.has(node.id);

      const dimmed = (!isInSpotlight) || (hasFocus && !isInFocusNetwork);
      const baseColor = dimmed ? "#94a3b8" : node.color;

      // 1. 选中态的外发光层 / 聚焦扩散环
      if (isSelected) {
        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r + 7 / globalScale);
        ctx.fillStyle = hexToRgba("#4f46e5", 0.22);
        ctx.fill();
        traceShapePath(ctx, node.shape, x, y, r + 4 / globalScale);
        ctx.strokeStyle = "#4f46e5";
        ctx.lineWidth = 2.2 / globalScale;
        ctx.stroke();
        ctx.restore();
      } else if (isHovered) {
        ctx.save();
        traceShapePath(ctx, node.shape, x, y, r + 4 / globalScale);
        ctx.strokeStyle = hexToRgba(baseColor, 0.65);
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
        ctx.restore();
      }

      // 2. 节点底层玻璃器皿（Vessel Background）
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.fillStyle = dimmed
        ? "rgba(241, 245, 249, 0.55)"
        : hexToRgba(baseColor, 0.12);
      ctx.fill();

      // 3. 水波填充：高度 = 证据新鲜度 / 活跃度
      ctx.save();
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.clip();

      const freshness = Math.min(1, Math.max(0.08, node.freshness));
      const waterLevel = y + r - 2 * r * freshness;
      const waveAmp = Math.min(3.2, r * 0.12);
      const phase = node.id * 1.6;
      const startX = x - r * 1.25;
      const endX = x + r * 1.25;
      const midX = (startX + endX) / 2;
      const cp1Y = waterLevel - Math.sin(phase) * waveAmp;
      const cp2Y = waterLevel + Math.sin(phase) * waveAmp;

      // 垂直渐变液体
      const grad = ctx.createLinearGradient(x, waterLevel, x, y + r * 1.2);
      grad.addColorStop(0, hexToRgba(baseColor, dimmed ? 0.35 : 0.8));
      grad.addColorStop(1, hexToRgba(baseColor, dimmed ? 0.55 : 0.98));

      ctx.beginPath();
      ctx.moveTo(startX, y + r * 1.3);
      ctx.lineTo(startX, waterLevel);
      ctx.quadraticCurveTo(startX + (midX - startX) / 2, cp1Y, midX, waterLevel);
      ctx.quadraticCurveTo(midX + (endX - midX) / 2, cp2Y, endX, waterLevel);
      ctx.lineTo(endX, y + r * 1.3);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // 弯月面高光波纹（Meniscus Highlight）
      if (!dimmed && freshness > 0.12) {
        ctx.beginPath();
        ctx.moveTo(startX, waterLevel);
        ctx.quadraticCurveTo(startX + (midX - startX) / 2, cp1Y, midX, waterLevel);
        ctx.quadraticCurveTo(midX + (endX - midX) / 2, cp2Y, endX, waterLevel);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
        ctx.lineWidth = Math.max(1, 1.2 / globalScale);
        ctx.stroke();
      }

      // 上方玻璃反光弧光
      if (!dimmed) {
        const sheenGrad = ctx.createLinearGradient(x, y - r, x, y);
        sheenGrad.addColorStop(0, "rgba(255, 255, 255, 0.38)");
        sheenGrad.addColorStop(0.6, "rgba(255, 255, 255, 0.05)");
        sheenGrad.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = sheenGrad;
        ctx.beginPath();
        ctx.arc(x, y - r * 0.4, r * 0.85, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // 4. 外边框（Rim）
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.strokeStyle = isSelected
        ? "#4f46e5"
        : dimmed
        ? "#cbd5e1"
        : hexToRgba(baseColor, 0.92);
      ctx.lineWidth = (isSelected ? 2.6 : isHovered ? 2.2 : 1.4) / Math.max(globalScale, 0.6);
      ctx.stroke();

      // 5. 节点中心实体类型简标（中文字符，远观一眼识别）
      const shortGlyph = EXTENDED_SHORT_TEXT[node.entityType] || node.entityType.slice(0, 1).toUpperCase();
      const glyphSize = Math.max(9, Math.min(13, r * 0.68));
      ctx.font = `600 ${glyphSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      const liquidIsHigh = freshness >= 0.45;
      ctx.fillStyle = dimmed
        ? "#64748b"
        : liquidIsHigh
        ? "#ffffff"
        : hexToRgba(baseColor, 0.95);

      if (liquidIsHigh && !dimmed) {
        ctx.shadowColor = "rgba(0, 0, 0, 0.45)";
        ctx.shadowBlur = 3;
      }
      ctx.fillText(shortGlyph, x, y);
      ctx.shadowBlur = 0;

      // 6. 节点下方自适应高对比度文字药丸（Adaptive LOD Typography）
      const shouldDrawLabel =
        showLabels ||
        isSelected ||
        isHovered ||
        isInFocusNetwork ||
        globalScale >= 0.8 ||
        node.degree >= 4;

      if (shouldDrawLabel && (!dimmed || isSelected || isHovered)) {
        const rawName = node.name || "";
        const maxLen = isSelected || isHovered ? 24 : 12;
        const displayName = rawName.length > maxLen ? `${rawName.slice(0, maxLen)}…` : rawName;

        const fontSize = Math.max(9, Math.min(12, 11 / Math.sqrt(Math.max(globalScale, 0.65))));
        ctx.font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        const textMetrics = ctx.measureText(displayName);
        const textWidth = textMetrics.width;

        const pillHeight = fontSize + 6;
        const pillWidth = textWidth + 12;
        const pillY = y + r + 3 / globalScale;

        // 磨砂药丸底色
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
          : isHovered
          ? hexToRgba(baseColor, 0.85)
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
    [
      selectedEntityId,
      hoveredNodeId,
      spotlightType,
      focusEntityId,
      highlightedIds,
      showLabels,
    ]
  );

  // 绘制连线文字药丸（关系名称）
  const paintLinkCanvas = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source;
      const target = link.target;
      if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(target.x)) return;

      const isFocused =
        (selectedEntityId !== null && (source.id === selectedEntityId || target.id === selectedEntityId)) ||
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
    [selectedEntityId, hoveredNodeId, showLinkLabels]
  );

  // 统计类型分布
  const typeDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach((n) => {
      counts[n.entityType] = (counts[n.entityType] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center">
          <Info className="mb-3 h-10 w-10 text-muted-foreground/60" />
          <p className="text-base font-medium text-foreground">暂无可展示的图谱实体与关系</p>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">
            请先创建实验笔记并提交审核，审核通过后系统将依据科研规则自动抽取实体网络。
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div
      className={`relative flex flex-col transition-all duration-200 ${
        isFullscreen
          ? "fixed inset-0 z-50 h-screen w-screen bg-background p-4"
          : "w-full"
      }`}
    >
      <Card className="flex flex-1 flex-col overflow-hidden border-border/75 shadow-card bg-card">
        {/* 图谱顶部状态控制栏 */}
        <CardHeader className="flex-none border-b border-border/60 bg-muted/20 py-2.5 px-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm font-semibold sm:text-base">实证图谱可视化</CardTitle>
              <Badge variant="secondary" className="text-[11px] font-normal">
                {nodes.length} 实体 · {links.length} 关系
              </Badge>
              {spotlightType && (
                <Badge
                  variant="outline"
                  className="cursor-pointer gap-1 border-primary/40 bg-primary/10 text-primary text-[11px]"
                  onClick={() => setSpotlightType(null)}
                >
                  聚光灯: {kgEntityTypeText[spotlightType] || spotlightType}
                  <X className="h-3 w-3" />
                </Badge>
              )}
            </div>

            {/* 快捷实体类型聚光灯胶囊 */}
            <div className="hidden min-w-0 flex-1 items-center justify-end gap-1.5 lg:flex">
              {typeDistribution.slice(0, 5).map(([type, count]) => {
                const isCurrent = spotlightType === type;
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setSpotlightType(isCurrent ? null : type)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] transition-colors ${
                      isCurrent
                        ? "border-primary bg-primary text-primary-foreground font-medium shadow-xs"
                        : "border-border/70 bg-background/80 text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: getEntityColor(type) }}
                    />
                    {kgEntityTypeText[type] || type}
                    <span className="opacity-70">({count})</span>
                  </button>
                );
              })}
            </div>

            {/* 核心操作控制组 */}
            <div className="flex items-center gap-1">
              {/* 显示项设置下拉菜单 */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 gap-1 px-2.5 text-xs">
                    <Layers className="h-3.5 w-3.5" />
                    <span>图层</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel className="text-xs">视觉显示选项</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuCheckboxItem
                    checked={showLabels}
                    onCheckedChange={setShowLabels}
                    className="text-xs"
                  >
                    <Tag className="mr-2 h-3.5 w-3.5" />
                    常显实体标签
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={showLinkLabels}
                    onCheckedChange={setShowLinkLabels}
                    className="text-xs"
                  >
                    <ArrowRight className="mr-2 h-3.5 w-3.5" />
                    显示关系连线标签
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={subgraphOnly}
                    onCheckedChange={setSubgraphOnly}
                    disabled={selectedEntityId === null}
                    className="text-xs"
                  >
                    <Network className="mr-2 h-3.5 w-3.5" />
                    仅查看选中子图
                  </DropdownMenuCheckboxItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => setLegendOpen((v) => !v)}
                title={legendOpen ? "收起语义图例" : "展开语义图例"}
                aria-label="图例切换"
              >
                <MapIcon className="h-3.5 w-3.5" />
              </Button>

              <div className="mx-1 h-4 w-px bg-border/80" />

              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => zoomGraph(0.8)}
                title="缩小画布"
                aria-label="缩小"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => zoomGraph(1.25)}
                title="放大画布"
                aria-label="放大"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => fitGraph(300)}
                title="重置视图居中"
                aria-label="居中"
              >
                <Focus className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => {
                  graphRef.current?.d3ReheatSimulation?.();
                }}
                title="重新激发力导引布局"
                aria-label="重新布局"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={toggleFullscreen}
                title={isFullscreen ? "退出全屏 (Esc)" : "全屏图谱探索"}
                aria-label="全屏切换"
              >
                {isFullscreen ? (
                  <Minimize2 className="h-3.5 w-3.5" />
                ) : (
                  <Maximize2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>
        </CardHeader>

        {/* 画布核心区域 */}
        <CardContent
          ref={containerRef}
          className={`relative overflow-hidden p-0 bg-dot-grid bg-muted/10 ${
            isFullscreen ? "flex-1 h-full" : "h-[min(72vh,46rem)] min-h-[34rem]"
          }`}
        >
          {graphSize.width > 0 && (
            <ForceGraph2D
              ref={graphRef as any}
              graphData={graphData}
              width={graphSize.width}
              height={graphSize.height}
              nodeLabel={(node: any) =>
                `${kgEntityTypeText[node.entityType] || node.entityType}: ${node.name} · 证据新鲜度 ${(
                  node.freshness * 100
                ).toFixed(0)}% · 关联度 ${node.degree}`
              }
              nodeVal={(node: any) => node.val}
              nodeCanvasObject={paintNode}
              linkCanvasObjectMode={() => "after"}
              linkCanvasObject={paintLinkCanvas}
              linkLabel={(link: any) =>
                `${link.label}（置信度 ${(link.confidence || 0).toFixed(2)}）`
              }
              linkColor={(link: any) => {
                const sourceId = typeof link.source === "object" ? link.source.id : link.source;
                const targetId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  focusEntityId !== null && (sourceId === focusEntityId || targetId === focusEntityId);

                if (focusEntityId !== null) {
                  return isLinkedToFocus ? link.color : "rgba(203, 213, 225, 0.22)";
                }
                return hexToRgba(link.color, 0.7);
              }}
              linkWidth={(link: any) => {
                const sourceId = typeof link.source === "object" ? link.source.id : link.source;
                const targetId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  focusEntityId !== null && (sourceId === focusEntityId || targetId === focusEntityId);
                return isLinkedToFocus ? 2.5 : 1.2;
              }}
              linkDirectionalArrowLength={6}
              linkDirectionalArrowRelPos={0.88}
              linkDirectionalArrowColor={(link: any) => link.color}
              linkCurvature={0.12}
              onNodeHover={(node: any) => setHoveredNodeId(node ? node.id : null)}
              onNodeClick={(node: any) => {
                onEntitySelect(node.id === selectedEntityId ? null : node.id);
              }}
              onBackgroundClick={() => {
                onEntitySelect(null);
                setSpotlightType(null);
              }}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              enablePointerInteraction={true}
              onEngineStop={handleEngineStop}
              minZoom={0.2}
              maxZoom={3.5}
              cooldownTicks={120}
              cooldownTime={1500}
              d3AlphaDecay={0.05}
              d3VelocityDecay={0.4}
              warmupTicks={50}
              autoPauseRedraw
            />
          )}

          {/* 创新点三：语义映射五通道图例浮层 */}
          {legendOpen && (
            <div className="absolute bottom-3 left-3 z-10 w-72 rounded-xl border border-border/80 bg-background/95 p-3.5 shadow-subtle backdrop-blur-md">
              <div className="mb-2.5 flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  <p className="text-xs font-semibold text-foreground">五通道语义映射（论文创新点）</p>
                </div>
                <button
                  type="button"
                  aria-label="收起语义图例"
                  className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  onClick={() => setLegendOpen(false)}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>

              <div className="space-y-2.5 text-[11px] leading-relaxed text-muted-foreground">
                <div>
                  <p className="mb-1 font-medium text-foreground">1. 形状 = 实体角色（业务归类）</p>
                  <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                    {SHAPE_LABELS.map(({ shape, label }) => (
                      <span key={shape} className="inline-flex items-center gap-1.5">
                        <svg width="12" height="12" viewBox="0 0 12 12" className="flex-none">
                          {shape === "circle" && <circle cx="6" cy="6" r="5" fill="#64748b" />}
                          {shape === "square" && (
                            <rect x="1.5" y="1.5" width="9" height="9" rx="2" fill="#64748b" />
                          )}
                          {shape === "diamond" && (
                            <path d="M6 0.5 L11.5 6 L6 11.5 L0.5 6 Z" fill="#64748b" />
                          )}
                          {shape === "hexagon" && (
                            <path
                              d="M8.9 1.2 L11.3 6 L8.9 10.8 L3.1 10.8 L0.7 6 L3.1 1.2 Z"
                              fill="#64748b"
                            />
                          )}
                          {shape === "triangle" && (
                            <path d="M6 1 L11.3 10.4 L0.7 10.4 Z" fill="#64748b" />
                          )}
                        </svg>
                        <span>{label}</span>
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-1 font-medium text-foreground">2. 水波高度 = 证据新鲜度</p>
                  <div className="flex items-center gap-2">
                    <div className="relative h-4 w-28 overflow-hidden rounded border border-border/80 bg-muted/30">
                      <div className="absolute inset-y-0 left-0 w-3/4 bg-primary/80" />
                      <div className="absolute top-0 right-1/4 h-full w-0.5 bg-white shadow-xs" />
                    </div>
                    <span className="text-[10px]">满波=最近实证 · 低波=待复核</span>
                  </div>
                </div>

                <div>
                  <p className="mb-1 font-medium text-foreground">3. 边颜色 = 关系语义分类</p>
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {RELATION_GROUP_LEGEND.map((g) => (
                      <span key={g.label} className="inline-flex items-center gap-1.5">
                        <span
                          className="inline-block h-1 w-3 rounded-full"
                          style={{ backgroundColor: g.color }}
                        />
                        <span>{g.label}</span>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="pt-1 text-[10px] text-muted-foreground/80 border-t border-border/40">
                  <span>大小 = 关联枢纽度 · 颜色 = 实体类型 · 连线中点 = 语义动作</span>
                </div>
              </div>
            </div>
          )}

          {/* 右侧滑出式「实体详情检视抽屉」(Entity Inspector Drawer) */}
          {selectedDetails && (
            <div className="absolute top-3 right-3 bottom-3 z-20 flex w-80 flex-col overflow-hidden rounded-xl border border-border/80 bg-background/95 shadow-xl backdrop-blur-md transition-all">
              {/* 抽屉头部 */}
              <div className="flex items-start justify-between border-b border-border/60 bg-muted/30 p-3.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 flex-none rounded-full ring-2 ring-black/10"
                      style={{ backgroundColor: selectedDetails.node.color }}
                    />
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                      {kgEntityTypeText[selectedDetails.node.entityType] || selectedDetails.node.entityType}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">
                      {ENTITY_SHAPES[selectedDetails.node.entityType]
                        ? SHAPE_LABELS.find((s) => s.shape === ENTITY_SHAPES[selectedDetails.node.entityType])
                            ?.label
                        : "实体"}
                    </span>
                  </div>
                  <h3 className="mt-1.5 truncate text-sm font-semibold text-foreground" title={selectedDetails.node.name}>
                    {selectedDetails.node.name}
                  </h3>
                </div>
                <button
                  type="button"
                  aria-label="关闭详情抽屉"
                  onClick={() => onEntitySelect(null)}
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* 抽屉主体属性与证据 */}
              <div className="flex-1 space-y-3 overflow-y-auto p-3.5 text-xs">
                {/* 证据时效度量 */}
                <div className="rounded-lg border border-border/70 bg-muted/20 p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1 text-[11px] font-medium text-foreground">
                      <Clock className="h-3.5 w-3.5 text-primary" />
                      证据新鲜度
                    </span>
                    <Badge
                      variant={
                        selectedDetails.node.freshness > 0.7
                          ? "default"
                          : selectedDetails.node.freshness > 0.3
                          ? "secondary"
                          : "outline"
                      }
                      className="text-[10px] py-0"
                    >
                      {(selectedDetails.node.freshness * 100).toFixed(0)}%
                      {selectedDetails.node.freshness > 0.7
                        ? " · 活跃"
                        : selectedDetails.node.freshness > 0.3
                        ? " · 稳定"
                        : " · 久未佐证"}
                    </Badge>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.round(selectedDetails.node.freshness * 100)}%`,
                        backgroundColor: selectedDetails.node.color,
                      }}
                    />
                  </div>
                  {selectedDetails.node.updatedAt && (
                    <p className="mt-1.5 text-[10px] text-muted-foreground">
                      最近实证时间：{new Date(selectedDetails.node.updatedAt).toLocaleString()}
                    </p>
                  )}
                </div>

                {/* 拓扑关联度统计 */}
                <div className="flex items-center justify-between rounded-lg border border-border/70 bg-muted/20 p-2.5">
                  <div className="flex items-center gap-1.5">
                    <Network className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium text-foreground">关联度</span>
                  </div>
                  <span className="font-semibold tabular-nums text-foreground">
                    {selectedDetails.node.degree} 处关联
                  </span>
                </div>

                {/* 关联网络明细（可点击跳转） */}
                <div className="space-y-1.5">
                  <p className="font-medium text-foreground">关联实体清单 ({selectedDetails.connected.length})</p>
                  {selectedDetails.connected.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">暂无一跳关联节点</p>
                  ) : (
                    <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
                      {selectedDetails.connected.map((item) => (
                        <div
                          key={item.id}
                          onClick={() => {
                            onEntitySelect(item.neighborId);
                            focusOnNode(item.neighborId);
                          }}
                          className="group flex cursor-pointer items-center justify-between rounded-md border border-border/60 bg-background/80 p-2 text-[11px] transition-colors hover:border-primary/50 hover:bg-primary/5"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1">
                              <span
                                className="inline-block h-1.5 w-1.5 rounded-full"
                                style={{ backgroundColor: item.groupColor }}
                              />
                              <span className="text-[10px] text-muted-foreground">
                                {item.relationLabel}
                              </span>
                            </div>
                            <p className="truncate font-medium text-foreground group-hover:text-primary">
                              {item.neighborLabel}
                            </p>
                          </div>
                          <Badge variant="outline" className="text-[9px] py-0 px-1 ml-1 flex-none">
                            {kgEntityTypeText[item.neighborType] || item.neighborType}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 抽屉底部快捷操作 */}
              <div className="flex items-center gap-2 border-t border-border/60 bg-muted/30 p-2.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 flex-1 text-xs"
                  onClick={() => focusOnNode(selectedDetails.node.id)}
                >
                  <Focus className="mr-1.5 h-3 w-3" />
                  定位中心
                </Button>
                <Button
                  size="sm"
                  variant={subgraphOnly ? "default" : "outline"}
                  className="h-7 flex-1 text-xs"
                  onClick={() => setSubgraphOnly((v) => !v)}
                >
                  <Network className="mr-1.5 h-3 w-3" />
                  {subgraphOnly ? "显示全图" : "隔离子图"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
