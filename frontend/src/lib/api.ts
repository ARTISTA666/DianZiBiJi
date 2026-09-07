import { toast } from "sonner";
import type { components } from "./api-schema";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

/** 会话过期（401 被踢回登录页）时写入 sessionStorage 的标记键。 */
export const SESSION_EXPIRED_FLAG = "auth.session-expired";

let isRedirecting = false;

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

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
  display_name?: string;
  project_role: string;
  can_read: boolean;
  can_write: boolean;
  can_review: boolean;
  can_evaluate: boolean;
  can_manage: boolean;
  is_independent_reviewer: boolean;
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
  schema_json: {
    fields?: Array<{
      key: string;
      label: string;
      type: string;
      required?: boolean;
    }>;
  };
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
  provider: string;
  embedding_model: string;
  generation_model: string;
  status: string;
  created_by: number;
  created_at: string;
  updated_at: string;
};

export type RagStatus = components["schemas"]["RagStatusRead"];

export type RagQueryResponse = {
  answer: string;
  conversation_id: string | null;
  sources: Array<{
    chunk_id: number | null;
    file_id: number | null;
    filename: string | null;
    dify_document_id: string | null;
    snippet: string | null;
    vector_score: number | null;
    lexical_score: number | null;
    retrieval_score: number | null;
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
    retrieval_score: number;
    relation_roles: string[];
  }>;
  rag_mode: string;
  query_log_id: number | null;
  response_ms: number | null;
  provider: string;
  model_name: string | null;
  fallback_reason: string | null;
  citation_audit: {
    passed: boolean;
    citation_count: number;
    invalid_citations: string[];
    has_evidence: boolean;
    message: string;
    repair_attempted: boolean;
  } | null;
};

export type AIQueryEvaluation = {
  id: number;
  query_log_id: number;
  evaluator_user_id: number;
  score: number;
  is_accurate: boolean;
  is_traceable: boolean;
  comment: string | null;
  review_protocol: "method_masked" | "unblinded" | string;
  created_at: string;
  updated_at: string;
};

export type BlindReviewEvaluation = {
  score: number;
  is_accurate: boolean;
  is_traceable: boolean;
  comment: string | null;
  updated_at: string;
};

export type BlindReviewEvidence = {
  evidence_id: string;
  content: string;
};

export type BlindReviewItem = {
  blind_id: string;
  question: string;
  answer: string | null;
  evidence: BlindReviewEvidence[];
  evaluation: BlindReviewEvaluation | null;
};

export type BlindReviewBatch = {
  batch_id: string;
  total_items: number;
  completed_items: number;
};

export type MaturityGate = {
  key: string;
  title: string;
  path: string;
  exists: boolean;
  passed: boolean;
  generated_at: string | null;
  blockers: string[];
};

export type MaturityStatus = {
  passed: boolean;
  human_review_allowed: boolean;
  human_review_report_allowed: boolean;
  gates: MaturityGate[];
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
  provider: string;
  model_name: string | null;
  prompt_version: string;
  retrieval_config_json: Record<string, unknown>;
  usage_json: Record<string, unknown>;
  fallback_reason: string | null;
  error_message: string | null;
  experiment_run_id: number | null;
  experiment_case_index: number | null;
  experiment_repetition_index: number | null;
  experiment_execution_order: number | null;
  created_at: string;
  evaluation: AIQueryEvaluation | null;
  evaluations: AIQueryEvaluation[];
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
  evaluation_count: number;
  evaluator_count: number;
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
  accuracy_agreement: {
    paired_ratings: number;
    agreement_rate: number | null;
    cohens_kappa: number | null;
  };
  traceability_agreement: {
    paired_ratings: number;
    agreement_rate: number | null;
    cohens_kappa: number | null;
  };
};

export type AIExperimentRun = {
  id: number;
  project_id: number;
  created_by: number;
  name: string;
  status: string;
  questions_json: string[];
  modes_json: string[];
  config_snapshot_json: Record<string, unknown>;
  summary_json: {
    errors?: Array<{ question_index: number; question: string; mode: string; error: string }>;
    mode_stats?: Array<{
      mode: string;
      completed: number;
      failed: number;
      avg_response_ms: number;
      avg_source_count: number;
      avg_graph_hit_count: number;
    }>;
  };
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  created_at: string;
  completed_at: string | null;
};

