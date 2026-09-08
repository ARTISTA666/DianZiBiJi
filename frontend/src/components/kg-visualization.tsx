/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Focus,
  Layers,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  RotateCcw,
  X,
  ZoomIn,
  ZoomOut,
  ChevronDown,
  Eye,
  Pin,
  PinOff,
  Search,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { kgEntityTypeText, kgRelationTypeText } from "@/components/constants";
// @ts-expect-error d3 is untyped
import { forceCollide, forceX, forceY } from "d3";

// react-force-graph-2d 不支持 SSR，需动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((mod) => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex h-[34rem] items-center justify-center text-sm text-muted-foreground">
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
  relation_label?: string;
  confidence?: number;
}

interface GraphNode {
  id: number;
  name: string;
  displayName: string;
  labelWithSummary: string;
  entityType: string;
  val: number;
  degree: number;
  color: string;
  shape: NodeShape;
  freshness: number;
  updatedAt?: string;
  radius: number;
  isNote: boolean;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
  pinned?: boolean;
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

// 实体类型 → 极简现代科研语义色板
const ENTITY_COLORS: Record<string, string> = {
  note: "#6366f1",         // 实验笔记：靛蓝（核心枢纽）
  project: "#3b82f6",      // 课题：蓝色
  reagent: "#f97316",      // 试剂：橙色
  chemical: "#f59e0b",     // 化学品：琥珀橙
  instrument: "#64748b",   // 仪器：板岩灰
  software: "#475569",     // 软件：深灰
  result: "#0ea5e9",       // 产物/结果：天蓝
  biosample: "#14b8a6",    // 生物样本：蓝绿
  gene: "#10b981",         // 基因/靶标：翡翠绿
  protein: "#059669",      // 蛋白：深绿
  disease: "#ef4444",      // 疾病：红色
  cell_line: "#ec4899",    // 细胞系：粉红
  treatment: "#eab308",    // 处理条件：黄色
  culture: "#84cc16",      // 培养条件：嫩绿
  perturbation: "#f43f5e", // 扰动：玫红
  user: "#8b5cf6",         // 人员：紫色
  file: "#06b6d4",         // 文件：青色
};

// 关系类型 → 边颜色映射
const RELATION_COLORS: Record<string, string> = {
  uses_reagent: "#f97316",
  uses_instrument: "#64748b",
  targets_gene: "#10b981",
  operates_on: "#84cc16",
  produces_result: "#0ea5e9",
  created_by: "#8b5cf6",
  associated_with: "#94a3b8",
  part_of: "#3b82f6",
  observed_in: "#a855f7",
  regulates: "#ef4444",
  interacts_with: "#ec4899",
  treats: "#eab308",
  has_sample: "#14b8a6",
  has_perturbation: "#f43f5e",
  derived_from: "#14b8a6",
  measured_by: "#64748b",
  controls: "#0ea5e9",
  expressed_in: "#a855f7",
  analyzed_by: "#475569",
  references: "#6366f1",
  has_note: "#6366f1",
  has_experiment_type: "#6366f1",
  uses_sample: "#14b8a6",
};

export const ENTITY_SHAPES: Record<string, NodeShape> = {
  note: "circle",
  project: "circle",
  user: "circle",
  file: "circle",
  cell_line: "circle",
  gene: "circle",
  protein: "circle",
  chemical: "circle",
  reagent: "circle",
  disease: "circle",
  method: "circle",
  instrument: "circle",
  result: "circle",
  tissue: "circle",
  species: "circle",
  biosample: "circle",
  perturbation: "circle",
  treatment: "circle",
  culture: "circle",
  group: "circle",
  geo_accession: "circle",
  software: "circle",
};

export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  if (clean.length === 3) {
    const r = parseInt(clean[0] + clean[0], 16);
    const g = parseInt(clean[1] + clean[1], 16);
    const b = parseInt(clean[2] + clean[2], 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  if (clean.length === 6) {
    const r = parseInt(clean.substring(0, 2), 16);
    const g = parseInt(clean.substring(2, 4), 16);
    const b = parseInt(clean.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return hex;
}

export function getEntityColor(type: string): string {
  return ENTITY_COLORS[type] || "#64748b";
}

export function getRelationColor(type: string): string {
  return RELATION_COLORS[type] || "#94a3b8";
}

export function traceShapePath(ctx: CanvasRenderingContext2D, _shape: NodeShape, x: number, y: number, r: number) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
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
  const lastClickRef = useRef<{ id: number | string; time: number } | null>(null);

  const [graphSize, setGraphSize] = useState({ width: 0, height: 620 });
  const [legendOpen, setLegendOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const hoverTimerRef = useRef<number | null>(null);

  // 图内即时搜索
  const [inGraphSearch, setInGraphSearch] = useState("");

  // 显示控制选项
  const [labelMode, setLabelMode] = useState<"smart" | "all" | "none">("smart");
  const [showLinkLabels, setShowLinkLabels] = useState(false);

  // 构建图拓扑基础数据
  const { nodes, links, entityMap, noteEntities, entityToNoteMap } = useMemo(() => {
    const map = new Map<number, KgEntity>();
    entities.forEach((e) => map.set(e.id, e));

    // 所有外部传入的有效实体均予以渲染，杜绝因关系过滤产生孤立实体导致整图被吞白屏
    const visibleEntities = entities;

    const times = visibleEntities
      .map((e) => (e.updated_at ? new Date(e.updated_at).getTime() : Number.NaN))
      .filter((t) => Number.isFinite(t));
    const minT = times.length ? Math.min(...times) : 0;
    const maxT = times.length ? Math.max(...times) : 0;
    const span = maxT - minT || 1;

    const entToNotes = new Map<number, number[]>();
    relations.forEach((r) => {
      const src = map.get(r.source_entity_id);
      const tgt = map.get(r.target_entity_id);
      if (src?.entity_type === "note") {
        const list = entToNotes.get(r.target_entity_id) || [];
        list.push(r.source_entity_id);
        entToNotes.set(r.target_entity_id, list);
      }
      if (tgt?.entity_type === "note") {
        const list = entToNotes.get(r.source_entity_id) || [];
        list.push(r.target_entity_id);
        entToNotes.set(r.source_entity_id, list);
      }
    });

    const graphNodes: GraphNode[] = visibleEntities.map((e) => {
      const degree = relations.filter(
        (r) => r.source_entity_id === e.id || r.target_entity_id === e.id
      ).length;
      const t = e.updated_at ? new Date(e.updated_at).getTime() : Number.NaN;
      const freshness = Number.isFinite(t) ? 0.15 + 0.85 * ((t - minT) / span) : 0.5;

      const isNote = e.entity_type === "note" || e.entity_type === "project";
      // 节点尺寸平滑映射：实验笔记枢纽 18px，普通实体依据关联度 10~13px
      const radius = isNote
        ? 18
        : Math.max(9.5, Math.min(13.5, 9 + Math.sqrt(degree) * 0.9));

      const typeText = kgEntityTypeText[e.entity_type] || e.entity_type;
      const displayName = e.label.length > 14 ? `${e.label.slice(0, 14)}…` : e.label;
      const longName = e.label.length > 26 ? `${e.label.slice(0, 26)}…` : e.label;
      const labelWithSummary = `${longName} · ${typeText}`;

      return {
        id: e.id,
        name: e.label,
        displayName,
        labelWithSummary,
        entityType: e.entity_type,
        val: radius,
        degree,
        color: isNote ? "#6366f1" : getEntityColor(e.entity_type),
        shape: "circle",
        freshness,
        updatedAt: e.updated_at,
        radius,
        isNote,
      };
    });

    const graphLinks: GraphLink[] = relations
      .filter((r) => map.has(r.source_entity_id) && map.has(r.target_entity_id))
      .map((r) => ({
        source: r.source_entity_id,
        target: r.target_entity_id,
        label: kgRelationTypeText[r.relation_type] || r.relation_type,
        relationType: r.relation_type,
        confidence: r.confidence ?? 0.85,
        color: getRelationColor(r.relation_type),
      }));

    const notes = graphNodes.filter((n) => n.isNote);

    return {
      nodes: graphNodes,
      links: graphLinks,
      entityMap: map,
      noteEntities: notes,
      entityToNoteMap: entToNotes,
    };
  }, [entities, relations]);

  // 关键稳定性保障：严格单向引用图数据，避免 Hover 触发父组件重绘时因传参新对象导致 D3 物理力场频繁重热（Reheat）剧烈乱动
  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  // 组件卸载时销毁未决的 hover 防抖定时器
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) {
        window.clearTimeout(hoverTimerRef.current);
      }
    };
  }, []);

