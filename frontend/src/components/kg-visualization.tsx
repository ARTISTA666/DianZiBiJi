/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Focus, Info, ZoomIn, ZoomOut } from "lucide-react";
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
}

interface GraphLink {
  source: number;
  target: number;
  label: string;
  confidence: number;
}

// 实体类型 → 颜色映射
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

function getEntityColor(entityType: string): string {
  return ENTITY_COLORS[entityType] || "#94a3b8";
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

  // 构建图数据
  const { nodes, links } = useMemo(() => {
    // 只展示有关系的实体
    const relatedIds = new Set<number>();
    relations.forEach((r) => {
      relatedIds.add(r.source_entity_id);
      relatedIds.add(r.target_entity_id);
    });
    const visibleEntities = entities.filter((e) => relatedIds.has(e.id));

    const graphNodes: GraphNode[] = visibleEntities.map((e) => ({
      id: e.id,
      name: e.label,
      entityType: e.entity_type,
      val: Math.max(3, Math.min(12, relations.filter(
        (r) => r.source_entity_id === e.id || r.target_entity_id === e.id
      ).length * 2)),
      color: getEntityColor(e.entity_type),
    }));

    const graphLinks: GraphLink[] = relations
      .filter((r) => relatedIds.has(r.source_entity_id) && relatedIds.has(r.target_entity_id))
      .map((r) => ({
        source: r.source_entity_id,
        target: r.target_entity_id,
        label: kgRelationTypeText[r.relation_type] || r.relation_type,
        confidence: r.confidence,
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
    graph.d3Force("link")?.distance(52);
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
          <p className="text-sm text-muted-foreground">暂无可可视化的图谱数据</p>
          <p className="mt-1 text-xs text-muted-foreground">请先创建实验笔记并审核，系统会自动抽取实体和关系</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">图谱可视化</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {nodes.length} 节点 · {links.length} 边 · 点击节点查看关联
            </p>
          </div>
          <div className="min-w-0 flex-1 items-center justify-end gap-2 sm:flex">
            {/* 图例 */}
            <div className="hidden min-w-0 flex-1 flex-wrap justify-end gap-1.5 sm:flex">
              {typeDistribution.slice(0, 6).map(([label, count]) => {
                const entityType = Object.entries(kgEntityTypeText).find(([, v]) => v === label)?.[0] || label;
                return (
                  <Badge key={label} variant="outline" className="gap-1 text-[10px] font-normal">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: getEntityColor(entityType) }} />
                    {label} ({count})
                  </Badge>
                );
              })}
            </div>
            <div className="flex items-center rounded-md border bg-background/90">
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="缩小图谱" title="缩小图谱" onClick={() => zoomGraph(0.8)}>
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="放大图谱" title="放大图谱" onClick={() => zoomGraph(1.25)}>
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="重置图谱视图" title="重置图谱视图" onClick={() => graphRef.current?.zoomToFit?.(250, 36)}>
                <Focus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent ref={graphContainerRef} className="relative h-[min(68vh,44rem)] min-h-[32rem] overflow-hidden p-0">
        {graphSize.width > 0 && <ForceGraph2D
          ref={graphRef as any}
          graphData={graphData}
          width={graphSize.width}
          height={graphSize.height}
          nodeLabel={(node: any) => `${kgEntityTypeText[node.entityType] || node.entityType}: ${node.name}`}
          nodeColor={(node: any) => {
            if (selectedEntityId !== null && !highlightedIds.has(node.id)) return "#e2e8f0";
            return node.color;
          }}
          nodeRelSize={4.5}
          nodeVal={(node: any) => node.val}
          linkLabel={(link: any) => `${link.label}（置信度 ${link.confidence.toFixed(2)}）`}
          linkColor={(link: any) => {
            if (selectedEntityId !== null) {
              const isHighlighted = link.source.id === selectedEntityId || link.target.id === selectedEntityId
                || link.source === selectedEntityId || link.target === selectedEntityId;
              return isHighlighted ? "#6366f1" : "#e2e8f0";
            }
            return "#94a3b8";
          }}
          linkWidth={(link: any) => {
            if (selectedEntityId !== null) {
              const isHighlighted = link.source.id === selectedEntityId || link.target.id === selectedEntityId
                || link.source === selectedEntityId || link.target === selectedEntityId;
              return isHighlighted ? 2 : 0.5;
            }
            return 1;
          }}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.9}
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
      </CardContent>
    </Card>
  );
}
