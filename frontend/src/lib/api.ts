const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export type CurrentUser = {
  id: number;
  username: string;
  display_name: string;
  role: string;
};

export type Project = {
  id: number;
  name: string;
  description: string | null;
  is_sensitive: boolean;
  status: string;
  approval_enabled: boolean;
  owner_user_id: number | null;
};

export type User = {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: string;
  status: string;
};

export type ProjectMember = {
  id: number;
  project_id: number;
  user_id: number;
  project_role: string;
  can_read: boolean;
  can_write: boolean;
  can_review: boolean;
  can_manage: boolean;
};

export type Group = {
  id: number;
  name: string;
  description: string | null;
  leader_user_id: number | null;
};

export type GroupMember = {
  id: number;
  group_id: number;
  user_id: number;
  group_role: string;
};

export type Template = {
  id: number;
  name: string;
  experiment_type: string;
  schema_json: { fields?: Array<{ key: string; label: string; type: string }> };
  default_content_json: Record<string, unknown>;
  is_active: boolean;
};

export type Note = {
  id: number;
  project_id: number;
  template_id: number | null;
  title: string;
  experiment_type: string;
  experiment_date: string | null;
  owner_user_id: number;
  status: string;
  current_version_id: number | null;
  created_at: string;
  updated_at: string;
};

export type NoteVersion = {
  id: number;
  note_id: number;
  version_number: number;
  fixed_fields_json: Record<string, string>;
  content_json: Record<string, unknown>;
  created_by: number;
  change_summary: string | null;
  is_locked: boolean;
  created_at: string;
};

export type NoteApproval = {
  id: number;
  note_id: number;
  version_id: number;
  reviewer_user_id: number;
  action: string;
  comment: string | null;
  created_at: string;
};

export type StoredFile = {
  id: number;
  project_id: number;
  note_id: number | null;
  uploaded_by: number;
  file_category: string;
  original_filename: string;
  mime_type: string | null;
  file_size: number;
  file_hash: string;
  status: string;
  knowledge_sync_status: string;
  knowledge_synced_at: string | null;
  knowledge_sync_message: string | null;
  created_at: string;
};

export type RagDataset = {
  id: number;
  project_id: number;
  dify_dataset_id: string;
  dify_dataset_name: string;
  status: string;
  created_by: number;
  created_at: string;
  updated_at: string;
};

export type RagStatus = {
  initialized: boolean;
  dataset: RagDataset | null;
  pending_sync_count: number;
  failed_sync_count: number;
  synced_count: number;
};

export type RagQueryResponse = {
  answer: string;
  conversation_id: string | null;
  sources: Array<{
    file_id: number | null;
    filename: string | null;
    dify_document_id: string | null;
    snippet: string | null;
  }>;
  graph_context: Array<{
    relation_id: number;
    relation_type: string;
    relation_label: string;
    source_entity_id: number;
    source_label: string;
    source_entity_type: string;
    source_entity_type_label: string;
    target_entity_id: number;
    target_label: string;
    target_entity_type: string;
    target_entity_type_label: string;
    confidence: number;
  }>;
  rag_mode: string;
  query_log_id: number | null;
  response_ms: number | null;
};

export type AIQueryEvaluation = {
  id: number;
  query_log_id: number;
  evaluator_user_id: number;
  score: number;
  is_accurate: boolean;
  is_traceable: boolean;
  comment: string | null;
  created_at: string;
  updated_at: string;
};

export type AIQueryLog = {
  id: number;
  project_id: number;
  user_id: number;
  question: string;
  answer: string | null;
  rag_mode: string;
  graph_hit_count: number;
  source_count: number;
  response_ms: number;
  conversation_id: string | null;
  graph_context_json: RagQueryResponse["graph_context"];
  sources_json: RagQueryResponse["sources"];
  error_message: string | null;
  created_at: string;
  evaluation: AIQueryEvaluation | null;
};

export type AIQueryModeStats = {
  rag_mode: string;
  total_queries: number;
  evaluated_queries: number;
  avg_score: number | null;
  accurate_rate: number | null;
  traceable_rate: number | null;
  avg_graph_hit_count: number;
  avg_source_count: number;
  avg_response_ms: number;
};

export type AIQueryAnalytics = {
  project_id: number;
  total_queries: number;
  evaluated_queries: number;
  evaluation_rate: number;
  project_rag_queries: number;
  kg_enhanced_queries: number;
  failed_queries: number;
  avg_response_ms: number;
  avg_score: number | null;
  accurate_rate: number | null;
  traceable_rate: number | null;
  avg_graph_hit_count: number;
  avg_source_count: number;
  mode_stats: AIQueryModeStats[];
};

