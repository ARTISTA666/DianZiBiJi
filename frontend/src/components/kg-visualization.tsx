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
  Compass,
  FlaskConical,
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
import { kgEntityTypeText, kgRelationTypeText, kgEntityShortText } from "@/components/constants";
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

// 实体类型 → 颜色映射
const ENTITY_COLORS: Record<string, string> = {
  note: "#6366f1",
  project: "#3b82f6",
  user: "#8b5cf6",
  file: "#06b6d4",
  cell_line: "#ec4899",
  gene: "#10b981",
  protein: "#14b8a6",
  chemical: "#f59e0b",
  reagent: "#f97316",
  disease: "#ef4444",
  method: "#84cc16",
  instrument: "#64748b",
  result: "#0ea5e9",
  tissue: "#a855f7",
  species: "#10b981",
  biosample: "#06b6d4",
  perturbation: "#f43f5e",
  treatment: "#eab308",
  culture: "#84cc16",
  group: "#6366f1",
  geo_accession: "#0284c7",
  software: "#475569",
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
  has_sample: "#06b6d4",
  has_perturbation: "#f43f5e",
  derived_from: "#14b8a6",
  measured_by: "#64748b",
  controls: "#0ea5e9",
  expressed_in: "#a855f7",
  analyzed_by: "#475569",
  references: "#6366f1",
  has_note: "#6366f1",
  has_experiment_type: "#6366f1",
  uses_sample: "#06b6d4",
};

// 实体类型 → 几何外形映射
export const ENTITY_SHAPES: Record<string, NodeShape> = {
  note: "square",
  project: "square",
  user: "circle",
  file: "circle",
  cell_line: "hexagon",
  gene: "diamond",
  protein: "diamond",
  chemical: "circle",
  reagent: "circle",
  disease: "triangle",
  method: "hexagon",
  instrument: "square",
  result: "triangle",
  tissue: "hexagon",
  species: "circle",
  biosample: "hexagon",
  perturbation: "triangle",
  treatment: "diamond",
  culture: "hexagon",
  group: "square",
  geo_accession: "diamond",
  software: "square",
};

