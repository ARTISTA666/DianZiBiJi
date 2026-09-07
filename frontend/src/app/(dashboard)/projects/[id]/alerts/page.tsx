"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { listProjectAlerts, type ProjectAlertInbox } from "@/lib/api";
import { ProjectAlertsPanel } from "@/components/project-alerts";

export default function AlertsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const members = useProjectStore((s) => s.members);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const [inbox, setInbox] = useState<ProjectAlertInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const membership = members.find((member) => member.user_id === user?.id);
  const isOwner = selectedProject?.owner_user_id === user?.id;
  const canManage =
    user?.role === "super_admin" ||
    isOwner ||
    membership?.can_manage === true ||
    membership?.project_role === "owner";

  const load = async () => {
    if (!token) return;
    setError("");
    try {
      const data = await listProjectAlerts(token, projectId);
      setInbox(data);
    } catch (e) {
      setError(getErrorMessage(e, "预警加载失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, projectId]);

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
          {error}
        </div>
      )}
      <ProjectAlertsPanel
        projectId={projectId}
        token={token ?? ""}
        canManage={canManage}
        inbox={inbox}
        loading={loading}
        onRefresh={load}
      />
    </div>
  );
}