export type AgentGenerationRun = {
  id: number;
  project_id: number;
  user_id: number;
  task_type: string;
  input_params_json: {
    date_from?: string | null;
    date_to?: string | null;
    collaboration_steps?: Array<{
      key: string;
      name: string;
      status: string;
      message: string;
    }>;
    review_result?: {
      passed: boolean;
      citation_count: number;
      invalid_citations: string[];
      message: string;
    };
    repair_attempted?: boolean;
  };
  title: string;
  body: string;
  source_note_ids_json: number[];
  source_file_ids_json: number[];
  source_graph_relation_ids_json: number[];
  provider: string;
  model_name: string | null;
  prompt_version: string;
  usage_json: Record<string, unknown>;
  status: string;
  response_ms: number;
  message: string | null;
  created_at: string;
};

export type AgentRuntimeSnapshot = {
  session: {
    id: string;
    project_id: number | null;
    status: string;
    provider: string;
    model_name: string;
    prompt_version: string;
    usage: Record<string, unknown>;
    active_turn?: string | null;
  };
  messages: Array<{ id: number; role: "user" | "assistant"; content: string; metadata: Record<string, unknown> }>;
  steps: Array<{
    id: number;
    sequence_no: number;
    tool_name: string;
    risk: string;
    arguments_summary: string;
    status: string;
    result: Record<string, unknown> | null;
  }>;
  pending_actions: Array<{
    id: string;
    tool_name: string;
    arguments_summary: string;
    status: string;
    expires_at: string;
  }>;
  turns?: AgentTurn[];
};

export type AgentProfile = "fast" | "deep";

export type AgentTurn = {
  id: string;
  profile: AgentProfile;
  prompt_version: string;
  status: string;
  input: string;
  plan?: { text?: string; profile?: AgentProfile; budget?: Record<string, unknown> } | null;
  plan_hash?: string | null;
  budget: Record<string, unknown>;
  usage: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

export type AgentTurnStartResponse = AgentRuntimeSnapshot & {
  turn_id: string;
  status: string;
};

export type AgentTurnPreviewResponse = {
  turn_id: string;
  status: "awaiting_plan_approval";
  plan: NonNullable<AgentTurn["plan"]>;
  plan_hash: string;
  budget: Record<string, unknown>;
};

export type AgentEvent = {
  id: number;
  event: string;
  data: Record<string, unknown>;
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

type KnowledgeExtractionRun = {
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

// Authentication uses the HttpOnly cookie set by /auth/login; the token
// parameter is kept for call-site compatibility but is never sent, so the
// token no longer needs to live in JS-accessible storage.
async function apiFetch<T>(
  path: string,
  _token?: string,
  init?: RequestInit,
  parseResponse: (response: Response) => Promise<T> = (response) => response.json() as Promise<T>,
): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    if (!navigator.onLine) {
      toast.error("网络已断开，请检查网络连接");
    } else if (error instanceof TypeError && error.message.includes("Failed to fetch")) {
      toast.error("网络连接失败，请检查网络后重试");
    }
    throw error;
  }
  if (!response.ok) {
    if (response.status === 401 && !isRedirecting) {
      isRedirecting = true;
      // 登录接口自身的 401（账号/密码错误）不算会话过期，不写标记。
      if (!path.startsWith("/auth/")) {
        try {
          sessionStorage.setItem(SESSION_EXPIRED_FLAG, "1");
        } catch {
          // sessionStorage 不可用时静默降级，登录页仅缺少过期提示。
        }
      }
      try {
        const { useAuthStore } = await import("@/stores/auth-store");
        useAuthStore.getState().logout();
      } catch {
        // Auth store may already be cleared; proceed with redirect.
      }
      window.location.replace("/login");
    }
    const text = await response.text();
    let message = text || `请求失败: ${response.status}`;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep non-JSON upstream errors unchanged.
    }
    const requestId = response.headers.get("x-request-id");
    // requestId 仅保留在错误对象上，不拼进用户可见文案。
    throw new ApiRequestError(message, response.status, requestId);
  }
  if (response.status === 204) return null as unknown as T;
  return parseResponse(response);
}

function jsonInit(method: string, payload?: unknown): RequestInit {
  return payload === undefined ? { method } : { method, body: JSON.stringify(payload) };
}

function post<T>(path: string, token?: string, payload?: unknown) {
  return apiFetch<T>(path, token, jsonInit("POST", payload));
}