// 关系类型归类
const RELATION_GROUPS: Record<string, { color: string; label: string }> = {
  uses_reagent: { color: "#f97316", label: "试剂物料" },
  uses_instrument: { color: "#64748b", label: "仪器设备" },
  targets_gene: { color: "#10b981", label: "生物靶标" },
  operates_on: { color: "#84cc16", label: "实验操作" },
  produces_result: { color: "#0ea5e9", label: "产物结果" },
  created_by: { color: "#8b5cf6", label: "人员归属" },
  associated_with: { color: "#94a3b8", label: "关联推断" },
  part_of: { color: "#3b82f6", label: "课题架构" },
  observed_in: { color: "#a855f7", label: "组织样本" },
  regulates: { color: "#ef4444", label: "调控网络" },
  interacts_with: { color: "#ec4899", label: "分子互作" },
  treats: { color: "#eab308", label: "处理条件" },
  has_sample: { color: "#06b6d4", label: "生物样品" },
  has_perturbation: { color: "#f43f5e", label: "扰动处理" },
  derived_from: { color: "#14b8a6", label: "样本衍生" },
  measured_by: { color: "#64748b", label: "测定仪器" },
  controls: { color: "#0ea5e9", label: "质控内参" },
  expressed_in: { color: "#a855f7", label: "组织表达" },
  analyzed_by: { color: "#475569", label: "分析软件" },
  references: { color: "#6366f1", label: "引用参考" },
  has_note: { color: "#6366f1", label: "实验笔记" },
  has_experiment_type: { color: "#6366f1", label: "实验类型" },
  uses_sample: { color: "#06b6d4", label: "使用样品" },
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

export function traceShapePath(ctx: CanvasRenderingContext2D, shape: NodeShape, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (shape) {
    case "circle":
      ctx.arc(x, y, r, 0, Math.PI * 2);
      break;
    case "square": {
      const k = r * 0.92;
      const corner = Math.min(5, r * 0.28);
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
  const lastClickRef = useRef<{ id: number | string; time: number } | null>(null);

  const [graphSize, setGraphSize] = useState({ width: 0, height: 620 });
  const [legendOpen, setLegendOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const [spotlightType, setSpotlightType] = useState<string | null>(null);

  // 核心视觉重心模式：单实验聚焦 vs 全课题星系总览
  const [viewMode, setViewMode] = useState<"focus" | "all">("focus");
  const [activeExperimentId, setActiveExperimentId] = useState<number | null>(null);

  // 图内即时搜索
  const [inGraphSearch, setInGraphSearch] = useState("");

  // 显示控制选项
  const [labelMode, setLabelMode] = useState<"smart" | "all" | "none">("smart");
  const [showLinkLabels, setShowLinkLabels] = useState(false);

  // 构建图拓扑基础数据
  const { nodes, links, entityMap, noteEntities, entityToNoteMap } = useMemo(() => {
    const map = new Map<number, KgEntity>();
    entities.forEach((e) => map.set(e.id, e));

    const relatedIds = new Set<number>();
    relations.forEach((r) => {
      relatedIds.add(r.source_entity_id);
      relatedIds.add(r.target_entity_id);
    });

    const visibleEntities = entities.filter((e) => relatedIds.has(e.id));

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
      const radius = isNote
        ? 21
        : Math.max(11, Math.min(14, 10 + Math.sqrt(degree) * 1.0));

      return {
        id: e.id,
        name: e.label,
        entityType: e.entity_type,
        val: radius,
        degree,
        color: isNote ? "#6366f1" : getEntityColor(e.entity_type),
        shape: isNote ? "square" : (ENTITY_SHAPES[e.entity_type] || "circle"),
        freshness,
        updatedAt: e.updated_at,
        radius,
        isNote,
      };
    });

    const graphLinks: GraphLink[] = relations
      .filter((r) => relatedIds.has(r.source_entity_id) && relatedIds.has(r.target_entity_id))
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

  // 默认自动选定第一个实验笔记
  useEffect(() => {
    if (activeExperimentId === null && noteEntities.length > 0) {
      setActiveExperimentId(noteEntities[0].id);
    }
  }, [noteEntities, activeExperimentId]);

  // 处于【单实验精读】模式时，精确计算当前实验及其直接关联实体集合
  const focusEntityIds = useMemo(() => {
    if (viewMode === "all" || activeExperimentId === null) {
      return new Set<number>(nodes.map((n) => n.id));
    }
    const set = new Set<number>([activeExperimentId]);
    relations.forEach((r) => {
      if (r.source_entity_id === activeExperimentId) set.add(r.target_entity_id);
      if (r.target_entity_id === activeExperimentId) set.add(r.source_entity_id);
    });
    return set;
  }, [viewMode, activeExperimentId, nodes, relations]);

  // 计算当前聚焦的核心实体（优先级：鼠标悬停 > 选中实体）
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
        const group = RELATION_GROUPS[r.relation_type] || { color: "#94a3b8", label: "其它" };
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
          groupColor: group.color,
          groupLabel: group.label,
        };
      });

    const parentNoteIds = entityToNoteMap.get(selectedEntityId) || [];
    const parentNotes = parentNoteIds
      .map((id) => entityMap.get(id))
      .filter(Boolean) as KgEntity[];

    return {
      node,
      connected,
      parentNotes,
    };
  }, [selectedEntityId, nodes, relations, entityMap, entityToNoteMap]);

  // 科学实验星系聚类物理引擎：实验围绕各自笔记聚簇，形成清晰引力场
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

    graph.d3Force("charge")?.strength(-320).distanceMax(500);
    graph.d3Force("link")?.distance(75);
    graph.d3Force("center")?.strength(0.04);

    if (forceCollide) {
      graph.d3Force("collide", forceCollide((n: any) => (n.radius || 12) + 16).iterations(2));
    }
  }, [noteEntities, entityToNoteMap, graphSize.width, graphSize.height]);

  const fitGraph = useCallback(
    (duration = 400) => {
      if (viewMode === "focus" && activeExperimentId !== null) {
        graphRef.current?.zoomToFit?.(duration, 70, (node: any) => focusEntityIds.has(node.id));
      } else {
        graphRef.current?.zoomToFit?.(duration, 56);
      }
    },
    [viewMode, activeExperimentId, focusEntityIds]
  );

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
    fitOnEngineStopRef.current = true;
  }, [viewMode, activeExperimentId]);

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

  // 高保真聚光灯 Canvas 节点绘制
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x;
      const y = node.y;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const r = node.radius || 12;
      const isInSpotlight = !spotlightType || node.entityType === spotlightType;

      const hasActiveFocus = primaryFocusId !== null;
      const isInFocusNetwork = highlightedIds.has(node.id);

      // 在聚焦单实验模式下，所有显示的实体均为焦点实体；
      // 在全景星系模式下，悬停或选定时非关联网状实体骤降至 0.08 极低透明度
      const dimmed = viewMode === "all" && ((!isInSpotlight) || (hasActiveFocus && !isInFocusNetwork));
      const baseColor = dimmed ? "#64748b" : node.color;
      const isFocusCenter = node.id === primaryFocusId;

      ctx.save();
      ctx.globalAlpha = dimmed ? 0.08 : 1.0;

      // 1. 重心焦点外环：耀眼发光霓虹环
      if (isFocusCenter) {
        traceShapePath(ctx, node.shape, x, y, r + 7 / globalScale);
        ctx.fillStyle = hexToRgba("#6366f1", 0.35);
        ctx.fill();
        traceShapePath(ctx, node.shape, x, y, r + 3.5 / globalScale);
        ctx.strokeStyle = "#818cf8";
        ctx.lineWidth = 2.4 / globalScale;
        ctx.stroke();
      } else if (isInFocusNetwork && hasActiveFocus && viewMode === "all") {
        traceShapePath(ctx, node.shape, x, y, r + 2.5 / globalScale);
        ctx.strokeStyle = hexToRgba(baseColor, 0.85);
        ctx.lineWidth = 1.6 / globalScale;
        ctx.stroke();
      } else if (node.pinned) {
        traceShapePath(ctx, node.shape, x, y, r + 2 / globalScale);
        ctx.strokeStyle = "#f59e0b";
        ctx.lineWidth = 1.5 / globalScale;
        ctx.stroke();
      }

      // 2. 节点底层玻璃器皿
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.fillStyle = dimmed
        ? "rgba(241, 245, 249, 0.15)"
        : node.isNote
        ? "rgba(49, 46, 129, 0.45)"
        : hexToRgba(baseColor, 0.15);
      ctx.fill();

      // 3. 水波填充（弯月面起伏）
      ctx.save();
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.clip();

      const freshness = Math.min(1, Math.max(0.08, node.freshness));
      const waterLevel = y + r - 2 * r * freshness;
      const waveAmp = Math.min(2.5, r * 0.1);
      const phase = node.id * 1.7;
      const startX = x - r * 1.25;
      const endX = x + r * 1.25;
      const midX = (startX + endX) / 2;
      const cp1Y = waterLevel - Math.sin(phase) * waveAmp;
      const cp2Y = waterLevel + Math.sin(phase) * waveAmp;

      const grad = ctx.createLinearGradient(x, waterLevel, x, y + r * 1.15);
      grad.addColorStop(0, hexToRgba(baseColor, dimmed ? 0.3 : 0.82));
      grad.addColorStop(1, hexToRgba(baseColor, dimmed ? 0.45 : 0.98));

      ctx.beginPath();
      ctx.moveTo(startX, y + r * 1.3);
      ctx.lineTo(startX, waterLevel);
      ctx.quadraticCurveTo(startX + (midX - startX) / 2, cp1Y, midX, waterLevel);
      ctx.quadraticCurveTo(midX + (endX - midX) / 2, cp2Y, endX, waterLevel);
      ctx.lineTo(endX, y + r * 1.3);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      if (!dimmed && freshness > 0.12) {
        ctx.beginPath();
        ctx.moveTo(startX, waterLevel);
        ctx.quadraticCurveTo(startX + (midX - startX) / 2, cp1Y, midX, waterLevel);
        ctx.quadraticCurveTo(midX + (endX - midX) / 2, cp2Y, endX, waterLevel);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.8)";
        ctx.lineWidth = Math.max(0.8, 1.1 / globalScale);
        ctx.stroke();
      }
      ctx.restore();

      // 4. 外边框（实验笔记采用特别加粗与金色高亮，构成显著重心）
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.strokeStyle = node.isNote
        ? "#eab308"
        : isFocusCenter
        ? "#6366f1"
        : node.pinned
        ? "#f59e0b"
        : hexToRgba(baseColor, dimmed ? 0.25 : 0.92);
      ctx.lineWidth = Math.max(1, (node.isNote ? 2.5 : isFocusCenter ? 2.0 : 1.3) / globalScale);
      ctx.stroke();

      // 5. 内部简写标志
      ctx.font = `600 ${Math.max(7, Math.min(10, r * 0.72))}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      ctx.fillStyle = dimmed
        ? "rgba(148, 163, 184, 0.4)"
        : node.isNote
        ? "#fef08a"
        : "#ffffff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const badgeText = node.isNote ? "📝" : (kgEntityShortText[node.entityType] || node.name.slice(0, 1));
      ctx.fillText(badgeText, x, y);

      // 6. 语义标签：在单实验精读模式下始终清晰显示；在全景模式下智能聚焦
      const shouldDrawLabel =
        labelMode === "all" ||
        (labelMode === "smart" && (viewMode === "focus" || node.isNote || isFocusCenter || isInFocusNetwork)) ||
        (labelMode === "smart" && globalScale >= 1.7);

      if (shouldDrawLabel && !dimmed) {
        const rawName = node.name || "";
        const maxLen = isFocusCenter || node.isNote ? 28 : 13;
        const displayName = rawName.length > maxLen ? `${rawName.slice(0, maxLen)}…` : rawName;
        const typePrefix = node.isNote ? "📝 " : `[${kgEntityTypeText[node.entityType] || node.entityType}] `;
        const fullLabel = `${typePrefix}${displayName}`;

        const fontSize = Math.max(
          8.5,
          Math.min(11, (node.isNote ? 11 : 9.5) / Math.sqrt(Math.max(globalScale, 0.65)))
        );
        ctx.font = `${node.isNote ? "600" : "500"} ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        const textMetrics = ctx.measureText(fullLabel);
        const textWidth = textMetrics.width;

        const pillHeight = fontSize + 5;
        const pillWidth = textWidth + (node.isNote ? 14 : 10);
        const pillY = y + r + 2.5 / globalScale;

        // 标签背景药丸
        ctx.fillStyle = node.isNote
          ? "rgba(30, 27, 75, 0.96)"
          : isFocusCenter
          ? "rgba(15, 23, 42, 0.95)"
          : "rgba(15, 23, 42, 0.82)";
        ctx.beginPath();
        ctx.roundRect(x - pillWidth / 2, pillY, pillWidth, pillHeight, 3.5);
        ctx.fill();

        ctx.strokeStyle = node.isNote
          ? "#eab308"
          : isFocusCenter
          ? "#818cf8"
          : "rgba(255, 255, 255, 0.18)";
        ctx.lineWidth = (node.isNote ? 1.2 : 0.8) / globalScale;
        ctx.stroke();

        ctx.fillStyle = node.isNote ? "#fef08a" : isFocusCenter ? "#ffffff" : "#e2e8f0";
        ctx.fillText(fullLabel, x, pillY + pillHeight / 2);
      }

      ctx.restore();
    },
    [spotlightType, primaryFocusId, highlightedIds, labelMode, viewMode]
  );

  // 连线中点语义药丸标签
  const paintLinkCanvas = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source;
      const target = link.target;
      if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(target.x)) return;

      const isFocused =
        primaryFocusId !== null &&
        (source.id === primaryFocusId || target.id === primaryFocusId);

      if (!showLinkLabels && !isFocused && viewMode !== "focus") return;

      const mx = (source.x + target.x) / 2;
      const my = (source.y + target.y) / 2;

      const label = link.label;
      const fontSize = Math.max(7.5, Math.min(10, 9 / Math.sqrt(Math.max(globalScale, 0.65))));
      ctx.font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      const tw = ctx.measureText(label).width;
      const pw = tw + 8;
      const ph = fontSize + 4;

      ctx.save();
      ctx.fillStyle = isFocused ? "rgba(15, 23, 42, 0.94)" : "rgba(15, 23, 42, 0.75)";
      ctx.beginPath();
      ctx.roundRect(mx - pw / 2, my - ph / 2, pw, ph, 3);
      ctx.fill();

      ctx.strokeStyle = isFocused ? hexToRgba(link.color, 0.9) : "rgba(255, 255, 255, 0.14)";
      ctx.lineWidth = 0.8 / globalScale;
      ctx.stroke();

      ctx.fillStyle = isFocused ? "#ffffff" : "#cbd5e1";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, mx, my);
      ctx.restore();
    },
    [primaryFocusId, showLinkLabels, viewMode]
  );

  return (
    <div
      className={`relative flex flex-col transition-all duration-300 ${
        isFullscreen
          ? "fixed inset-0 z-50 bg-background/95 backdrop-blur-md p-4"
          : "w-full"
      }`}
    >
      <Card className="flex flex-1 flex-col overflow-hidden border-border/75 shadow-card bg-card">
        {/* 顶栏模式切换与工具集 */}
        <CardHeader className="flex-none border-b border-border/60 bg-muted/20 py-2.5 px-4">
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            {/* 左侧：视图模式切换 */}
            <div className="flex items-center gap-2">
              <div className="flex items-center rounded-lg border border-border/80 bg-background/80 p-0.5 shadow-xs">
                <button
                  type="button"
                  onClick={() => {
                    setViewMode("focus");
                    if (activeExperimentId === null && noteEntities.length > 0) {
                      setActiveExperimentId(noteEntities[0].id);
                    }
                    setTimeout(() => fitGraph(350), 100);
                  }}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                    viewMode === "focus"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <FlaskConical className="h-3.5 w-3.5" />
                  <span>单实验精读</span>
                  <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0 border-white/20">
                    推荐
                  </Badge>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setViewMode("all");
                    setTimeout(() => fitGraph(350), 100);
                  }}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                    viewMode === "all"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Compass className="h-3.5 w-3.5" />
                  <span>全课题星系</span>
                  <span className="text-[10px] opacity-75 tabular-nums">({nodes.length})</span>
                </button>
              </div>

              <Badge variant="secondary" className="hidden sm:inline-flex text-[11px] font-normal">
                {viewMode === "focus"
                  ? `聚焦当前实验 · ${focusEntityIds.size} 个关键实体`
                  : `全课题总览 · ${nodes.length} 个实体 · 鼠标悬停聚焦`}
              </Badge>
            </div>

            {/* 中间：图内即时搜索框 */}
            <div className="flex items-center gap-1.5 max-w-xs flex-1">
              <div className="relative w-full">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={inGraphSearch}
                  onChange={(e) => setInGraphSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleInGraphSearch();
                  }}
                  placeholder="图内快速定位实体..."
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
                title="释放所有手动钉住的节点"
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
                  <DropdownMenuLabel>实体标签显示</DropdownMenuLabel>
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
                    始终显示全部
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "none"}
                    onCheckedChange={() => setLabelMode("none")}
                  >
                    极简无标签
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
                onClick={() => fitGraph(400)}
                className="h-7 px-2 text-xs"
                title="重置相机视角"
              >
                <Focus className="h-3.5 w-3.5" />
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

        {/* 单实验选择带 */}
        {noteEntities.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/50 bg-muted/10 px-4 py-2 text-xs no-scrollbar">
            <span className="flex-none text-[11px] font-medium text-muted-foreground mr-1">实验选择:</span>
            {noteEntities.map((note, idx) => {
              const isActive = viewMode === "focus" && activeExperimentId === note.id;
              return (
                <button
                  key={note.id}
                  type="button"
                  onClick={() => {
                    setViewMode("focus");
                    setActiveExperimentId(note.id);
                    onEntitySelect(note.id);
                    setTimeout(() => fitGraph(350), 100);
                  }}
                  title={note.name}
                  className={`flex-none truncate max-w-64 rounded-md px-2.5 py-1 text-xs transition-all ${
                    isActive
                      ? "bg-primary text-primary-foreground font-medium shadow-xs ring-2 ring-primary/30"
                      : "bg-background/80 text-foreground/80 hover:bg-primary/10 border border-border/70"
                  }`}
                >
                  📝 实验 #{idx + 1}: {note.name.split("：")[0] || note.name}
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
              graphData={{ nodes, links }}
              width={graphSize.width}
              height={graphSize.height}
              nodeVisibility={(node: any) => focusEntityIds.has(node.id)}
              linkVisibility={(link: any) => {
                const sId = typeof link.source === "object" ? link.source.id : link.source;
                const tId = typeof link.target === "object" ? link.target.id : link.target;
                return focusEntityIds.has(sId) && focusEntityIds.has(tId);
              }}
              nodeLabel={(node: any) =>
                `${kgEntityTypeText[node.entityType] || node.entityType}: ${node.name} · 置信度 ${(
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
                  primaryFocusId !== null && (sourceId === primaryFocusId || targetId === primaryFocusId);

                if (viewMode === "all" && primaryFocusId !== null) {
                  return isLinkedToFocus ? link.color : "rgba(148, 163, 184, 0.04)";
                }
                return hexToRgba(link.color, isLinkedToFocus ? 0.9 : 0.45);
              }}
              linkWidth={(link: any) => {
                const sourceId = typeof link.source === "object" ? link.source.id : link.source;
                const targetId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  primaryFocusId !== null && (sourceId === primaryFocusId || targetId === primaryFocusId);
                return isLinkedToFocus ? 2.6 : 1.0;
              }}
              linkDirectionalArrowLength={(link: any) => {
                const sourceId = typeof link.source === "object" ? link.source.id : link.source;
                const targetId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  primaryFocusId !== null && (sourceId === primaryFocusId || targetId === primaryFocusId);
                return isLinkedToFocus ? 6.5 : 4.5;
              }}
              linkDirectionalArrowRelPos={0.88}
              linkDirectionalArrowColor={(link: any) => link.color}
              linkCurvature={0.08}
              onNodeHover={(node: any) => setHoveredNodeId(node ? node.id : null)}
              onNodeClick={(node: any) => {
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
              }}
              onNodeRightClick={(node: any) => {
                delete node.fx;
                delete node.fy;
                node.pinned = false;
                graphRef.current?.d3ReheatSimulation?.();
              }}
              onNodeDragEnd={(node: any) => {
                node.fx = node.x;
                node.fy = node.y;
                node.pinned = true;
              }}
              onBackgroundClick={() => {
                onEntitySelect(null);
                setSpotlightType(null);
              }}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              enablePointerInteraction={true}
              onEngineStop={handleEngineStop}
              minZoom={0.15}
              maxZoom={3.5}
              cooldownTicks={160}
              cooldownTime={2500}
              d3AlphaDecay={0.04}
              d3VelocityDecay={0.35}
              warmupTicks={60}
            />
          )}

          {/* 右侧毛玻璃全息实体检视抽屉 */}
          {selectedDetails && (
            <div className="absolute top-3 right-3 bottom-3 w-80 z-20 flex flex-col rounded-xl border border-border/80 bg-card/95 p-4 shadow-2xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-right-4 duration-200">
              {/* 头部 */}
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

              {/* 核心指标 */}
              <div className="grid grid-cols-2 gap-2 py-3 border-b border-border/50 text-xs">
                <div className="rounded-md bg-muted/40 p-2">
                  <p className="text-[10px] text-muted-foreground">拓扑关联度</p>
                  <p className="text-base font-bold text-foreground">
                    {selectedDetails.node.degree} <span className="text-[10px] font-normal text-muted-foreground">条关联</span>
                  </p>
                </div>
                <div className="rounded-md bg-muted/40 p-2">
                  <p className="text-[10px] text-muted-foreground">证据新鲜度</p>
                  <p className="text-base font-bold text-foreground">
                    {(selectedDetails.node.freshness * 100).toFixed(0)}%
                  </p>
                </div>
              </div>

              {/* 关联实体清单 */}
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

              {/* 操作按钮区 */}
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

          {/* 底部折叠式「五通道语义映射图例」小胶囊 */}
          <div className="absolute bottom-3 left-3 z-10">
            {!legendOpen ? (
              <button
                type="button"
                onClick={() => setLegendOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background/90 px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-subtle backdrop-blur-md transition-colors hover:bg-background hover:text-foreground"
              >
                <MapIcon className="h-3.5 w-3.5 text-primary" />
                <span>五通道图例</span>
              </button>
            ) : (
              <div className="w-80 rounded-xl border border-border/80 bg-background/95 p-3.5 shadow-card backdrop-blur-md transition-all">
                <div className="mb-2 flex items-center justify-between border-b border-border/50 pb-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <Layers className="h-4 w-4 text-primary" />
                    <span>五通道科学可视化映射体系</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLegendOpen(false)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <div className="space-y-2 text-[11px] text-muted-foreground">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">1. 颜色通道</span>
                    <span>实体类别（试剂橙、仪器灰、靶标绿）</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">2. 尺寸通道</span>
                    <span>拓扑关联度（连接数越大半径越舒展）</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">3. 几何通道</span>
                    <span>实体角色（方块笔记、菱形分子、六边生物）</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">4. 水波通道</span>
                    <span>证据时效（液面高度与起伏反映更新时间）</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">5. 动态通道</span>
                    <span>箭头指向与定向脉冲粒子流动</span>
                  </div>
                </div>

                {/* 类别聚光灯快速过滤器 */}
                <div className="mt-3 border-t border-border/50 pt-2">
                  <div className="mb-1 text-[10px] text-muted-foreground">类别高亮隔离（点击聚焦）:</div>
                  <div className="flex flex-wrap gap-1">
                    {Object.keys(ENTITY_COLORS)
                      .slice(0, 8)
                      .map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => setSpotlightType(spotlightType === t ? null : t)}
                          className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition-colors ${
                            spotlightType === t
                              ? "bg-primary text-primary-foreground font-semibold"
                              : "bg-muted text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{ backgroundColor: ENTITY_COLORS[t] }}
                          />
                          <span>{kgEntityTypeText[t] || t}</span>
                        </button>
                      ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 画布悬浮控制器 */}
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
              onClick={() => fitGraph(400)}
              title="适应画布"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
