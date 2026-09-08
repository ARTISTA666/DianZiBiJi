import Link from "next/link";
import React, { type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { RagQueryResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

export type RagSource = RagQueryResponse["sources"][number];
export type RagGraphContextItem = RagQueryResponse["graph_context"][number];

export const ragModeText: Record<string, string> = {
  auto: "自动选择",
  project_rag: "项目级 RAG",
  kg_enhanced_rag: "图谱增强 RAG",
  structured_query: "结构化查询",
  pure_llm: "纯 LLM",
  bm25_rag: "BM25 RAG",
};

// 正则提升至模块作用域的源字符串，避免每次渲染重新构造 RegExp 对象。
const CITATION_SOURCE = String.raw`\[(S|G)(\d+)\]`;
const CITATION_REGEX = () => new RegExp(CITATION_SOURCE, "gi");

export function snippetPreview(text: string | null | undefined, limit = 120): string {
  if (!text) return "";
  const trimmed = text.trim();
  return trimmed.length > limit ? `${trimmed.slice(0, limit)}…` : trimmed;
}

export function formatRetrievalScore(score: number | null | undefined): string {
  return typeof score === "number" ? score.toFixed(3) : "—";
}

function Tooltip({ children }: { children: ReactNode }) {
  return (
    <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 hidden w-64 -translate-x-1/2 rounded-md border bg-popover p-2 text-left text-xs font-normal normal-case leading-relaxed text-popover-foreground shadow-md group-hover:block">
      {children}
    </span>
  );
}

function SourceCitationChipInner({
  marker,
  source,
  projectId,
}: {
  marker: string;
  source: RagSource;
  projectId: number;
}) {
  const href = source.file_id
    ? `/projects/${projectId}/data#file-${source.file_id}`
    : `/projects/${projectId}/data`;
  return (
    <span className="group relative inline-block align-baseline">
      <Link
        href={href}
        title="点击跳转到资料页"
        className="mx-0.5 inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-1.5 text-xs font-medium text-primary no-underline hover:bg-primary/20"
      >
        {marker}
      </Link>
      <Tooltip>
        <span className="block font-medium">{source.filename || "未知文件"}</span>
        {source.snippet && (
          <span className="mt-1 block break-words text-muted-foreground">
            {snippetPreview(source.snippet)}
          </span>
        )}
        <span className="mt-1 block text-muted-foreground">
          相关度 {formatRetrievalScore(source.retrieval_score)}
        </span>
      </Tooltip>
    </span>
  );
}
const SourceCitationChip = React.memo(SourceCitationChipInner);

function GraphCitationChipInner({ marker, context }: { marker: string; context: RagGraphContextItem }) {
  return (
    <span className="group relative inline-block align-baseline">
      <span className="mx-0.5 inline-flex cursor-help items-center rounded-full border border-emerald-600/30 bg-emerald-600/10 px-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
        {marker}
      </span>
      <Tooltip>
        <span className="block break-words">
          {context.source_label} → {context.relation_label} → {context.target_label}
        </span>
        <span className="mt-1 block text-muted-foreground">
          置信度 {context.confidence.toFixed(2)}
        </span>
      </Tooltip>
    </span>
  );
}
const GraphCitationChip = React.memo(GraphCitationChipInner);

/**
 * 将回答文本按 [S#] / [G#] 引用标记切分为文本段与引用 chip。
 * 编号规则与后端 backend/src/rag.rs 的 format_sources / format_graph_context 一致：
 * [S1] 对应 sources[0]，[G1] 对应 graph_context[0]（均为 1 起）。
 * 越界或非法编号降级为普通文本。
 */
export function CitationRichText({
  answer,
  sources,
  graphContext,
  projectId,
}: {
  answer: string;
  sources: RagSource[];
  graphContext: RagGraphContextItem[];
  projectId: number;
}) {
  const segments: ReactNode[] = [];
  const pattern = CITATION_REGEX();
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(answer)) !== null) {
    if (match.index > lastIndex) {
      segments.push(answer.slice(lastIndex, match.index));
    }
    const kind = match[1].toUpperCase();
    const index = Number(match[2]) - 1;
    const marker = `${kind}${match[2]}`;
    if (kind === "S" && index >= 0 && index < sources.length) {
      segments.push(
        <SourceCitationChip key={`c-${key++}`} marker={marker} source={sources[index]} projectId={projectId} />,
      );
    } else if (kind === "G" && index >= 0 && index < graphContext.length) {
      segments.push(
        <GraphCitationChip key={`c-${key++}`} marker={marker} context={graphContext[index]} />,
      );
    } else {
      segments.push(match[0]);
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < answer.length) {
    segments.push(answer.slice(lastIndex));
  }
  return <>{segments}</>;
}

/** 来源列表：文件名 + 片段摘要 + 相关度，点击跳转资料页。 */
export function RagSourceList({ sources, projectId }: { sources: RagSource[]; projectId: number }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3 border-t pt-3">
      <p className="mb-1 text-xs text-muted-foreground">来源：</p>
      <div className="space-y-1.5">
        {sources.map((src, i) => (
          <Link
            key={src.file_id ?? `s${i}`}
            href={src.file_id ? `/projects/${projectId}/data#file-${src.file_id}` : `/projects/${projectId}/data`}
            className="block rounded-md border p-2 text-xs no-underline hover:bg-muted/60"
          >
            <p className="font-medium text-foreground">
              [S{i + 1}] {src.filename || "未知文件"}
            </p>
            {src.snippet && (
              <p className="mt-0.5 text-muted-foreground">{snippetPreview(src.snippet)}</p>
            )}
            <p className="mt-0.5 text-muted-foreground">
              相关度 {formatRetrievalScore(src.retrieval_score)}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}

function formatCitationAuditBadge(audit: NonNullable<RagQueryResponse["citation_audit"]>): {
  label: string;
  tooltip: string;
} {
  if (audit.passed) {
    return {
      label: audit.citation_count > 0 ? `引用校验通过（${audit.citation_count} 个编号）` : "引用校验通过",
      tooltip: audit.message || `共核对 ${audit.citation_count} 个证据编号，全部有效。`,
    };
  }

  // 校验未通过时，拆分总体判定与明细两段，彻底杜绝“未通过：通过……”的自相矛盾文案
  const rawMessage = audit.message || "";
  const strippedMessage = rawMessage.replace(/^引用校验通过[，,]\s*/, "").trim();

  let detail = strippedMessage;
  if (rawMessage.includes("缺少强制引用")) {
    detail = "缺关键事实强制引用 → 降级 needs_review";
  } else if (audit.invalid_citations && audit.invalid_citations.length > 0) {
    detail = `${audit.invalid_citations.length} 处编号无效 → 降级 needs_review`;
  } else if (audit.has_evidence && audit.citation_count === 0) {
    detail = "未引用检索证据 → 降级 needs_review";
  }

  const prefix = audit.citation_count > 0 ? `${audit.citation_count} 个编号核对通过；` : "";
  const label = `${prefix}${detail}`;
  const tooltip = `总体判定：降级待复核 (needs_review)\n明细：${rawMessage || detail}`;

  return { label, tooltip };
}

/** 质量元信息行：模式、耗时、引用校验、降级原因。 */
export function RagMetaInfo({ result }: { result: RagQueryResponse }) {
  const audit = result.citation_audit;
  const noProjectEvidence = audit?.has_evidence === false;
  const noEvidenceLabel = result.rag_mode === "pure_llm"
    ? "无项目证据（纯 LLM）"
    : result.rag_mode === "structured_query"
      ? "未命中图谱证据"
      : "未命中项目证据";

  const auditBadge = audit ? (() => {
    if (noProjectEvidence) {
      return (
        <Badge variant="outline" className="font-normal" title={audit.message}>
          {noEvidenceLabel}
        </Badge>
      );
    }
    const { label, tooltip } = formatCitationAuditBadge(audit);
    return (
      <Badge
        variant={audit.passed ? "secondary" : "destructive"}
        className="font-normal"
        title={tooltip}
      >
        {label}
      </Badge>
    );
  })() : null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-2 text-xs text-muted-foreground">
      <Badge variant="outline" className="font-normal">
        {ragModeText[result.rag_mode] || result.rag_mode}
      </Badge>
      {result.response_ms !== null && <span>耗时 {result.response_ms} ms</span>}
      {auditBadge}
      {result.fallback_reason && (
        <span className="text-warning">降级：{result.fallback_reason}</span>
      )}
    </div>
  );
}

/** 完整回答块：富文本回答 + 来源列表 + 元信息。
 *  使用 React.memo 包装——每条对话条目是独立的，
 *  新增对话不会重渲染已有对话。 */
function RagAnswerBlockInner({
  result,
  projectId,
}: {
  result: RagQueryResponse;
  projectId: number;
}) {
  return (
    <div>
      <div className={cn("text-sm whitespace-pre-wrap")}>
        <CitationRichText
          answer={result.answer}
          sources={result.sources}
          graphContext={result.graph_context}
          projectId={projectId}
        />
      </div>
      <RagSourceList sources={result.sources} projectId={projectId} />
      <RagMetaInfo result={result} />
    </div>
  );
}
export const RagAnswerBlock = React.memo(RagAnswerBlockInner);
