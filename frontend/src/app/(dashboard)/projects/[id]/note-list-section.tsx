"use client";

import { FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { PagePagination } from "@/components/shared/page-pagination";
import { statusText } from "@/components/constants";
import { handleCardKeyDown } from "@/lib/utils";

export type NoteListNote = {
  id: number;
  template_id: number | null;
  title: string;
  experiment_type: string;
  experiment_date: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

interface NoteListSectionProps {
  notes: NoteListNote[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
  onSelectNote: (note: NoteListNote) => void;
}

// 状态徽章语义色映射：approved=success、submitted=info、returned=warning、
// voided=destructive、draft=灰（secondary），其余状态回退 outline。
const statusBadgeVariant: Record<string, "success" | "info" | "warning" | "destructive" | "secondary" | "outline"> = {
  approved: "success",
  submitted: "info",
  returned: "warning",
  voided: "destructive",
  draft: "secondary",
};

const NOTES_PER_PAGE = 10;

export function NoteListSection({
  notes,
  total,
  page,
  onPageChange,
  onSelectNote,
}: NoteListSectionProps) {
  const totalPages = Math.max(1, Math.ceil(total / NOTES_PER_PAGE));
  const rangeStart = total === 0 ? 0 : page * NOTES_PER_PAGE + 1;
  const rangeEnd = Math.min((page + 1) * NOTES_PER_PAGE, total);

  return (
    <>
      {/* 列表信息 */}
      <p className="text-sm text-muted-foreground">
        {total > 0
          ? `第 ${rangeStart}-${rangeEnd} 条，共 ${total} 条`
          : "暂无笔记"}
      </p>

      {notes.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={total === 0 ? "暂无笔记" : "没有匹配的笔记"}
          description={total === 0 ? "点击右上角「新建笔记」开启第一条实验记录" : "尝试调整筛选状态或清空关键词搜索"}
        />
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <Card
              key={note.id}
              role="button"
              tabIndex={0}
              className="group cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover border-border/75 hover:border-primary/40 bg-card"
              onClick={() => onSelectNote(note)}
              onKeyDown={(e) =>
                handleCardKeyDown(e, () => onSelectNote(note))
              }
            >
              <CardHeader className="p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <CardTitle className="text-base font-semibold group-hover:text-primary transition-colors">
                        {note.title}
                      </CardTitle>
                      <Badge variant="outline" className="text-[11px] font-normal py-0 h-5 text-muted-foreground border-border/60">
                        {note.experiment_type}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>实验日期: {note.experiment_date || "—"}</span>
                      <span>·</span>
                      <span>更新于 {new Date(note.updated_at).toLocaleDateString("zh-CN")}</span>
                    </div>
                  </div>
                  <Badge variant={statusBadgeVariant[note.status] || "outline"} className="shrink-0">
                    {statusText[note.status] || note.status}
                  </Badge>
                </div>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      {/* 分页控件 */}
      {total > NOTES_PER_PAGE && (
        <PagePagination
          startItem={rangeStart}
          endItem={rangeEnd}
          total={total}
          hasPrev={page > 0}
          hasNext={page < totalPages - 1}
          onPrev={() => onPageChange(page - 1)}
          onNext={() => onPageChange(page + 1)}
          pageInfo={`第 ${page + 1} / ${totalPages} 页`}
          separator="-"
          className="border-t pt-4"
        />
      )}
    </>
  );
}
