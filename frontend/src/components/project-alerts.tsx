"use client";

import { useState } from "react";
import { AlertTriangle, BellRing, Check, Loader2, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { getErrorMessage } from "@/lib/utils";
import {
  acknowledgeProjectAlert,
  evaluateProjectAlerts,
  upsertProjectAlertThreshold,
  ALERT_METRIC_TEXT,
  type ProjectAlertInbox,
} from "@/lib/api";

const DEFAULT_THRESHOLDS: Record<string, { warn: number; critical: number }> = {
  review_stall_hours: { warn: 72, critical: 168 },
  return_rate: { warn: 0.3, critical: 0.5 },
  blueprint_stagnant_days: { warn: 14, critical: 30 },
  progress_deviation: { warn: 0.7, critical: 0.9 },
};

const METRIC_UNIT: Record<string, string> = {
  review_stall_hours: "小时",
  return_rate: "占比",
  blueprint_stagnant_days: "天",
  progress_deviation: "占比",
};

function formatValue(metric: string, value: number): string {
  if (metric === "return_rate" || metric === "progress_deviation") {
    return `${Math.round(value * 100)}%`;
  }
  return `${Math.round(value * 10) / 10}`;
}

function levelBadge(level: string) {
  if (level === "critical") {
    return <Badge className="bg-red-100 text-red-700 hover:bg-red-100">紧急</Badge>;
  }
  return <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100">警告</Badge>;
}

export function ProjectAlertsPanel({
  projectId,
  token,
  canManage,
  inbox,
  loading,
  onRefresh,
}: {
  projectId: number;
  token: string;
  canManage: boolean;
  inbox: ProjectAlertInbox | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const feedback = useActionFeedback();
  const [evaluating, setEvaluating] = useState(false);
  const [ackingId, setAckingId] = useState<number | null>(null);
  const [ackNote, setAckNote] = useState("");
  const [showThresholds, setShowThresholds] = useState(false);
  const [thresholdBusy, setThresholdBusy] = useState<string | null>(null);

  const openAlerts = (inbox?.alerts || []).filter((a) => a.status === "open");
  const historyAlerts = (inbox?.alerts || []).filter((a) => a.status !== "open");

  const handleEvaluate = async () => {
    setEvaluating(true);
    try {
      const summary = await evaluateProjectAlerts(token, projectId);
      const firing = summary.metrics.filter((m) => m.level !== "none");
      feedback.success(firing.length > 0 ? `评估完成：${firing.length} 项指标触发预警` : "评估完成：各项指标正常");
      onRefresh();
    } catch (e) {
      feedback.error(getErrorMessage(e, "评估失败"));
    } finally {
      setEvaluating(false);
    }
  };

  const handleAcknowledge = async (alertId: number) => {
    setAckingId(alertId);
    try {
      await acknowledgeProjectAlert(token, projectId, alertId, {
        note: ackNote.trim() || undefined,
      });
      feedback.success("已确认该预警");
      setAckNote("");
      onRefresh();
    } catch (e) {
      feedback.error(getErrorMessage(e, "确认失败"));
    } finally {
      setAckingId(null);
    }
  };

  const handleThresholdSave = async (
    metric: string,
    warn: number,
    critical: number,
    enabled: boolean,
  ) => {
    setThresholdBusy(metric);
    try {
      await upsertProjectAlertThreshold(token, projectId, {
        metric,
        warn_threshold: warn,
        critical_threshold: critical,
        enabled,
      });
      feedback.success(`阈值已更新：${ALERT_METRIC_TEXT[metric] || metric}`);
      onRefresh();
    } catch (e) {
      feedback.error(getErrorMessage(e, "阈值更新失败"));
    } finally {
      setThresholdBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Card className="border-border/75 bg-card shadow-card">
        <CardHeader className="pb-3 border-b border-border/60 bg-muted/20">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <BellRing className="h-4 w-4" />
                预警收件箱
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                AI 自主推进 + 阈值触发报警 + 导师自主干预——不做每步审核，只在指标越界时提醒
              </p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowThresholds((v) => !v)} disabled={!canManage}>
                <Settings2 className="mr-2 h-3.5 w-3.5" />
                {showThresholds ? "收起阈值" : "调整阈值"}
              </Button>
              <Button size="sm" onClick={handleEvaluate} disabled={evaluating}>
                {evaluating ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <BellRing className="mr-2 h-3.5 w-3.5" />}
                立即评估
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {openAlerts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              当前没有待处理预警。点击「立即评估」按当前阈值重新计算四项指标。
            </p>
          ) : (
            <div className="space-y-2">
              {openAlerts.map((alert) => (
                <div key={alert.id} className="rounded-lg border border-border/70 bg-muted/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {levelBadge(alert.level)}
                      <span className="text-sm font-medium">
                        {ALERT_METRIC_TEXT[alert.metric] || alert.metric}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        当前值 {formatValue(alert.metric, alert.metric_value)}
                        {METRIC_UNIT[alert.metric] ? `（${METRIC_UNIT[alert.metric]}）` : ""}
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {new Date(alert.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{alert.detail}</p>
                  {canManage && (
                    <div className="mt-2 flex items-center gap-2">
                      <Input
                        aria-label="确认备注"
                        value={ackNote}
                        onChange={(e) => setAckNote(e.target.value)}
                        placeholder="确认备注（可选，如：已线下提醒学生）"
                        className="h-8 flex-1 text-xs"
                      />
                      <Button
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => handleAcknowledge(alert.id)}
                        disabled={ackingId === alert.id}
                      >
                        {ackingId === alert.id ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <Check className="mr-1 h-3 w-3" />
                        )}
                        确认
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {showThresholds && canManage && (
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">阈值调整（warn ≤ critical）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(inbox?.thresholds.length ? inbox.thresholds : []).map((t) => (
              <ThresholdRow
                key={t.id}
                metric={t.metric}
                warn={t.warn_threshold}
                critical={t.critical_threshold}
                enabled={t.enabled}
                busy={thresholdBusy === t.metric}
                onSave={handleThresholdSave}
              />
            ))}
            {["review_stall_hours", "return_rate", "blueprint_stagnant_days", "progress_deviation"]
              .filter((m) => !(inbox?.thresholds || []).some((t) => t.metric === m))
              .map((metric) => (
                <ThresholdRow
                  key={metric}
                  metric={metric}
                  warn={DEFAULT_THRESHOLDS[metric]?.warn ?? 1}
                  critical={DEFAULT_THRESHOLDS[metric]?.critical ?? 2}
                  enabled
                  busy={thresholdBusy === metric}
                  onSave={handleThresholdSave}
                />
              ))}
            <p className="text-[11px] text-muted-foreground">
              每次调整都写入审计日志；指标回落到正常区间后，对应 open 预警自动转为 resolved。
            </p>
          </CardContent>
        </Card>
      )}

      {historyAlerts.length > 0 && (
        <Card className="border-border/75 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">历史预警</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {historyAlerts.map((alert) => (
              <div key={alert.id} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="py-0 text-[10px] font-normal">
                    {alert.status === "acknowledged" ? "已确认" : "已自动回落"}
                  </Badge>
                  <span>{ALERT_METRIC_TEXT[alert.metric] || alert.metric}</span>
                  <span className="text-muted-foreground">{formatValue(alert.metric, alert.metric_value)}</span>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {new Date(alert.acknowledged_at ?? alert.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ThresholdRow({
  metric,
  warn,
  critical,
  enabled,
  busy,
  onSave,
}: {
  metric: string;
  warn: number;
  critical: number;
  enabled: boolean;
  busy: boolean;
  onSave: (metric: string, warn: number, critical: number, enabled: boolean) => void;
}) {
  const [warnValue, setWarnValue] = useState(String(warn));
  const [criticalValue, setCriticalValue] = useState(String(critical));
  const [isEnabled, setIsEnabled] = useState(enabled);
  const warnNum = Number(warnValue);
  const criticalNum = Number(criticalValue);
  const valid = Number.isFinite(warnNum) && Number.isFinite(criticalNum) && warnNum >= 0 && criticalNum >= warnNum;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/60 bg-muted/10 p-2">
      <span className="flex min-w-28 items-center gap-1 text-xs font-medium">
        <AlertTriangle className="h-3 w-3 text-muted-foreground" />
        {ALERT_METRIC_TEXT[metric] || metric}
      </span>
      <div className="flex items-center gap-1">
        <Label className="text-[11px] text-muted-foreground">警告</Label>
        <Input
          aria-label={`${metric} 警告阈值`}
          value={warnValue}
          onChange={(e) => setWarnValue(e.target.value)}
          className="h-7 w-24 text-xs"
        />
      </div>
      <div className="flex items-center gap-1">
        <Label className="text-[11px] text-muted-foreground">紧急</Label>
        <Input
          aria-label={`${metric} 紧急阈值`}
          value={criticalValue}
          onChange={(e) => setCriticalValue(e.target.value)}
          className="h-7 w-24 text-xs"
        />
      </div>
      <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={isEnabled}
          onChange={(e) => setIsEnabled(e.target.checked)}
          className="h-3 w-3"
        />
        启用
      </label>
      <Button
        size="sm"
        variant="outline"
        className="ml-auto h-7 text-xs"
        disabled={!valid || busy}
        onClick={() => onSave(metric, warnNum, criticalNum, isEnabled)}
      >
        {busy ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
        保存
      </Button>
    </div>
  );
}
