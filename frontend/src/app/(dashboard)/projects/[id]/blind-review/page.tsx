"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, ClipboardCheck, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore } from "@/stores";
import {
  evaluateBlindReviewItem,
  getBlindReviewBatches,
  getBlindReviewItems,
  type BlindReviewBatch,
  type BlindReviewItem,
} from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

type ReviewDraft = {
  score: string;
  accurate: string;
  traceable: string;
  comment: string;
};

const emptyDraft: ReviewDraft = {
  score: "",
  accurate: "",
  traceable: "",
  comment: "",
};

export default function BlindReviewPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((state) => state.token);
  const requestEpoch = useRef(0);
  const [batches, setBatches] = useState<BlindReviewBatch[]>([]);
  const [batchId, setBatchId] = useState("");
  const [items, setItems] = useState<BlindReviewItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [busy, setBusy] = useState(true);
  const [submitting, setSubmitting] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;
    setError("");
    getBlindReviewBatches(token, projectId)
      .then((nextBatches) => {
        if (!active) return;
        setBatches(nextBatches);
        setBatchId((current) => current || nextBatches[0]?.batch_id || "");
        if (nextBatches.length === 0) setBusy(false);
      })
      .catch((cause) => {
        if (!active) return;
        setError(getErrorMessage(cause, "盲评批次加载失败"));
        setBusy(false);
      });
    return () => { active = false; };
  }, [token, projectId]);

  useEffect(() => {
    if (!token || !batchId) return;
    const epoch = ++requestEpoch.current;
    setBusy(true);
    setError("");
    setMessage("");
    getBlindReviewItems(token, projectId, { batch_id: batchId })
      .then((nextItems) => {
        if (epoch !== requestEpoch.current) return;
        setItems(nextItems);
        setDrafts(Object.fromEntries(nextItems.map((item) => [
          item.blind_id,
          item.evaluation
            ? {
                score: String(item.evaluation.score),
                accurate: String(item.evaluation.is_accurate),
                traceable: String(item.evaluation.is_traceable),
                comment: item.evaluation.comment || "",
              }
            : { ...emptyDraft },
        ])));
      })
      .catch((cause) => {
        if (epoch === requestEpoch.current) {
          setError(getErrorMessage(cause, "盲评题目加载失败"));
          setItems([]);
        }
      })
      .finally(() => {
        if (epoch === requestEpoch.current) setBusy(false);
      });
  }, [token, projectId, batchId]);

  const updateDraft = (blindId: string, patch: Partial<ReviewDraft>) => {
    setDrafts((current) => ({
      ...current,
      [blindId]: { ...(current[blindId] || emptyDraft), ...patch },
    }));
  };

  const submitReview = async (item: BlindReviewItem) => {
    if (!token || item.evaluation || submitting) return;
    const draft = drafts[item.blind_id] || emptyDraft;
    if (!draft.score || !draft.accurate || !draft.traceable) {
      setError("请完成评分、准确性和可追溯性判断后再提交");
      return;
    }
    setSubmitting(item.blind_id);
    setError("");
    setMessage("");
    try {
      const evaluation = await evaluateBlindReviewItem(token, projectId, item.blind_id, {
        score: Number(draft.score),
        is_accurate: draft.accurate === "true",
        is_traceable: draft.traceable === "true",
        comment: draft.comment.trim() || null,
      });
      setItems((current) => current.map((candidate) => (
        candidate.blind_id === item.blind_id ? { ...candidate, evaluation } : candidate
      )));
      const nextBatches = await getBlindReviewBatches(token, projectId);
      setBatches(nextBatches);
      setMessage(`盲评 ${item.blind_id} 已保存`);
    } catch (cause) {
      setError(getErrorMessage(cause, "盲评提交失败"));
    } finally {
      setSubmitting("");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-md border border-blue-200 bg-blue-50 p-4 text-blue-900">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <h2 className="font-semibold">独立人工盲评</h2>
          <p className="mt-1 text-sm">正式评审前必须先冻结题集、语料和评分规则。当前页面隐藏方法名称、模型和原始日志标识。</p>
        </div>
      </div>

      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}
      {message && <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700">{message}</p>}

      <Card>
        <CardContent className="grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div className="space-y-2">
            <Label htmlFor="blind-review-batch">盲评批次</Label>
            <Select
              value={batchId || "__none_batch__"}
              onValueChange={(v) => setBatchId(v === "__none_batch__" ? "" : v)}
              disabled={batches.length === 0}
            >
              <SelectTrigger id="blind-review-batch">
                <SelectValue placeholder="暂无可评批次" />
              </SelectTrigger>
              <SelectContent>
                {batches.length === 0 && <SelectItem value="__none_batch__">暂无可评批次</SelectItem>}
                {batches.map((batch) => (
                  <SelectItem key={batch.batch_id} value={batch.batch_id}>
                    {batch.batch_id}（{batch.completed_items}/{batch.total_items}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Badge variant="outline" className="h-8 px-3">
            {items.filter((item) => item.evaluation).length}/{items.length} 已完成
          </Badge>
        </CardContent>
      </Card>

      {busy ? (
        <p className="py-8 text-center text-sm text-muted-foreground">加载盲评题目...</p>
      ) : items.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-sm text-muted-foreground">当前批次暂无可评题目</CardContent>
        </Card>
      ) : (
        items.map((item) => {
          const draft = drafts[item.blind_id] || emptyDraft;
          const completed = item.evaluation !== null;
          return (
            <Card key={item.blind_id} data-testid={`blind-review-${item.blind_id}`}>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ClipboardCheck className="h-4 w-4" />{item.blind_id}
                  </CardTitle>
                  {completed && <Badge className="bg-green-600"><CheckCircle2 className="mr-1 h-3 w-3" />已提交</Badge>}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">问题</p>
                  <p className="mt-1 text-sm">{item.question}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">匿名回答</p>
                  <p className="mt-1 whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm">{item.answer || "（无回答）"}</p>
                </div>
                {item.evidence.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">匿名证据</p>
                    <div className="mt-1 space-y-2">
                      {item.evidence.map((evidence) => (
                        <p key={evidence.evidence_id} className="rounded-md border p-2 text-sm">
                          <span className="mr-2 font-mono text-xs text-muted-foreground">{evidence.evidence_id}</span>
                          {evidence.content}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor={`${item.blind_id}-score`}>{item.blind_id} 评分</Label>
                    <Select
                      value={draft.score || "__none_score__"}
                      disabled={completed}
                      onValueChange={(v) => updateDraft(item.blind_id, { score: v === "__none_score__" ? "" : v })}
                    >
                      <SelectTrigger id={`${item.blind_id}-score`}><SelectValue placeholder="请选择" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none_score__">请选择</SelectItem>
                        {[1, 2, 3, 4, 5].map((score) => <SelectItem key={score} value={String(score)}>{score}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`${item.blind_id}-accurate`}>{item.blind_id} 准确性</Label>
                    <Select
                      value={draft.accurate || "__none_accurate__"}
                      disabled={completed}
                      onValueChange={(v) => updateDraft(item.blind_id, { accurate: v === "__none_accurate__" ? "" : v })}
                    >
                      <SelectTrigger id={`${item.blind_id}-accurate`}><SelectValue placeholder="请选择" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none_accurate__">请选择</SelectItem>
                        <SelectItem value="true">准确</SelectItem>
                        <SelectItem value="false">不准确</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`${item.blind_id}-traceable`}>{item.blind_id} 可追溯性</Label>
                    <Select
                      value={draft.traceable || "__none_traceable__"}
                      disabled={completed}
                      onValueChange={(v) => updateDraft(item.blind_id, { traceable: v === "__none_traceable__" ? "" : v })}
                    >
                      <SelectTrigger id={`${item.blind_id}-traceable`}><SelectValue placeholder="请选择" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none_traceable__">请选择</SelectItem>
                        <SelectItem value="true">可追溯</SelectItem>
                        <SelectItem value="false">不可追溯</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`${item.blind_id}-comment`}>{item.blind_id} 评价备注</Label>
                  <Textarea id={`${item.blind_id}-comment`} rows={2} value={draft.comment} disabled={completed}
                    onChange={(event) => updateDraft(item.blind_id, { comment: event.target.value })} />
                </div>
                {!completed && (
                  <Button onClick={() => submitReview(item)} disabled={submitting === item.blind_id}>
                    {submitting === item.blind_id ? "提交中..." : "提交并继续"}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}
