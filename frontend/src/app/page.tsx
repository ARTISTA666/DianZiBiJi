"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AgentGenerationRun,
  AIExperimentRun,
  AIQueryAnalytics,
  AIQueryLog,
  CurrentUser,
  DashboardSummary,
  Group,
  GroupMember,
  AuditLog,
  Note,
  NoteApproval,
  NoteVersion,
  Notification,
  KnowledgeEntity,
  KnowledgeGraph,
  Project,
  ProjectMember,
  RagQueryResponse,
  RagStatus,
  SearchResult,
  StoredFile,
  Template,
  User,
  addGroupMember,
  addProjectMember,
  addProjectReviewer,
  archiveFile,
  approveNote,
  archiveNote,
  createGroup,
  createNote,
  createProject,
  createUser,
  disableUser,
  downloadRagExperiment,
  fileDownloadUrl,
  getGroupMembers,
  getAuditLogs,
  getGroups,
  getMe,
  getNoteApprovals,
  getNoteVersions,
  getPendingApprovals,
  getProjectFiles,
  getProjectMembers,
  getProjectRagStatus,
  getProjectNotes,
  getProjects,
  getTemplates,
  getUsers,
  login,
  logoutSession,
  initProjectRag,
  queryProjectRag,
  reindexSearch,
  searchDocuments,
  extractOcr,
  extractNoteKnowledgeGraph,
  evaluateQueryLog,
  generateAgentOutput,
  getAgentRuns,
  getDashboardSummary,
  getProjectKnowledgeGraph,
  getProjectQueryAnalytics,
  getProjectQueryLogs,
  getRagExperiments,
  getNotifications,
  publishNotification,
  rebuildProjectKnowledgeGraph,
  removeGroupMember,
  removeProjectMember,
  reviewFile,
  runRagExperiment,
  returnNote,
  syncFileToRag,
  submitNote,
  updateFile,
  updateGroup,
  updateNote,
  updateProject,
  updateProjectMember,
  updateUser,
  uploadFile,
  voidNote,
} from "@/lib/api";

// ── Shared components ──
import { LoginPage } from "@/components/shared/LoginPage";
import { MessageBanner } from "@/components/shared/MessageBanner";
import { TopHeader } from "@/components/shared/TopHeader";
import { WorkspaceSidebar } from "@/components/shared/WorkspaceSidebar";
import { DashboardMetrics } from "@/components/shared/DashboardMetrics";
import { cardClass, kgRelationLabel, kgTypeLabel } from "@/components/shared/utils";

// ── Project tab components ──
import { ProjectHeader } from "@/components/project/ProjectHeader";
import { ProjectOverview } from "@/components/project/ProjectOverview";
import { NotesPanel, type NoteEditorState } from "@/components/project/NotesPanel";
import { FilesPanel } from "@/components/project/FilesPanel";
import { SearchPanel } from "@/components/project/SearchPanel";
import { KnowledgeGraphPanel } from "@/components/project/KnowledgeGraphPanel";
import { ReportsPanel } from "@/components/project/ReportsPanel";
import { ApprovalsPanel } from "@/components/project/ApprovalsPanel";
import { MembersPanel } from "@/components/project/MembersPanel";
import { ProjectLogsPanel } from "@/components/project/ProjectLogsPanel";

// ── Admin components ──
import { UserCreatePanel, UserManagementPanel } from "@/components/admin/UserManagementPanel";
import { AdminProjectPanel } from "@/components/admin/AdminProjectPanel";
import { GroupManagementPanel } from "@/components/admin/GroupManagementPanel";
import { AuditLogPanel } from "@/components/admin/AuditLogPanel";

// ── Constants ──
import {
  projectTabs,
} from "@/components/constants";
import type { ProjectTab } from "@/components/constants";

const emptyEditor: NoteEditorState = {
  title: "",
  experiment_type: "PCR",
  experiment_date: new Date().toISOString().slice(0, 10),
  template_id: null,
  fixed_fields_json: {},
  content_text: "",
};