  // 计算当前聚焦的核心实体（优先级：鼠标悬停 > 选中锁定的实体）
  const primaryFocusId = hoveredNodeId ?? selectedEntityId;

  // 计算一跳关联的高亮网络
  const highlightedIds = useMemo(() => {
    if (primaryFocusId === null) return new Set<number>();
    const ids = new Set<number>([primaryFocusId]);
    relations.forEach((r) => {
      if (r.source_entity_id === primaryFocusId) ids.add(r.target_entity_id);
      if (r.target_entity_id === primaryFocusId) ids.add(r.source_entity_id);
    });
    return ids;
  }, [primaryFocusId, relations]);

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
        return {
          id: r.id,
          relationType: r.relation_type,
          relationLabel: kgRelationTypeText[r.relation_type] || r.relation_type,
          confidence: r.confidence ?? 0.85,
          isOutgoing,
          neighborId,
          neighborLabel: neighbor?.label || `实体 #${neighborId}`,
          neighborType: neighbor?.entity_type || "unknown",
          neighborColor: getEntityColor(neighbor?.entity_type || ""),
        };
      });

    return {
      node,
      connected,
    };
  }, [selectedEntityId, nodes, relations, entityMap]);

  // 科学实验星系聚类力场
  const configureGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;

    const notes = noteEntities;
    const count = notes.length || 1;
    const w = graphSize.width || 900;
    const h = graphSize.height || 600;

    const rx = Math.max(220, Math.min(360, w * 0.35));
    const ry = Math.max(160, Math.min(260, h * 0.32));
    const noteAnchorMap = new Map<number, { x: number; y: number }>();

    notes.forEach((n, idx) => {
      const angle = (idx * 2 * Math.PI) / count - Math.PI / 2;
      noteAnchorMap.set(n.id, {
        x: Math.cos(angle) * rx,
        y: Math.sin(angle) * ry,
      });
    });

    if (forceX) {
      graph.d3Force(
        "galaxyX",
        forceX((node: any) => {
          if (node.isNote) return noteAnchorMap.get(node.id)?.x ?? 0;
          const parentNotes = entityToNoteMap.get(node.id);
          if (parentNotes && parentNotes.length > 0) {
            const sumX = parentNotes.reduce((acc, id) => acc + (noteAnchorMap.get(id)?.x ?? 0), 0);
            return sumX / parentNotes.length;
          }
          return 0;
        }).strength(0.24)
      );
    }

    if (forceY) {
      graph.d3Force(
        "galaxyY",
        forceY((node: any) => {
          if (node.isNote) return noteAnchorMap.get(node.id)?.y ?? 0;
          const parentNotes = entityToNoteMap.get(node.id);
          if (parentNotes && parentNotes.length > 0) {
            const sumY = parentNotes.reduce((acc, id) => acc + (noteAnchorMap.get(id)?.y ?? 0), 0);
            return sumY / parentNotes.length;
          }
          return 0;
        }).strength(0.24)
      );
    }

    graph.d3Force("charge")?.strength(-300).distanceMax(480);
    graph.d3Force("link")?.distance(72);
    graph.d3Force("center")?.strength(0.04);

    if (forceCollide) {
      graph.d3Force("collide", forceCollide((n: any) => (n.radius || 11) + 14).iterations(2));
    }
  }, [noteEntities, entityToNoteMap, graphSize.width, graphSize.height]);

  const fitGraph = useCallback((duration = 400) => {
    graphRef.current?.zoomToFit?.(duration, 56);
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
    graph.zoom?.(Math.max(0.15, Math.min(3.5, current * factor)), 200);
  }, []);

  const focusOnNode = useCallback((nodeId: number) => {
    const targetNode = nodes.find((n) => n.id === nodeId);
    if (!targetNode || !graphRef.current) return;
    const x = targetNode.x;
    const y = targetNode.y;
    if (Number.isFinite(x) && Number.isFinite(y)) {
      graphRef.current.centerAt(x, y, 600);
      graphRef.current.zoom(1.6, 600);
    }
  }, [nodes]);

  const toggleNodePin = useCallback((nodeId: number, pin: boolean) => {
    const graphData = graphRef.current?.graphData?.();
    const target = graphData?.nodes?.find((n: any) => n.id === nodeId);
    if (target) {
      if (pin) {
        target.fx = target.x;
        target.fy = target.y;
        target.pinned = true;
      } else {
        delete target.fx;
        delete target.fy;
        target.pinned = false;
        graphRef.current?.d3ReheatSimulation?.();
      }
    }
  }, []);

  const handleUnpinAll = useCallback(() => {
    const graphData = graphRef.current?.graphData?.();
    (graphData?.nodes || []).forEach((n: any) => {
      delete n.fx;
      delete n.fy;
      n.pinned = false;
    });
    graphRef.current?.d3ReheatSimulation?.();
  }, []);

  const handleInGraphSearch = useCallback(() => {
    const q = inGraphSearch.trim().toLowerCase();
    if (!q) return;
    const matched = nodes.find((n) => n.name.toLowerCase().includes(q));
    if (matched) {
      onEntitySelect(matched.id);
      focusOnNode(matched.id);
    }
  }, [inGraphSearch, nodes, onEntitySelect, focusOnNode]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((v) => !v);
    setTimeout(() => fitGraph(200), 150);
  }, [fitGraph]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const updateSize = () => {
      setGraphSize({
        width: container.clientWidth,
        height: container.clientHeight || 620,
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
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (isFullscreen) setIsFullscreen(false);
        else if (selectedEntityId !== null) onEntitySelect(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen, selectedEntityId, onEntitySelect]);

  // 🌟 极简高雅 Canvas 节点绘制（借鉴 Obsidian / Neo4j 工业级设计）
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x;
      const y = node.y;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const hasActiveFocus = primaryFocusId !== null;
      const isInFocusNetwork = highlightedIds.has(node.id);

      // 🌟 用户核心优化需求 1：hover 聚焦时，只显示相关的，其他都不显示！
      if (hasActiveFocus && !isInFocusNetwork) {
        return;
      }

      const r = node.radius || 11;
      const isFocusCenter = node.id === primaryFocusId;

      ctx.save();

      // 1. 焦点光晕环
      if (isFocusCenter) {
        ctx.beginPath();
        ctx.arc(x, y, r + 5.5 / globalScale, 0, Math.PI * 2);
        ctx.fillStyle = hexToRgba("#6366f1", 0.3);
        ctx.fill();

        ctx.beginPath();
        ctx.arc(x, y, r + 2.5 / globalScale, 0, Math.PI * 2);
        ctx.strokeStyle = "#818cf8";
        ctx.lineWidth = 2.2 / globalScale;
        ctx.stroke();
      } else if (hasActiveFocus && isInFocusNetwork) {
        ctx.beginPath();
        ctx.arc(x, y, r + 2 / globalScale, 0, Math.PI * 2);
        ctx.strokeStyle = hexToRgba(node.color, 0.75);
        ctx.lineWidth = 1.6 / globalScale;
        ctx.stroke();
      }

      // 2. 🌟 用户核心优化需求 2：图标精简，纯粹干净的圆形几何节点，不塞杂乱文字/emoji
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = node.color;
      ctx.fill();

      // 节点边框
      ctx.strokeStyle = node.pinned
        ? "#f59e0b"
        : node.isNote
        ? "#c7d2fe"
        : "rgba(255, 255, 255, 0.55)";
      ctx.lineWidth = (node.pinned ? 2 : node.isNote ? 1.5 : 1) / globalScale;
      ctx.stroke();

      // 3. 语义标签展示：
      // - 聚焦时：焦点节点与其相邻邻居均展示清晰标签
      // - 全景态时：仅实验笔记展示标签，保持极简呼吸感
      const shouldDrawLabel =
        hasActiveFocus
          ? isInFocusNetwork
          : (labelMode === "all" || (labelMode === "smart" && (node.isNote || globalScale >= 1.7)));

      if (shouldDrawLabel) {
        const displayName = node.displayName || node.name || "";
        const labelText = isFocusCenter || node.isNote ? node.labelWithSummary || displayName : displayName;

        const fontSize = Math.max(
          8.5,
          Math.min(11, (node.isNote ? 11 : 9.5) / Math.sqrt(Math.max(globalScale, 0.65)))
        );
        ctx.font = `${node.isNote || isFocusCenter ? "600" : "500"} ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
        const textMetrics = ctx.measureText(labelText);
        const textWidth = textMetrics.width;

        const pillHeight = fontSize + 4;
        const pillWidth = textWidth + 8;
        const pillY = y + r + 3 / globalScale;

        // 半透明深色磨砂药丸
        ctx.fillStyle = isFocusCenter
          ? "rgba(15, 23, 42, 0.95)"
          : node.isNote
          ? "rgba(30, 27, 75, 0.92)"
          : "rgba(15, 23, 42, 0.82)";
        ctx.beginPath();
        if (typeof (ctx as any).roundRect === "function") {
          (ctx as any).roundRect(x - pillWidth / 2, pillY, pillWidth, pillHeight, 3);
        } else {
          ctx.rect(x - pillWidth / 2, pillY, pillWidth, pillHeight);
        }
        ctx.fill();

        ctx.fillStyle = isFocusCenter ? "#ffffff" : node.isNote ? "#e0e7ff" : "#f1f5f9";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(labelText, x, pillY + pillHeight / 2);
      }

      ctx.restore();
    },
    [primaryFocusId, highlightedIds, labelMode]
  );

  // 关键稳定性保障：专用于射线拾取判定（Shadow Canvas），稳定提供拾取色块，杜绝 Hover 碰撞震颤循环
  // P1-2 优化：将拾取半径扩大至 ≥24px，并将处于可见态的标签药丸一并纳入拾取层，大幅提高悬停聚焦与点击锁定的命中率
  const paintNodePointerArea = useCallback(
    (node: any, color: string, ctx: CanvasRenderingContext2D) => {
      const x = node.x;
      const y = node.y;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      const baseR = node.radius || 11;
      const pickR = Math.max(24, baseR + 12);
      ctx.beginPath();
      ctx.arc(x, y, pickR, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // 当节点附带文本标签时，将标签药丸区域也绘制到 Shadow Canvas，使得文字区域同样可响应 Hover 聚焦与点击
      const hasActiveFocus = primaryFocusId !== null;
      const isInFocusNetwork = highlightedIds.has(node.id);
      const isFocusCenter = node.id === primaryFocusId;
      const shouldDrawLabel =
        hasActiveFocus
          ? isInFocusNetwork
          : (labelMode === "all" || (labelMode === "smart" && node.isNote));

      if (shouldDrawLabel) {
        const displayName = node.displayName || node.name || "";
        const labelText = isFocusCenter || node.isNote ? (node.labelWithSummary || displayName) : displayName;
        if (labelText) {
          const approxWidth = Math.max(32, labelText.length * 9 + 12);
          const pillHeight = 18;
          const pillY = y + baseR + 2;
          ctx.beginPath();
          ctx.rect(x - approxWidth / 2, pillY, approxWidth, pillHeight);
          ctx.fillStyle = color;
          ctx.fill();
        }
      }
    },
    [primaryFocusId, highlightedIds, labelMode]
  );

  // 连线中点语义药丸标签
  const paintLinkCanvas = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source;
      const target = link.target;
      if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(target.x)) return;

      const sId = typeof source === "object" ? source.id : source;
      const tId = typeof target === "object" ? target.id : target;
      const isFocused = primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);

      // hover 聚焦时，仅在相连边上显示标签
      if (primaryFocusId !== null && !isFocused) return;
      if (!showLinkLabels && !isFocused) return;

      const mx = (source.x + target.x) / 2;
      const my = (source.y + target.y) / 2;

      const label = link.label;
      const fontSize = Math.max(7.5, Math.min(10, 9 / Math.sqrt(Math.max(globalScale, 0.65))));
      ctx.font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
      const tw = ctx.measureText(label).width;
      const pw = tw + 8;
      const ph = fontSize + 4;

      ctx.save();
      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      ctx.beginPath();
      if (typeof (ctx as any).roundRect === "function") {
        (ctx as any).roundRect(mx - pw / 2, my - ph / 2, pw, ph, 3);
      } else {
        ctx.rect(mx - pw / 2, my - ph / 2, pw, ph);
      }
      ctx.fill();

      ctx.strokeStyle = hexToRgba(link.color, 0.85);
      ctx.lineWidth = 0.9 / globalScale;
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, mx, my);
      ctx.restore();
    },
    [primaryFocusId, showLinkLabels]
  );

  // 防抖的悬停处理器：离开节点时给予 70ms 缓冲，防止跨节点或经过节点缝隙时界面剧烈闪烁抖动
  const handleNodeHover = useCallback((node: any) => {
    if (hoverTimerRef.current) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }

    if (node) {
      setHoveredNodeId(node.id);
    } else {
      hoverTimerRef.current = window.setTimeout(() => {
        setHoveredNodeId(null);
        hoverTimerRef.current = null;
      }, 70);
    }
  }, []);

  const isNodeVisible = useCallback(
    (node: any) => {
      if (primaryFocusId === null) return true;
      return highlightedIds.has(node.id);
    },
    [primaryFocusId, highlightedIds]
  );

  const isLinkVisible = useCallback(
    (link: any) => {
      if (primaryFocusId === null) return true;
      const sId = typeof link.source === "object" ? link.source.id : link.source;
      const tId = typeof link.target === "object" ? link.target.id : link.target;
      return sId === primaryFocusId || tId === primaryFocusId;
    },
    [primaryFocusId]
  );

  const nodeLabelAccessor = useCallback(
    (node: any) =>
      `${kgEntityTypeText[node.entityType] || node.entityType}: ${node.name} · 关联度 ${node.degree}`,
    []
  );

  const nodeValAccessor = useCallback((node: any) => node.val, []);

  const linkCanvasObjectModeAccessor = useCallback(() => "after", []);

  const linkLabelAccessor = useCallback(
    (link: any) => `${link.label}（置信度 ${(link.confidence || 0).toFixed(2)}）`,
    []
  );

  const linkColorAccessor = useCallback(
    (link: any) => {
      const sId = typeof link.source === "object" ? link.source.id : link.source;
      const tId = typeof link.target === "object" ? link.target.id : link.target;
      const isLinkedToFocus =
        primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);

      if (primaryFocusId !== null) {
        return isLinkedToFocus ? link.color : "transparent";
      }
      return hexToRgba(link.color, 0.28);
    },
    [primaryFocusId]
  );

  const linkWidthAccessor = useCallback(
    (link: any) => {
      const sId = typeof link.source === "object" ? link.source.id : link.source;
      const tId = typeof link.target === "object" ? link.target.id : link.target;
      const isLinkedToFocus =
        primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);

      if (primaryFocusId !== null) {
        return isLinkedToFocus ? 2.2 : 0;
      }
      return 0.75;
    },
    [primaryFocusId]
  );

  const linkArrowLengthAccessor = useCallback(
    (link: any) => {
      const sId = typeof link.source === "object" ? link.source.id : link.source;
      const tId = typeof link.target === "object" ? link.target.id : link.target;
      const isLinkedToFocus =
        primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);

      if (primaryFocusId !== null) {
        return isLinkedToFocus ? 6.5 : 0;
      }
      return 3.5;
    },
    [primaryFocusId]
  );

  const linkArrowColorAccessor = useCallback((link: any) => link.color, []);

  const handleNodeClick = useCallback(
    (node: any) => {
      const now = Date.now();
      if (
        lastClickRef.current &&
        lastClickRef.current.id === node.id &&
        now - lastClickRef.current.time < 350
      ) {
        delete node.fx;
        delete node.fy;
        node.pinned = false;
        graphRef.current?.d3ReheatSimulation?.();
        lastClickRef.current = null;
        return;
      }
      lastClickRef.current = { id: node.id, time: now };
      onEntitySelect(node.id === selectedEntityId ? null : node.id);
    },
    [selectedEntityId, onEntitySelect]
  );

  const handleNodeRightClick = useCallback((node: any) => {
    delete node.fx;
    delete node.fy;
    node.pinned = false;
    graphRef.current?.d3ReheatSimulation?.();
  }, []);

  const handleNodeDragEnd = useCallback((node: any) => {
    node.fx = node.x;
    node.fy = node.y;
    node.pinned = true;
  }, []);

  const handleBackgroundClick = useCallback(() => {
    onEntitySelect(null);
  }, [onEntitySelect]);

  const focusedNode = useMemo(() => {
    if (primaryFocusId === null) return null;
    return nodes.find((n) => n.id === primaryFocusId);
  }, [primaryFocusId, nodes]);

  return (
    <div
      className={`relative flex flex-col transition-all duration-300 ${
        isFullscreen
          ? "fixed inset-0 z-50 bg-background/95 backdrop-blur-md p-4"
          : "w-full"
      }`}
    >
      <Card className="flex flex-1 flex-col overflow-hidden border-border/75 shadow-card bg-card">
        {/* 顶栏控制台 */}
        <CardHeader className="flex-none border-b border-border/60 bg-muted/20 py-2 px-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {/* 左侧：状态指示 */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs">
                {focusedNode ? (
                  <>
                    <Sparkles className="h-3.5 w-3.5 text-indigo-500 animate-pulse" />
                    <span className="font-medium text-foreground truncate max-w-48">
                      已聚焦: {focusedNode.name}
                    </span>
                    <Badge variant="secondary" className="text-[10px] py-0 px-1 font-normal">
                      {highlightedIds.size - 1} 个关联实体
                    </Badge>
                  </>
                ) : (
                  <>
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    <span className="text-muted-foreground">全景图谱 ({nodes.length} 实体)</span>
                    <span className="text-[11px] text-muted-foreground/80">· 悬停聚焦一跳 · 单击锁定 · 拖拽固定</span>
                  </>
                )}
              </div>

              {selectedEntityId !== null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onEntitySelect(null)}
                  className="h-7 px-2 text-xs text-primary font-medium hover:text-primary/80"
                  title="释放当前实体的锁定聚焦，恢复全景图谱浏览"
                >
                  <X className="mr-1 h-3 w-3" />
                  释放锁定
                </Button>
              )}
            </div>

            {/* 中间：图内即时搜索 */}
            <div className="flex items-center gap-1.5 max-w-xs flex-1">
              <div className="relative w-full">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={inGraphSearch}
                  onChange={(e) => setInGraphSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleInGraphSearch();
                  }}
                  placeholder="搜索实体快速定位..."
                  className="h-7 pl-8 pr-7 text-xs bg-background/90"
                />
                {inGraphSearch && (
                  <button
                    type="button"
                    onClick={() => setInGraphSearch("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* 右侧：工具按钮 */}
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleUnpinAll}
                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                title="释放所有手动拖拽固定的节点位置，恢复力导向自动布局"
              >
                <PinOff className="mr-1 h-3.5 w-3.5" />
                释放固定
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-7 px-2 text-xs gap-1">
                    <Eye className="h-3.5 w-3.5" />
                    <span>标签</span>
                    <ChevronDown className="h-3 w-3 opacity-60" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="text-xs">
                  <DropdownMenuLabel>实体标签策略</DropdownMenuLabel>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "smart"}
                    onCheckedChange={() => setLabelMode("smart")}
                  >
                    智能聚焦（推荐）
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "all"}
                    onCheckedChange={() => setLabelMode("all")}
                  >
                    全景常显全部
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "none"}
                    onCheckedChange={() => setLabelMode("none")}
                  >
                    极简仅悬停显
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuCheckboxItem
                    checked={showLinkLabels}
                    onCheckedChange={(c) => setShowLinkLabels(c)}
                  >
                    连线关系标签
                  </DropdownMenuCheckboxItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onEntitySelect(null);
                  fitGraph(400);
                }}
                className="h-7 px-2 text-xs"
                title="重置全景视角"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                onClick={toggleFullscreen}
                className="h-7 px-2 text-xs"
                title="全屏切换"
              >
                {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </CardHeader>

        {/* 顶部实验快捷穿梭胶囊 */}
        {noteEntities.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/50 bg-muted/10 px-4 py-1.5 text-xs no-scrollbar">
            <span className="flex-none text-[11px] font-medium text-muted-foreground mr-1">实验直达:</span>
            <button
              type="button"
              onClick={() => {
                onEntitySelect(null);
                fitGraph(350);
              }}
              className={`flex-none rounded-md px-2.5 py-0.5 text-xs transition-colors ${
                selectedEntityId === null
                  ? "bg-primary text-primary-foreground font-medium shadow-xs"
                  : "bg-background/80 text-muted-foreground hover:text-foreground border border-border/70"
              }`}
            >
              全部总览 ({nodes.length})
            </button>
            {noteEntities.map((note, idx) => {
              const isSelected = selectedEntityId === note.id;
              return (
                <button
                  key={note.id}
                  type="button"
                  onClick={() => {
                    onEntitySelect(note.id);
                    focusOnNode(note.id);
                  }}
                  title={note.name}
                  className={`flex-none truncate max-w-56 rounded-md px-2.5 py-0.5 text-xs transition-colors ${
                    isSelected
                      ? "bg-indigo-600 text-white font-medium shadow-xs"
                      : "bg-background/80 text-foreground/80 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 border border-border/70"
                  }`}
                >
                  实验 #{idx + 1}: {note.name.split("：")[0] || note.name}
                </button>
              );
            })}
          </div>
        )}

        {/* 画布核心区域 */}
        <CardContent
          ref={containerRef}
          className={`relative overflow-hidden p-0 bg-dot-grid bg-muted/10 ${
            isFullscreen ? "flex-1 h-full" : "h-[min(76vh,50rem)] min-h-[36rem]"
          }`}
        >
          {graphSize.width > 0 && (
            <ForceGraph2D
              ref={graphRef as any}
              graphData={graphData}
              width={graphSize.width}
              height={graphSize.height}
              nodeVisibility={isNodeVisible}
              linkVisibility={isLinkVisible}
              nodeLabel={nodeLabelAccessor}
              nodeVal={nodeValAccessor}
              nodeCanvasObject={paintNode}
              nodePointerAreaPaint={paintNodePointerArea}
              linkCanvasObjectMode={linkCanvasObjectModeAccessor}
              linkCanvasObject={paintLinkCanvas}
              linkLabel={linkLabelAccessor}
              linkColor={linkColorAccessor}
              linkWidth={linkWidthAccessor}
              linkDirectionalArrowLength={linkArrowLengthAccessor}
              linkDirectionalArrowRelPos={0.88}
              linkDirectionalArrowColor={linkArrowColorAccessor}
              linkCurvature={0.06}
              onNodeHover={handleNodeHover}
              onNodeClick={handleNodeClick}
              onNodeRightClick={handleNodeRightClick}
              onNodeDragEnd={handleNodeDragEnd}
              onBackgroundClick={handleBackgroundClick}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              enablePointerInteraction={true}
              onEngineStop={handleEngineStop}
              minZoom={0.15}
              maxZoom={3.5}
              cooldownTicks={120}
              cooldownTime={1800}
              d3AlphaDecay={0.05}
              d3VelocityDecay={0.45}
              warmupTicks={80}
              autoPauseRedraw={false}
            />
          )}

          {/* 右侧毛玻璃全息实体检视抽屉 */}
          {selectedDetails && (
            <div className="absolute top-3 right-3 bottom-3 w-80 z-20 flex flex-col rounded-xl border border-border/80 bg-card/95 p-4 shadow-2xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-right-4 duration-200">
              <div className="flex items-start justify-between gap-2 border-b border-border/60 pb-3">
                <div className="min-w-0">
                  <Badge
                    className="mb-1 text-[10px] px-1.5 py-0"
                    style={{
                      backgroundColor: hexToRgba(selectedDetails.node.color, 0.15),
                      color: selectedDetails.node.color,
                      borderColor: hexToRgba(selectedDetails.node.color, 0.4),
                    }}
                    variant="outline"
                  >
                    {kgEntityTypeText[selectedDetails.node.entityType] || selectedDetails.node.entityType}
                  </Badge>
                  <h4 className="text-sm font-semibold text-foreground truncate" title={selectedDetails.node.name}>
                    {selectedDetails.node.name}
                  </h4>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground shrink-0"
                  onClick={() => onEntitySelect(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-2 py-3 border-b border-border/50 text-xs">
                <div className="rounded-md bg-muted/40 p-2">
                  <p className="text-[10px] text-muted-foreground">拓扑关联度</p>
                  <p className="text-base font-bold text-foreground">
                    {selectedDetails.node.degree} <span className="text-[10px] font-normal text-muted-foreground">条关联</span>
                  </p>
                </div>
                <div className="rounded-md bg-muted/40 p-2">
                  <p className="text-[10px] text-muted-foreground">置信度</p>
                  <p className="text-base font-bold text-foreground">
                    {(selectedDetails.node.freshness * 100).toFixed(0)}%
                  </p>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto py-2 space-y-1.5 min-h-0">
                <p className="text-[11px] font-medium text-muted-foreground">
                  直接关联实体 ({selectedDetails.connected.length})
                </p>
                {selectedDetails.connected.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => {
                      onEntitySelect(c.neighborId);
                      focusOnNode(c.neighborId);
                    }}
                    className="flex items-center justify-between gap-1.5 rounded-lg border border-border/50 bg-background/60 p-2 text-xs hover:border-primary/50 hover:bg-primary/5 cursor-pointer transition-colors"
                  >
                    <div className="min-w-0 flex items-center gap-1.5">
                      <span
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: c.neighborColor }}
                      />
                      <span className="truncate font-medium text-foreground">{c.neighborLabel}</span>
                    </div>
                    <Badge variant="secondary" className="text-[10px] px-1 py-0 shrink-0">
                      {c.relationLabel}
                    </Badge>
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-border/60 flex items-center gap-2">
                <Button
                  size="sm"
                  variant="default"
                  className="flex-1 text-xs h-8"
                  onClick={() => focusOnNode(selectedDetails.node.id)}
                >
                  <Focus className="mr-1.5 h-3.5 w-3.5" />
                  对焦居中
                </Button>
                {selectedDetails.node.pinned ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs h-8 px-2"
                    title="释放该节点固定位置"
                    onClick={() => toggleNodePin(selectedDetails.node.id, false)}
                  >
                    <PinOff className="h-3.5 w-3.5 text-amber-500" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs h-8 px-2"
                    title="钉住该节点位置"
                    onClick={() => toggleNodePin(selectedDetails.node.id, true)}
                  >
                    <Pin className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* 底部折叠式「图例说明」与交互提示 */}
          <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2">
            {!legendOpen ? (
              <>
                <button
                  type="button"
                  onClick={() => setLegendOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background/90 px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-subtle backdrop-blur-md transition-colors hover:bg-background hover:text-foreground"
                >
                  <MapIcon className="h-3.5 w-3.5 text-primary" />
                  <span>实体色板图例</span>
                </button>
                <div className="hidden md:inline-flex items-center rounded-lg border border-border/70 bg-background/85 px-2.5 py-1 text-[11px] text-muted-foreground shadow-xs backdrop-blur-md">
                  💡 悬停节点聚焦一跳 · 点击锁定 · 拖拽可固定位置
                </div>
              </>
            ) : (
              <div className="w-72 rounded-xl border border-border/80 bg-background/95 p-3.5 shadow-card backdrop-blur-md transition-all">
                <div className="mb-2 flex items-center justify-between border-b border-border/50 pb-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <Layers className="h-4 w-4 text-primary" />
                    <span>科研知识图谱图例</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLegendOpen(false)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                  {Object.entries(ENTITY_COLORS).slice(0, 10).map(([type, color]) => (
                    <div key={type} className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                      <span className="text-muted-foreground truncate">{kgEntityTypeText[type] || type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 画布悬浮缩放控制器 */}
          <div className="absolute bottom-3 right-3 z-10 flex items-center gap-1 rounded-lg border border-border/80 bg-background/90 p-1 shadow-subtle backdrop-blur-md">
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
              onClick={() => zoomGraph(0.8)}
              title="缩小"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => {
                onEntitySelect(null);
                fitGraph(400);
              }}
              title="重置全景"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
