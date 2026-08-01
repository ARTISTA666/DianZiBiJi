"use client";

import { KeyboardEvent } from "react";
import { FileText, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { statusText } from "@/components/constants";

export type NoteListNote = {
  id: number;
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
  searchQuery: string;
  serverNotesCount: number;
}

const NOTES_PER_PAGE = 10;

const handleCardKeyDown = (e: KeyboardEvent, callback: () => void) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    callback();
  }
};

export function NoteListSection({
  notes,
  total,
  page,
  onPageChange,
  onSelectNote,
  searchQuery,
  serverNotesCount,
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
        {searchQuery.trim() && notes.length !== serverNotesCount && (
          <span>（筛选显示 {notes.length} 条）</span>
        )}
      </p>

      {notes.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center">
            <FileText className="mx-auto h-10 w-10 text-muted-foreground/50" />
            <p className="mt-3 text-sm text-muted-foreground">
              {total === 0 ? "暂无笔记" : "没有匹配的笔记"}
            </p>
          </CardContent>
        </Card>
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
                  <Badge
                    variant={
                      note.status === "approved"
                        ? "default"
                        : note.status === "submitted"
                        ? "secondary"
                        : "outline"
                    }
                  >
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
        <div className="flex items-center justify-between border-t pt-4">
          <p className="text-sm text-muted-foreground">
            第 {rangeStart}-{rangeEnd} 条，共 {total} 条
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              上一页
            </Button>
            <span className="text-sm text-muted-foreground">
              第 {page + 1} / {totalPages} 页
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => onPageChange(page + 1)}
            >
              下一页
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
