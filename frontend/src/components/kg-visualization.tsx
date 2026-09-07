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
  ChevronDown,
  ChevronRight,
  BookOpen,
  Eye,
  Workflow,
  Pin,
  PinOff,
  Search,
  Compass,
  Boxes,
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
      const corner = Math.min(6, r * 0.28);
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

  // 🌟 核心革新体验：双模视图架构 (Single Experiment Subgraph vs Global Multi-Galaxy Panorama)
  const [viewScope, setViewScope] = useState<"single" | "global">("single");
  const [selectedExperimentId, setSelectedExperimentId] = useState<number | null>(null);

  // 单实验精读模式下的专业布局算法：
  const [subgraphLayout, setSubgraphLayout] = useState<"pipeline" | "force" | "radial">("pipeline");

  // 图内即时搜索
  const [inGraphSearch, setInGraphSearch] = useState("");

  // 显示控制选项
  const [labelMode, setLabelMode] = useState<"smart" | "all" | "none">("smart");
  const [showLinkLabels, setShowLinkLabels] = useState(false);

  // 构建基础图拓扑数据
  const { nodes, links, entityMap, noteEntities, entityToNoteMap } = useMemo(() => {
    const map = new Map<number, KgEntity>();
    entities.forEach((e) => map.set(e.id, e));

    const relatedIds = new Set<number>();
    relations.forEach((r) => {
      relatedIds.add(r.source_entity_id);
      relatedIds.add(r.target_entity_id);
    });

    const visibleEntities = entities.filter((e) => relatedIds.has(e.id));

    // 水波通道 = 证据新鲜度
    const times = visibleEntities
      .map((e) => (e.updated_at ? new Date(e.updated_at).getTime() : Number.NaN))
      .filter((t) => Number.isFinite(t));
    const minT = times.length ? Math.min(...times) : 0;
    const maxT = times.length ? Math.max(...times) : 0;
    const span = maxT - minT || 1;

    // 实体与实验笔记从属映射
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
        ? 22
        : Math.max(12, Math.min(15, 11 + Math.sqrt(degree) * 1.0));

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
        confidence: r.confidence,
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

  // 默认选定第一个实验笔记
  useEffect(() => {
    if (selectedExperimentId === null && noteEntities.length > 0) {
      setSelectedExperimentId(noteEntities[0].id);
    }
  }, [noteEntities, selectedExperimentId]);

  // 🌟 当前生效的图数据：根据【单实验子图模式】或【全局星系总览】动态提取
  const activeGraphData = useMemo(() => {
    // 1. 全局全景模式：渲染全量 86 个节点
    if (viewScope === "global") {
      const gNodes = nodes.map((n) => ({ ...n, fx: undefined, fy: undefined }));
      return { nodes: gNodes, links };
    }

    // 2. 单实验子图模式：只提取当前选定实验及其 1-hop 关联实体（通常仅 10~14 个实体）
    const expId = selectedExperimentId ?? noteEntities[0]?.id;
    if (!expId) {
      return { nodes, links };
    }

    const subEntityIds = new Set<number>([expId]);
    relations.forEach((r) => {
      if (r.source_entity_id === expId) subEntityIds.add(r.target_entity_id);
      if (r.target_entity_id === expId) subEntityIds.add(r.source_entity_id);
    });

    const subNodes = nodes
      .filter((n) => subEntityIds.has(n.id))
      .map((n) => ({ ...n }));

    const subLinks = links.filter((l) => {
      const sId = typeof l.source === "object" ? l.source.id : l.source;
      const tId = typeof l.target === "object" ? l.target.id : l.target;
      return subEntityIds.has(sId) && subEntityIds.has(tId);
    });

    const w = graphSize.width || 900;
    const h = graphSize.height || 600;

    // A. 📐 科学反应分层流向链路 (Reaction Pipeline Flow)
    if (subgraphLayout === "pipeline") {
      const stageReagents: GraphNode[] = [];
      const stageConditions: GraphNode[] = [];
      const stageCore: GraphNode[] = [];
      const stageOutputs: GraphNode[] = [];

      subNodes.forEach((n) => {
        if (n.id === expId) {
          stageCore.unshift(n); // 核心实验笔记置于中心顶部
          return;
        }
        const t = n.entityType.toLowerCase();
        if (t.includes("reagent") || t.includes("chemical") || t.includes("compound")) {
          stageReagents.push(n);
        } else if (t.includes("condition") || t.includes("treatment") || t.includes("perturbation") || t.includes("culture")) {
          stageConditions.push(n);
        } else if (t.includes("instrument") || t.includes("software")) {
          stageCore.push(n);
        } else {
          stageOutputs.push(n);
        }
      });

      const colSpacing = Math.min(230, Math.max(160, w * 0.22));
      const stages = [
        { list: stageReagents, x: -1.5 * colSpacing },
        { list: stageConditions, x: -0.5 * colSpacing },
        { list: stageCore, x: 0.5 * colSpacing },
        { list: stageOutputs, x: 1.5 * colSpacing },
      ];

      stages.forEach(({ list, x }) => {
        const count = list.length;
        if (count === 0) return;
        const rowSpacing = Math.min(76, Math.max(48, (h * 0.72) / Math.max(count, 1)));
        list.forEach((node, idx) => {
          const y = (idx - (count - 1) / 2) * rowSpacing;
          node.fx = x;
          node.fy = y;
          node.x = x;
          node.y = y;
        });
      });
    } else if (subgraphLayout === "radial") {
      // B. 🎯 同心圆辐射布局 (Radial Ego-Network)
      const centerNode = subNodes.find((n) => n.id === expId);
      if (centerNode) {
        centerNode.fx = 0;
        centerNode.fy = 0;
        centerNode.x = 0;
        centerNode.y = 0;
      }
      const others = subNodes.filter((n) => n.id !== expId);
      const rx = Math.min(280, Math.max(180, w * 0.28));
      const ry = Math.min(210, Math.max(140, h * 0.26));
      others.forEach((n, idx) => {
        const angle = (idx * 2 * Math.PI) / Math.max(others.length, 1) - Math.PI / 2;
        const x = Math.cos(angle) * rx;
        const y = Math.sin(angle) * ry;
        n.fx = x;
        n.fy = y;
        n.x = x;
        n.y = y;
      });
    } else {
      // C. 🌌 微观星系引力排布 (Force Simulation)
      subNodes.forEach((n) => {
        n.fx = undefined;
        n.fy = undefined;
      });
    }

    return { nodes: subNodes, links: subLinks };
  }, [viewScope, selectedExperimentId, noteEntities, nodes, links, relations, subgraphLayout, graphSize.width, graphSize.height]);

  // 当前聚焦目标（优先级：鼠标悬停 > 选中实体）
  const primaryFocusId = hoveredNodeId ?? selectedEntityId;

  // 一跳关联子网络
  const highlightedIds = useMemo(() => {
    if (primaryFocusId === null) return new Set<number>();
    const ids = new Set<number>([primaryFocusId]);
    relations.forEach((r) => {
      if (r.source_entity_id === primaryFocusId) ids.add(r.target_entity_id);
      if (r.target_entity_id === primaryFocusId) ids.add(r.source_entity_id);
    });
    return ids;
  }, [primaryFocusId, relations]);

  // 选中的实体详情
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

    // 查找该实体从属的实验笔记
    const parentNoteIds = entityToNoteMap.get(selectedEntityId) || [];
    const parentNotes = parentNoteIds
      .map((id) => entityMap.get(id))
      .filter((n): n is KgEntity => Boolean(n));

    return {
      node,
      connected,
      parentNotes,
    };
  }, [selectedEntityId, nodes, relations, entityMap, entityToNoteMap]);

  // 配置全局模式力导引引擎
  const configureGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;

    if (viewScope === "single") {
      // 单实验微力导引：低斥力、紧凑连线，秒级收敛
      graph.d3Force("charge")?.strength(-180).distanceMax(400);
      graph.d3Force("link")?.distance(65);
      graph.d3Force("center")?.strength(0.08);
      if (forceCollide) {
        graph.d3Force("collide", forceCollide((n: any) => (n.radius || 12) + 20).iterations(2));
      }
      return;
    }

    // 全局全景模式：以 9 个实验笔记为星系重心
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
  }, [viewScope, noteEntities, entityToNoteMap, graphSize.width, graphSize.height]);

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
    const targetNode = activeGraphData.nodes.find((n) => n.id === nodeId);
    if (!targetNode || !graphRef.current) return;
    const x = targetNode.x;
    const y = targetNode.y;
    if (Number.isFinite(x) && Number.isFinite(y)) {
      graphRef.current.centerAt(x, y, 600);
      graphRef.current.zoom(1.6, 600);
    }
  }, [activeGraphData.nodes]);

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

  // 切换实验时自动对焦
  const handleSwitchExperiment = useCallback(
    (noteId: number) => {
      setSelectedExperimentId(noteId);
      setViewScope("single");
      onEntitySelect(noteId);
      setTimeout(() => fitGraph(350), 80);
    },
    [fitGraph, onEntitySelect]
  );

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((v) => !v);
    setTimeout(() => fitGraph(200), 150);
  }, [fitGraph]);

  // 释放所有固定钉住的节点
  const handleUnpinAll = useCallback(() => {
    activeGraphData.nodes.forEach((n: any) => {
      delete n.fx;
      delete n.fy;
      n.pinned = false;
    });
    graphRef.current?.d3ReheatSimulation?.();
  }, [activeGraphData.nodes]);

  // 图内搜索执行定位
  const handleInGraphSearch = useCallback(() => {
    const q = inGraphSearch.trim().toLowerCase();
    if (!q) return;
    const matched = activeGraphData.nodes.find((n) => n.name.toLowerCase().includes(q));
    if (matched) {
      onEntitySelect(matched.id);
      focusOnNode(matched.id);
    }
  }, [inGraphSearch, activeGraphData.nodes, onEntitySelect, focusOnNode]);

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
    const timer = window.setTimeout(configureGraph, 80);
    return () => window.clearTimeout(timer);
  }, [configureGraph, graphSize.width, graphSize.height, activeGraphData.nodes.length]);

  useEffect(() => {
    fitOnEngineStopRef.current = true;
  }, [activeGraphData]);

  // 键盘快捷操作
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

      const isSingleMode = viewScope === "single";
      const dimmed = !isSingleMode && ((!isInSpotlight) || (hasActiveFocus && !isInFocusNetwork));
      const baseColor = dimmed ? "#64748b" : node.color;
      const isFocusCenter = node.id === primaryFocusId;

      ctx.save();
      ctx.globalAlpha = dimmed ? 0.05 : 1.0;

      // 1. 焦点发光外环
      if (isFocusCenter) {
        traceShapePath(ctx, node.shape, x, y, r + 7 / globalScale);
        ctx.fillStyle = hexToRgba("#6366f1", 0.35);
        ctx.fill();
        traceShapePath(ctx, node.shape, x, y, r + 3.5 / globalScale);
        ctx.strokeStyle = "#818cf8";
        ctx.lineWidth = 2.4 / globalScale;
        ctx.stroke();
      } else if (isInFocusNetwork && hasActiveFocus && !isSingleMode) {
        traceShapePath(ctx, node.shape, x, y, r + 2.5 / globalScale);
        ctx.strokeStyle = hexToRgba(baseColor, 0.85);
        ctx.lineWidth = 1.6 / globalScale;
        ctx.stroke();
      }

      // 2. 底层器皿背景
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.fillStyle = dimmed
        ? "rgba(241, 245, 249, 0.15)"
        : node.isNote
        ? "rgba(49, 46, 129, 0.45)"
        : hexToRgba(baseColor, 0.15);
      ctx.fill();

      // 3. 水波纹起伏填充
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

      // 4. 外边框
      traceShapePath(ctx, node.shape, x, y, r);
      ctx.strokeStyle = node.isNote
        ? "#eab308"
        : isFocusCenter
        ? "#818cf8"
        : dimmed
        ? "#334155"
        : hexToRgba(baseColor, 0.9);
      ctx.lineWidth = (node.isNote ? 2.5 : isFocusCenter ? 2.2 : 1.2) / Math.max(globalScale, 0.6);
      ctx.stroke();

      // 5. 钉住微标记（如果被用户拖拽固定）
      if (node.fx !== undefined && !isSingleMode) {
        ctx.beginPath();
        ctx.arc(x + r * 0.7, y - r * 0.7, 3.5 / globalScale, 0, Math.PI * 2);
        ctx.fillStyle = "#f59e0b";
        ctx.fill();
      }

      // 6. 节点中心图标
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (node.isNote) {
        ctx.font = `${Math.max(10, r * 0.75)}px sans-serif`;
        ctx.fillText("📝", x, y);
      } else {
        const shortGlyph = EXTENDED_SHORT_TEXT[node.entityType] || node.entityType.slice(0, 1).toUpperCase();
        const glyphSize = Math.max(8, Math.min(10.5, r * 0.7));
        ctx.font = `600 ${glyphSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;

        const liquidIsHigh = freshness >= 0.45;
        ctx.fillStyle = dimmed ? "#64748b" : liquidIsHigh ? "#ffffff" : hexToRgba(baseColor, 0.95);
        if (liquidIsHigh && !dimmed) {
          ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
          ctx.shadowBlur = 2.5;
        }
        ctx.fillText(shortGlyph, x, y);
        ctx.shadowBlur = 0;
      }

      // 7. 标签绘制：单实验精读模式下全显标签，清爽可读；全局模式下智能按需呈现
      const shouldDrawLabel =
        isSingleMode ||
        labelMode === "all" ||
        node.isNote ||
        isFocusCenter ||
        (hasActiveFocus && isInFocusNetwork) ||
        (labelMode === "smart" && globalScale >= 1.6);

      if (shouldDrawLabel && !dimmed) {
        const rawName = node.name || "";
        const maxLen = isSingleMode ? 28 : (isFocusCenter || node.isNote ? 26 : 11);
        const displayName = rawName.length > maxLen ? `${rawName.slice(0, maxLen)}…` : rawName;

        const fontSize = Math.max(
          8.5,
          Math.min(11, (node.isNote ? 11 : 9.5) / Math.sqrt(Math.max(globalScale, 0.65)))
        );
        ctx.font = `${node.isNote ? "600" : "500"} ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        const textMetrics = ctx.measureText(displayName);
        const textWidth = textMetrics.width;

        const pillHeight = fontSize + 5;
        const pillWidth = textWidth + (node.isNote ? 14 : 10);
        const pillY = y + r + 2.5 / globalScale;

        // 标签药丸
        ctx.fillStyle = node.isNote
          ? "rgba(30, 27, 75, 0.96)"
          : isFocusCenter
          ? "rgba(15, 23, 42, 0.95)"
          : "rgba(15, 23, 42, 0.78)";
        ctx.beginPath();
        ctx.roundRect(x - pillWidth / 2, pillY, pillWidth, pillHeight, 3.5);
        ctx.fill();

        ctx.strokeStyle = node.isNote
          ? "#eab308"
          : isFocusCenter
          ? "#818cf8"
          : hexToRgba(baseColor, 0.5);
        ctx.lineWidth = 1 / Math.max(globalScale, 0.8);
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(displayName, x, pillY + pillHeight / 2);
      }

      ctx.restore();
    },
    [primaryFocusId, highlightedIds, spotlightType, labelMode, viewScope]
  );

  // 连线绘制
  const paintLinkCanvas = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (!showLinkLabels) return;
      const s = link.source;
      const t = link.target;
      if (!s || !t || !Number.isFinite(s.x) || !Number.isFinite(t.x)) return;

      const isFocused =
        primaryFocusId !== null &&
        (s.id === primaryFocusId || t.id === primaryFocusId);

      if (!isFocused && globalScale < 1.4) return;

      const mx = (s.x + t.x) / 2;
      const my = (s.y + t.y) / 2;
      const label = link.label || link.relationType;

      ctx.save();
      const fontSize = Math.max(7.5, Math.min(10, 8.5 / globalScale));
      ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      const w = ctx.measureText(label).width + 6;
      const h = fontSize + 4;

      ctx.fillStyle = isFocused ? "rgba(15, 23, 42, 0.92)" : "rgba(30, 41, 59, 0.7)";
      ctx.beginPath();
      ctx.roundRect(mx - w / 2, my - h / 2, w, h, 2);
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
    [primaryFocusId, showLinkLabels]
  );

  const activeExpNode = useMemo(() => {
    return noteEntities.find((n) => n.id === selectedExperimentId) || noteEntities[0] || null;
  }, [noteEntities, selectedExperimentId]);

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
        {/* 🌟 核心升级 1：工作区模式切换与顶栏工具 */}
        <CardHeader className="flex-none border-b border-border/60 bg-muted/20 py-2.5 px-4">
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            {/* 左侧：视图模式切换（单实验精读 vs 全景星系） */}
            <div className="flex items-center gap-2">
              <div className="flex items-center rounded-lg border border-border/80 bg-background/80 p-0.5 shadow-xs">
                <button
                  type="button"
                  onClick={() => {
                    setViewScope("single");
                    if (selectedExperimentId === null && noteEntities.length > 0) {
                      setSelectedExperimentId(noteEntities[0].id);
                    }
                    setTimeout(() => fitGraph(300), 100);
                  }}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                    viewScope === "single"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <FlaskConical className="h-3.5 w-3.5" />
                  <span>单实验精读流程图</span>
                  <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0 border-white/20">
                    推荐
                  </Badge>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setViewScope("global");
                    setTimeout(() => fitGraph(300), 100);
                  }}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                    viewScope === "global"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Compass className="h-3.5 w-3.5" />
                  <span>全课题星系总览</span>
                  <span className="text-[10px] opacity-75 tabular-nums">({nodes.length})</span>
                </button>
              </div>

              {/* 当前模式状态说明徽标 */}
              <Badge variant="secondary" className="hidden sm:inline-flex text-[11px] font-normal">
                {viewScope === "single"
                  ? `${activeGraphData.nodes.length} 个当前实验实体 · 纯净零干扰`
                  : `${noteEntities.length} 实验星系 · ${nodes.length} 实体 · ${links.length} 关系`}
              </Badge>
            </div>

            {/* 中间：图内即时搜索框 */}
            <div className="relative hidden md:flex items-center w-48 lg:w-56">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={inGraphSearch}
                onChange={(e) => setInGraphSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleInGraphSearch();
                }}
                placeholder="图内定位实体..."
                className="h-8 pl-8 pr-7 text-xs bg-background/90"
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

            {/* 右侧：单实验布局切换与画布控制 */}
            <div className="flex items-center gap-1.5">
              {viewScope === "single" && (
                <div className="flex items-center rounded-lg border border-border/70 bg-background/80 p-0.5">
                  <button
                    type="button"
                    onClick={() => setSubgraphLayout("pipeline")}
                    title="反应链路分层流向排布 (推荐)"
                    className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
                      subgraphLayout === "pipeline"
                        ? "bg-muted text-foreground font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Workflow className="h-3 w-3 text-primary" />
                    <span>反应流向</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubgraphLayout("force")}
                    title="微观引力场排布"
                    className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
                      subgraphLayout === "force"
                        ? "bg-muted text-foreground font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Boxes className="h-3 w-3 text-indigo-500" />
                    <span>星系微力</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubgraphLayout("radial")}
                    title="同心圆辐射排布"
                    className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
                      subgraphLayout === "radial"
                        ? "bg-muted text-foreground font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Compass className="h-3 w-3 text-emerald-500" />
                    <span>同心圆</span>
                  </button>
                </div>
              )}

              {/* 标签策略菜单 */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 gap-1 px-2.5 text-xs">
                    <Layers className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">
                      {labelMode === "smart" ? "智能标签" : labelMode === "all" ? "全显标签" : "极简几何"}
                    </span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel className="text-xs">标签展示策略</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "smart"}
                    onCheckedChange={() => setLabelMode("smart")}
                    className="text-xs"
                  >
                    <Sparkles className="mr-2 h-3.5 w-3.5 text-primary" />
                    智能聚焦（推荐）
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "all"}
                    onCheckedChange={() => setLabelMode("all")}
                    className="text-xs"
                  >
                    <Tag className="mr-2 h-3.5 w-3.5" />
                    常显全部标签
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem
                    checked={labelMode === "none"}
                    onCheckedChange={() => setLabelMode("none")}
                    className="text-xs"
                  >
                    <Eye className="mr-2 h-3.5 w-3.5" />
                    极简几何（仅悬停显）
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuCheckboxItem
                    checked={showLinkLabels}
                    onCheckedChange={setShowLinkLabels}
                    className="text-xs"
                  >
                    <ArrowRight className="mr-2 h-3.5 w-3.5" />
                    常显连线关系名称
                  </DropdownMenuCheckboxItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <div className="h-4 w-px bg-border/80" />

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
                title="复位并居中"
                aria-label="复位居中"
              >
                <Focus className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => {
                  handleUnpinAll();
                  configureGraph();
                  graphRef.current?.d3ReheatSimulation?.();
                }}
                title="释放所有固定位置并重新布局"
                aria-label="重新布局"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={toggleFullscreen}
                title={isFullscreen ? "退出全屏 (Esc)" : "全屏沉浸探索"}
                aria-label="全屏切换"
              >
                {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </CardHeader>

        {/* 🌟 核心升级 2：实验快速导航带（在单实验精读模式下高亮切换实验；全局模式下点击一键钻取） */}
        {noteEntities.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/60 bg-muted/30 px-3 py-1.5 scrollbar-none">
            <span className="flex-none text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
              <BookOpen className="h-3.5 w-3.5 text-primary" />
              {viewScope === "single" ? "当前实验精读:" : "实验导航钻取:"}
            </span>

            {noteEntities.map((note, idx) => {
              const isActive = (viewScope === "single" && selectedExperimentId === note.id) || (viewScope === "global" && selectedEntityId === note.id);
              return (
                <button
                  key={note.id}
                  type="button"
                  onClick={() => handleSwitchExperiment(note.id)}
                  onMouseEnter={() => setHoveredNodeId(note.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  title={note.name}
                  className={`flex-none truncate max-w-64 rounded-md px-2.5 py-1 text-xs transition-all ${
                    isActive
                      ? "bg-indigo-600 text-white font-medium shadow-sm ring-2 ring-indigo-400/40"
                      : "bg-background/80 text-foreground/80 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 border border-border/70"
                  }`}
                >
                  📝 实验 #{idx + 1}: {note.name.split("：")[0] || note.name}
                </button>
              );
            })}
          </div>
        )}

        {/* 画布主内容区域 */}
        <CardContent
          ref={containerRef}
          className="relative flex-1 p-0 overflow-hidden bg-dot-grid"
          style={{ minHeight: graphSize.height }}
        >
          {graphSize.width > 0 && (
            <ForceGraph2D
              ref={graphRef}
              width={graphSize.width}
              height={graphSize.height}
              graphData={activeGraphData}
              nodeId="id"
              nodeLabel={(node: any) =>
                `${node.name}（${kgEntityTypeText[node.entityType] || node.entityType}）· 置信度 ${(
                  node.freshness * 100
                ).toFixed(0)}% · 关联度 ${node.degree}`
              }
              nodeVal={(node: any) => node.val}
              nodeCanvasObject={paintNode}
              linkCanvasObjectMode={() => "after"}
              linkCanvasObject={paintLinkCanvas}
              linkLabel={(link: any) => `${link.label}（置信度 ${(link.confidence || 0).toFixed(2)}）`}
              linkColor={(link: any) => {
                const sId = typeof link.source === "object" ? link.source.id : link.source;
                const tId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);

                if (viewScope === "global" && primaryFocusId !== null) {
                  return isLinkedToFocus ? link.color : "rgba(148, 163, 184, 0.04)";
                }
                return hexToRgba(link.color, viewScope === "single" ? 0.65 : 0.35);
              }}
              linkWidth={(link: any) => {
                const sId = typeof link.source === "object" ? link.source.id : link.source;
                const tId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);
                return isLinkedToFocus ? 2.6 : viewScope === "single" ? 1.6 : 0.8;
              }}
              linkDirectionalArrowLength={(link: any) => {
                const sId = typeof link.source === "object" ? link.source.id : link.source;
                const tId = typeof link.target === "object" ? link.target.id : link.target;
                const isLinkedToFocus =
                  primaryFocusId !== null && (sId === primaryFocusId || tId === primaryFocusId);
                return isLinkedToFocus ? 7 : 5;
              }}
              linkDirectionalArrowRelPos={0.88}
              linkDirectionalArrowColor={(link: any) => link.color}
              linkCurvature={viewScope === "single" && subgraphLayout === "pipeline" ? 0.0 : 0.08}
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
              cooldownTicks={140}
              cooldownTime={2000}
              d3AlphaDecay={0.06}
              d3VelocityDecay={0.42}
              warmupTicks={70}
              autoPauseRedraw
            />
          )}

          {/* 🌟 核心升级 3：单实验反应流向布局 Stage 提示指示器 */}
          {viewScope === "single" && subgraphLayout === "pipeline" && activeExpNode && (
            <div className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4 rounded-full border border-border/70 bg-background/85 px-4 py-1 shadow-subtle backdrop-blur-md">
              <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                ① 试剂原料
              </span>
              <span className="text-[10px] text-muted-foreground">➔</span>
              <span className="text-[11px] font-semibold text-sky-600 dark:text-sky-400">
                ② 反应条件
              </span>
              <span className="text-[10px] text-muted-foreground">➔</span>
              <span className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">
                ③ 实验核心 & 仪器
              </span>
              <span className="text-[10px] text-muted-foreground">➔</span>
              <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                ④ 产物与表征
              </span>
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
                <span>语义映射图例 (五通道)</span>
                <ChevronDown className="h-3.5 w-3.5 opacity-60" />
              </button>
            ) : (
              <div className="w-72 rounded-xl border border-border/80 bg-background/95 p-3.5 shadow-xl backdrop-blur-md animate-in fade-in zoom-in-95">
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

                <div className="space-y-2 text-[11px] leading-relaxed text-muted-foreground">
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
                      <div className="relative h-3.5 w-24 overflow-hidden rounded border border-border/80 bg-muted/30">
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
                    <span>大小 = 关联枢纽度 · 颜色 = 实体类型 · 中心汉字 = 实体简码</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 🌟 核心升级 4：右侧滑出式「全息实体详情检视抽屉」(Side Holographic Inspector Drawer) */}
          {selectedDetails && (
            <div className="absolute top-3 right-3 bottom-3 z-20 flex w-80 sm:w-96 flex-col overflow-hidden rounded-2xl border border-border/80 bg-background/95 shadow-elevate backdrop-blur-md animate-in slide-in-from-right-4 duration-200">
              {/* 抽屉头部 */}
              <div className="flex items-start justify-between border-b border-border/60 bg-muted/20 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 flex-none rounded-full ring-2 ring-black/10"
                      style={{ backgroundColor: selectedDetails.node.color }}
                    />
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                      {kgEntityTypeText[selectedDetails.node.entityType] || selectedDetails.node.entityType}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">
                      {selectedDetails.node.isNote ? "核心实验记录" : "科研实体"}
                    </span>
                  </div>
                  <h3 className="mt-2 text-sm font-bold text-foreground break-words leading-tight" title={selectedDetails.node.name}>
                    {selectedDetails.node.name}
                  </h3>
                </div>
                <button
                  type="button"
                  aria-label="关闭详情抽屉"
                  onClick={() => onEntitySelect(null)}
                  className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* 抽屉主体属性与证据 */}
              <div className="flex-1 space-y-3.5 overflow-y-auto p-4 text-xs">
                {/* 关键度量双卡片 */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-border/60 bg-muted/25 p-2.5">
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Network className="h-3 w-3 text-primary" />
                      关联度数
                    </span>
                    <p className="mt-1 text-base font-bold tabular-nums text-foreground">
                      {selectedDetails.node.degree} 处连接
                    </p>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-muted/25 p-2.5">
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3 text-emerald-500" />
                      证据新鲜度
                    </span>
                    <p className="mt-1 text-base font-bold tabular-nums text-foreground">
                      {Math.round(selectedDetails.node.freshness * 100)}%
                    </p>
                  </div>
                </div>

                {/* 所属实验课题（针对实体显示其归属的实验） */}
                {selectedDetails.parentNotes && selectedDetails.parentNotes.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="font-semibold text-foreground flex items-center gap-1 text-[11px]">
                      <BookOpen className="h-3.5 w-3.5 text-primary" /> 所属实验记录
                    </p>
                    <div className="space-y-1">
                      {selectedDetails.parentNotes.map((note) => (
                        <div
                          key={note.id}
                          onClick={() => handleSwitchExperiment(note.id)}
                          className="group flex cursor-pointer items-center justify-between rounded-lg border border-border/60 bg-background/80 p-2 text-xs transition-colors hover:border-primary/40 hover:bg-primary/5"
                        >
                          <span className="truncate font-medium text-foreground group-hover:text-primary">
                            📝 {note.label}
                          </span>
                          <span className="flex items-center text-[10px] text-primary group-hover:underline">
                            精读 <ChevronRight className="h-3 w-3" />
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 关联网络明细（可点击跳转对焦） */}
                <div className="space-y-2">
                  <p className="font-semibold text-foreground text-[11px]">
                    一跳关联实体清单 ({selectedDetails.connected.length})
                  </p>
                  {selectedDetails.connected.length === 0 ? (
                    <p className="text-muted-foreground">暂无一跳关联节点</p>
                  ) : (
                    <div className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
                      {selectedDetails.connected.map((item) => (
                        <div
                          key={item.id}
                          onClick={() => {
                            onEntitySelect(item.neighborId);
                            focusOnNode(item.neighborId);
                          }}
                          className="group flex cursor-pointer items-center justify-between rounded-lg border border-border/60 bg-background/80 p-2 text-xs transition-colors hover:border-primary/50 hover:bg-primary/5"
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
                            <p className="truncate font-medium text-foreground group-hover:text-primary mt-0.5">
                              {item.neighborLabel}
                            </p>
                          </div>
                          <Badge variant="outline" className="text-[9px] py-0 px-1.5 ml-1 flex-none">
                            {kgEntityTypeText[item.neighborType] || item.neighborType}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 抽屉底部快捷操作 */}
              <div className="flex items-center gap-2 border-t border-border/60 bg-muted/30 p-3">
                {selectedDetails.node.isNote && viewScope === "global" && (
                  <Button
                    size="sm"
                    className="flex-1 text-xs h-8"
                    onClick={() => handleSwitchExperiment(selectedDetails.node.id)}
                  >
                    <FlaskConical className="mr-1.5 h-3.5 w-3.5" />
                    进入此实验精读
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
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
        </CardContent>
      </Card>
    </div>
  );
}
