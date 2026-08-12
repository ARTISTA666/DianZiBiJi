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
        />
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <Card
              key={note.id}
              role="button"
              tabIndex={0}
              className="cursor-pointer transition-shadow hover:shadow-sm"
              onClick={() => onSelectNote(note)}
              onKeyDown={(e) =>
                handleCardKeyDown(e, () => onSelectNote(note))
              }
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <CardTitle className="text-base">{note.title}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {note.experiment_type} · {note.experiment_date || "—"}
                    </p>
                  </div>
                  <Badge variant={statusBadgeVariant[note.status] || "outline"}>
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
