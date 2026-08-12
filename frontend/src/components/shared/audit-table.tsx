"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { auditActionText } from "@/components/constants";
import type { AuditLog, User } from "@/lib/api";

interface AuditTableProps {
  logs: AuditLog[];
  /** 可选：有用户字典时显示用户名，否则退化为 #用户ID（如项目设置页无全量用户列表）。 */
  usersById?: Map<number, User>;
  /** 管理员需要保留动作代码筛选线索，项目成员只看业务化文案。 */
  showTechnicalCode?: boolean;
}

const targetTypeText: Record<string, string> = {
  file: "文件",
  file_ocr_result: "OCR 结果",
  note: "实验笔记",
  project: "项目",
  user: "用户",
  group: "小组",
};

const detailKeyText: Record<string, string> = {
  character_count: "识别字符数",
  corrected_character_count: "校对字符数",
  extraction_method: "识别方式",
  ocr_result_id: "OCR 结果",
  review_status: "审核状态",
  truncated: "是否截断",
  extracted_entities: "实体数",
  extracted_relations: "关系数",
  completed_cases: "完成用例数",
  failed_cases: "失败用例数",
  source_note_count: "来源笔记数",
  task_type: "任务类型",
  fallback_reason: "备用原因",
  graph_context_count: "图谱依据数",
  chunk_count: "文档片段数",
  embedding_model: "向量模型",
  generation_model: "生成模型",
};

function friendlyValue(key: string, value: unknown): string {
  if (key === "truncated") return value ? "是" : "否";
  if (key === "review_status") {
    return { pending_review: "待人工确认", confirmed: "已确认" }[String(value)] || String(value);
  }
  if (key === "extraction_method") return "图片文字识别";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function summarizeDetail(action: string, detail: Record<string, unknown> | null | undefined): string {
  if (!detail || Object.keys(detail).length === 0) {
    return auditActionText[action] || "已完成操作";
  }
  if (action === "extract_file_text" && typeof detail.character_count === "number") {
    return `已提取 ${detail.character_count} 个字符，等待人工确认`;
  }
  if (action === "confirm_file_ocr" && typeof detail.corrected_character_count === "number") {
    return `已确认 OCR 校对，共 ${detail.corrected_character_count} 个字符`;
  }
  if (action === "extract_note_kg" || action === "auto_extract_note_kg") {
    const entityCount = detail.extracted_entities;
    const relationCount = detail.extracted_relations;
    if (typeof entityCount === "number" || typeof relationCount === "number") {
      return `已提取 ${entityCount ?? 0} 个实体、${relationCount ?? 0} 条关系`;
    }
  }
  if (action === "run_rag_experiment" && (typeof detail.completed_cases === "number" || typeof detail.failed_cases === "number")) {
    return `已完成 ${detail.completed_cases ?? 0} 个问答用例，失败 ${detail.failed_cases ?? 0} 个`;
  }
  if (action === "generate_agent_output" && typeof detail.source_note_count === "number") {
    return `已生成实验报告，引用 ${detail.source_note_count} 条实验笔记`;
  }
  if (action === "query_local_rag" && typeof detail.graph_context_count === "number") {
    return `已完成一次知识库问答，使用 ${detail.graph_context_count} 条图谱依据`;
  }
  if (action === "index_rag_document" && typeof detail.chunk_count === "number") {
    return `已将资料加入知识库，拆分为 ${detail.chunk_count} 个文档片段`;
  }
  if (action === "init_local_rag") {
    return "已初始化本地知识库";
  }
  const entries = Object.entries(detail).slice(0, 2).map(([key, value]) => {
    const text = friendlyValue(key, value);
    return `${detailKeyText[key] || key}：${text.length > 24 ? `${text.slice(0, 24)}…` : text}`;
  });
  return entries.join("；");
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

/**
 * 共享审计日志表格（全局审计页与项目设置页复用）。
 * E2E 依赖：动作原代码必须以独立 <code> 节点渲染（getByText 精确匹配）。
 */
export function AuditTable({ logs, usersById, showTechnicalCode = true }: AuditTableProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleDetail = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" aria-label="展开详情" />
            <TableHead>时间</TableHead>
            <TableHead>操作人</TableHead>
            <TableHead>动作</TableHead>
            <TableHead>目标</TableHead>
            <TableHead>项目</TableHead>
            <TableHead>详情摘要</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {logs.map((log) => {
            const expanded = expandedIds.has(log.id);
            const actionLabel = auditActionText[log.action] || "其他操作";
            const detailEntries = Object.entries(log.detail_json || {});
            return (
              <Fragment key={log.id}>
                <TableRow>
                  <TableCell className="px-2">
                    <button
                      type="button"
                      aria-label={expanded ? `收起详情 ${log.id}` : `展开详情 ${log.id}`}
                      aria-expanded={expanded}
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => toggleDetail(log.id)}
                    >
                      {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{formatTime(log.created_at)}</TableCell>
                  <TableCell>
                    {log.actor_user_id
                      ? usersById?.get(log.actor_user_id)?.username || `#${log.actor_user_id}`
                      : "系统"}
                  </TableCell>
                  <TableCell>
                    <div>
                      <p className="text-sm">{actionLabel}</p>
                      {showTechnicalCode && <p className="text-[10px] text-muted-foreground">记录类型：<code>{log.action}</code></p>}
                    </div>
                  </TableCell>
                  <TableCell>
                    {targetTypeText[log.target_type || ""] || log.target_type || "-"}
                    {log.target_id ? ` #${log.target_id}` : ""}
                  </TableCell>
                  <TableCell>{log.project_id ? `#${log.project_id}` : "-"}</TableCell>
                  <TableCell className="max-w-72 truncate text-muted-foreground" title={JSON.stringify(log.detail_json)}>
                    {summarizeDetail(log.action, log.detail_json)}
                  </TableCell>
                </TableRow>
                {expanded && (
                  <TableRow>
                    <TableCell />
                    <TableCell colSpan={6}>
                      <div className="space-y-3 rounded-md bg-muted/30 p-3 text-sm">
                        <div>
                          <p className="text-xs text-muted-foreground">这次操作</p>
                          <p className="mt-1">{summarizeDetail(log.action, log.detail_json)}</p>
                        </div>
                        {detailEntries.length > 0 && (
                          <div className="grid gap-2 sm:grid-cols-2">
                            {detailEntries.map(([key, value]) => (
                              <div key={key} className="rounded border bg-background px-3 py-2">
                                <p className="text-xs text-muted-foreground">{detailKeyText[key] || key}</p>
                                <p className="mt-1 break-words">{friendlyValue(key, value)}</p>
                              </div>
                            ))}
                          </div>
                        )}
                        <details>
                          <summary className="cursor-pointer text-xs text-muted-foreground">查看原始记录（高级）</summary>
                          <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-background p-3 text-xs">
                            {JSON.stringify(log.detail_json, null, 2)}
                          </pre>
                        </details>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
