import { ragModeText, type RagGraphContextItem, type RagSource } from "./citations";

/** AI 问答页的一轮对话记录（导出与追问建议共用）。 */
export type AiConversationEntry = {
  question: string;
  result: {
    answer: string;
    rag_mode: string;
    response_ms: number | null;
    sources: RagSource[];
    graph_context: RagGraphContextItem[];
  };
};

/**
 * 根据最近一轮回答的来源与图谱上下文生成 2-3 个追问建议。
 * 纯函数：便于独立测试，不依赖任何页面状态。
 */
export function suggestFollowUps(
  lastQuestion: string,
  sources: RagSource[],
  graphContext: RagGraphContextItem[],
): string[] {
  const suggestions: string[] = [];
  // 基于来源文件名建议深入
  const filename = sources[0]?.filename;
  if (filename) suggestions.push(`关于 ${filename} 还有哪些细节？`);
  // 基于图谱上下文建议关联查询
  const relation = graphContext[0];
  if (relation && relation.source_label && relation.target_label) {
    suggestions.push(`与 ${relation.source_label} 和 ${relation.target_label} 有什么关联？`);
  }
  // 通用建议
  suggestions.push("请总结以上问题的关键要点");
  return suggestions.slice(0, 3);
}

/** 将当前对话导出为 Markdown 文件（纯函数：构建内容并触发浏览器下载）。 */
export function exportConversation(
  conversation: AiConversationEntry[],
  projectName: string,
) {
  if (typeof window === "undefined") return;
  const lines: string[] = [`# ${projectName} — AI 问答记录`, ``, `导出时间：${new Date().toLocaleString("zh-CN")}`, ``];
  conversation.forEach((entry, i) => {
    lines.push(`## 问题 ${i + 1}`);
    lines.push(``);
    lines.push(entry.question);
    lines.push(``);
    lines.push(`### 回答（${ragModeText[entry.result.rag_mode] || entry.result.rag_mode}，${entry.result.response_ms ?? "—"} ms）`);
    lines.push(``);
    lines.push(entry.result.answer);
    lines.push(``);
    if (entry.result.sources.length > 0) {
      lines.push(`**来源：**`);
      entry.result.sources.forEach((source, j) => {
        lines.push(`- [S${j + 1}] ${source.filename || "未知文件"}（相关度 ${source.retrieval_score?.toFixed(3) ?? "—"}）`);
      });
      lines.push(``);
    }
    lines.push(`---`);
    lines.push(``);
  });
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${projectName}-AI问答-${new Date().toISOString().slice(0, 10)}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