function patch<T>(path: string, token: string, payload: unknown) {
  return apiFetch<T>(path, token, jsonInit("PATCH", payload));
}

function del<T>(path: string, token: string) {
  return apiFetch<T>(path, token, { method: "DELETE" });
}

export function login(username: string, password: string) {
  return post<LoginResponse>("/auth/login", undefined, { username, password });
}

export function getMe(token: string) {
  return apiFetch<CurrentUser>("/auth/me", token);
}

export function getMaturityStatus(token: string) {
  return apiFetch<MaturityStatus>("/maturity/status", token);
}

export function logoutSession(token: string) {
  return post<{ ok: boolean }>("/auth/logout", token);
}

export function changeOwnPassword(token: string, currentPassword: string, newPassword: string) {
  return post<LoginResponse>("/users/me/password", token, {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export type ProjectListResponse = {
  items: Project[];
  total: number;
  skip: number;
  limit: number;
};

export function getProject(token: string, projectId: number) {
  return apiFetch<Project>(`/projects/${projectId}`, token);
}

export function getProjectsPaginated(token: string, skip = 0, limit = 20) {
  return apiFetch<ProjectListResponse>(`/projects?skip=${skip}&limit=${limit}`, token);
}

export function createProject(token: string, payload: Partial<Project> & { name: string }) {
  return post<Project>("/projects", token, payload);
}

export function updateProject(token: string, projectId: number, payload: Partial<Project>) {
  return patch<Project>(`/projects/${projectId}`, token, payload);
}

export function getUsers(token: string) {
  return apiFetch<PaginatedResponse<User>>("/users", token);
}

export function createUser(token: string, payload: { username: string; password: string; display_name: string; email?: string; role: string }) {
  return post<User>("/users", token, payload);
}

export function updateUser(token: string, userId: number, payload: Partial<User> & { password?: string }) {
  return patch<User>(`/users/${userId}`, token, payload);
}

export function disableUser(token: string, userId: number) {
  return post<User>(`/users/${userId}/disable`, token);
}

export function getGroups(token: string) {
  return apiFetch<Group[]>("/groups", token);
}

export function createGroup(token: string, payload: { name: string; description?: string; leader_user_id?: number | null }) {
  return post<Group>("/groups", token, payload);
}

export function updateGroup(token: string, groupId: number, payload: Partial<Group>) {
  return patch<Group>(`/groups/${groupId}`, token, payload);
}

export function getGroupMembers(token: string, groupId: number) {
  return apiFetch<GroupMember[]>(`/groups/${groupId}/members`, token);
}

export function addGroupMember(token: string, groupId: number, payload: { user_id: number; group_role: string }) {
  return post<GroupMember>(`/groups/${groupId}/members`, token, payload);
}

export function removeGroupMember(token: string, groupId: number, userId: number) {
  return del<{ ok: boolean }>(`/groups/${groupId}/members/${userId}`, token);
}

export function getProjectMembers(token: string, projectId: number) {
  return apiFetch<ProjectMember[]>(`/projects/${projectId}/members`, token);
}

export function addProjectMember(token: string, projectId: number, payload: Omit<ProjectMember, "id" | "project_id" | "is_independent_reviewer">) {
  return post<{ ok: boolean }>(`/projects/${projectId}/members`, token, payload);
}

export function updateProjectMember(token: string, projectId: number, userId: number, payload: Partial<Omit<ProjectMember, "id" | "project_id" | "user_id" | "is_independent_reviewer">>) {
  return patch<ProjectMember>(`/projects/${projectId}/members/${userId}`, token, payload);
}

export function removeProjectMember(token: string, projectId: number, userId: number) {
  return del<{ ok: boolean }>(`/projects/${projectId}/members/${userId}`, token);
}

export function addProjectReviewer(token: string, projectId: number, payload: { user_id: number; review_scope?: string }) {
  return post<{ id: number; project_id: number; user_id: number; review_scope: string }>(`/projects/${projectId}/reviewers`, token, payload);
}

export function removeProjectReviewer(token: string, projectId: number, userId: number) {
  return del<{ ok: boolean }>(`/projects/${projectId}/reviewers/${userId}`, token);
}

export function getTemplates(token: string) {
  return apiFetch<Template[]>("/templates", token);
}

export function getAuditLogs(
  token: string,
  filters: {
    actor_user_id?: string;
    project_id?: string;
    action?: string;
    date_from?: string;
    date_to?: string;
    skip?: number;
    limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return apiFetch<PaginatedResponse<AuditLog>>(`/audit-logs${params.toString() ? `?${params.toString()}` : ""}`, token);
}

export function getProjectAuditLogs(
  token: string,
  projectId: number,
  filters: {
    actor_user_id?: string;
    action?: string;
    date_from?: string;
    date_to?: string;
    skip?: number;
    limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const qs = params.toString();
  return apiFetch<PaginatedResponse<AuditLog>>(`/projects/${projectId}/audit-logs${qs ? `?${qs}` : ""}`, token);
}

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
};

export function getProjectNotes(token: string, projectId: number, params: {
  skip?: number;
  limit?: number;
  status?: string;
  search?: string;
  sort?: string;
} = {}) {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.status) searchParams.set("status", params.status);
  if (params.search) searchParams.set("search", params.search);
  if (params.sort) searchParams.set("sort", params.sort);
  const qs = searchParams.toString();
  return apiFetch<PaginatedResponse<Note>>(`/projects/${projectId}/notes${qs ? `?${qs}` : ""}`, token);
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
  return post<Note>(`/projects/${projectId}/notes`, token, payload);
}

export function updateNote(
  token: string,
  noteId: number,
  payload: {
    title?: string;
    experiment_type?: string;
    experiment_date?: string;
    template_id?: number | null;
    fixed_fields_json?: Record<string, string>;
    content_json?: Record<string, unknown>;
    change_summary?: string;
  },
) {
  return patch<Note>(`/notes/${noteId}`, token, payload);
}

export function submitNote(token: string, noteId: number) {
  return post<Note>(`/notes/${noteId}/submit`, token);
}

export function approveNote(token: string, noteId: number, comment: string) {
  return post<Note>(`/notes/${noteId}/approve`, token, { comment });
}

export function returnNote(token: string, noteId: number, comment: string) {
  return post<Note>(`/notes/${noteId}/return`, token, { comment });
}

export function archiveNote(token: string, noteId: number) {
  return post<Note>(`/notes/${noteId}/archive`, token);
}

export function voidNote(token: string, noteId: number, comment: string) {
  return post<Note>(`/notes/${noteId}/void`, token, { comment });
}

export function getNoteVersions(token: string, noteId: number) {
  return apiFetch<NoteVersion[]>(`/notes/${noteId}/versions`, token);
}

export function getNoteApprovals(token: string, noteId: number) {
  return apiFetch<NoteApproval[]>(`/notes/${noteId}/approvals`, token);
}

export function getNoteFiles(token: string, noteId: number) {
  return apiFetch<StoredFile[]>(`/notes/${noteId}/files`, token);
}

export function getPendingApprovals(token: string) {
  return apiFetch<Note[]>("/approvals/pending", token);
}

export function getProjectFiles(token: string, projectId: number) {
  return apiFetch<PaginatedResponse<StoredFile>>(`/projects/${projectId}/files`, token);
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
  return patch<StoredFile>(`/files/${fileId}`, token, payload);
}

export function archiveFile(token: string, fileId: number) {
  return post<StoredFile>(`/files/${fileId}/archive`, token);
}

export function reviewFile(token: string, fileId: number, action: "approve" | "reject", comment = "") {
  return post<StoredFile>(`/files/${fileId}/review`, token, { action, comment });
}

export function initProjectRag(token: string, projectId: number) {
  return post<RagStatus>(`/projects/${projectId}/rag/init`, token);
}

export function getProjectRagStatus(token: string, projectId: number) {
  return apiFetch<RagStatus>(`/projects/${projectId}/rag/status`, token);
}

export function syncFileToRag(token: string, fileId: number) {
  return post<RagStatus>(`/files/${fileId}/rag/sync`, token);
}

export function queryProjectRag(
  token: string,
  projectId: number,
  query: string,
  mode = "auto",
  history?: Array<{ question: string; answer: string }>,
) {
  return post<RagQueryResponse>(`/projects/${projectId}/rag/query`, token, { query, mode, history });
}

export function getProjectQueryLogs(token: string, projectId: number) {
  return apiFetch<AIQueryLog[]>(`/projects/${projectId}/rag/query-logs`, token);
}

export function getProjectQueryAnalytics(token: string, projectId: number) {
  return apiFetch<AIQueryAnalytics>(`/projects/${projectId}/rag/analytics`, token);
}

export function getRagExperiments(token: string, projectId: number) {
  return apiFetch<AIExperimentRun[]>(`/projects/${projectId}/rag/experiments`, token);
}

export function getRagExperiment(token: string, runId: number) {
  return apiFetch<AIExperimentRun>(`/rag/experiments/${runId}`, token);
}

export function runRagExperiment(
  token: string,
  projectId: number,
  payload: {
    name: string;
    questions: string[];
    modes?: string[];
    repetitions?: number;
    randomize_order?: boolean;
    random_seed?: number | null;
    expected_corpus_snapshot_hash?: string | null;
    expected_graph_snapshot_hash?: string | null;
  },
) {
  return post<AIExperimentRun>(`/projects/${projectId}/rag/experiments`, token, payload);
}

export function resumeRagExperiment(token: string, runId: number) {
  return post<AIExperimentRun>(`/rag/experiments/${runId}/resume`, token);
}

export async function downloadRagExperiment(token: string, runId: number) {
  return apiFetch<Blob>(
    `/rag/experiments/${runId}/export.csv`,
    token,
    undefined,
    (response) => response.blob(),
  );
}

export async function downloadRagExperimentEvidence(token: string, runId: number) {
  return apiFetch<Blob>(
    `/rag/experiments/${runId}/evidence.json`,
    token,
    undefined,
    (response) => response.blob(),
  );
}

export function evaluateQueryLog(
  token: string,
  logId: number,
  payload: { score: number; is_accurate: boolean; is_traceable: boolean; comment?: string | null },
) {
  return post<AIQueryEvaluation>(`/rag/query-logs/${logId}/evaluation`, token, payload);
}

export function submitQueryLogFeedback(
  token: string,
  logId: number,
  payload: { value: "helpful" | "not_helpful"; comment?: string | null },
) {
  return post<{ accepted: boolean; value: "helpful" | "not_helpful" }>(
    `/rag/query-logs/${logId}/feedback`,
    token,
    payload,
  );
}

export function getBlindReviewBatches(token: string, projectId: number) {
  return apiFetch<BlindReviewBatch[]>(`/projects/${projectId}/rag/blind-review/batches`, token);
}

export function getBlindReviewItems(
  token: string,
  projectId: number,
  filters: { batch_id?: string; pending_only?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (filters.batch_id) params.set("batch_id", filters.batch_id);
  if (filters.pending_only !== undefined) params.set("pending_only", String(filters.pending_only));
  return apiFetch<BlindReviewItem[]>(
    `/projects/${projectId}/rag/blind-review/items${params.toString() ? `?${params.toString()}` : ""}`,
    token,
  );
}

export function evaluateBlindReviewItem(
  token: string,
  projectId: number,
  blindId: string,
  payload: { score: number; is_accurate: boolean; is_traceable: boolean; comment?: string | null },
) {
  return post<BlindReviewEvaluation>(
    `/projects/${projectId}/rag/blind-review/items/${encodeURIComponent(blindId)}/evaluation`,
    token,
    payload,
  );
}

export async function downloadBlindReviewBatchExport(token: string, projectId: number, batchId: string) {
  return apiFetch<Blob>(
    `/projects/${projectId}/rag/blind-review/batches/${encodeURIComponent(batchId)}/export.csv`,
    token,
    undefined,
    (response) => response.blob(),
  );
}

export function getProjectKnowledgeGraph(token: string, projectId: number) {
  return apiFetch<KnowledgeGraph>(`/projects/${projectId}/kg/graph`, token);
}

export function extractNoteKnowledgeGraph(token: string, noteId: number, rebuild = true) {
  return post<KnowledgeExtractionRun>(`/notes/${noteId}/kg/extract`, token, { rebuild });
}

export function rebuildProjectKnowledgeGraph(token: string, projectId: number) {
  return post<KnowledgeExtractionRun[]>(`/projects/${projectId}/kg/rebuild`, token);
}

// ── 知识蓝图（计划态图谱） ─────────────────────────────────

export type BlueprintEvidence = {
  entity_ids: number[];
  entity_count: number;
  last_evidence_at: string | null;
};

export type BlueprintNode = {
  id: number;
  entity_type: string;
  label: string;
  description: string;
  status: string;
  source_kind: string;
  source_label: string;
  priority: number;
  created_at: string;
  updated_at: string;
  evidence: BlueprintEvidence;
};

export type BlueprintEdge = {
  id: number;
  source_node_id: number;
  target_node_id: number;
  relation_type: string;
  status: string;
  priority: number;
};

export type BlueprintDocument = {
  id: number;
  title: string;
  source_kind: string;
  parse_mode: string;
  node_count: number;
  edge_count: number;
  message: string;
  created_at: string;
};

export type KnowledgeBlueprint = {
  project_id: number;
  coverage: { total_nodes: number; covered_nodes: number; completion: number };
  nodes: BlueprintNode[];
  edges: BlueprintEdge[];
  documents: BlueprintDocument[];
};

export function getProjectKnowledgeBlueprint(token: string, projectId: number) {
  return apiFetch<KnowledgeBlueprint>(`/projects/${projectId}/kg/blueprint`, token);
}

export function parseProjectKnowledgeBlueprint(
  token: string,
  projectId: number,
  payload: {
    title: string;
    source_kind: string;
    priority?: number;
    text?: string;
    file_id?: number;
    note_id?: number;
  },
) {
  return post<{
    document_id: number;
    parse_mode: string;
    nodes_added: number;
    nodes_updated: number;
    edges_added: number;
    edges_dropped: number;
    message: string;
  }>(`/projects/${projectId}/kg/blueprint/parse`, token, payload);
}

// ── 项目预警（创新点四：预警与人工审核闭环） ────────────────

export type AlertMetricSnapshot = {
  metric: string;
  value: number;
  level: string;
};

export type AlertThreshold = {
  id: number;
  project_id: number;
  metric: string;
  warn_threshold: number;
  critical_threshold: number;
  enabled: boolean;
  updated_by: number;
  updated_at: string;
};

export type ProjectAlert = {
  id: number;
  project_id: number;
  metric: string;
  metric_value: number;
  level: string;
  status: string;
  detail: string;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
  created_at: string;
};

export type ProjectAlertInbox = {
  alerts: ProjectAlert[];
  thresholds: AlertThreshold[];
};

export type AlertEvaluationSummary = {
  evaluated_at: string;
  metrics: AlertMetricSnapshot[];
};

export const ALERT_METRIC_TEXT: Record<string, string> = {
  review_stall_hours: "审批停滞",
  return_rate: "退回率",
  blueprint_stagnant_days: "蓝图停滞",
  progress_deviation: "进展偏差",
};

export function listProjectAlerts(token: string, projectId: number) {
  return apiFetch<ProjectAlertInbox>(`/projects/${projectId}/alerts`, token);
}

export function evaluateProjectAlerts(token: string, projectId: number) {
  return post<AlertEvaluationSummary>(`/projects/${projectId}/alerts/evaluate`, token);
}

export function acknowledgeProjectAlert(
  token: string,
  projectId: number,
  alertId: number,
  payload: { note?: string } = {},
) {
  return post<null>(`/projects/${projectId}/alerts/${alertId}/acknowledge`, token, payload);
}

export function upsertProjectAlertThreshold(
  token: string,
  projectId: number,
  payload: {
    metric: string;
    warn_threshold: number;
    critical_threshold: number;
    enabled: boolean;
  },
) {
  return post<AlertThreshold>(`/projects/${projectId}/alerts/thresholds`, token, payload);
}

export function patchProjectKnowledgeBlueprintNode(
  token: string,
  projectId: number,
  nodeId: number,
  payload: { status?: string; description?: string },
) {
  return patch<{ updated: boolean; id: number }>(
    `/projects/${projectId}/kg/blueprint/nodes/${nodeId}`,
    token,
    payload,
  );
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

type SearchStatus = {
  total_documents: number;
  project_documents: number;
};

export function reindexSearch(token: string, projectId?: number) {
  const params = projectId !== undefined ? `?project_id=${projectId}` : "";
  return post<SearchStatus>(`/api/search/index${params}`, token);
}

export function searchDocuments(token: string, query: string, projectId?: number) {
  return post<SearchResult[]>("/api/search", token, { query, project_id: projectId ?? null });
}

// ── OCR ───────────────────────────────────────────────────

export type OcrJobResult = {
  ocr_result_id: number;
  file_id: number;
  extracted_text: string;
  raw_text: string;
  source_ids: string[];
  character_count: number;
  truncated: boolean;
  extraction_method: string;
  review_status: string;
  created_by: number;
  reviewed_by: number | null;
  created_at: string;
  reviewed_at: string | null;
};

export function extractOcr(token: string, fileId: number) {
  return post<OcrJobResult>("/api/ocr/extract", token, { file_id: fileId });
}

export function getLatestOcrResult(token: string, fileId: number) {
  return apiFetch<OcrJobResult>(`/api/ocr/files/${fileId}/latest`, token);
}

export function confirmOcrResult(token: string, resultId: number, correctedText: string) {
  return post<OcrJobResult>(`/api/ocr/results/${resultId}/confirm`, token, {
    corrected_text: correctedText,
  });
}

// ── Reports ───────────────────────────────────────────────

export function generateAgentOutput(
  token: string,
  payload: { project_id: number; task_type: string; date_from?: string | null; date_to?: string | null },
) {
  return post<AgentGenerationRun>("/api/agents/generate", token, payload);
}

export function getAgentRuns(token: string, projectId: number) {
  return apiFetch<AgentGenerationRun[]>(`/projects/${projectId}/agents/runs`, token);
}

export function createAgentSession(token: string, projectId: number | null) {
  return post<AgentRuntimeSnapshot>("/api/agent/sessions", token, { project_id: projectId });
}

export function sendAgentSessionMessage(token: string, sessionId: string, content: string) {
  return post<AgentRuntimeSnapshot>(`/api/agent/sessions/${sessionId}/messages`, token, { content });
}

export function createAgentTurn(
  token: string,
  sessionId: string,
  content: string,
  profile: AgentProfile = "fast",
) {
  if (profile === "deep") {
    return post<AgentTurnPreviewResponse>(`/api/agent/sessions/${sessionId}/turns`, token, {
      content,
      profile,
    });
  }
  return post<AgentTurnStartResponse>(`/api/agent/sessions/${sessionId}/turns`, token, {
    content,
    profile,
  });
}

export function startAgentTurn(token: string, sessionId: string, turnId: string, planHash: string) {
  return post<AgentTurnStartResponse>(
    `/api/agent/sessions/${sessionId}/turns/${turnId}/start`,
    token,
    { plan_hash: planHash },
  );
}

export function cancelAgentTurn(token: string, sessionId: string, turnId: string) {
  return post<{ turn_id: string; status: string }>(
    `/api/agent/sessions/${sessionId}/turns/${turnId}/cancel`,
    token,
  );
}

/**
 * Subscribe to the durable Agent event log. EventSource reconnects using the
 * server-provided event id; callers should treat events as at-least-once and
 * deduplicate by id before updating UI state.
 */
export function subscribeAgentSessionEvents(
  _token: string,
  sessionId: string,
  onEvent: (event: AgentEvent) => void,
  onError?: () => void,
) {
  const source = new EventSource(`${API_BASE_URL}/api/agent/sessions/${sessionId}/events`, {
    withCredentials: true,
  });
  const eventTypes = [
    "message.delta",
    "plan.preview",
    "turn.started",
    "turn.completed",
    "turn.cancelled",
    "tool.started",
    "tool.completed",
    "confirmation.required",
    "confirmation.rejected",
    "confirmation.completed",
    "error",
  ];
  const listeners = eventTypes.map((eventType) => {
    const listener = (event: Event) => {
      const message = event as MessageEvent<string>;
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(message.data) as Record<string, unknown>;
      } catch {
        data = { value: message.data };
      }
      onEvent({ id: Number(message.lastEventId || 0), event: eventType, data });
    };
    source.addEventListener(eventType, listener);
    return [eventType, listener] as const;
  });
  source.onerror = () => onError?.();
  return () => {
    for (const [eventType, listener] of listeners) source.removeEventListener(eventType, listener);
    source.close();
  };
}

export function approveAgentPendingAction(token: string, actionId: string) {
  return post<{ id: string; tool: string; status: string; execution_status: string }>(
    `/api/agent/pending-actions/${actionId}/approve`, token,
  );
}

export function rejectAgentPendingAction(token: string, actionId: string) {
  return post<{ id: string; tool: string; status: string }>(
    `/api/agent/pending-actions/${actionId}/reject`, token,
  );
}