export type AgentGenerationRun = {
  id: number;
  project_id: number;
  user_id: number;
  task_type: string;
  input_params_json: Record<string, string | null>;
  title: string;
  body: string;
  source_note_ids_json: number[];
  source_file_ids_json: number[];
  source_graph_relation_ids_json: number[];
  status: string;
  response_ms: number;
  message: string | null;
  created_at: string;
};

export type KnowledgeEntity = {
  id: number;
  project_id: number;
  entity_type: string;
  label: string;
  normalized_label: string;
  natural_key: string;
  source_type: string | null;
  source_id: number | null;
  properties: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type KnowledgeRelation = {
  id: number;
  project_id: number;
  source_entity_id: number;
  target_entity_id: number;
  relation_type: string;
  source_type: string | null;
  source_id: number | null;
  confidence: number;
  properties: Record<string, unknown>;
  created_at: string;
};

export type KnowledgeGraph = {
  project_id: number;
  entities: KnowledgeEntity[];
  relations: KnowledgeRelation[];
};

export type KnowledgeExtractionRun = {
  id: number;
  project_id: number;
  note_id: number;
  triggered_by: number;
  status: string;
  extracted_entities: number;
  extracted_relations: number;
  message: string | null;
  created_at: string;
};

export type AuditLog = {
  id: number;
  actor_user_id: number | null;
  project_id: number | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  detail_json: Record<string, unknown>;
  created_at: string;
};

export async function apiFetch<T>(path: string, token?: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function login(username: string, password: string) {
  return apiFetch<LoginResponse>("/auth/login", undefined, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getMe(token: string) {
  return apiFetch<CurrentUser>("/auth/me", token);
}

export function logoutSession(token: string) {
  return apiFetch<{ ok: boolean }>("/auth/logout", token, { method: "POST" });
}

export function getProjects(token: string) {
  return apiFetch<Project[]>("/projects", token);
}

export function createProject(token: string, payload: Partial<Project> & { name: string }) {
  return apiFetch<Project>("/projects", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProject(token: string, projectId: number, payload: Partial<Project>) {
  return apiFetch<Project>(`/projects/${projectId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getUsers(token: string) {
  return apiFetch<User[]>("/users", token);
}

export function createUser(token: string, payload: { username: string; password: string; display_name: string; email?: string; role: string }) {
  return apiFetch<User>("/users", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(token: string, userId: number, payload: Partial<User> & { password?: string }) {
  return apiFetch<User>(`/users/${userId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function disableUser(token: string, userId: number) {
  return apiFetch<User>(`/users/${userId}/disable`, token, { method: "POST" });
}

export function getGroups(token: string) {
  return apiFetch<Group[]>("/groups", token);
}

export function createGroup(token: string, payload: { name: string; description?: string; leader_user_id?: number | null }) {
  return apiFetch<Group>("/groups", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateGroup(token: string, groupId: number, payload: Partial<Group>) {
  return apiFetch<Group>(`/groups/${groupId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getGroupMembers(token: string, groupId: number) {
  return apiFetch<GroupMember[]>(`/groups/${groupId}/members`, token);
}

export function addGroupMember(token: string, groupId: number, payload: { user_id: number; group_role: string }) {
  return apiFetch<GroupMember>(`/groups/${groupId}/members`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function removeGroupMember(token: string, groupId: number, userId: number) {
  return apiFetch<{ ok: boolean }>(`/groups/${groupId}/members/${userId}`, token, { method: "DELETE" });
}

export function getProjectMembers(token: string, projectId: number) {
  return apiFetch<ProjectMember[]>(`/projects/${projectId}/members`, token);
}

export function addProjectMember(token: string, projectId: number, payload: Omit<ProjectMember, "id" | "project_id">) {
  return apiFetch<{ ok: boolean }>(`/projects/${projectId}/members`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProjectMember(token: string, projectId: number, userId: number, payload: Partial<Omit<ProjectMember, "id" | "project_id" | "user_id">>) {
  return apiFetch<ProjectMember>(`/projects/${projectId}/members/${userId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function removeProjectMember(token: string, projectId: number, userId: number) {
  return apiFetch<{ ok: boolean }>(`/projects/${projectId}/members/${userId}`, token, { method: "DELETE" });
}

export function addProjectReviewer(token: string, projectId: number, payload: { user_id: number; review_scope?: string }) {
  return apiFetch<{ id: number; project_id: number; user_id: number; review_scope: string }>(`/projects/${projectId}/reviewers`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTemplates(token: string) {
  return apiFetch<Template[]>("/templates", token);
}

export function getAuditLogs(
  token: string,
  filters: { actor_user_id?: string; project_id?: string; action?: string; date_from?: string; date_to?: string } = {},
) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return apiFetch<AuditLog[]>(`/audit-logs${params.toString() ? `?${params.toString()}` : ""}`, token);
}

export function getProjectNotes(token: string, projectId: number) {
  return apiFetch<Note[]>(`/projects/${projectId}/notes`, token);
}

export function createNote(
  token: string,
  projectId: number,
  payload: {
    title: string;
    experiment_type: string;
    experiment_date?: string;
    template_id?: number | null;
    fixed_fields_json: Record<string, string>;
    content_json: Record<string, unknown>;
  },
) {
  return apiFetch<Note>(`/projects/${projectId}/notes`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateNote(
  token: string,
  noteId: number,
  payload: {
    title?: string;
    experiment_type?: string;
    experiment_date?: string;
    fixed_fields_json?: Record<string, string>;
    content_json?: Record<string, unknown>;
    change_summary?: string;
  },
) {
  return apiFetch<Note>(`/notes/${noteId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function submitNote(token: string, noteId: number) {
  return apiFetch<Note>(`/notes/${noteId}/submit`, token, { method: "POST" });
}

export function approveNote(token: string, noteId: number, comment: string) {
  return apiFetch<Note>(`/notes/${noteId}/approve`, token, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function returnNote(token: string, noteId: number, comment: string) {
  return apiFetch<Note>(`/notes/${noteId}/return`, token, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function archiveNote(token: string, noteId: number) {
  return apiFetch<Note>(`/notes/${noteId}/archive`, token, { method: "POST" });
}

export function voidNote(token: string, noteId: number, comment: string) {
  return apiFetch<Note>(`/notes/${noteId}/void`, token, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function getNoteVersions(token: string, noteId: number) {
  return apiFetch<NoteVersion[]>(`/notes/${noteId}/versions`, token);
}

export function getNoteApprovals(token: string, noteId: number) {
  return apiFetch<NoteApproval[]>(`/notes/${noteId}/approvals`, token);
}

export function getPendingApprovals(token: string) {
  return apiFetch<Note[]>("/approvals/pending", token);
}

export function getProjectFiles(token: string, projectId: number) {
  return apiFetch<StoredFile[]>(`/projects/${projectId}/files`, token);
}

export function uploadFile(token: string, projectId: number, file: File, noteId?: number | null, category = "note_attachment") {
  const form = new FormData();
  form.append("upload", file);
  const params = new URLSearchParams({ file_category: category });
  if (noteId) params.set("note_id", String(noteId));
  return apiFetch<StoredFile>(`/projects/${projectId}/files?${params.toString()}`, token, {
    method: "POST",
    body: form,
  });
}

export function updateFile(token: string, fileId: number, payload: { original_filename?: string }) {
  return apiFetch<StoredFile>(`/files/${fileId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveFile(token: string, fileId: number) {
  return apiFetch<StoredFile>(`/files/${fileId}/archive`, token, { method: "POST" });
}

export function reviewFile(token: string, fileId: number, action: "approve" | "reject", comment = "") {
  return apiFetch<StoredFile>(`/files/${fileId}/review`, token, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
}

export function initProjectRag(token: string, projectId: number) {
  return apiFetch<RagStatus>(`/projects/${projectId}/rag/init`, token, { method: "POST" });
}

export function getProjectRagStatus(token: string, projectId: number) {
  return apiFetch<RagStatus>(`/projects/${projectId}/rag/status`, token);
}

export function syncFileToRag(token: string, fileId: number) {
  return apiFetch<RagStatus>(`/files/${fileId}/rag/sync`, token, { method: "POST" });
}

export function queryProjectRag(token: string, projectId: number, query: string, mode = "auto") {
  return apiFetch<RagQueryResponse>(`/projects/${projectId}/rag/query`, token, {
    method: "POST",
    body: JSON.stringify({ query, mode }),
  });
}

export function getProjectQueryLogs(token: string, projectId: number) {
  return apiFetch<AIQueryLog[]>(`/projects/${projectId}/rag/query-logs`, token);
}

export function getProjectQueryAnalytics(token: string, projectId: number) {
  return apiFetch<AIQueryAnalytics>(`/projects/${projectId}/rag/analytics`, token);
}

export function evaluateQueryLog(
  token: string,
  logId: number,
  payload: { score: number; is_accurate: boolean; is_traceable: boolean; comment?: string | null },
) {
  return apiFetch<AIQueryEvaluation>(`/rag/query-logs/${logId}/evaluation`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProjectKnowledgeGraph(token: string, projectId: number) {
  return apiFetch<KnowledgeGraph>(`/projects/${projectId}/kg/graph`, token);
}

export function getNoteKnowledgeGraph(token: string, noteId: number) {
  return apiFetch<KnowledgeGraph>(`/notes/${noteId}/kg/graph`, token);
}

export function extractNoteKnowledgeGraph(token: string, noteId: number, rebuild = true) {
  return apiFetch<KnowledgeExtractionRun>(`/notes/${noteId}/kg/extract`, token, {
    method: "POST",
    body: JSON.stringify({ rebuild }),
  });
}

export function rebuildProjectKnowledgeGraph(token: string, projectId: number) {
  return apiFetch<KnowledgeExtractionRun[]>(`/projects/${projectId}/kg/rebuild`, token, { method: "POST" });
}

export function fileDownloadUrl(fileId: number) {
  return `${API_BASE_URL}/files/${fileId}/download`;
}

// ── Search ────────────────────────────────────────────────

export type SearchResult = {
  document_id: number;
  note_id: number;
  project_id: number;
  title: string;
  snippet: string;
  source_ids: string[];
};

export type SearchStatus = {
  total_documents: number;
  project_documents: number;
};

export function reindexSearch(token: string, projectId?: number) {
  const params = projectId !== undefined ? `?project_id=${projectId}` : "";
  return apiFetch<SearchStatus>(`/api/search/index${params}`, token, { method: "POST" });
}

export function searchDocuments(token: string, query: string, projectId?: number) {
  return apiFetch<SearchResult[]>("/api/search", token, {
    method: "POST",
    body: JSON.stringify({ query, project_id: projectId ?? null }),
  });
}

// ── OCR ───────────────────────────────────────────────────

export type OcrJobResult = {
  file_id: number;
  extracted_text: string;
  source_ids: string[];
};

export function extractOcr(token: string, fileId: number) {
  return apiFetch<OcrJobResult>("/api/ocr/extract", token, {
    method: "POST",
    body: JSON.stringify({ file_id: fileId }),
  });
}

// ── Reports ───────────────────────────────────────────────

export type ReportDraft = {
  title: string;
  body: string;
  source_note_ids: number[];
};

export function createReportDraft(token: string, projectId: number, reportType = "daily") {
  return apiFetch<ReportDraft>("/api/reports/draft", token, {
    method: "POST",
    body: JSON.stringify({ report_type: reportType, project_id: projectId }),
  });
}

export function generateAgentOutput(
  token: string,
  payload: { project_id: number; task_type: string; date_from?: string | null; date_to?: string | null },
) {
  return apiFetch<AgentGenerationRun>("/api/agents/generate", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentRuns(token: string, projectId: number) {
  return apiFetch<AgentGenerationRun[]>(`/projects/${projectId}/agents/runs`, token);
}

// ── Dashboard ─────────────────────────────────────────────

export type DashboardSummary = {
  projects: number;
  experiments: number;
  attachments: number;
  audit_events: number;
  users: number;
  pending_approvals: number;
};

export function getDashboardSummary(token: string) {
  return apiFetch<DashboardSummary>("/api/dashboard/summary", token);
}

// ── Notifications ─────────────────────────────────────────

export type Notification = {
  id: number;
  project_id: number | null;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
};

export function getNotifications(token: string, projectId?: number) {
  const params = projectId !== undefined ? `?project_id=${projectId}` : "";
  return apiFetch<Notification[]>(`/api/notifications${params}`, token);
}

export function publishNotification(token: string, title: string, message = "", projectId?: number | null) {
  return apiFetch<Notification>("/api/notifications", token, {
    method: "POST",
    body: JSON.stringify({ title, message, project_id: projectId ?? null }),
  });
}

export function markNotificationRead(token: string, notificationId: number) {
  return apiFetch<Notification>(`/api/notifications/${notificationId}/read`, token, { method: "POST" });
}
