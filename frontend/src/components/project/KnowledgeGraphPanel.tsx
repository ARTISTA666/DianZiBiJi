"use client";

import { Sparkles } from "lucide-react";
import type { KnowledgeGraph, KnowledgeEntity, KnowledgeRelation, Note } from "@/lib/api";
import { cardClass, shortLabel } from "../shared/utils";
import {
  kgEntityTypeText,
  kgRelationTypeText,
  kgEntityColors,
  kgEntityShortText,
  statusText,
} from "../constants";

interface KnowledgeGraphPanelProps {
  kgGraph: KnowledgeGraph | null;
  kgBusy: boolean;
  kgEntityFilter: string;
  onKgEntityFilterChange: (v: string) => void;
  kgRelationFilter: string;
  onKgRelationFilterChange: (v: string) => void;
  selectedKgEntityId: number | null;
  onSelectedKgEntityIdChange: (id: number | null) => void;
  kgEntityTypeOptions: string[];
  kgRelationTypeOptions: string[];
  kgEntityStats: Array<[string, number]>;
  filteredKgEntities: KnowledgeEntity[];
  filteredKgRelations: KnowledgeRelation[];
  selectedKgEntity: KnowledgeEntity | null;
  selectedKgEntityRelations: KnowledgeRelation[];
  kgEntityById: Map<number, KnowledgeEntity>;
  notes: Note[];
  selectedNote: Note | null;
  canWriteSelectedProject: boolean;
  kgLayout: {
    nodes: Array<{ entity: KnowledgeEntity; x: number; y: number }>;
    relations: KnowledgeRelation[];
    nodeById: Map<number, { entity: KnowledgeEntity; x: number; y: number }>;
  };
  onRefreshGraph: () => void;
  onExtractNote: (note?: Note) => void;
  onRebuildGraph: () => void;
  onNavigateNotes: (note: Note) => void;
  onNavigateFiles: () => void;
}

function kgTypeLabel(type: string) {
  return kgEntityTypeText[type] || type;
}

function kgRelationLabel(type: string) {
  return kgRelationTypeText[type] || type;
}