// ── Main Page ──────────────────────────────────────────────
export default function Home() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupMembers, setGroupMembers] = useState<GroupMember[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [workspaceView, setWorkspaceView] = useState<"project" | "admin">("project");
  const [activeProjectTab, setActiveProjectTab] = useState<ProjectTab>("overview");
  const [notes, setNotes] = useState<Note[]>([]);
  const [pendingNotes, setPendingNotes] = useState<Note[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [noteFilters, setNoteFilters] = useState({ keyword: "", status: "", experiment_type: "" });
  const [fileFilters, setFileFilters] = useState({ keyword: "", category: "", status: "" });
  const [selectedNote, setSelectedNote] = useState<Note | null>(null);
  const [versions, setVersions] = useState<NoteVersion[]>([]);
  const [approvals, setApprovals] = useState<NoteApproval[]>([]);
  const [editor, setEditor] = useState<NoteEditorState>(emptyEditor);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [newUser, setNewUser] = useState({ username: "", password: "ChangeMe123", display_name: "", email: "", role: "member" });
  const [userEdits, setUserEdits] = useState<Record<number, { display_name: string; email: string; role: string; status: string; password: string }>>({});
  const [newProject, setNewProject] = useState({ name: "", description: "", is_sensitive: false, approval_enabled: true, owner_user_id: "" });
  const [projectEdit, setProjectEdit] = useState({ name: "", description: "", is_sensitive: false, approval_enabled: true, owner_user_id: "", status: "active" });
  const [memberDraft, setMemberDraft] = useState({ user_id: "", project_role: "member", can_read: true, can_write: true, can_review: false, can_manage: false });
  const [newGroup, setNewGroup] = useState({ name: "", description: "", leader_user_id: "" });
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [groupDraft, setGroupDraft] = useState({ user_id: "", group_role: "member" });
  const [fileEdits, setFileEdits] = useState<Record<number, string>>({});
  const [auditFilters, setAuditFilters] = useState({ actor_user_id: "", project_id: "", action: "", date_from: "", date_to: "" });
  const [approvalComment, setApprovalComment] = useState("");
  const [fileReviewComment, setFileReviewComment] = useState("");
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [ragQuestion, setRagQuestion] = useState("");
  const [ragMode, setRagMode] = useState("auto");
  const [ragAnswer, setRagAnswer] = useState<RagQueryResponse | null>(null);
  const [queryLogs, setQueryLogs] = useState<AIQueryLog[]>([]);
  const [queryAnalytics, setQueryAnalytics] = useState<AIQueryAnalytics | null>(null);
  const [experimentRuns, setExperimentRuns] = useState<AIExperimentRun[]>([]);
  const [experimentDraft, setExperimentDraft] = useState({
    name: "普通 RAG 与图谱增强 RAG 对照实验",
    questions: "PCR 实验用了哪些关键试剂？\nPCR 实验的关键结果是什么？",
  });
  const [experimentBusy, setExperimentBusy] = useState(false);
  const [evaluationDrafts, setEvaluationDrafts] = useState<Record<number, {
    score: string;
    is_accurate: boolean | null;
    is_traceable: boolean | null;
    comment: string;
  }>>({});
  const [ragBusy, setRagBusy] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [agentRun, setAgentRun] = useState<AgentGenerationRun | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentGenerationRun[]>([]);
  const [agentDraft, setAgentDraft] = useState({ task_type: "experiment_summary", date_from: "", date_to: "" });
  const [agentBusy, setAgentBusy] = useState(false);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [notifList, setNotifList] = useState<Notification[]>([]);
  const [ocrResult, setOcrResult] = useState<string | null>(null);
  const [kgGraph, setKgGraph] = useState<KnowledgeGraph | null>(null);
  const [kgEntityFilter, setKgEntityFilter] = useState("");
  const [kgRelationFilter, setKgRelationFilter] = useState("");
  const [selectedKgEntityId, setSelectedKgEntityId] = useState<number | null>(null);
  const [kgBusy, setKgBusy] = useState(false);

  // ── Derived state ──
  const selectedProject = useMemo(() => projects.find((p) => p.id === selectedProjectId) || null, [projects, selectedProjectId]);
  const selectedGroup = useMemo(() => groups.find((g) => g.id === selectedGroupId) || null, [groups, selectedGroupId]);
  const selectedTemplate = useMemo(() => templates.find((t) => t.id === editor.template_id) || null, [templates, editor.template_id]);
  const canAdmin = user?.role === "super_admin";
  const usersById = useMemo(() => new Map(users.map((u) => [u.id, u])), [users]);
  const currentProjectMember = useMemo(() => members.find((m) => m.user_id === user?.id) || null, [members, user?.id]);
  const canManageSelectedProject = Boolean(
    canAdmin ||
      (user && selectedProject?.owner_user_id === user.id) ||
      (currentProjectMember && (currentProjectMember.can_manage || currentProjectMember.project_role === "owner")),
  );
  const canWriteSelectedProject = Boolean(canAdmin || canManageSelectedProject || currentProjectMember?.can_write);
  const canReviewSelectedProject = Boolean(canAdmin || canManageSelectedProject || currentProjectMember?.can_review);
  const canSubmitSelectedNote = Boolean(selectedNote && user && selectedNote.owner_user_id === user.id && ["draft", "returned"].includes(selectedNote.status));
  const experimentTypes = useMemo(() => Array.from(new Set(notes.map((n) => n.experiment_type))).filter(Boolean), [notes]);
  const projectAuditLogs = useMemo(
    () => auditLogs.filter((log) => !selectedProjectId || log.project_id === selectedProjectId),
    [auditLogs, selectedProjectId],
  );
  const filteredNotes = useMemo(() => {
    const kw = noteFilters.keyword.trim().toLowerCase();
    return notes.filter((n) => {
      if (kw && !n.title.toLowerCase().includes(kw) && !n.experiment_type.toLowerCase().includes(kw)) return false;
      if (noteFilters.status && n.status !== noteFilters.status) return false;
      if (noteFilters.experiment_type && n.experiment_type !== noteFilters.experiment_type) return false;
      return true;
    });
  }, [notes, noteFilters]);
  const filteredFiles = useMemo(() => {
    const kw = fileFilters.keyword.trim().toLowerCase();
    return files.filter((f) => {
      if (kw && !f.original_filename.toLowerCase().includes(kw) && !f.file_hash.toLowerCase().includes(kw)) return false;
      if (fileFilters.category && f.file_category !== fileFilters.category) return false;
      if (fileFilters.status && f.status !== fileFilters.status) return false;
      return true;
    });
  }, [files, fileFilters]);
  const kgEntityById = useMemo(() => new Map((kgGraph?.entities || []).map((e) => [e.id, e])), [kgGraph]);
  const kgEntityTypeOptions = useMemo(
    () => Array.from(new Set((kgGraph?.entities || []).map((e) => e.entity_type))).sort((a, b) => kgTypeLabel(a).localeCompare(kgTypeLabel(b), "zh-CN")),
    [kgGraph],
  );
  const kgRelationTypeOptions = useMemo(
    () => Array.from(new Set((kgGraph?.relations || []).map((r) => r.relation_type))).sort((a, b) => kgRelationLabel(a).localeCompare(kgRelationLabel(b), "zh-CN")),
    [kgGraph],
  );
  const filteredKgRelationsByBoth = useMemo(() => {
    return (kgGraph?.relations || []).filter((r) => {
      if (kgRelationFilter && r.relation_type !== kgRelationFilter) return false;
      if (!kgEntityFilter) return true;
      const s = kgEntityById.get(r.source_entity_id);
      const t = kgEntityById.get(r.target_entity_id);
      return s?.entity_type === kgEntityFilter || t?.entity_type === kgEntityFilter;
    });
  }, [kgEntityById, kgEntityFilter, kgGraph, kgRelationFilter]);
  const filteredKgEntities = useMemo(() => {
    if (!kgEntityFilter && !kgRelationFilter) return kgGraph?.entities || [];
    const relatedIds = new Set<number>();
    filteredKgRelationsByBoth.forEach((r) => { relatedIds.add(r.source_entity_id); relatedIds.add(r.target_entity_id); });
    return (kgGraph?.entities || []).filter(
      (e) => relatedIds.has(e.id) || (!kgRelationFilter && e.entity_type === kgEntityFilter),
    );
  }, [filteredKgRelationsByBoth, kgEntityFilter, kgGraph, kgRelationFilter]);
  const selectedKgEntity = useMemo(
    () => (selectedKgEntityId ? kgEntityById.get(selectedKgEntityId) || null : null),
    [kgEntityById, selectedKgEntityId],
  );
  const selectedKgEntityRelations = useMemo(
    () => selectedKgEntity
      ? (kgGraph?.relations || []).filter((r) => r.source_entity_id === selectedKgEntity.id || r.target_entity_id === selectedKgEntity.id)
      : [],
    [kgGraph, selectedKgEntity],
  );
  const kgEntityStats = useMemo(() => {
    const counts: Record<string, number> = {};
    (kgGraph?.entities || []).forEach((e) => { counts[e.entity_type] = (counts[e.entity_type] || 0) + 1; });
    return Object.entries(counts).sort(([a], [b]) => kgTypeLabel(a).localeCompare(kgTypeLabel(b), "zh-CN"));
  }, [kgGraph]);
  const kgLayout = useMemo(() => {
    const typePriority: Record<string, number> = { project: 0, note: 1, experiment_type: 2, result: 3, reagent: 4, instrument: 5, sample: 6, user: 7, file: 8 };
    const degreeById = new Map<number, number>();
    filteredKgRelationsByBoth.forEach((r) => {
      degreeById.set(r.source_entity_id, (degreeById.get(r.source_entity_id) || 0) + 1);
      degreeById.set(r.target_entity_id, (degreeById.get(r.target_entity_id) || 0) + 1);
    });
    const ranked = [...filteredKgEntities].sort(
      (a, b) => (typePriority[a.entity_type] ?? 99) - (typePriority[b.entity_type] ?? 99) || (degreeById.get(b.id) || 0) - (degreeById.get(a.id) || 0) || a.id - b.id,
    );
    const projectEntity = ranked.find((e) => e.entity_type === "project");
    const inner = ranked.filter((e) => e.entity_type === "note").sort((a, b) => (degreeById.get(b.id) || 0) - (degreeById.get(a.id) || 0)).slice(0, 6);
    const selectedIds = new Set(inner.map((e) => e.id));
    if (projectEntity) selectedIds.add(projectEntity.id);
    const outerQuotas: Array<[string, number]> = [["user", 1], ["experiment_type", 2], ["reagent", 2], ["instrument", 1], ["sample", 1], ["result", 2]];
    const outer = outerQuotas.flatMap(([et, limit]) =>
      ranked.filter((e) => e.entity_type === et && !selectedIds.has(e.id)).sort((a, b) => (degreeById.get(b.id) || 0) - (degreeById.get(a.id) || 0)).slice(0, limit),
    );
    const cx = 400, cy = 250;
    const nodes: Array<{ entity: KnowledgeEntity; x: number; y: number }> = [];
    if (projectEntity) nodes.push({ entity: projectEntity, x: cx, y: cy });
    inner.forEach((e, i) => {
      const angle = (Math.PI * 2 * i) / Math.max(inner.length, 1) - Math.PI / 2;
      nodes.push({ entity: e, x: cx + Math.cos(angle) * 165, y: cy + Math.sin(angle) * 105 });
    });
    outer.forEach((e, i) => {
      const angle = (Math.PI * 2 * i) / Math.max(outer.length, 1) - Math.PI / 2 + Math.PI / 14;
      nodes.push({ entity: e, x: cx + Math.cos(angle) * 330, y: cy + Math.sin(angle) * 205 });
    });
    const nodeIds = new Set(nodes.map((n) => n.entity.id));
    const rels = filteredKgRelationsByBoth
      .filter((r) => nodeIds.has(r.source_entity_id) && nodeIds.has(r.target_entity_id))
      .sort((a, b) => Number(b.source_entity_id === projectEntity?.id || b.target_entity_id === projectEntity?.id) - Number(a.source_entity_id === projectEntity?.id || a.target_entity_id === projectEntity?.id))
      .slice(0, 36);
    const nodeById = new Map(nodes.map((n) => [n.entity.id, n]));
    return { nodes, relations: rels, nodeById };
  }, [filteredKgEntities, filteredKgRelationsByBoth]);

  // ── refreshAll ──
  async function refreshAll(activeToken = token, projectId = selectedProjectId) {
    if (!activeToken) return;
    setError("");
    try {
      const [projectItems, templateItems, pendingItems] = await Promise.all([
        getProjects(activeToken), getTemplates(activeToken), getPendingApprovals(activeToken).catch(() => []),
      ]);
      setProjects(projectItems); setTemplates(templateItems); setPendingNotes(pendingItems);
      const nextProjectId = projectId || projectItems[0]?.id || null;
      setSelectedProjectId(nextProjectId);
      const userItems = await getUsers(activeToken).catch(() => []);
      setUsers(userItems);
      if (user?.role === "super_admin") {
        const [groupItems, auditItems] = await Promise.all([
          getGroups(activeToken).catch(() => []), getAuditLogs(activeToken, auditFilters).catch(() => []),
        ]);
        setGroups(groupItems); setAuditLogs(auditItems);
        const nextGroupId = selectedGroupId || groupItems[0]?.id || null;
        setSelectedGroupId(nextGroupId);
        if (nextGroupId) { setGroupMembers(await getGroupMembers(activeToken, nextGroupId).catch(() => [])); }
        else { setGroupMembers([]); }
      }
      if (nextProjectId) {
        const [noteItems, fileItems, memberItems, ragStatusItem, kgGraphItem, queryLogItems, queryAnalyticsItem, experimentItems, agentRunItems] = await Promise.all([
          getProjectNotes(activeToken, nextProjectId), getProjectFiles(activeToken, nextProjectId),
          getProjectMembers(activeToken, nextProjectId).catch(() => []),
          getProjectRagStatus(activeToken, nextProjectId).catch(() => null),
          getProjectKnowledgeGraph(activeToken, nextProjectId).catch(() => null),
          getProjectQueryLogs(activeToken, nextProjectId).catch(() => []),
          getProjectQueryAnalytics(activeToken, nextProjectId).catch(() => null),
          getRagExperiments(activeToken, nextProjectId).catch(() => []),
          getAgentRuns(activeToken, nextProjectId).catch(() => []),
        ]);
        setNotes(noteItems); setFiles(fileItems); setMembers(memberItems);
        setRagStatus(ragStatusItem); setKgGraph(kgGraphItem);
        setQueryLogs(queryLogItems); setQueryAnalytics(queryAnalyticsItem);
        setExperimentRuns(experimentItems); setAgentRuns(agentRunItems);
        setAgentRun(agentRunItems[0] || null);
      } else {
        setKgGraph(null); setQueryLogs([]); setQueryAnalytics(null);
        setExperimentRuns([]); setAgentRuns([]); setAgentRun(null);
      }
      getDashboardSummary(activeToken).then(setDashboardSummary).catch(() => {});
      getNotifications(activeToken).then(setNotifList).catch(() => {});
    } catch (err) { setError(err instanceof Error ? err.message : "刷新失败"); }
  }

  // ── Effects ──
  useEffect(() => {
    if (selectedProject) {
      setProjectEdit({
        name: selectedProject.name, description: selectedProject.description || "",
        is_sensitive: selectedProject.is_sensitive, approval_enabled: selectedProject.approval_enabled,
        owner_user_id: selectedProject.owner_user_id ? String(selectedProject.owner_user_id) : "",
        status: selectedProject.status,
      });
    }
  }, [selectedProject]);

  useEffect(() => {
    if (token && selectedGroupId && canAdmin) {
      getGroupMembers(token, selectedGroupId).then(setGroupMembers).catch(() => setGroupMembers([]));
    }
  }, [token, selectedGroupId, canAdmin]);

  useEffect(() => {
    const savedToken = window.localStorage.getItem("eln_token") || "";
    if (!savedToken) return;
    setToken(savedToken);
    getMe(savedToken).then(setUser).catch(() => window.localStorage.removeItem("eln_token"));
  }, []);

  useEffect(() => { if (token && user) void refreshAll(token, selectedProjectId); }, [token, user?.id]);
  useEffect(() => { if (token && selectedProjectId) void refreshAll(token, selectedProjectId); }, [selectedProjectId]);

  // ── Auth handlers ──
  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError("");
    try {
      const result = await login(username, password);
      window.localStorage.setItem("eln_token", result.access_token);
      setToken(result.access_token); setUser(await getMe(result.access_token));
    } catch (err) { setError(err instanceof Error ? err.message : "登录失败"); }
  }

  function logout() {
    if (token) void logoutSession(token).catch(() => undefined);
    window.localStorage.removeItem("eln_token");
    setToken(""); setUser(null); setProjects([]); setNotes([]);
  }

  // ── Note handlers ──
  function applyTemplate(templateId: number) {
    const t = templates.find((item) => item.id === templateId);
    if (!t) return;
    const fields = Object.fromEntries((t.schema_json.fields || []).map((f) => [f.key, editor.fixed_fields_json[f.key] || ""]));
    setEditor({ ...editor, template_id: t.id, experiment_type: t.experiment_type, fixed_fields_json: fields, content_text: editor.content_text || "请记录实验过程、关键观察、结果分析和下一步计划。" });
  }

  function editNote(note: Note) {
    setSelectedNote(note);
    Promise.all([getNoteVersions(token, note.id), getNoteApprovals(token, note.id)]).then(([v, a]) => {
      setVersions(v); setApprovals(a);
      const latest = v[0];
      setEditor({
        id: note.id, title: note.title, experiment_type: note.experiment_type,
        experiment_date: note.experiment_date || new Date().toISOString().slice(0, 10),
        template_id: note.template_id,
        fixed_fields_json: latest?.fixed_fields_json || {},
        content_text: typeof latest?.content_json?.text === "string" ? latest.content_json.text : "",
      });
    });
  }

  async function afterNoteAction(action: Promise<Note>, successMessage: string) {
    try {
      const note = await action;
      setMessage(successMessage); setApprovalComment("");
      await refreshAll(token, note.project_id); editNote(note);
    } catch (err) { setError(err instanceof Error ? err.message : "操作失败"); }
  }

  async function saveNote(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId) return;
    if (!canWriteSelectedProject) { setError("当前账号没有项目写入权限"); return; }
    setMessage("");
    const payload = {
      title: editor.title, experiment_type: editor.experiment_type, experiment_date: editor.experiment_date,
      template_id: editor.template_id, fixed_fields_json: editor.fixed_fields_json,
      content_json: { text: editor.content_text }, change_summary: "前端编辑保存",
    };
    try {
      const note = editor.id ? await updateNote(token, editor.id, payload) : await createNote(token, selectedProjectId, payload);
      setSelectedNote(note); setEditor({ ...editor, id: note.id });
      setMessage(note.status === "approved" ? "实验笔记已保存，已审核内容将同步更新知识图谱" : "实验笔记已保存；草稿不会进入知识图谱，审核通过后自动抽取");
      await refreshAll(); editNote(note);
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  }

  // ── CRUD handlers ──
  async function handleCreateUser(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await createUser(token, { ...newUser, email: newUser.email || undefined });
    setNewUser({ username: "", password: "ChangeMe123", display_name: "", email: "", role: "member" });
    setMessage("用户已创建"); await refreshAll();
  }

  async function handleUpdateUser(userItem: User) {
    const draft = userEdits[userItem.id] || { display_name: userItem.display_name, email: userItem.email || "", role: userItem.role, status: userItem.status, password: "" };
    await updateUser(token, userItem.id, { display_name: draft.display_name, email: draft.email || null, role: draft.role, status: draft.status, ...(draft.password ? { password: draft.password } : {}) });
    setMessage("用户已更新"); setUserEdits((cur) => ({ ...cur, [userItem.id]: { ...draft, password: "" } })); await refreshAll();
  }

  async function handleCreateProject(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await createProject(token, { ...newProject, owner_user_id: newProject.owner_user_id ? Number(newProject.owner_user_id) : null });
    setNewProject({ name: "", description: "", is_sensitive: false, approval_enabled: true, owner_user_id: "" });
    setMessage("项目已创建"); await refreshAll();
  }

  async function handleUpdateProject(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId) return;
    await updateProject(token, selectedProjectId, { name: projectEdit.name, description: projectEdit.description, is_sensitive: projectEdit.is_sensitive, approval_enabled: projectEdit.approval_enabled, owner_user_id: projectEdit.owner_user_id ? Number(projectEdit.owner_user_id) : null, status: projectEdit.status });
    setMessage("项目已更新"); await refreshAll(token, selectedProjectId);
  }

  async function handleAddMember(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId) return;
    await addProjectMember(token, selectedProjectId, { ...memberDraft, user_id: Number(memberDraft.user_id) });
    setMemberDraft({ user_id: "", project_role: "member", can_read: true, can_write: true, can_review: false, can_manage: false });
    setMessage("项目成员已授权"); await refreshAll();
  }

  async function handleUpdateMember(member: ProjectMember, payload: Partial<ProjectMember>) {
    if (!selectedProjectId) return;
    await updateProjectMember(token, selectedProjectId, member.user_id, payload);
    setMessage("项目成员权限已更新"); await refreshAll(token, selectedProjectId);
  }

  async function handleRemoveMember(member: ProjectMember) {
    if (!selectedProjectId) return;
    await removeProjectMember(token, selectedProjectId, member.user_id);
    setMessage("项目成员已移除"); await refreshAll(token, selectedProjectId);
  }

  async function handleCreateGroup(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const group = await createGroup(token, { name: newGroup.name, description: newGroup.description || undefined, leader_user_id: newGroup.leader_user_id ? Number(newGroup.leader_user_id) : null });
    setNewGroup({ name: "", description: "", leader_user_id: "" }); setSelectedGroupId(group.id);
    setMessage("小组已创建"); await refreshAll();
  }

  async function handleUpdateGroup() {
    if (!selectedGroup) return;
    await updateGroup(token, selectedGroup.id, { name: selectedGroup.name, description: selectedGroup.description, leader_user_id: selectedGroup.leader_user_id });
    setMessage("小组已更新"); await refreshAll();
  }

  async function handleAddGroupMember(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedGroupId) return;
    await addGroupMember(token, selectedGroupId, { user_id: Number(groupDraft.user_id), group_role: groupDraft.group_role });
    setGroupDraft({ user_id: "", group_role: "member" }); setMessage("小组成员已更新"); await refreshAll();
  }

  async function handleAuditSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAuditLogs(await getAuditLogs(token, auditFilters));
  }

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canWriteSelectedProject) { setError("当前账号没有文件上传权限"); return; }
    const input = e.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !selectedProjectId) return;
    await uploadFile(token, selectedProjectId, file, selectedNote?.id, selectedNote ? "note_attachment" : "knowledge_document");
    input.value = ""; setMessage("文件已上传"); await refreshAll();
  }

  async function handleDownload(file: StoredFile) {
    const response = await fetch(fileDownloadUrl(file.id), { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setError("下载失败"); return; }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = file.original_filename; link.click();
    window.URL.revokeObjectURL(url);
  }

  async function handleUpdateFile(file: StoredFile) {
    if (!canWriteSelectedProject) { setError("当前账号没有文件维护权限"); return; }
    const nextName = (fileEdits[file.id] ?? file.original_filename).trim();
    if (!nextName || nextName === file.original_filename) return;
    await updateFile(token, file.id, { original_filename: nextName });
    setMessage("文件元信息已更新"); await refreshAll();
  }

  async function handleArchiveFile(file: StoredFile) {
    if (!canWriteSelectedProject) { setError("当前账号没有文件归档权限"); return; }
    await archiveFile(token, file.id); setMessage("文件已归档"); await refreshAll();
  }

  async function handleReviewFile(fileId: number, action: "approve" | "reject", comment: string) {
    await reviewFile(token, fileId, action, comment); await refreshAll();
  }

  // ── RAG handlers ──
  async function handleInitRag() {
    if (!selectedProjectId || !canReviewSelectedProject) return;
    setRagBusy(true); setError("");
    try { const ns = await initProjectRag(token, selectedProjectId); setRagStatus(ns); setMessage("AI 知识库已初始化"); }
    catch (err) { setError(err instanceof Error ? err.message : "初始化 AI 知识库失败"); }
    finally { setRagBusy(false); }
  }

  async function handleSyncRagFile(file: StoredFile) {
    if (!canReviewSelectedProject) return;
    setRagBusy(true); setError("");
    try { const ns = await syncFileToRag(token, file.id); setRagStatus(ns); setMessage("资料已同步到 AI 知识库"); await refreshAll(token, file.project_id); }
    catch (err) { setError(err instanceof Error ? err.message : "同步资料失败"); await refreshAll(token, file.project_id); }
    finally { setRagBusy(false); }
  }

  async function handleQueryRag(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId || !ragQuestion.trim()) return;
    setRagBusy(true); setError("");
    try {
      const result = await queryProjectRag(token, selectedProjectId, ragQuestion, ragMode);
      setRagAnswer(result);
      const [nl, na] = await Promise.all([
        getProjectQueryLogs(token, selectedProjectId).catch(() => []),
        getProjectQueryAnalytics(token, selectedProjectId).catch(() => null),
      ]);
      setQueryLogs(nl); setQueryAnalytics(na);
    } catch (err) { setError(err instanceof Error ? err.message : "AI 查询失败"); }
    finally { setRagBusy(false); }
  }

  async function handleEvaluateQueryLog(log: AIQueryLog) {
    const draft = evaluationDrafts[log.id] || { score: log.evaluation ? String(log.evaluation.score) : "", is_accurate: log.evaluation?.is_accurate ?? null, is_traceable: log.evaluation?.is_traceable ?? null, comment: log.evaluation?.comment || "" };
    if (!selectedProjectId) return;
    if (!draft.score || draft.is_accurate === null || draft.is_traceable === null) { setError("请完整选择评分、准确性和可追溯性后再保存"); return; }
    setRagBusy(true); setError("");
    try {
      await evaluateQueryLog(token, log.id, { score: Number(draft.score), is_accurate: draft.is_accurate, is_traceable: draft.is_traceable, comment: draft.comment || null });
      const [nl, na] = await Promise.all([getProjectQueryLogs(token, selectedProjectId), getProjectQueryAnalytics(token, selectedProjectId).catch(() => null)]);
      setQueryLogs(nl); setQueryAnalytics(na); setMessage("问答评价已保存");
    } catch (err) { setError(err instanceof Error ? err.message : "保存评价失败"); }
    finally { setRagBusy(false); }
  }

  async function handleRunRagExperiment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId || !canReviewSelectedProject) return;
    const questions = experimentDraft.questions.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (questions.length === 0) { setError("请至少输入一个实验问题，每行一个"); return; }
    setExperimentBusy(true); setError("");
    try {
      const run = await runRagExperiment(token, selectedProjectId, { name: experimentDraft.name, questions, modes: ["project_rag", "kg_enhanced_rag"] });
      const [runs, logs, analytics] = await Promise.all([getRagExperiments(token, selectedProjectId), getProjectQueryLogs(token, selectedProjectId), getProjectQueryAnalytics(token, selectedProjectId)]);
      setExperimentRuns(runs); setQueryLogs(logs); setQueryAnalytics(analytics);
      setMessage(`对照实验 #${run.id} 已完成：成功 ${run.completed_cases}，失败 ${run.failed_cases}`);
    } catch (err) { setError(err instanceof Error ? err.message : "运行对照实验失败"); }
    finally { setExperimentBusy(false); }
  }

  async function handleDownloadRagExperiment(run: AIExperimentRun) {
    setError("");
    try {
      const blob = await downloadRagExperiment(token, run.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `rag-experiment-${run.id}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : "导出实验结果失败"); }
  }

  // ── Search handler ──
  async function handleSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedProjectId || !searchQuery.trim()) return;
    setSearchBusy(true); setError("");
    try { await reindexSearch(token, selectedProjectId); const r = await searchDocuments(token, searchQuery, selectedProjectId); setSearchResults(r); setMessage("搜索完成"); }
    catch (err) { setError(err instanceof Error ? err.message : "搜索失败"); }
    finally { setSearchBusy(false); }
  }

  // ── Agent handler ──
  async function handleGenerateAgent() {
    if (!selectedProjectId) return;
    setAgentBusy(true); setError("");
    try {
      const run = await generateAgentOutput(token, { project_id: selectedProjectId, task_type: agentDraft.task_type, date_from: agentDraft.date_from || null, date_to: agentDraft.date_to || null });
      setAgentRun(run); setAgentRuns(await getAgentRuns(token, selectedProjectId).catch(() => [run])); setMessage("智能体生成结果已保存");
    } catch (err) { setError(err instanceof Error ? err.message : "智能生成失败"); }
    finally { setAgentBusy(false); }
  }

  // ── OCR handler ──
  async function handleOcrExtract(file: StoredFile) {
    setError("");
    try { const r = await extractOcr(token, file.id); setOcrResult(r.extracted_text); setMessage(`OCR 提取完成：${r.extracted_text.length} 字符`); }
    catch (err) { setError(err instanceof Error ? err.message : "OCR 提取失败"); }
  }

  // ── KG handlers ──
  async function refreshKnowledgeGraph(projectId = selectedProjectId) {
    if (!projectId) return;
    setKgBusy(true); setError("");
    try { setKgGraph(await getProjectKnowledgeGraph(token, projectId)); }
    catch (err) { setError(err instanceof Error ? err.message : "知识图谱加载失败"); }
    finally { setKgBusy(false); }
  }

  async function handleExtractSelectedNoteKg(note?: Note) {
    const target = note ?? selectedNote;
    if (!target || !canWriteSelectedProject) return;
    setKgBusy(true); setError("");
    try {
      const run = await extractNoteKnowledgeGraph(token, target.id, true);
      setMessage(`已抽取当前笔记图谱：${run.extracted_entities} 个实体，${run.extracted_relations} 条关系`);
      await refreshKnowledgeGraph(run.project_id);
    } catch (err) { setError(err instanceof Error ? err.message : "当前笔记图谱抽取失败"); }
    finally { setKgBusy(false); }
  }

  async function handleRebuildProjectKg() {
    if (!selectedProjectId || !canWriteSelectedProject) return;
    setKgBusy(true); setError("");
    try {
      const runs = await rebuildProjectKnowledgeGraph(token, selectedProjectId);
      const ec = runs.reduce((s, r) => s + r.extracted_entities, 0);
      const rc = runs.reduce((s, r) => s + r.extracted_relations, 0);
      setMessage(`项目图谱已重建：${runs.length} 篇笔记，${ec} 个实体，${rc} 条关系`);
      await refreshKnowledgeGraph(selectedProjectId);
    } catch (err) { setError(err instanceof Error ? err.message : "项目知识图谱重建失败"); }
    finally { setKgBusy(false); }
  }

  // ── Wrapped callbacks for child components ──
  const handleApprove = (noteId: number, comment: string) => { void afterNoteAction(approveNote(token, noteId, comment), "实验笔记已通过"); };
  const handleReturn = (noteId: number, comment: string) => { void afterNoteAction(returnNote(token, noteId, comment), "实验笔记已退回"); };
  const handleSubmitNote = () => { if (selectedNote) void afterNoteAction(submitNote(token, selectedNote.id), "实验笔记已提交审批"); };
  const handleArchiveNote = () => { if (selectedNote) void afterNoteAction(archiveNote(token, selectedNote.id), "实验笔记已归档"); };
  const handleVoidNote = () => { if (selectedNote) void afterNoteAction(voidNote(token, selectedNote.id, approvalComment), "实验笔记已作废"); };
  const handleNewNote = () => { setSelectedNote(null); setVersions([]); setApprovals([]); setEditor(emptyEditor); };
  const handleRefreshQueryLogs = () => {
    if (selectedProjectId) {
      Promise.all([getProjectQueryLogs(token, selectedProjectId).catch(() => []), getProjectQueryAnalytics(token, selectedProjectId).catch(() => null)])
        .then(([nl, na]) => { setQueryLogs(nl); setQueryAnalytics(na); });
    }
  };
  const handleEvaluationDraftChange = (logId: number, draft: { score: string; is_accurate: boolean | null; is_traceable: boolean | null; comment: string }) => {
    setEvaluationDrafts((cur) => ({ ...cur, [logId]: draft }));
  };
  const handleAddReviewer = (member: ProjectMember) => {
    if (selectedProjectId) void addProjectReviewer(token, selectedProjectId, { user_id: member.user_id }).then(() => refreshAll(token, selectedProjectId));
  };
  const handleRemoveGroupMember = (groupId: number, userId: number) => { void removeGroupMember(token, groupId, userId).then(() => refreshAll()); };

  // ── Render: Login ──
  if (!user) {
    return (
      <LoginPage
        username={username}
        password={password}
        error={error}
        onUsernameChange={setUsername}
        onPasswordChange={setPassword}
        onSubmit={handleLogin}
      />
    );
  }

  // ── Render: Main App ──
  const projectPendingCount = pendingNotes.filter((n) => !selectedProjectId || n.project_id === selectedProjectId).length;

  return (
    <main className="min-h-screen bg-surface">
      <TopHeader user={user} token={token} onRefresh={() => void refreshAll()} onLogout={logout} />

      <div className="mx-auto grid min-w-0 max-w-[1440px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <WorkspaceSidebar
          workspaceView={workspaceView}
          projects={projects}
          groups={groups}
          users={users}
          selectedProjectId={selectedProjectId}
          selectedGroupId={selectedGroupId}
          canAdmin={canAdmin}
          onSetWorkspaceView={setWorkspaceView}
          onSetSelectedProjectId={setSelectedProjectId}
          onSetSelectedGroupId={setSelectedGroupId}
        />

        <section className="min-w-0 space-y-6">
          <MessageBanner message={message} error={error} />

          {/* ── Dashboard Metrics ── */}
          {workspaceView === "project" && (
            <DashboardMetrics
              notes={notes}
              pendingNotes={pendingNotes}
              files={files}
              ragInitialized={ragStatus?.initialized ?? false}
            />
          )}

          {/* ── Admin Workspace ── */}
          {canAdmin && workspaceView === "admin" && (
            <div className="space-y-4">
              <div className={cardClass("p-5")}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">系统管理</h2>
                    <p className="mt-1 text-sm text-muted">集中管理用户、小组、项目和审计记录，日常实验操作请回到项目工作台。</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:w-[520px]">
                    {[
                      { label: "用户", value: users.length },
                      { label: "项目", value: projects.length },
                      { label: "小组", value: groups.length },
                      { label: "审计", value: auditLogs.length },
                    ].map((item) => (
                      <div key={item.label} className="rounded-md border border-border bg-surface px-3 py-2">
                        <p className="text-xs text-muted">{item.label}</p>
                        <p className="mt-1 font-semibold">{item.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <UserCreatePanel newUser={newUser} onNewUserChange={setNewUser} onCreateUser={handleCreateUser} />

                <AdminProjectPanel
                  users={users}
                  newProject={newProject}
                  onNewProjectChange={setNewProject}
                  onCreateProject={handleCreateProject}
                />
              </div>

              {/* User Table (full width) */}
              <UserManagementPanel
                users={users}
                currentUser={user}
                userEdits={userEdits}
                onUserEditChange={(userId, edit) => setUserEdits({ ...userEdits, [userId]: edit })}
                onUpdateUser={handleUpdateUser}
                onDisableUser={(userId) => { void disableUser(token, userId).then(() => refreshAll()); }}
              />

              <GroupManagementPanel
                groups={groups}
                selectedGroup={selectedGroup}
                selectedGroupId={selectedGroupId}
                groupMembers={groupMembers}
                groupDraft={groupDraft}
                onGroupDraftChange={setGroupDraft}
                newGroup={newGroup}
                onNewGroupChange={setNewGroup}
                users={users}
                usersById={usersById}
                onSetSelectedGroupId={setSelectedGroupId}
                onSelectedGroupChange={(g) => setGroups(groups.map((gr) => gr.id === g.id ? g : gr))}
                onCreateGroup={handleCreateGroup}
                onUpdateGroup={handleUpdateGroup}
                onAddGroupMember={handleAddGroupMember}
                onRemoveGroupMember={handleRemoveGroupMember}
              />

              <AuditLogPanel
                auditLogs={auditLogs}
                auditFilters={auditFilters}
                onAuditFiltersChange={setAuditFilters}
                users={users}
                projects={projects}
                usersById={usersById}
                onSearch={handleAuditSearch}
              />
            </div>
          )}

          {/* ── Project Workspace ── */}
          {workspaceView === "project" && selectedProjectId && (
            <ProjectHeader
              selectedProject={selectedProject}
              activeProjectTab={activeProjectTab}
              onTabChange={setActiveProjectTab}
              kgEntityCount={kgGraph?.entities.length ?? 0}
              kgRelationCount={kgGraph?.relations.length ?? 0}
              queryLogCount={queryLogs.length}
              agentRunCount={agentRuns.length}
            />
          )}

          {/* ── Project Tabs ── */}
          {workspaceView === "project" && activeProjectTab === "overview" && (
            <ProjectOverview
              notes={notes}
              pendingNotes={pendingNotes}
              files={files}
              selectedProjectId={selectedProjectId}
              onNavigateNotes={(note) => { setActiveProjectTab("notes"); editNote(note); }}
              onNavigateApprovals={() => setActiveProjectTab("approvals")}
              onNavigateFiles={() => setActiveProjectTab("files")}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "notes" && (
            <NotesPanel
              editor={editor}
              onEditorChange={setEditor}
              selectedNote={selectedNote}
              selectedTemplate={selectedTemplate}
              templates={templates}
              notes={notes}
              filteredNotes={filteredNotes}
              noteFilters={noteFilters}
              onNoteFiltersChange={setNoteFilters}
              experimentTypes={experimentTypes}
              versions={versions}
              approvals={approvals}
              canWriteSelectedProject={canWriteSelectedProject}
              canReviewSelectedProject={canReviewSelectedProject}
              canSubmitSelectedNote={canSubmitSelectedNote}
              onSaveNote={saveNote}
              onEditNote={editNote}
              onNewNote={handleNewNote}
              onApplyTemplate={applyTemplate}
              onSubmitNote={handleSubmitNote}
              onArchiveNote={handleArchiveNote}
              onVoidNote={handleVoidNote}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "files" && (
            <FilesPanel
              ragStatus={ragStatus}
              ragQuestion={ragQuestion}
              onRagQuestionChange={setRagQuestion}
              ragMode={ragMode}
              onRagModeChange={setRagMode}
              ragAnswer={ragAnswer}
              ragBusy={ragBusy}
              queryLogs={queryLogs}
              queryAnalytics={queryAnalytics}
              experimentRuns={experimentRuns}
              experimentDraft={experimentDraft}
              onExperimentDraftChange={setExperimentDraft}
              experimentBusy={experimentBusy}
              evaluationDrafts={evaluationDrafts}
              onEvaluationDraftChange={handleEvaluationDraftChange}
              files={files}
              filteredFiles={filteredFiles}
              fileFilters={fileFilters}
              onFileFiltersChange={setFileFilters}
              fileEdits={fileEdits}
              onFileEditChange={(id, name) => setFileEdits({ ...fileEdits, [id]: name })}
              fileReviewComment={fileReviewComment}
              onFileReviewCommentChange={setFileReviewComment}
              ocrResult={ocrResult}
              selectedNote={selectedNote}
              selectedProjectId={selectedProjectId}
              canReviewSelectedProject={canReviewSelectedProject}
              canWriteSelectedProject={canWriteSelectedProject}
              onInitRag={handleInitRag}
              onSyncRagFile={handleSyncRagFile}
              onQueryRag={handleQueryRag}
              onEvaluateQueryLog={handleEvaluateQueryLog}
              onRunRagExperiment={handleRunRagExperiment}
              onDownloadRagExperiment={handleDownloadRagExperiment}
              onUpload={handleUpload}
              onDownload={handleDownload}
              onUpdateFile={handleUpdateFile}
              onArchiveFile={handleArchiveFile}
              onOcrExtract={handleOcrExtract}
              onReviewFile={handleReviewFile}
              onRefreshQueryLogs={handleRefreshQueryLogs}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "search" && (
            <SearchPanel
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              searchResults={searchResults}
              searchBusy={searchBusy}
              selectedProjectId={selectedProjectId}
              onSearch={handleSearch}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "kg" && selectedProjectId && (
            <KnowledgeGraphPanel
              kgGraph={kgGraph}
              kgBusy={kgBusy}
              kgEntityFilter={kgEntityFilter}
              onKgEntityFilterChange={setKgEntityFilter}
              kgRelationFilter={kgRelationFilter}
              onKgRelationFilterChange={setKgRelationFilter}
              selectedKgEntityId={selectedKgEntityId}
              onSelectedKgEntityIdChange={setSelectedKgEntityId}
              kgEntityTypeOptions={kgEntityTypeOptions}
              kgRelationTypeOptions={kgRelationTypeOptions}
              kgEntityStats={kgEntityStats}
              filteredKgEntities={filteredKgEntities}
              filteredKgRelations={filteredKgRelationsByBoth}
              selectedKgEntity={selectedKgEntity}
              selectedKgEntityRelations={selectedKgEntityRelations}
              kgEntityById={kgEntityById}
              notes={notes}
              selectedNote={selectedNote}
              canWriteSelectedProject={canWriteSelectedProject}
              kgLayout={kgLayout}
              onRefreshGraph={() => void refreshKnowledgeGraph()}
              onExtractNote={(note) => void handleExtractSelectedNoteKg(note)}
              onRebuildGraph={() => void handleRebuildProjectKg()}
              onNavigateNotes={(note) => { setActiveProjectTab("notes"); editNote(note); }}
              onNavigateFiles={() => setActiveProjectTab("files")}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "reports" && (
            <ReportsPanel
              agentDraft={agentDraft}
              onAgentDraftChange={setAgentDraft}
              agentRun={agentRun}
              onAgentRunSelect={setAgentRun}
              agentRuns={agentRuns}
              agentBusy={agentBusy}
              selectedProjectId={selectedProjectId}
              onGenerate={() => void handleGenerateAgent()}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "approvals" && (
            <ApprovalsPanel
              pendingNotes={pendingNotes}
              selectedProjectId={selectedProjectId}
              approvalComment={approvalComment}
              onApprovalCommentChange={setApprovalComment}
              canReviewSelectedProject={canReviewSelectedProject}
              onApprove={handleApprove}
              onReturn={handleReturn}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "members" && (
            <MembersPanel
              selectedProject={selectedProject}
              selectedProjectId={selectedProjectId}
              members={members}
              users={users}
              usersById={usersById}
              projectEdit={projectEdit}
              onProjectEditChange={setProjectEdit}
              memberDraft={memberDraft}
              onMemberDraftChange={setMemberDraft}
              canManageSelectedProject={canManageSelectedProject}
              onUpdateProject={handleUpdateProject}
              onAddMember={handleAddMember}
              onUpdateMember={handleUpdateMember}
              onRemoveMember={handleRemoveMember}
              onAddReviewer={handleAddReviewer}
            />
          )}

          {workspaceView === "project" && activeProjectTab === "logs" && (
            <ProjectLogsPanel
              auditLogs={projectAuditLogs}
              usersById={usersById}
              canAdmin={canAdmin}
            />
          )}
        </section>
      </div>
    </main>
  );
}