export function KnowledgeGraphPanel({
  kgGraph,
  kgBusy,
  kgEntityFilter,
  onKgEntityFilterChange,
  kgRelationFilter,
  onKgRelationFilterChange,
  selectedKgEntityId,
  onSelectedKgEntityIdChange,
  kgEntityTypeOptions,
  kgRelationTypeOptions,
  kgEntityStats,
  filteredKgEntities,
  filteredKgRelations,
  selectedKgEntity,
  selectedKgEntityRelations,
  kgEntityById,
  notes,
  selectedNote,
  canWriteSelectedProject,
  kgLayout,
  onRefreshGraph,
  onExtractNote,
  onRebuildGraph,
  onNavigateNotes,
  onNavigateFiles,
}: KnowledgeGraphPanelProps) {
  return (
    <div className="grid gap-4">
      {/* Header */}
      <div className={cardClass("p-5")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={18} />实验知识图谱</h2>
            <p className="mt-1 text-sm text-muted">
              从实验笔记中抽取项目、人员、附件、试剂、仪器、样本和结果关系，用于后续图谱增强 RAG。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={kgBusy}
              onClick={onRefreshGraph}
              className="rounded-md border border-border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              刷新图谱
            </button>
            {canWriteSelectedProject && selectedNote && (
              <button
                type="button"
                disabled={kgBusy}
                onClick={() => onExtractNote()}
                className="rounded-md border border-brand px-3 py-2 text-sm text-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                抽取当前笔记
              </button>
            )}
            {canWriteSelectedProject && (
              <button
                type="button"
                disabled={kgBusy || notes.length === 0}
                onClick={onRebuildGraph}
                className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                重建项目图谱
              </button>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          {[
            { label: "实体总数", value: kgGraph?.entities.length ?? 0 },
            { label: "关系总数", value: kgGraph?.relations.length ?? 0 },
            { label: "实验笔记", value: kgEntityStats.find(([t]) => t === "note")?.[1] ?? 0 },
            { label: "抽取状态", value: kgBusy ? "处理中..." : kgGraph?.entities.length ? "已生成" : "待生成" },
          ].map((item) => (
            <div key={item.label} className="rounded-md border border-border px-3 py-2">
              <p className="text-xs text-muted">{item.label}</p>
              <p className="mt-1 font-medium">{item.value}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={kgEntityFilter}
            onChange={(e) => {
              onKgEntityFilterChange(e.target.value);
              onSelectedKgEntityIdChange(null);
            }}
          >
            <option value="">全部实体类型</option>
            {kgEntityTypeOptions.map((type) => (
              <option key={type} value={type}>{kgTypeLabel(type)}</option>
            ))}
          </select>
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={kgRelationFilter}
            onChange={(e) => onKgRelationFilterChange(e.target.value)}
          >
            <option value="">全部关系类型</option>
            {kgRelationTypeOptions.map((type) => (
              <option key={type} value={type}>{kgRelationLabel(type)}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              onKgEntityFilterChange("");
              onKgRelationFilterChange("");
              onSelectedKgEntityIdChange(null);
            }}
            className="rounded-md border border-border px-3 py-2 text-sm"
          >
            清除筛选
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">
          当前筛选展示 {filteredKgEntities.length} 个实体、{filteredKgRelations.length} 条关系。
        </p>
      </div>

      {/* Graph + Entity Details */}
      <div className="grid gap-4 xl:grid-cols-[1.45fr_0.55fr]">
        <div className={cardClass("p-5")}>
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold">项目关系图</h3>
            <p className="text-xs text-muted">按关联度展示 16 个代表节点 / 36 条关系</p>
          </div>
          {(!kgGraph || kgGraph.entities.length === 0) && (
            <div className="mt-4 rounded-md border border-dashed border-border bg-surface px-4 py-10 text-center text-sm text-muted">
              当前项目还没有知识图谱。先选择一篇笔记抽取，或直接重建项目图谱。
            </div>
          )}
          {kgGraph && kgGraph.entities.length > 0 && (
            <div className="mt-4 overflow-auto rounded-md border border-border bg-surface">
              <svg viewBox="0 0 800 500" className="h-[500px] min-w-[800px] w-full" aria-label="项目知识图谱">
                <rect width="800" height="500" fill="#f8fafc" />
                {kgLayout.relations.map((rel) => {
                  const source = kgLayout.nodeById.get(rel.source_entity_id);
                  const target = kgLayout.nodeById.get(rel.target_entity_id);
                  if (!source || !target) return null;
                  const isConnected =
                    !selectedKgEntityId ||
                    rel.source_entity_id === selectedKgEntityId ||
                    rel.target_entity_id === selectedKgEntityId;
                  return (
                    <line
                      key={rel.id}
                      x1={source.x} y1={source.y} x2={target.x} y2={target.y}
                      stroke={isConnected ? "#94a3b8" : "#e2e8f0"}
                      strokeWidth={isConnected ? 1.5 : 0.8}
                      opacity={isConnected ? 0.72 : 0.28}
                    >
                      <title>{kgRelationLabel(rel.relation_type)}</title>
                    </line>
                  );
                })}
                {kgLayout.nodes.map((node) => {
                  const color = kgEntityColors[node.entity.entity_type] || "#64748b";
                  const isProject = node.entity.entity_type === "project";
                  const isSelected = selectedKgEntityId === node.entity.id;
                  const isRelated =
                    !selectedKgEntityId ||
                    isSelected ||
                    selectedKgEntityRelations.some(
                      (r) => r.source_entity_id === node.entity.id || r.target_entity_id === node.entity.id
                    );
                  return (
                    <g
                      key={node.entity.id}
                      onClick={() => onSelectedKgEntityIdChange(isSelected ? null : node.entity.id)}
                      className="cursor-pointer"
                      opacity={isRelated ? 1 : 0.35}
                    >
                      <circle
                        cx={node.x} cy={node.y}
                        r={isProject ? 38 : 18}
                        fill={color} opacity="0.96"
                        stroke={isSelected ? "#0f172a" : "#ffffff"}
                        strokeWidth={isSelected ? 4 : 2}
                      />
                      {isProject ? (
                        <>
                          <text x={node.x} y={node.y - 3} textAnchor="middle" className="fill-white text-[11px] font-semibold">
                            {shortLabel(node.entity.label, 10)}
                          </text>
                          <text x={node.x} y={node.y + 13} textAnchor="middle" className="fill-white text-[9px] opacity-90">
                            项目
                          </text>
                        </>
                      ) : (
                        <>
                          <text x={node.x} y={node.y + 4} textAnchor="middle" className="fill-white text-[9px] font-bold">
                            {kgEntityShortText[node.entity.entity_type] || "点"}
                          </text>
                          <text
                            x={node.x} y={node.y + 34}
                            textAnchor="middle"
                            className="fill-slate-800 text-[10px] font-medium"
                            style={{ paintOrder: "stroke", stroke: "#f8fafc", strokeWidth: 4, strokeLinejoin: "round" }}
                          >
                            {shortLabel(node.entity.label, 10)}
                          </text>
                        </>
                      )}
                      <title>{kgTypeLabel(node.entity.entity_type)}：{node.entity.label}</title>
                    </g>
                  );
                })}
              </svg>
            </div>
          )}
        </div>

        <div className={cardClass("p-5")}>
          <h3 className="font-semibold">实体类型分布</h3>
          <div className="mt-4 space-y-2 text-sm">
            {kgEntityStats.length === 0 && <p className="text-muted">暂无实体统计。</p>}
            {kgEntityStats.map(([type, count]) => (
              <div key={type} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: kgEntityColors[type] || "#64748b" }} />
                  {kgTypeLabel(type)}
                </span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
          </div>
          <div className="mt-5 border-t border-border pt-4 text-sm">
            <h4 className="font-semibold">实体详情</h4>
            {!selectedKgEntity && <p className="mt-3 text-muted">点击图谱节点查看实体来源、属性和关联关系。</p>}
            {selectedKgEntity && (
              <div className="mt-3 space-y-3">
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="font-medium">{selectedKgEntity.label}</p>
                  <p className="mt-1 text-xs text-muted">
                    {kgTypeLabel(selectedKgEntity.entity_type)}
                    {selectedKgEntity.source_type ? ` · 来源 ${selectedKgEntity.source_type} #${selectedKgEntity.source_id}` : ""}
                  </p>
                  {selectedKgEntity.source_type === "note" && selectedKgEntity.source_id && (
                    <button
                      type="button"
                      onClick={() => {
                        const n = notes.find((item) => item.id === selectedKgEntity.source_id);
                        if (n) onNavigateNotes(n);
                      }}
                      className="mt-2 rounded-md border border-brand px-3 py-1 text-xs text-brand"
                    >
                      跳转笔记
                    </button>
                  )}
                  {selectedKgEntity.source_type === "file" && selectedKgEntity.source_id && (
                    <button type="button" onClick={onNavigateFiles} className="mt-2 rounded-md border border-brand px-3 py-1 text-xs text-brand">
                      查看资料库
                    </button>
                  )}
                </div>
                {Object.keys(selectedKgEntity.properties || {}).length > 0 && (
                  <pre className="max-h-32 overflow-auto rounded-md border border-border bg-surface px-3 py-2 text-xs text-muted">
                    {JSON.stringify(selectedKgEntity.properties, null, 2)}
                  </pre>
                )}
                <div className="max-h-44 space-y-2 overflow-auto">
                  {selectedKgEntityRelations.length === 0 && <p className="text-xs text-muted">暂无关联关系。</p>}
                  {selectedKgEntityRelations.map((rel) => {
                    const source = kgEntityById.get(rel.source_entity_id);
                    const target = kgEntityById.get(rel.target_entity_id);
                    return (
                      <div key={rel.id} className="rounded-md border border-border px-3 py-2 text-xs">
                        <p className="font-medium">{source?.label || rel.source_entity_id} → {target?.label || rel.target_entity_id}</p>
                        <p className="mt-1 text-muted">{kgRelationLabel(rel.relation_type)} · 置信度 {rel.confidence.toFixed(2)}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Extraction Entry + Relation List */}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className={cardClass("p-5")}>
          <h3 className="font-semibold">笔记抽取入口</h3>
          <div className="mt-4 max-h-72 space-y-2 overflow-auto">
            {notes.length === 0 && <p className="text-sm text-muted">当前项目还没有实验笔记。</p>}
            {notes.map((note) => (
              <div key={note.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
                <button type="button" onClick={() => onNavigateNotes(note)} className="min-w-0 text-left">
                  <span className="block truncate font-medium">{note.title}</span>
                  <span className="mt-1 block text-xs text-muted">{note.experiment_type} · {statusText[note.status] || note.status}</span>
                </button>
                {canWriteSelectedProject && (
                  <button
                    type="button"
                    disabled={kgBusy}
                    onClick={() => onExtractNote(note)}
                    className="shrink-0 rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    抽取
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className={cardClass("p-5")}>
          <h3 className="font-semibold">关系明细</h3>
          <div className="mt-4 max-h-72 space-y-2 overflow-auto text-sm">
            {filteredKgRelations.length === 0 && <p className="text-muted">暂无关系数据。</p>}
            {filteredKgRelations.slice(0, 80).map((rel) => {
              const source = kgEntityById.get(rel.source_entity_id);
              const target = kgEntityById.get(rel.target_entity_id);
              return (
                <div key={rel.id} className="rounded-md border border-border px-3 py-2">
                  <p className="font-medium">{source?.label || rel.source_entity_id} → {target?.label || rel.target_entity_id}</p>
                  <p className="mt-1 text-xs text-muted">{kgRelationLabel(rel.relation_type)} · 置信度 {rel.confidence.toFixed(2)}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
