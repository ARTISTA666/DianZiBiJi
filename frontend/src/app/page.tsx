"use client";

import {
  BarChart,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  FolderPlus,
  LayoutDashboard,
  Lock,
  LogOut,
  Paperclip,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";
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

const roleOptions = ["super_admin", "pi", "group_leader", "project_owner", "reviewer", "member"];
const projectRoleOptions = ["owner", "reviewer", "member", "viewer"];
const statusText: Record<string, string> = {
  draft: "草稿",
  submitted: "待审核",
  approved: "已审核",
  returned: "已退回",
  archived: "已归档",
  voided: "已作废",
};
const knowledgeSyncText: Record<string, string> = {
  not_applicable: "不入库",
  pending_review: "待资料审核",
  pending_sync: "待同步",
  synced: "已入库",
  failed: "同步失败",
};
const projectTabs = [
  { key: "overview", label: "项目概览", icon: Database },
  { key: "notes", label: "实验笔记", icon: FileText },
  { key: "files", label: "资料库", icon: Upload },
  { key: "search", label: "搜索", icon: FileSearch },
  { key: "kg", label: "知识图谱", icon: Sparkles },
  { key: "reports", label: "报告", icon: BarChart },
  { key: "approvals", label: "审批中心", icon: ClipboardCheck },
  { key: "members", label: "成员权限", icon: Users },
  { key: "logs", label: "项目日志", icon: ShieldCheck },
] as const;
type ProjectTab = (typeof projectTabs)[number]["key"];

const agentTaskOptions = [
  { value: "experiment_summary", label: "实验总结" },
  { value: "weekly_report", label: "周报" },
  { value: "stage_report", label: "项目阶段报告" },
  { value: "graph_overview", label: "实验过程图谱概览" },
];

type NoteEditorState = {
  id?: number;
  title: string;
  experiment_type: string;
  experiment_date: string;
  template_id: number | null;
  fixed_fields_json: Record<string, string>;
  content_text: string;
};

const emptyEditor: NoteEditorState = {
  title: "",
  experiment_type: "PCR",
  experiment_date: new Date().toISOString().slice(0, 10),
  template_id: null,
  fixed_fields_json: {},
  content_text: "",
};

const kgEntityTypeText: Record<string, string> = {
  project: "项目",
  note: "实验笔记",
  user: "人员",
  file: "附件资料",
  experiment_type: "实验类型",
  reagent: "试剂",
  instrument: "仪器",
  sample: "样本",
  result: "实验结果",
};

const kgRelationTypeText: Record<string, string> = {
  has_note: "包含笔记",
  created_by: "创建者",
  has_attachment: "关联附件",
  has_experiment_type: "实验类型",
  uses_reagent: "使用试剂",
  uses_instrument: "使用仪器",
  uses_sample: "使用样本",
  produces_result: "产生结果",
};

const kgEntityColors: Record<string, string> = {
  project: "#0f766e",
  note: "#2563eb",
  user: "#7c3aed",
  file: "#ea580c",
  experiment_type: "#0891b2",
  reagent: "#16a34a",
  instrument: "#9333ea",
  sample: "#ca8a04",
  result: "#dc2626",
};

const kgEntityShortText: Record<string, string> = {
  project: "项",
  note: "笔",
  user: "人",
  file: "附",
  experiment_type: "类",
  reagent: "试",
  instrument: "仪",
  sample: "样",
  result: "果",
};

function cardClass(extra = "") {
  return `rounded-md border border-border bg-white shadow-panel ${extra}`;
}

function kgTypeLabel(type: string) {
  return kgEntityTypeText[type] || type;
}

function kgRelationLabel(type: string) {
  return kgRelationTypeText[type] || type;
}

function shortLabel(label: string, maxLength = 14) {
  return label.length > maxLength ? `${label.slice(0, maxLength)}...` : label;
}

function ragModeLabel(mode: string) {
  if (mode === "kg_enhanced_rag") return "知识图谱增强 RAG";
  if (mode === "project_rag") return "项目级 RAG";
  return "自动选择";
}

function formatRate(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return `${Math.round(value * 100)}%`;
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return value.toFixed(2).replace(/\.00$/, "");
}

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

  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId) || null, [projects, selectedProjectId]);
  const selectedGroup = useMemo(() => groups.find((group) => group.id === selectedGroupId) || null, [groups, selectedGroupId]);
  const selectedTemplate = useMemo(() => templates.find((template) => template.id === editor.template_id) || null, [templates, editor.template_id]);
  const canAdmin = user?.role === "super_admin";
  const usersById = useMemo(() => new Map(users.map((item) => [item.id, item])), [users]);
  const currentProjectMember = useMemo(() => members.find((member) => member.user_id === user?.id) || null, [members, user?.id]);
  const canManageSelectedProject = Boolean(
    canAdmin ||
      (user && selectedProject?.owner_user_id === user.id) ||
      (currentProjectMember && (currentProjectMember.can_manage || currentProjectMember.project_role === "owner")),
  );
  const canWriteSelectedProject = Boolean(canAdmin || canManageSelectedProject || currentProjectMember?.can_write);
  const canReviewSelectedProject = Boolean(canAdmin || canManageSelectedProject || currentProjectMember?.can_review);
  const canSubmitSelectedNote = Boolean(selectedNote && user && selectedNote.owner_user_id === user.id && ["draft", "returned"].includes(selectedNote.status));
  const experimentTypes = useMemo(() => Array.from(new Set(notes.map((note) => note.experiment_type))).filter(Boolean), [notes]);
  const projectAuditLogs = useMemo(
    () => auditLogs.filter((log) => !selectedProjectId || log.project_id === selectedProjectId),
    [auditLogs, selectedProjectId],
  );
  const filteredNotes = useMemo(() => {
    const keyword = noteFilters.keyword.trim().toLowerCase();
    return notes.filter((note) => {
      const matchesKeyword = !keyword || note.title.toLowerCase().includes(keyword) || note.experiment_type.toLowerCase().includes(keyword);
      const matchesStatus = !noteFilters.status || note.status === noteFilters.status;
      const matchesType = !noteFilters.experiment_type || note.experiment_type === noteFilters.experiment_type;
      return matchesKeyword && matchesStatus && matchesType;
    });
  }, [notes, noteFilters]);
  const filteredFiles = useMemo(() => {
    const keyword = fileFilters.keyword.trim().toLowerCase();
    return files.filter((file) => {
      const matchesKeyword = !keyword || file.original_filename.toLowerCase().includes(keyword) || file.file_hash.toLowerCase().includes(keyword);
      const matchesCategory = !fileFilters.category || file.file_category === fileFilters.category;
      const matchesStatus = !fileFilters.status || file.status === fileFilters.status;
      return matchesKeyword && matchesCategory && matchesStatus;
    });
  }, [files, fileFilters]);
  const kgEntityById = useMemo(() => new Map((kgGraph?.entities || []).map((entity) => [entity.id, entity])), [kgGraph]);
  const kgEntityTypeOptions = useMemo(
    () => Array.from(new Set((kgGraph?.entities || []).map((entity) => entity.entity_type))).sort((left, right) => kgTypeLabel(left).localeCompare(kgTypeLabel(right), "zh-CN")),
    [kgGraph],
  );
  const kgRelationTypeOptions = useMemo(
    () => Array.from(new Set((kgGraph?.relations || []).map((relation) => relation.relation_type))).sort((left, right) => kgRelationLabel(left).localeCompare(kgRelationLabel(right), "zh-CN")),
    [kgGraph],
  );
  const filteredKgRelations = useMemo(() => {
    return (kgGraph?.relations || []).filter((relation) => {
      const matchesType = !kgRelationFilter || relation.relation_type === kgRelationFilter;
      if (!matchesType) return false;
      if (!kgEntityFilter) return true;
      const source = kgEntityById.get(relation.source_entity_id);
      const target = kgEntityById.get(relation.target_entity_id);
      return source?.entity_type === kgEntityFilter || target?.entity_type === kgEntityFilter;
    });
  }, [kgEntityById, kgEntityFilter, kgGraph, kgRelationFilter]);
  const filteredKgEntities = useMemo(() => {
    if (!kgEntityFilter && !kgRelationFilter) return kgGraph?.entities || [];
    const relatedIds = new Set<number>();
    filteredKgRelations.forEach((relation) => {
      relatedIds.add(relation.source_entity_id);
      relatedIds.add(relation.target_entity_id);
    });
    return (kgGraph?.entities || []).filter(
      (entity) => relatedIds.has(entity.id) || (!kgRelationFilter && entity.entity_type === kgEntityFilter),
    );
  }, [filteredKgRelations, kgEntityFilter, kgGraph, kgRelationFilter]);
  const selectedKgEntity = useMemo(
    () => (selectedKgEntityId ? kgEntityById.get(selectedKgEntityId) || null : null),
    [kgEntityById, selectedKgEntityId],
  );
  const selectedKgEntityRelations = useMemo(
    () =>
      selectedKgEntity
        ? (kgGraph?.relations || []).filter(
            (relation) => relation.source_entity_id === selectedKgEntity.id || relation.target_entity_id === selectedKgEntity.id,
          )
        : [],
    [kgGraph, selectedKgEntity],
  );
  const kgEntityStats = useMemo(() => {
    const counts: Record<string, number> = {};
    (kgGraph?.entities || []).forEach((entity) => {
      counts[entity.entity_type] = (counts[entity.entity_type] || 0) + 1;
    });
    return Object.entries(counts).sort(([left], [right]) => kgTypeLabel(left).localeCompare(kgTypeLabel(right), "zh-CN"));
  }, [kgGraph]);
  const kgLayout = useMemo(() => {
    const typePriority: Record<string, number> = {
      project: 0,
      note: 1,
      experiment_type: 2,
      result: 3,
      reagent: 4,
      instrument: 5,
      sample: 6,
      user: 7,
      file: 8,
    };
    const degreeById = new Map<number, number>();
    filteredKgRelations.forEach((relation) => {
      degreeById.set(relation.source_entity_id, (degreeById.get(relation.source_entity_id) || 0) + 1);
      degreeById.set(relation.target_entity_id, (degreeById.get(relation.target_entity_id) || 0) + 1);
    });
    const rankedEntities = [...filteredKgEntities].sort(
      (left, right) =>
        (typePriority[left.entity_type] ?? 99) - (typePriority[right.entity_type] ?? 99) ||
        (degreeById.get(right.id) || 0) - (degreeById.get(left.id) || 0) ||
        left.id - right.id,
    );
    const projectEntity = rankedEntities.find((entity) => entity.entity_type === "project");
    const innerEntities = rankedEntities
      .filter((entity) => entity.entity_type === "note")
      .sort((left, right) => (degreeById.get(right.id) || 0) - (degreeById.get(left.id) || 0))
      .slice(0, 6);
    const selectedIds = new Set(innerEntities.map((entity) => entity.id));
    if (projectEntity) selectedIds.add(projectEntity.id);
    const outerTypeQuotas: Array<[string, number]> = [
      ["user", 1],
      ["experiment_type", 2],
      ["reagent", 2],
      ["instrument", 1],
      ["sample", 1],
      ["result", 2],
    ];
    const outerEntities = outerTypeQuotas.flatMap(([entityType, limit]) =>
      rankedEntities
        .filter((entity) => entity.entity_type === entityType && !selectedIds.has(entity.id))
        .sort((left, right) => (degreeById.get(right.id) || 0) - (degreeById.get(left.id) || 0))
        .slice(0, limit),
    );
    const centerX = 400;
    const centerY = 250;
    const nodes: Array<{ entity: KnowledgeEntity; x: number; y: number }> = [];
    if (projectEntity) nodes.push({ entity: projectEntity, x: centerX, y: centerY });
    innerEntities.forEach((entity, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(innerEntities.length, 1) - Math.PI / 2;
      nodes.push({
        entity,
        x: centerX + Math.cos(angle) * 165,
        y: centerY + Math.sin(angle) * 105,
      });
    });
    outerEntities.forEach((entity, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(outerEntities.length, 1) - Math.PI / 2 + Math.PI / 14;
      nodes.push({
        entity,
        x: centerX + Math.cos(angle) * 330,
        y: centerY + Math.sin(angle) * 205,
      });
    });
    const nodeIds = new Set(nodes.map((node) => node.entity.id));
    const relations = filteredKgRelations
      .filter((relation) => nodeIds.has(relation.source_entity_id) && nodeIds.has(relation.target_entity_id))
      .sort(
        (left, right) =>
          Number(right.source_entity_id === projectEntity?.id || right.target_entity_id === projectEntity?.id) -
          Number(left.source_entity_id === projectEntity?.id || left.target_entity_id === projectEntity?.id),
      )
      .slice(0, 36);
    const nodeById = new Map(nodes.map((node) => [node.entity.id, node]));
    return { nodes, relations, nodeById };
  }, [filteredKgEntities, filteredKgRelations]);

  async function refreshAll(activeToken = token, projectId = selectedProjectId) {
    if (!activeToken) return;
    setError("");
    try {
      const [projectItems, templateItems, pendingItems] = await Promise.all([
        getProjects(activeToken),
        getTemplates(activeToken),
        getPendingApprovals(activeToken).catch(() => []),
      ]);
      setProjects(projectItems);
      setTemplates(templateItems);
      setPendingNotes(pendingItems);
      const nextProjectId = projectId || projectItems[0]?.id || null;
      setSelectedProjectId(nextProjectId);
      const userItems = await getUsers(activeToken).catch(() => []);
      setUsers(userItems);
      if (user?.role === "super_admin") {
        const [groupItems, auditItems] = await Promise.all([
          getGroups(activeToken).catch(() => []),
          getAuditLogs(activeToken, auditFilters).catch(() => []),
        ]);
        setGroups(groupItems);
        setAuditLogs(auditItems);
        const nextGroupId = selectedGroupId || groupItems[0]?.id || null;
        setSelectedGroupId(nextGroupId);
        if (nextGroupId) {
          setGroupMembers(await getGroupMembers(activeToken, nextGroupId).catch(() => []));
        } else {
          setGroupMembers([]);
        }
      }
      if (nextProjectId) {
        const [noteItems, fileItems, memberItems, ragStatusItem, kgGraphItem, queryLogItems, queryAnalyticsItem, experimentItems, agentRunItems] = await Promise.all([
          getProjectNotes(activeToken, nextProjectId),
          getProjectFiles(activeToken, nextProjectId),
          getProjectMembers(activeToken, nextProjectId).catch(() => []),
          getProjectRagStatus(activeToken, nextProjectId).catch(() => null),
          getProjectKnowledgeGraph(activeToken, nextProjectId).catch(() => null),
          getProjectQueryLogs(activeToken, nextProjectId).catch(() => []),
          getProjectQueryAnalytics(activeToken, nextProjectId).catch(() => null),
          getRagExperiments(activeToken, nextProjectId).catch(() => []),
          getAgentRuns(activeToken, nextProjectId).catch(() => []),
        ]);
        setNotes(noteItems);
        setFiles(fileItems);
        setMembers(memberItems);
        setRagStatus(ragStatusItem);
        setKgGraph(kgGraphItem);
        setQueryLogs(queryLogItems);
        setQueryAnalytics(queryAnalyticsItem);
        setExperimentRuns(experimentItems);
        setAgentRuns(agentRunItems);
        setAgentRun(agentRunItems[0] || null);
      } else {
        setKgGraph(null);
        setQueryLogs([]);
        setQueryAnalytics(null);
        setExperimentRuns([]);
        setAgentRuns([]);
        setAgentRun(null);
      }
      // 后台加载仪表盘数据（不阻塞）
      getDashboardSummary(activeToken).then(setDashboardSummary).catch(() => {});
      getNotifications(activeToken).then(setNotifList).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "刷新失败");
    }
  }

  useEffect(() => {
    if (selectedProject) {
      setProjectEdit({
        name: selectedProject.name,
        description: selectedProject.description || "",
        is_sensitive: selectedProject.is_sensitive,
        approval_enabled: selectedProject.approval_enabled,
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
    getMe(savedToken)
      .then((me) => {
        setUser(me);
      })
      .catch(() => window.localStorage.removeItem("eln_token"));
  }, []);

  useEffect(() => {
    if (token && user) void refreshAll(token, selectedProjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.id]);

  useEffect(() => {
    if (token && selectedProjectId) void refreshAll(token, selectedProjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const result = await login(username, password);
      window.localStorage.setItem("eln_token", result.access_token);
      setToken(result.access_token);
      setUser(await getMe(result.access_token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  }

  function logout() {
    if (token) void logoutSession(token).catch(() => undefined);
    window.localStorage.removeItem("eln_token");
    setToken("");
    setUser(null);
    setProjects([]);
    setNotes([]);
  }

  function applyTemplate(templateId: number) {
    const template = templates.find((item) => item.id === templateId);
    if (!template) return;
    const fields = Object.fromEntries((template.schema_json.fields || []).map((field) => [field.key, editor.fixed_fields_json[field.key] || ""]));
    setEditor({
      ...editor,
      template_id: template.id,
      experiment_type: template.experiment_type,
      fixed_fields_json: fields,
      content_text: editor.content_text || "请记录实验过程、关键观察、结果分析和下一步计划。",
    });
  }

  function editNote(note: Note) {
    setSelectedNote(note);
    Promise.all([getNoteVersions(token, note.id), getNoteApprovals(token, note.id)]).then(([items, approvalItems]) => {
      setVersions(items);
      setApprovals(approvalItems);
      const latest = items[0];
      setEditor({
        id: note.id,
        title: note.title,
        experiment_type: note.experiment_type,
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
      setMessage(successMessage);
      setApprovalComment("");
      await refreshAll(token, note.project_id);
      editNote(note);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  }

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    if (!canWriteSelectedProject) {
      setError("当前账号没有项目写入权限");
      return;
    }
    setMessage("");
    const payload = {
      title: editor.title,
      experiment_type: editor.experiment_type,
      experiment_date: editor.experiment_date,
      template_id: editor.template_id,
      fixed_fields_json: editor.fixed_fields_json,
      content_json: { text: editor.content_text },
      change_summary: "前端编辑保存",
    };
    try {
      const note = editor.id
        ? await updateNote(token, editor.id, payload)
        : await createNote(token, selectedProjectId, payload);
      setSelectedNote(note);
      setEditor({ ...editor, id: note.id });
      setMessage(
        note.status === "approved"
          ? "实验笔记已保存，已审核内容将同步更新知识图谱"
          : "实验笔记已保存；草稿不会进入知识图谱，审核通过后自动抽取",
      );
      await refreshAll();
      editNote(note);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createUser(token, { ...newUser, email: newUser.email || undefined });
    setNewUser({ username: "", password: "ChangeMe123", display_name: "", email: "", role: "member" });
    setMessage("用户已创建");
    await refreshAll();
  }

  async function handleUpdateUser(userItem: User) {
    const draft = userEdits[userItem.id] || { display_name: userItem.display_name, email: userItem.email || "", role: userItem.role, status: userItem.status, password: "" };
    await updateUser(token, userItem.id, {
      display_name: draft.display_name,
      email: draft.email || null,
      role: draft.role,
      status: draft.status,
      ...(draft.password ? { password: draft.password } : {}),
    });
    setMessage("用户已更新");
    setUserEdits((current) => ({ ...current, [userItem.id]: { ...draft, password: "" } }));
    await refreshAll();
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createProject(token, {
      ...newProject,
      owner_user_id: newProject.owner_user_id ? Number(newProject.owner_user_id) : null,
    });
    setNewProject({ name: "", description: "", is_sensitive: false, approval_enabled: true, owner_user_id: "" });
    setMessage("项目已创建");
    await refreshAll();
  }

  async function handleUpdateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    await updateProject(token, selectedProjectId, {
      name: projectEdit.name,
      description: projectEdit.description,
      is_sensitive: projectEdit.is_sensitive,
      approval_enabled: projectEdit.approval_enabled,
      owner_user_id: projectEdit.owner_user_id ? Number(projectEdit.owner_user_id) : null,
      status: projectEdit.status,
    });
    setMessage("项目已更新");
    await refreshAll(token, selectedProjectId);
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    await addProjectMember(token, selectedProjectId, { ...memberDraft, user_id: Number(memberDraft.user_id) });
    setMemberDraft({ user_id: "", project_role: "member", can_read: true, can_write: true, can_review: false, can_manage: false });
    setMessage("项目成员已授权");
    await refreshAll();
  }

  async function handleUpdateMember(member: ProjectMember, payload: Partial<ProjectMember>) {
    if (!selectedProjectId) return;
    await updateProjectMember(token, selectedProjectId, member.user_id, payload);
    setMessage("项目成员权限已更新");
    await refreshAll(token, selectedProjectId);
  }

  async function handleRemoveMember(member: ProjectMember) {
    if (!selectedProjectId) return;
    await removeProjectMember(token, selectedProjectId, member.user_id);
    setMessage("项目成员已移除");
    await refreshAll(token, selectedProjectId);
  }

  async function handleCreateGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const group = await createGroup(token, {
      name: newGroup.name,
      description: newGroup.description || undefined,
      leader_user_id: newGroup.leader_user_id ? Number(newGroup.leader_user_id) : null,
    });
    setNewGroup({ name: "", description: "", leader_user_id: "" });
    setSelectedGroupId(group.id);
    setMessage("小组已创建");
    await refreshAll();
  }

  async function handleUpdateGroup() {
    if (!selectedGroup) return;
    await updateGroup(token, selectedGroup.id, {
      name: selectedGroup.name,
      description: selectedGroup.description,
      leader_user_id: selectedGroup.leader_user_id,
    });
    setMessage("小组已更新");
    await refreshAll();
  }

  async function handleAddGroupMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedGroupId) return;
    await addGroupMember(token, selectedGroupId, { user_id: Number(groupDraft.user_id), group_role: groupDraft.group_role });
    setGroupDraft({ user_id: "", group_role: "member" });
    setMessage("小组成员已更新");
    await refreshAll();
  }

  async function handleAuditSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuditLogs(await getAuditLogs(token, auditFilters));
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWriteSelectedProject) {
      setError("当前账号没有文件上传权限");
      return;
    }
    const input = event.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !selectedProjectId) return;
    await uploadFile(token, selectedProjectId, file, selectedNote?.id, selectedNote ? "note_attachment" : "knowledge_document");
    input.value = "";
    setMessage("文件已上传");
    await refreshAll();
  }

  async function handleDownload(file: StoredFile) {
    const response = await fetch(fileDownloadUrl(file.id), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      setError("下载失败");
      return;
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.original_filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  async function handleUpdateFile(file: StoredFile) {
    if (!canWriteSelectedProject) {
      setError("当前账号没有文件维护权限");
      return;
    }
    const nextName = (fileEdits[file.id] ?? file.original_filename).trim();
    if (!nextName || nextName === file.original_filename) return;
    await updateFile(token, file.id, { original_filename: nextName });
    setMessage("文件元信息已更新");
    await refreshAll();
  }

  async function handleArchiveFile(file: StoredFile) {
    if (!canWriteSelectedProject) {
      setError("当前账号没有文件归档权限");
      return;
    }
    await archiveFile(token, file.id);
    setMessage("文件已归档");
    await refreshAll();
  }

  async function handleInitRag() {
    if (!selectedProjectId || !canReviewSelectedProject) return;
    setRagBusy(true);
    setError("");
    try {
      const nextStatus = await initProjectRag(token, selectedProjectId);
      setRagStatus(nextStatus);
      setMessage("AI 知识库已初始化");
    } catch (err) {
      setError(err instanceof Error ? err.message : "初始化 AI 知识库失败");
    } finally {
      setRagBusy(false);
    }
  }

  async function handleSyncRagFile(file: StoredFile) {
    if (!canReviewSelectedProject) return;
    setRagBusy(true);
    setError("");
    try {
      const nextStatus = await syncFileToRag(token, file.id);
      setRagStatus(nextStatus);
      setMessage("资料已同步到 AI 知识库");
      await refreshAll(token, file.project_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "同步资料失败");
      await refreshAll(token, file.project_id);
    } finally {
      setRagBusy(false);
    }
  }

  async function handleQueryRag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !ragQuestion.trim()) return;
    setRagBusy(true);
    setError("");
    try {
      const result = await queryProjectRag(token, selectedProjectId, ragQuestion, ragMode);
      setRagAnswer(result);
      const [nextLogs, nextAnalytics] = await Promise.all([
        getProjectQueryLogs(token, selectedProjectId).catch(() => []),
        getProjectQueryAnalytics(token, selectedProjectId).catch(() => null),
      ]);
      setQueryLogs(nextLogs);
      setQueryAnalytics(nextAnalytics);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI 查询失败");
    } finally {
      setRagBusy(false);
    }
  }

  async function handleEvaluateQueryLog(log: AIQueryLog) {
    const draft = evaluationDrafts[log.id] || {
      score: log.evaluation ? String(log.evaluation.score) : "",
      is_accurate: log.evaluation?.is_accurate ?? null,
      is_traceable: log.evaluation?.is_traceable ?? null,
      comment: log.evaluation?.comment || "",
    };
    if (!selectedProjectId) return;
    if (!draft.score || draft.is_accurate === null || draft.is_traceable === null) {
      setError("请完整选择评分、准确性和可追溯性后再保存");
      return;
    }
    setRagBusy(true);
    setError("");
    try {
      await evaluateQueryLog(token, log.id, {
        score: Number(draft.score),
        is_accurate: draft.is_accurate,
        is_traceable: draft.is_traceable,
        comment: draft.comment || null,
      });
      const [nextLogs, nextAnalytics] = await Promise.all([
        getProjectQueryLogs(token, selectedProjectId),
        getProjectQueryAnalytics(token, selectedProjectId).catch(() => null),
      ]);
      setQueryLogs(nextLogs);
      setQueryAnalytics(nextAnalytics);
      setMessage("问答评价已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存评价失败");
    } finally {
      setRagBusy(false);
    }
  }

  async function handleRunRagExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !canReviewSelectedProject) return;
    const questions = experimentDraft.questions.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    if (questions.length === 0) {
      setError("请至少输入一个实验问题，每行一个");
      return;
    }
    setExperimentBusy(true);
    setError("");
    try {
      const run = await runRagExperiment(token, selectedProjectId, {
        name: experimentDraft.name,
        questions,
        modes: ["project_rag", "kg_enhanced_rag"],
      });
      const [runs, logs, analytics] = await Promise.all([
        getRagExperiments(token, selectedProjectId),
        getProjectQueryLogs(token, selectedProjectId),
        getProjectQueryAnalytics(token, selectedProjectId),
      ]);
      setExperimentRuns(runs);
      setQueryLogs(logs);
      setQueryAnalytics(analytics);
      setMessage(`对照实验 #${run.id} 已完成：成功 ${run.completed_cases}，失败 ${run.failed_cases}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行对照实验失败");
    } finally {
      setExperimentBusy(false);
    }
  }

  async function handleDownloadRagExperiment(run: AIExperimentRun) {
    setError("");
    try {
      const blob = await downloadRagExperiment(token, run.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `rag-experiment-${run.id}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出实验结果失败");
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !searchQuery.trim()) return;
    setSearchBusy(true);
    setError("");
    try {
      await reindexSearch(token, selectedProjectId);
      const results = await searchDocuments(token, searchQuery, selectedProjectId);
      setSearchResults(results);
      setMessage("搜索完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索失败");
    } finally {
      setSearchBusy(false);
    }
  }

  async function handleGenerateAgent() {
    if (!selectedProjectId) return;
    setAgentBusy(true);
    setError("");
    try {
      const run = await generateAgentOutput(token, {
        project_id: selectedProjectId,
        task_type: agentDraft.task_type,
        date_from: agentDraft.date_from || null,
        date_to: agentDraft.date_to || null,
      });
      setAgentRun(run);
      setAgentRuns(await getAgentRuns(token, selectedProjectId).catch(() => [run]));
      setMessage("智能体生成结果已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "智能生成失败");
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleOcrExtract(file: StoredFile) {
    setError("");
    try {
      const result = await extractOcr(token, file.id);
      setOcrResult(result.extracted_text);
      setMessage(`OCR 提取完成：${result.extracted_text.length} 字符`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR 提取失败");
    }
  }

  async function refreshKnowledgeGraph(projectId = selectedProjectId) {
    if (!projectId) return;
    setKgBusy(true);
    setError("");
    try {
      setKgGraph(await getProjectKnowledgeGraph(token, projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "知识图谱加载失败");
    } finally {
      setKgBusy(false);
    }
  }

  async function handleExtractSelectedNoteKg(note = selectedNote) {
    if (!note || !canWriteSelectedProject) return;
    setKgBusy(true);
    setError("");
    try {
      const run = await extractNoteKnowledgeGraph(token, note.id, true);
      setMessage(`已抽取当前笔记图谱：${run.extracted_entities} 个实体，${run.extracted_relations} 条关系`);
      await refreshKnowledgeGraph(run.project_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "当前笔记图谱抽取失败");
    } finally {
      setKgBusy(false);
    }
  }

  async function handleRebuildProjectKg() {
    if (!selectedProjectId || !canWriteSelectedProject) return;
    setKgBusy(true);
    setError("");
    try {
      const runs = await rebuildProjectKnowledgeGraph(token, selectedProjectId);
      const entityCount = runs.reduce((sum, run) => sum + run.extracted_entities, 0);
      const relationCount = runs.reduce((sum, run) => sum + run.extracted_relations, 0);
      setMessage(`项目图谱已重建：${runs.length} 篇笔记，${entityCount} 个实体，${relationCount} 条关系`);
      await refreshKnowledgeGraph(selectedProjectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目知识图谱重建失败");
    } finally {
      setKgBusy(false);
    }
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-surface px-6 py-10">
        <section className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className={cardClass("flex min-h-[520px] flex-col justify-between p-8")}>
            <div>
              <div className="mb-8 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-md bg-brand text-white">
                  <BookOpen size={24} />
                </div>
                <div>
                  <h1 className="text-2xl font-semibold">智能电子实验笔记系统</h1>
          <p className="mt-1 text-sm text-muted">知识图谱、RAG 与科研过程管理一体化工作台</p>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {[
                  { icon: ShieldCheck, title: "项目隔离", text: "敏感项目显式授权，普通成员只看授权项目。" },
                  { icon: ClipboardCheck, title: "审批留痕", text: "笔记提交、审核、退回和版本记录可追溯。" },
                  { icon: Paperclip, title: "附件归档", text: "文件上传、下载和审计记录已接入。" },
                  { icon: Database, title: "本地 RAG", text: "审核资料本地向量化，并由 DeepSeek 生成可追溯回答。" },
                ].map((item) => (
                  <div key={item.title} className="rounded-md border border-border p-4">
                    <item.icon className="mb-3 text-brand" size={22} />
                    <h2 className="font-medium">{item.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-muted">{item.text}</p>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-sm text-muted">默认管理员：admin / admin123。首次正式部署后请立即修改密码。</p>
          </div>
          <form onSubmit={handleLogin} className={cardClass("p-6")}>
            <h2 className="text-xl font-semibold">登录</h2>
            <label className="mt-6 block text-sm font-medium">
              账号
              <input className="mt-2 w-full rounded-md border border-border px-3 py-2 outline-none focus:border-brand" value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label className="mt-4 block text-sm font-medium">
              密码
              <input className="mt-2 w-full rounded-md border border-border px-3 py-2 outline-none focus:border-brand" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
            {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <button className="mt-6 w-full rounded-md bg-brand px-4 py-2 font-medium text-white hover:bg-[#145c73]">登录工作台</button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-surface">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-brand text-white">
              <BookOpen size={22} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">智能 ELN 工作台</h1>
              <p className="text-sm text-muted">{user.display_name} · {user.role}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => void refreshAll()} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface">
              <RefreshCw size={16} />
              刷新
            </button>
            <button onClick={logout} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface">
              <LogOut size={16} />
              退出
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid min-w-0 max-w-[1440px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className={cardClass("min-w-0 self-start p-3 lg:sticky lg:top-6")}>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-1">
            <button
              type="button"
              onClick={() => setWorkspaceView("project")}
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${workspaceView === "project" ? "bg-brand text-white" : "text-muted hover:bg-surface hover:text-ink"}`}
            >
              <LayoutDashboard size={17} />
              项目工作台
            </button>
            {canAdmin && (
              <button
                type="button"
                onClick={() => setWorkspaceView("admin")}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${workspaceView === "admin" ? "bg-brand text-white" : "text-muted hover:bg-surface hover:text-ink"}`}
              >
                <Settings size={17} />
                系统管理
              </button>
            )}
          </div>
          {workspaceView === "project" && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="mb-3 flex items-center justify-between px-1 text-xs font-semibold text-muted">
                <span>我的项目</span>
                <span>{projects.length}</span>
              </div>
              <div className="space-y-2">
                {projects.length === 0 && <p className="px-2 py-4 text-sm text-muted">暂无可访问项目。</p>}
                {projects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => setSelectedProjectId(project.id)}
                    className={`w-full rounded-md border px-3 py-3 text-left text-sm transition-colors ${selectedProjectId === project.id ? "border-brand bg-[#edf7f5] text-ink" : "border-transparent text-muted hover:border-border hover:bg-surface hover:text-ink"}`}
                  >
                    <span className="flex items-start justify-between gap-2 font-medium">
                      <span>{project.name}</span>
                      {project.is_sensitive && <Lock size={15} className="mt-0.5 shrink-0 text-warning" />}
                    </span>
                    <span className="mt-1 block text-xs">{project.approval_enabled ? "审批流程已启用" : "无需审批"}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>

        <section className="min-w-0 space-y-6">
          {(message || error) && (
            <div className={`rounded-md border px-4 py-3 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-green-200 bg-green-50 text-green-700"}`}>
              {error || message}
            </div>
          )}

          {workspaceView === "project" && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { icon: FileText, label: "实验笔记", value: notes.length },
              { icon: ClipboardCheck, label: "待审核", value: pendingNotes.length },
              { icon: Paperclip, label: "项目文件", value: files.length },
              { icon: Sparkles, label: "AI 能力", value: ragStatus?.initialized ? "已启用" : "待初始化" },
            ].map((item) => (
              <div key={item.label} className={cardClass("p-4 transition-shadow hover:shadow-[0_8px_24px_rgba(23,32,51,0.08)]")}>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted">{item.label}</span>
                  <item.icon size={18} className="text-brand" />
                </div>
                <p className="mt-3 text-2xl font-semibold">{item.value}</p>
              </div>
            ))}
          </div>
          )}

          {canAdmin && workspaceView === "admin" && (
            <div className="space-y-4">
              <div className={cardClass("p-5")}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">系统管理</h2>
                    <p className="mt-1 text-sm text-muted">集中管理用户、小组、项目和审计记录，日常实验操作请回到项目工作台。</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:w-[520px]">
                    <div className="rounded-md border border-border bg-surface px-3 py-2">
                      <p className="text-xs text-muted">用户</p>
                      <p className="mt-1 font-semibold">{users.length}</p>
                    </div>
                    <div className="rounded-md border border-border bg-surface px-3 py-2">
                      <p className="text-xs text-muted">项目</p>
                      <p className="mt-1 font-semibold">{projects.length}</p>
                    </div>
                    <div className="rounded-md border border-border bg-surface px-3 py-2">
                      <p className="text-xs text-muted">小组</p>
                      <p className="mt-1 font-semibold">{groups.length}</p>
                    </div>
                    <div className="rounded-md border border-border bg-surface px-3 py-2">
                      <p className="text-xs text-muted">审计</p>
                      <p className="mt-1 font-semibold">{auditLogs.length}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <form onSubmit={handleCreateUser} className={cardClass("p-5")}>
                  <h2 className="flex items-center gap-2 font-semibold"><UserPlus size={18} />创建用户</h2>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <input className="rounded-md border border-border px-3 py-2" placeholder="账号" value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} required />
                    <input className="rounded-md border border-border px-3 py-2" placeholder="姓名" value={newUser.display_name} onChange={(event) => setNewUser({ ...newUser, display_name: event.target.value })} required />
                    <input className="rounded-md border border-border px-3 py-2" placeholder="邮箱" value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} />
                    <select className="rounded-md border border-border px-3 py-2" value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
                      {roleOptions.map((role) => <option key={role}>{role}</option>)}
                    </select>
                    <input className="rounded-md border border-border px-3 py-2 md:col-span-2" placeholder="初始密码" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} required />
                  </div>
                  <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white"><Plus size={16} />创建用户</button>
                </form>

                <form onSubmit={handleCreateProject} className={cardClass("p-5")}>
                  <h2 className="flex items-center gap-2 font-semibold"><Database size={18} />创建项目</h2>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <input className="rounded-md border border-border px-3 py-2" placeholder="项目名称" value={newProject.name} onChange={(event) => setNewProject({ ...newProject, name: event.target.value })} required />
                    <select className="rounded-md border border-border px-3 py-2" value={newProject.owner_user_id} onChange={(event) => setNewProject({ ...newProject, owner_user_id: event.target.value })}>
                      <option value="">项目负责人可稍后设置</option>
                      {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                    </select>
                    <textarea className="rounded-md border border-border px-3 py-2 md:col-span-2" placeholder="项目说明" value={newProject.description} onChange={(event) => setNewProject({ ...newProject, description: event.target.value })} />
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={newProject.is_sensitive} onChange={(event) => setNewProject({ ...newProject, is_sensitive: event.target.checked })} />敏感项目</label>
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={newProject.approval_enabled} onChange={(event) => setNewProject({ ...newProject, approval_enabled: event.target.checked })} />启用审批</label>
                  </div>
                  <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white"><Plus size={16} />创建项目</button>
                </form>
              </div>

              <div className={cardClass("p-5")}>
                <h2 className="flex items-center gap-2 font-semibold"><Users size={18} />用户管理</h2>
                <div className="mt-4 grid gap-3">
                  {users.map((item) => {
                    const draft = userEdits[item.id] || {
                      display_name: item.display_name,
                      email: item.email || "",
                      role: item.role,
                      status: item.status,
                      password: "",
                    };
                    return (
                      <div key={item.id} className="grid gap-2 rounded-md border border-border p-3 lg:grid-cols-[1fr_1fr_1fr_1fr_1fr_auto]">
                        <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm">{item.username}</div>
                        <input className="rounded-md border border-border px-3 py-2 text-sm" value={draft.display_name} onChange={(event) => setUserEdits({ ...userEdits, [item.id]: { ...draft, display_name: event.target.value } })} />
                        <input className="rounded-md border border-border px-3 py-2 text-sm" placeholder="邮箱" value={draft.email} onChange={(event) => setUserEdits({ ...userEdits, [item.id]: { ...draft, email: event.target.value } })} />
                        <select className="rounded-md border border-border px-3 py-2 text-sm" value={draft.role} onChange={(event) => setUserEdits({ ...userEdits, [item.id]: { ...draft, role: event.target.value } })}>
                          {roleOptions.map((role) => <option key={role}>{role}</option>)}
                        </select>
                        <input className="rounded-md border border-border px-3 py-2 text-sm" placeholder="新密码可留空" value={draft.password} onChange={(event) => setUserEdits({ ...userEdits, [item.id]: { ...draft, password: event.target.value } })} />
                        <div className="flex flex-wrap gap-2">
                          <button type="button" onClick={() => void handleUpdateUser(item)} className="rounded-md bg-brand px-3 py-2 text-xs font-medium text-white">保存</button>
                          <button type="button" onClick={() => void disableUser(token, item.id).then(() => refreshAll())} disabled={item.id === user.id || item.status === "disabled"} className="rounded-md border border-border px-3 py-2 text-xs disabled:opacity-40">停用</button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <form onSubmit={handleCreateGroup} className={cardClass("p-5")}>
                  <h2 className="flex items-center gap-2 font-semibold"><FolderPlus size={18} />小组管理</h2>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <input className="rounded-md border border-border px-3 py-2" placeholder="小组名称" value={newGroup.name} onChange={(event) => setNewGroup({ ...newGroup, name: event.target.value })} required />
                    <select className="rounded-md border border-border px-3 py-2" value={newGroup.leader_user_id} onChange={(event) => setNewGroup({ ...newGroup, leader_user_id: event.target.value })}>
                      <option value="">小组负责人</option>
                      {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                    </select>
                    <textarea className="rounded-md border border-border px-3 py-2 md:col-span-2" placeholder="小组说明" value={newGroup.description} onChange={(event) => setNewGroup({ ...newGroup, description: event.target.value })} />
                  </div>
                  <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white"><Plus size={16} />创建小组</button>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {groups.map((group) => (
                      <button type="button" key={group.id} onClick={() => setSelectedGroupId(group.id)} className={`rounded-md border px-3 py-2 text-sm ${selectedGroupId === group.id ? "border-brand bg-[#eef8f6]" : "border-border"}`}>{group.name}</button>
                    ))}
                  </div>
                </form>

                {selectedGroup && (
                  <div className={cardClass("p-5")}>
                    <h2 className="font-semibold">小组详情</h2>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <input className="rounded-md border border-border px-3 py-2" value={selectedGroup.name} onChange={(event) => setGroups(groups.map((group) => group.id === selectedGroup.id ? { ...group, name: event.target.value } : group))} />
                      <select className="rounded-md border border-border px-3 py-2" value={selectedGroup.leader_user_id || ""} onChange={(event) => setGroups(groups.map((group) => group.id === selectedGroup.id ? { ...group, leader_user_id: event.target.value ? Number(event.target.value) : null } : group))}>
                        <option value="">小组负责人</option>
                        {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                      </select>
                      <textarea className="rounded-md border border-border px-3 py-2 md:col-span-2" value={selectedGroup.description || ""} onChange={(event) => setGroups(groups.map((group) => group.id === selectedGroup.id ? { ...group, description: event.target.value } : group))} />
                    </div>
                    <button type="button" onClick={() => void handleUpdateGroup()} className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存小组</button>
                    <div className="mt-4 border-t border-border pt-4">
                      <form onSubmit={handleAddGroupMember} className="flex flex-wrap gap-2">
                        <select className="rounded-md border border-border px-3 py-2 text-sm" value={groupDraft.user_id} onChange={(event) => setGroupDraft({ ...groupDraft, user_id: event.target.value })} required>
                          <option value="">选择成员</option>
                          {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                        </select>
                        <input className="rounded-md border border-border px-3 py-2 text-sm" value={groupDraft.group_role} onChange={(event) => setGroupDraft({ ...groupDraft, group_role: event.target.value })} />
                        <button className="rounded-md border border-border px-3 py-2 text-sm">添加/更新</button>
                      </form>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {groupMembers.map((member) => (
                          <span key={member.id} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-1 text-xs">
                            {usersById.get(member.user_id)?.display_name || `用户 ${member.user_id}`} · {member.group_role}
                            <button type="button" onClick={() => void removeGroupMember(token, member.group_id, member.user_id).then(() => refreshAll())} className="text-red-700">移除</button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className={cardClass("p-5")}>
                <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} />审计日志</h2>
                <form onSubmit={handleAuditSearch} className="mt-4 grid gap-3 md:grid-cols-5">
                  <select className="rounded-md border border-border px-3 py-2 text-sm" value={auditFilters.actor_user_id} onChange={(event) => setAuditFilters({ ...auditFilters, actor_user_id: event.target.value })}>
                    <option value="">全部用户</option>
                    {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                  </select>
                  <select className="rounded-md border border-border px-3 py-2 text-sm" value={auditFilters.project_id} onChange={(event) => setAuditFilters({ ...auditFilters, project_id: event.target.value })}>
                    <option value="">全部项目</option>
                    {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                  </select>
                  <input className="rounded-md border border-border px-3 py-2 text-sm" placeholder="动作" value={auditFilters.action} onChange={(event) => setAuditFilters({ ...auditFilters, action: event.target.value })} />
                  <input className="rounded-md border border-border px-3 py-2 text-sm" type="datetime-local" value={auditFilters.date_from} onChange={(event) => setAuditFilters({ ...auditFilters, date_from: event.target.value })} />
                  <div className="flex gap-2">
                    <input className="min-w-0 flex-1 rounded-md border border-border px-3 py-2 text-sm" type="datetime-local" value={auditFilters.date_to} onChange={(event) => setAuditFilters({ ...auditFilters, date_to: event.target.value })} />
                    <button className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white">筛选</button>
                  </div>
                </form>
                <div className="mt-4 max-h-80 overflow-auto rounded-md border border-border">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead className="sticky top-0 bg-surface text-xs text-muted">
                      <tr>
                        <th className="px-3 py-2 font-medium">时间</th>
                        <th className="px-3 py-2 font-medium">用户</th>
                        <th className="px-3 py-2 font-medium">项目</th>
                        <th className="px-3 py-2 font-medium">动作</th>
                        <th className="px-3 py-2 font-medium">对象</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.length === 0 && (
                        <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">暂无审计记录</td></tr>
                      )}
                      {auditLogs.map((log) => (
                        <tr key={log.id} className="border-t border-border">
                          <td className="px-3 py-2">{new Date(log.created_at).toLocaleString("zh-CN")}</td>
                          <td className="px-3 py-2">{log.actor_user_id ? usersById.get(log.actor_user_id)?.display_name || log.actor_user_id : "-"}</td>
                          <td className="px-3 py-2">{log.project_id ? projects.find((project) => project.id === log.project_id)?.name || log.project_id : "-"}</td>
                          <td className="px-3 py-2">{log.action}</td>
                          <td className="px-3 py-2">{log.target_type || "-"} {log.target_id || ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {workspaceView === "project" && selectedProjectId && (
            <div className={cardClass("overflow-hidden")}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 p-5">
                  <h2 className="truncate text-lg font-semibold">{selectedProject?.name || "请选择项目"}</h2>
                  <p className="mt-1 text-sm text-muted">{selectedProject?.description || "项目笔记、附件和审批会在这里汇总。"}</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
                    <span className="rounded-md border border-border px-2 py-1">{selectedProject?.approval_enabled ? "启用审批" : "未启用审批"}</span>
                    <span className="rounded-md border border-border px-2 py-1">{selectedProject?.is_sensitive ? "敏感项目" : "普通项目"}</span>
                    <span className="rounded-md border border-border px-2 py-1">{selectedProject?.status || "active"}</span>
                  </div>
                </div>
                <div className="grid shrink-0 grid-cols-2 gap-3 p-5 text-sm sm:grid-cols-4 lg:w-[420px]">
                  <div className="rounded-md border border-border bg-surface px-3 py-2">
                    <p className="text-xs text-muted">图谱实体</p>
                    <p className="mt-1 font-semibold">{kgGraph?.entities.length ?? 0}</p>
                  </div>
                  <div className="rounded-md border border-border bg-surface px-3 py-2">
                    <p className="text-xs text-muted">图谱关系</p>
                    <p className="mt-1 font-semibold">{kgGraph?.relations.length ?? 0}</p>
                  </div>
                  <div className="rounded-md border border-border bg-surface px-3 py-2">
                    <p className="text-xs text-muted">问答记录</p>
                    <p className="mt-1 font-semibold">{queryLogs.length}</p>
                  </div>
                  <div className="rounded-md border border-border bg-surface px-3 py-2">
                    <p className="text-xs text-muted">生成记录</p>
                    <p className="mt-1 font-semibold">{agentRuns.length}</p>
                  </div>
                </div>
              </div>
              <div className="border-t border-border bg-surface/70 px-3 py-3">
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {projectTabs.map((tab) => (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => setActiveProjectTab(tab.key)}
                      className={`flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm ${activeProjectTab === tab.key ? "border-brand bg-white text-brand shadow-panel" : "border-transparent text-muted hover:border-border hover:bg-white hover:text-ink"}`}
                    >
                      <tab.icon size={16} />
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {workspaceView === "project" && activeProjectTab === "overview" && (
            <div className="grid gap-4 md:grid-cols-3">
              <div className={cardClass("p-5")}>
                <h2 className="font-semibold">最近实验笔记</h2>
                <div className="mt-4 space-y-2">
                  {notes.slice(0, 5).map((note) => (
                    <button key={note.id} type="button" onClick={() => { setActiveProjectTab("notes"); editNote(note); }} className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-surface">
                      <span className="font-medium">{note.title}</span>
                      <span className="mt-1 block text-xs text-muted">{statusText[note.status] || note.status}</span>
                    </button>
                  ))}
                  {notes.length === 0 && <p className="text-sm text-muted">当前项目还没有实验笔记。</p>}
                </div>
              </div>
              <div className={cardClass("p-5")}>
                <h2 className="font-semibold">待处理审批</h2>
                <p className="mt-4 text-3xl font-semibold">{pendingNotes.filter((note) => !selectedProjectId || note.project_id === selectedProjectId).length}</p>
                <button type="button" onClick={() => setActiveProjectTab("approvals")} className="mt-4 rounded-md border border-border px-3 py-2 text-sm">查看审批中心</button>
              </div>
              <div className={cardClass("p-5")}>
                <h2 className="font-semibold">资料库状态</h2>
                <div className="mt-4 space-y-2 text-sm text-muted">
                  <p>文件总数：{files.length}</p>
                  <p>待审核资料：{files.filter((file) => file.file_category === "knowledge_document" && file.status === "uploaded").length}</p>
                  <p>待同步资料：{files.filter((file) => file.knowledge_sync_status === "pending_sync").length}</p>
                </div>
                <button type="button" onClick={() => setActiveProjectTab("files")} className="mt-4 rounded-md border border-border px-3 py-2 text-sm">打开资料库</button>
              </div>
            </div>
          )}

          {workspaceView === "project" && activeProjectTab === "members" && canManageSelectedProject && selectedProjectId && (
            <form onSubmit={handleUpdateProject} className={cardClass("p-5")}>
              <h2 className="flex items-center gap-2 font-semibold"><Database size={18} />项目设置</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <input className="rounded-md border border-border px-3 py-2" value={projectEdit.name} onChange={(event) => setProjectEdit({ ...projectEdit, name: event.target.value })} required />
                <select className="rounded-md border border-border px-3 py-2" value={projectEdit.owner_user_id} onChange={(event) => setProjectEdit({ ...projectEdit, owner_user_id: event.target.value })}>
                  <option value="">项目负责人</option>
                  {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                </select>
                <select className="rounded-md border border-border px-3 py-2" value={projectEdit.status} onChange={(event) => setProjectEdit({ ...projectEdit, status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="archived">archived</option>
                </select>
                <textarea className="rounded-md border border-border px-3 py-2 md:col-span-2 xl:col-span-3" value={projectEdit.description} onChange={(event) => setProjectEdit({ ...projectEdit, description: event.target.value })} />
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={projectEdit.is_sensitive} onChange={(event) => setProjectEdit({ ...projectEdit, is_sensitive: event.target.checked })} />敏感项目</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={projectEdit.approval_enabled} onChange={(event) => setProjectEdit({ ...projectEdit, approval_enabled: event.target.checked })} />启用审批</label>
                <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存项目</button>
              </div>
            </form>
          )}

          {workspaceView === "project" && activeProjectTab === "members" && (
          <div className={cardClass("p-5")}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold">成员权限</h2>
            </div>
            {selectedProjectId && canManageSelectedProject && (
              <form onSubmit={handleAddMember} className="mb-5 grid gap-3 rounded-md border border-border bg-surface p-4 md:grid-cols-[1fr_1fr_auto]">
                <select className="rounded-md border border-border px-3 py-2" value={memberDraft.user_id} onChange={(event) => setMemberDraft({ ...memberDraft, user_id: event.target.value })} required>
                  <option value="">选择授权用户</option>
                  {users.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.role}</option>)}
                </select>
                <select className="rounded-md border border-border px-3 py-2" value={memberDraft.project_role} onChange={(event) => setMemberDraft({ ...memberDraft, project_role: event.target.value })}>
                  {projectRoleOptions.map((role) => <option key={role}>{role}</option>)}
                </select>
                <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">添加成员</button>
                <div className="flex flex-wrap gap-4 text-sm md:col-span-3">
                  {(["can_read", "can_write", "can_review", "can_manage"] as const).map((key) => (
                    <label key={key} className="flex items-center gap-2">
                      <input type="checkbox" checked={memberDraft[key]} onChange={(event) => setMemberDraft({ ...memberDraft, [key]: event.target.checked })} />
                      {key}
                    </label>
                  ))}
                </div>
              </form>
            )}
            <div className="flex flex-wrap gap-2">
              {members.map((member) => (
                <div key={member.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-xs">
                  <span className="min-w-24 font-medium">{usersById.get(member.user_id)?.display_name || `用户 ${member.user_id}`}</span>
                  <select disabled={!canManageSelectedProject} className="rounded-md border border-border px-2 py-1 disabled:opacity-60" value={member.project_role} onChange={(event) => void handleUpdateMember(member, { project_role: event.target.value })}>
                    {projectRoleOptions.map((role) => <option key={role}>{role}</option>)}
                  </select>
                  {(["can_read", "can_write", "can_review", "can_manage"] as const).map((key) => (
                    <label key={key} className="flex items-center gap-1">
                      <input type="checkbox" disabled={!canManageSelectedProject} checked={member[key]} onChange={(event) => void handleUpdateMember(member, { [key]: event.target.checked })} />
                      {key.replace("can_", "")}
                    </label>
                  ))}
                  {canManageSelectedProject && (
                    <>
                      <button type="button" onClick={() => selectedProjectId && void addProjectReviewer(token, selectedProjectId, { user_id: member.user_id }).then(() => refreshAll(token, selectedProjectId))} className="rounded-md border border-border px-2 py-1">设为审核人</button>
                      <button type="button" onClick={() => void handleRemoveMember(member)} className="rounded-md border border-red-200 px-2 py-1 text-red-700">移除</button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "notes" && (
          <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
            <form onSubmit={saveNote} className={cardClass("p-5")}>
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 font-semibold"><FileText size={18} />实验笔记编辑</h2>
                {canWriteSelectedProject && (
                  <button type="button" onClick={() => { setSelectedNote(null); setVersions([]); setApprovals([]); setEditor(emptyEditor); }} className="rounded-md border border-border px-3 py-1 text-sm">新建</button>
                )}
              </div>
              {!canWriteSelectedProject && <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">当前账号仅可查看实验笔记，不能创建或编辑。</p>}
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <input disabled={!canWriteSelectedProject} className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" placeholder="实验标题" value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} required />
                <select disabled={!canWriteSelectedProject} className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" value={editor.template_id || ""} onChange={(event) => applyTemplate(Number(event.target.value))}>
                  <option value="">选择模板</option>
                  {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
                </select>
                <input disabled={!canWriteSelectedProject} className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" placeholder="实验类型" value={editor.experiment_type} onChange={(event) => setEditor({ ...editor, experiment_type: event.target.value })} required />
                <input disabled={!canWriteSelectedProject} className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" type="date" value={editor.experiment_date} onChange={(event) => setEditor({ ...editor, experiment_date: event.target.value })} />
              </div>
              {selectedTemplate && (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {(selectedTemplate.schema_json.fields || []).map((field) => (
                    <label key={field.key} className="text-sm font-medium">
                      {field.label}
                      <textarea disabled={!canWriteSelectedProject} className="mt-2 min-h-20 w-full rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" value={editor.fixed_fields_json[field.key] || ""} onChange={(event) => setEditor({ ...editor, fixed_fields_json: { ...editor.fixed_fields_json, [field.key]: event.target.value } })} />
                    </label>
                  ))}
                </div>
              )}
              <label className="mt-4 block text-sm font-medium">
                自由正文
                <textarea disabled={!canWriteSelectedProject} className="mt-2 min-h-44 w-full rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted" value={editor.content_text} onChange={(event) => setEditor({ ...editor, content_text: event.target.value })} placeholder="记录实验过程、观察、结果分析和下一步计划" />
              </label>
              <div className="mt-4 flex flex-wrap gap-2">
                {canWriteSelectedProject && <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存笔记</button>}
                {selectedNote && canSubmitSelectedNote && (
                  <button type="button" onClick={() => void afterNoteAction(submitNote(token, selectedNote.id), "实验笔记已提交审批")} className="rounded-md border border-border px-4 py-2 text-sm">提交审批</button>
                )}
                {selectedNote && canWriteSelectedProject && ["approved", "returned", "draft"].includes(selectedNote.status) && (
                  <button type="button" onClick={() => void afterNoteAction(archiveNote(token, selectedNote.id), "实验笔记已归档")} className="rounded-md border border-border px-4 py-2 text-sm">归档</button>
                )}
                {selectedNote && canReviewSelectedProject && selectedNote.status !== "voided" && (
                  <button type="button" onClick={() => void afterNoteAction(voidNote(token, selectedNote.id, approvalComment), "实验笔记已作废")} className="rounded-md border border-red-200 px-4 py-2 text-sm text-red-700">作废</button>
                )}
              </div>
            </form>

            <div className={cardClass("p-5")}>
              <h2 className="font-semibold">实验笔记列表</h2>
              <div className="mt-4 grid gap-2 md:grid-cols-3">
                <input className="rounded-md border border-border px-3 py-2 text-sm" placeholder="搜索标题/类型" value={noteFilters.keyword} onChange={(event) => setNoteFilters({ ...noteFilters, keyword: event.target.value })} />
                <select className="rounded-md border border-border px-3 py-2 text-sm" value={noteFilters.status} onChange={(event) => setNoteFilters({ ...noteFilters, status: event.target.value })}>
                  <option value="">全部状态</option>
                  {Object.entries(statusText).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <select className="rounded-md border border-border px-3 py-2 text-sm" value={noteFilters.experiment_type} onChange={(event) => setNoteFilters({ ...noteFilters, experiment_type: event.target.value })}>
                  <option value="">全部类型</option>
                  {experimentTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
              </div>
              <div className="mt-4 max-h-[520px] space-y-2 overflow-auto">
                {filteredNotes.length === 0 && <p className="text-sm text-muted">暂无匹配实验笔记。</p>}
                {filteredNotes.map((note) => (
                  <button key={note.id} onClick={() => editNote(note)} className={`w-full rounded-md border px-3 py-3 text-left text-sm ${selectedNote?.id === note.id ? "border-brand bg-[#eef8f6]" : "border-border hover:bg-surface"}`}>
                    <span className="font-medium">{note.title}</span>
                    <span className="mt-1 block text-xs text-muted">{note.experiment_type} · {statusText[note.status] || note.status}</span>
                  </button>
                ))}
              </div>
              {versions.length > 0 && (
                <div className="mt-5 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold">版本历史</h3>
                  <div className="mt-2 space-y-2 text-sm text-muted">
                    {versions.map((version) => (
                      <div key={version.id} className="rounded-md border border-border px-3 py-2">
                        v{version.version_number} · {version.is_locked ? "已锁定" : "未锁定"} · {new Date(version.created_at).toLocaleString("zh-CN")}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {approvals.length > 0 && (
                <div className="mt-5 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold">审批记录</h3>
                  <div className="mt-2 space-y-2 text-sm text-muted">
                    {approvals.map((approval) => (
                      <div key={approval.id} className="rounded-md border border-border px-3 py-2">
                        {approval.action} · 审核人 {approval.reviewer_user_id} · {new Date(approval.created_at).toLocaleString("zh-CN")}
                        {approval.comment && <p className="mt-1 text-foreground">{approval.comment}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "approvals" && (
          <div className={cardClass("p-5")}>
            <h2 className="flex items-center gap-2 font-semibold"><ClipboardCheck size={18} />审批中心</h2>
            {!canReviewSelectedProject && <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">当前账号没有项目审核权限。</p>}
            <div className="mt-4 space-y-2">
              {pendingNotes.filter((note) => !selectedProjectId || note.project_id === selectedProjectId).length === 0 && <p className="text-sm text-muted">当前项目暂无待审核笔记。</p>}
              {pendingNotes.filter((note) => !selectedProjectId || note.project_id === selectedProjectId).map((note) => (
                <div key={note.id} className="rounded-md border border-border p-3">
                  <p className="font-medium">{note.title}</p>
                  <p className="mt-1 text-xs text-muted">项目 {note.project_id} · {note.experiment_type}</p>
                  {canReviewSelectedProject && (
                    <>
                      <textarea className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm" placeholder="审核意见" value={approvalComment} onChange={(event) => setApprovalComment(event.target.value)} />
                      <div className="mt-2 flex gap-2">
                        <button type="button" onClick={() => void afterNoteAction(approveNote(token, note.id, approvalComment), "实验笔记已通过")} className="flex items-center gap-1 rounded-md bg-accent px-3 py-1 text-sm text-white"><CheckCircle2 size={15} />通过</button>
                        <button type="button" onClick={() => void afterNoteAction(returnNote(token, note.id, approvalComment), "实验笔记已退回")} className="flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm"><XCircle size={15} />退回</button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "files" && (
          <div className="grid gap-6">
            <div className={cardClass("p-5")}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={18} />AI 知识库</h2>
                  <p className="mt-1 text-sm text-muted">只使用当前项目中审核通过并同步的资料回答问题。</p>
                </div>
                {canReviewSelectedProject && (
                  <button
                    type="button"
                    disabled={ragBusy || ragStatus?.initialized}
                    onClick={() => void handleInitRag()}
                    className="rounded-md border border-border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {ragStatus?.initialized ? "已初始化" : "初始化知识库"}
                  </button>
                )}
              </div>
              <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">状态</p>
                  <p className="mt-1 font-medium">{ragStatus?.initialized ? "已初始化" : "未初始化"}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">待同步</p>
                  <p className="mt-1 font-medium">{ragStatus?.pending_sync_count ?? 0}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">已入库</p>
                  <p className="mt-1 font-medium">{ragStatus?.synced_count ?? 0}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">失败</p>
                  <p className="mt-1 font-medium">{ragStatus?.failed_sync_count ?? 0}</p>
                </div>
              </div>
              {ragStatus?.dataset && (
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
                  <span className="rounded-md border border-border px-2 py-1">生成模型：{ragStatus.dataset.generation_model}</span>
                  <span className="rounded-md border border-border px-2 py-1">嵌入模型：{ragStatus.dataset.embedding_model}</span>
                  <span className="rounded-md border border-border px-2 py-1">运行方式：本地向量检索 + DeepSeek</span>
                </div>
              )}
              {queryAnalytics && (
                <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">AI 成效概览</h3>
                      <p className="mt-1 text-xs text-muted">用于论文第 7 章的问答质量统计与模式对比。</p>
                    </div>
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-xs text-muted">
                      评价覆盖率 {formatRate(queryAnalytics.evaluation_rate)}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm md:grid-cols-6">
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">问答次数</p>
                      <p className="mt-1 font-medium">{queryAnalytics.total_queries}</p>
                    </div>
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">平均评分</p>
                      <p className="mt-1 font-medium">{formatScore(queryAnalytics.avg_score)}</p>
                    </div>
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">准确率</p>
                      <p className="mt-1 font-medium">{formatRate(queryAnalytics.accurate_rate)}</p>
                    </div>
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">可追溯率</p>
                      <p className="mt-1 font-medium">{formatRate(queryAnalytics.traceable_rate)}</p>
                    </div>
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">平均图谱命中</p>
                      <p className="mt-1 font-medium">{queryAnalytics.avg_graph_hit_count.toFixed(1)}</p>
                    </div>
                    <div className="rounded-md border border-border bg-white px-3 py-2">
                      <p className="text-xs text-muted">平均响应</p>
                      <p className="mt-1 font-medium">{Math.round(queryAnalytics.avg_response_ms)} ms</p>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {queryAnalytics.mode_stats.map((stat) => (
                      <div key={stat.rag_mode} className="rounded-md border border-border bg-white px-3 py-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-foreground">{ragModeLabel(stat.rag_mode)}</span>
                          <span className="text-muted">{stat.total_queries} 次 / 已评 {stat.evaluated_queries}</span>
                        </div>
                        <div className="mt-2 grid grid-cols-4 gap-2 text-muted">
                          <span>评分 {formatScore(stat.avg_score)}</span>
                          <span>准确 {formatRate(stat.accurate_rate)}</span>
                          <span>追溯 {formatRate(stat.traceable_rate)}</span>
                          <span>图谱 {stat.avg_graph_hit_count.toFixed(1)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {canReviewSelectedProject && (
                <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">论文对照实验</h3>
                      <p className="mt-1 text-xs text-muted">对同一题集分别运行普通 RAG 与知识图谱增强 RAG，并保存配置快照和 CSV。</p>
                    </div>
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-xs text-muted">
                      已运行 {experimentRuns.length} 次
                    </span>
                  </div>
                  <form onSubmit={handleRunRagExperiment} className="mt-3 grid gap-2">
                    <input
                      className="rounded-md border border-border px-3 py-2 text-sm"
                      value={experimentDraft.name}
                      onChange={(event) => setExperimentDraft({ ...experimentDraft, name: event.target.value })}
                      placeholder="实验名称"
                    />
                    <textarea
                      className="min-h-24 rounded-md border border-border px-3 py-2 text-sm"
                      value={experimentDraft.questions}
                      onChange={(event) => setExperimentDraft({ ...experimentDraft, questions: event.target.value })}
                      placeholder="每行一个问题"
                    />
                    <button
                      disabled={experimentBusy || !ragStatus?.initialized}
                      className="justify-self-start rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {experimentBusy ? "正在运行，请勿关闭页面" : "运行成对对照实验"}
                    </button>
                  </form>
                  <div className="mt-3 grid gap-2">
                    {experimentRuns.slice(0, 5).map((run) => (
                      <div key={run.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-white px-3 py-2 text-xs">
                        <div>
                          <p className="font-medium text-foreground">#{run.id} {run.name}</p>
                          <p className="mt-1 text-muted">
                            {run.completed_cases}/{run.total_cases} 成功 · {run.failed_cases} 失败 · {new Date(run.created_at).toLocaleString()}
                          </p>
                        </div>
                        <button type="button" onClick={() => void handleDownloadRagExperiment(run)} className="rounded-md border border-border px-3 py-1">
                          导出 CSV
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <form onSubmit={handleQueryRag} className="mt-4 grid gap-2 md:grid-cols-[180px_1fr_auto]">
                <select
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={ragMode}
                  onChange={(event) => setRagMode(event.target.value)}
                >
                  <option value="auto">自动选择</option>
                  <option value="project_rag">普通 RAG</option>
                  <option value="kg_enhanced_rag">图谱增强 RAG</option>
                </select>
                <input
                  className="min-w-0 rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="向当前项目资料提问"
                  value={ragQuestion}
                  onChange={(event) => setRagQuestion(event.target.value)}
                />
                <button
                  disabled={ragBusy || !ragStatus?.initialized}
                  className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  提问
                </button>
              </form>
              {!ragStatus?.initialized && <p className="mt-3 text-xs text-muted">请先由审核人或管理员初始化该项目知识库。</p>}
              {ragAnswer && (
                <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3 text-sm">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                      回答模式：{ragAnswer.rag_mode === "kg_enhanced_rag" ? "知识图谱增强 RAG" : "项目级 RAG"}
                    </span>
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                      图谱依据：{ragAnswer.graph_context.length} 条
                    </span>
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                      响应耗时：{ragAnswer.response_ms ?? 0} ms
                    </span>
                    <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                      模型：{ragAnswer.provider}/{ragAnswer.model_name || "未知"}
                    </span>
                    {ragAnswer.query_log_id && (
                      <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                        记录编号：{ragAnswer.query_log_id}
                      </span>
                    )}
                  </div>
                  {ragAnswer.fallback_reason && (
                    <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-2 py-2 text-xs text-amber-800">
                      降级说明：{ragAnswer.fallback_reason}
                    </p>
                  )}
                  <p className="whitespace-pre-wrap">{ragAnswer.answer || "AI 没有返回回答。"}</p>
                  {ragAnswer.graph_context.length > 0 && (
                    <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                      <p className="font-medium text-foreground">图谱依据</p>
                      <div className="mt-2 grid gap-2 md:grid-cols-2">
                        {ragAnswer.graph_context.map((item) => (
                          <div key={item.relation_id} className="rounded-md border border-border bg-white px-2 py-2">
                            <p className="font-medium text-foreground">
                              {item.source_label} → {item.target_label}
                            </p>
                            <p className="mt-1">
                              {item.source_entity_type_label} --{item.relation_label}--&gt; {item.target_entity_type_label}
                              {" · "}置信度 {item.confidence.toFixed(2)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {ragAnswer.sources.length > 0 && (
                    <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                      <p className="font-medium text-foreground">来源</p>
                      {ragAnswer.sources.map((source, index) => (
                        <p key={`${source.dify_document_id || source.file_id || index}-${index}`} className="mt-1">
                          {source.filename || source.dify_document_id || "未知资料"}
                          {source.snippet ? `：${source.snippet.slice(0, 120)}` : ""}
                          {source.retrieval_score != null ? `（综合相关度 ${source.retrieval_score.toFixed(3)}）` : ""}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div className="mt-4 border-t border-border pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">问答记录与评价</h3>
                  <button
                    type="button"
                    disabled={ragBusy || !selectedProjectId}
                    onClick={() =>
                      selectedProjectId &&
                      Promise.all([
                        getProjectQueryLogs(token, selectedProjectId).catch(() => []),
                        getProjectQueryAnalytics(token, selectedProjectId).catch(() => null),
                      ]).then(([nextLogs, nextAnalytics]) => {
                        setQueryLogs(nextLogs);
                        setQueryAnalytics(nextAnalytics);
                      })
                    }
                    className="rounded-md border border-border px-3 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    刷新记录
                  </button>
                </div>
                <div className="mt-3 max-h-96 space-y-3 overflow-auto">
                  {queryLogs.length === 0 && <p className="text-sm text-muted">暂无问答记录。</p>}
                  {queryLogs.slice(0, 8).map((log) => {
                    const draft = evaluationDrafts[log.id] || {
                      score: log.evaluation ? String(log.evaluation.score) : "",
                      is_accurate: log.evaluation?.is_accurate ?? null,
                      is_traceable: log.evaluation?.is_traceable ?? null,
                      comment: log.evaluation?.comment || "",
                    };
                    return (
                      <div key={log.id} className="rounded-md border border-border bg-white px-3 py-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                          <span>{new Date(log.created_at).toLocaleString()}</span>
                          <span>{log.rag_mode === "kg_enhanced_rag" ? "知识图谱增强 RAG" : "项目级 RAG"}</span>
                          <span>{log.provider}/{log.model_name || "未知模型"}</span>
                          <span>图谱 {log.graph_hit_count} 条</span>
                          <span>来源 {log.source_count} 个</span>
                          {log.experiment_run_id && <span>实验 #{log.experiment_run_id} / 题 {log.experiment_case_index}</span>}
                          <span>{log.response_ms} ms</span>
                          {log.evaluation && <span className="text-brand">已评价 {log.evaluation.score}/5</span>}
                        </div>
                        <p className="mt-2 font-medium">{log.question}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted">{log.error_message || log.answer || "无回答内容"}</p>
                        <div className="mt-3 grid gap-2 md:grid-cols-[90px_1fr_100px_110px_auto]">
                          <select
                            className="rounded-md border border-border px-2 py-1 text-xs"
                            value={draft.score}
                            onChange={(event) =>
                              setEvaluationDrafts((current) => ({ ...current, [log.id]: { ...draft, score: event.target.value } }))
                            }
                          >
                            <option value="">评分</option>
                            {[5, 4, 3, 2, 1].map((score) => (
                              <option key={score} value={score}>{score} 分</option>
                            ))}
                          </select>
                          <input
                            className="rounded-md border border-border px-2 py-1 text-xs"
                            placeholder="评价备注"
                            value={draft.comment}
                            onChange={(event) =>
                              setEvaluationDrafts((current) => ({ ...current, [log.id]: { ...draft, comment: event.target.value } }))
                            }
                          />
                          <select
                            aria-label="准确性"
                            className="rounded-md border border-border px-2 py-1 text-xs"
                            value={draft.is_accurate === null ? "" : String(draft.is_accurate)}
                            onChange={(event) =>
                              setEvaluationDrafts((current) => ({
                                ...current,
                                [log.id]: {
                                  ...draft,
                                  is_accurate: event.target.value === "" ? null : event.target.value === "true",
                                },
                              }))
                            }
                          >
                            <option value="">准确性</option>
                            <option value="true">准确</option>
                            <option value="false">不准确</option>
                          </select>
                          <select
                            aria-label="可追溯性"
                            className="rounded-md border border-border px-2 py-1 text-xs"
                            value={draft.is_traceable === null ? "" : String(draft.is_traceable)}
                            onChange={(event) =>
                              setEvaluationDrafts((current) => ({
                                ...current,
                                [log.id]: {
                                  ...draft,
                                  is_traceable: event.target.value === "" ? null : event.target.value === "true",
                                },
                              }))
                            }
                          >
                            <option value="">可追溯性</option>
                            <option value="true">可追溯</option>
                            <option value="false">不可追溯</option>
                          </select>
                          <button
                            type="button"
                            disabled={
                              ragBusy
                              || !draft.score
                              || draft.is_accurate === null
                              || draft.is_traceable === null
                            }
                            onClick={() => void handleEvaluateQueryLog(log)}
                            className="rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            保存评价
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className={cardClass("p-5")}>
              <h2 className="flex items-center gap-2 font-semibold"><Upload size={18} />附件与资料</h2>
              {canWriteSelectedProject ? (
                <form onSubmit={handleUpload} className="mt-4 flex flex-wrap gap-2">
                  <input name="file" type="file" className="rounded-md border border-border px-3 py-2 text-sm" />
                  <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">上传</button>
                  <span className="self-center text-xs text-muted">{selectedNote ? "上传为当前笔记附件" : "未选笔记时上传为项目资料"}</span>
                </form>
              ) : (
                <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">当前账号仅可查看和下载文件。</p>
              )}
              {canReviewSelectedProject && <textarea className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm" placeholder="资料审核意见" value={fileReviewComment} onChange={(event) => setFileReviewComment(event.target.value)} />}
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                <input className="rounded-md border border-border px-3 py-2 text-sm" placeholder="搜索文件名/哈希" value={fileFilters.keyword} onChange={(event) => setFileFilters({ ...fileFilters, keyword: event.target.value })} />
                <select className="rounded-md border border-border px-3 py-2 text-sm" value={fileFilters.category} onChange={(event) => setFileFilters({ ...fileFilters, category: event.target.value })}>
                  <option value="">全部类型</option>
                  <option value="note_attachment">笔记附件</option>
                  <option value="knowledge_document">资料库</option>
                </select>
                <select className="rounded-md border border-border px-3 py-2 text-sm" value={fileFilters.status} onChange={(event) => setFileFilters({ ...fileFilters, status: event.target.value })}>
                  <option value="">全部状态</option>
                  <option value="uploaded">uploaded</option>
                  <option value="approved">approved</option>
                  <option value="rejected">rejected</option>
                  <option value="archived">archived</option>
                </select>
              </div>
              <div className="mt-4 max-h-80 space-y-2 overflow-auto">
                {filteredFiles.length === 0 && <p className="text-sm text-muted">暂无匹配文件。</p>}
                {filteredFiles.map((file) => (
                  <div key={file.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <input
                        disabled={!canWriteSelectedProject}
                        className="w-full rounded-md border border-border px-2 py-1 text-sm font-medium disabled:bg-surface disabled:text-muted"
                        value={fileEdits[file.id] ?? file.original_filename}
                        onChange={(event) => setFileEdits({ ...fileEdits, [file.id]: event.target.value })}
                      />
                      <p className="text-xs text-muted">{file.file_category} · {file.status} · {(file.file_size / 1024).toFixed(1)} KB</p>
                      {file.file_category === "knowledge_document" && (
                        <p className="mt-1 text-xs text-muted">
                          知识库：{knowledgeSyncText[file.knowledge_sync_status] || file.knowledge_sync_status}
                          {file.knowledge_sync_message ? ` · ${file.knowledge_sync_message}` : ""}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      {canReviewSelectedProject && file.file_category === "knowledge_document" && file.status === "uploaded" && (
                        <>
                          <button type="button" onClick={() => reviewFile(token, file.id, "approve", fileReviewComment).then(() => refreshAll())} className="rounded-md border border-green-200 px-3 py-1 text-xs text-green-700">通过</button>
                          <button type="button" onClick={() => reviewFile(token, file.id, "reject", fileReviewComment).then(() => refreshAll())} className="rounded-md border border-red-200 px-3 py-1 text-xs text-red-700">拒绝</button>
                        </>
                      )}
                      {canReviewSelectedProject && file.file_category === "knowledge_document" && file.status === "approved" && file.knowledge_sync_status !== "synced" && ragStatus?.initialized && (
                        <button type="button" disabled={ragBusy} onClick={() => void handleSyncRagFile(file)} className="rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60">本地向量入库</button>
                      )}
                      {canWriteSelectedProject && <button type="button" onClick={() => void handleUpdateFile(file)} className="rounded-md border border-border px-3 py-1 text-xs">保存</button>}
                      {canWriteSelectedProject && file.status !== "archived" && (
                        <button type="button" onClick={() => void handleArchiveFile(file)} className="rounded-md border border-border px-3 py-1 text-xs">归档</button>
                      )}
                      <button type="button" onClick={() => handleDownload(file)} className="rounded-md border border-border px-3 py-1 text-xs">下载</button>
                      <button type="button" onClick={() => void handleOcrExtract(file)} className="rounded-md border border-border px-3 py-1 text-xs">OCR</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "search" && selectedProjectId && (
          <div className="grid gap-4">
            <div className={cardClass("p-5")}>
              <h2 className="flex items-center gap-2 font-semibold"><FileSearch size={18} />全文搜索</h2>
              <p className="mt-1 text-sm text-muted">在当前项目中搜索实验笔记的内容。</p>
              <form onSubmit={handleSearch} className="mt-4 flex flex-wrap gap-2">
                <input
                  className="min-w-[260px] flex-1 rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="输入搜索关键词"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
                <button disabled={searchBusy} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60">
                  {searchBusy ? "搜索中..." : "搜索"}
                </button>
              </form>
              {searchResults.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-sm text-muted">共找到 {searchResults.length} 条结果</p>
                  {searchResults.map((result) => (
                    <div key={result.document_id} className="rounded-md border border-border px-3 py-2 text-sm">
                      <p className="font-medium">{result.title}</p>
                      <p className="mt-1 text-muted line-clamp-2">{result.snippet}</p>
                      <p className="mt-1 text-xs text-muted">实验笔记 ID: {result.note_id}</p>
                    </div>
                  ))}
                </div>
              )}
              {searchResults.length === 0 && searchQuery && !searchBusy && (
                <p className="mt-4 text-sm text-muted">未找到匹配结果。</p>
              )}
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "kg" && selectedProjectId && (
          <div className="grid gap-4">
            <div className={cardClass("p-5")}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={18} />实验知识图谱</h2>
                  <p className="mt-1 text-sm text-muted">从实验笔记中抽取项目、人员、附件、试剂、仪器、样本和结果关系，用于后续图谱增强 RAG。</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={kgBusy}
                    onClick={() => void refreshKnowledgeGraph()}
                    className="rounded-md border border-border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    刷新图谱
                  </button>
                  {canWriteSelectedProject && selectedNote && (
                    <button
                      type="button"
                      disabled={kgBusy}
                      onClick={() => void handleExtractSelectedNoteKg()}
                      className="rounded-md border border-brand px-3 py-2 text-sm text-brand disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      抽取当前笔记
                    </button>
                  )}
                  {canWriteSelectedProject && (
                    <button
                      type="button"
                      disabled={kgBusy || notes.length === 0}
                      onClick={() => void handleRebuildProjectKg()}
                      className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      重建项目图谱
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">实体总数</p>
                  <p className="mt-1 font-medium">{kgGraph?.entities.length ?? 0}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">关系总数</p>
                  <p className="mt-1 font-medium">{kgGraph?.relations.length ?? 0}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">实验笔记</p>
                  <p className="mt-1 font-medium">{kgEntityStats.find(([type]) => type === "note")?.[1] ?? 0}</p>
                </div>
                <div className="rounded-md border border-border px-3 py-2">
                  <p className="text-xs text-muted">抽取状态</p>
                  <p className="mt-1 font-medium">{kgBusy ? "处理中..." : kgGraph?.entities.length ? "已生成" : "待生成"}</p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <select
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={kgEntityFilter}
                  onChange={(event) => {
                    setKgEntityFilter(event.target.value);
                    setSelectedKgEntityId(null);
                  }}
                >
                  <option value="">全部实体类型</option>
                  {kgEntityTypeOptions.map((type) => (
                    <option key={type} value={type}>{kgTypeLabel(type)}</option>
                  ))}
                </select>
                <select
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={kgRelationFilter}
                  onChange={(event) => setKgRelationFilter(event.target.value)}
                >
                  <option value="">全部关系类型</option>
                  {kgRelationTypeOptions.map((type) => (
                    <option key={type} value={type}>{kgRelationLabel(type)}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    setKgEntityFilter("");
                    setKgRelationFilter("");
                    setSelectedKgEntityId(null);
                  }}
                  className="rounded-md border border-border px-3 py-2 text-sm"
                >
                  清除筛选
                </button>
              </div>
              <p className="mt-2 text-xs text-muted">当前筛选展示 {filteredKgEntities.length} 个实体、{filteredKgRelations.length} 条关系。</p>
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.45fr_0.55fr]">
              <div className={cardClass("p-5")}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">项目关系图</h3>
                  <p className="text-xs text-muted">按关联度展示 16 个代表节点 / 36 条关系</p>
                </div>
                {(!kgGraph || kgGraph.entities.length === 0) && (
                  <div className="mt-4 rounded-md border border-dashed border-border bg-surface px-4 py-10 text-center text-sm text-muted">
                    当前项目还没有知识图谱。先选择一篇笔记抽取，或直接重建项目图谱。
                  </div>
                )}
                {kgGraph && kgGraph.entities.length > 0 && (
                  <div className="mt-4 overflow-auto rounded-md border border-border bg-surface">
                    <svg viewBox="0 0 800 500" className="h-[500px] min-w-[800px] w-full" aria-label="项目知识图谱">
                      <rect width="800" height="500" fill="#f8fafc" />
                      {kgLayout.relations.map((relation) => {
                        const source = kgLayout.nodeById.get(relation.source_entity_id);
                        const target = kgLayout.nodeById.get(relation.target_entity_id);
                        if (!source || !target) return null;
                        const isConnected =
                          !selectedKgEntityId ||
                          relation.source_entity_id === selectedKgEntityId ||
                          relation.target_entity_id === selectedKgEntityId;
                        return (
                          <line
                            key={relation.id}
                            x1={source.x}
                            y1={source.y}
                            x2={target.x}
                            y2={target.y}
                            stroke={isConnected ? "#94a3b8" : "#e2e8f0"}
                            strokeWidth={isConnected ? 1.5 : 0.8}
                            opacity={isConnected ? 0.72 : 0.28}
                          >
                            <title>{kgRelationLabel(relation.relation_type)}</title>
                          </line>
                        );
                      })}
                      {kgLayout.nodes.map((node) => {
                        const color = kgEntityColors[node.entity.entity_type] || "#64748b";
                        const isProject = node.entity.entity_type === "project";
                        const isSelected = selectedKgEntityId === node.entity.id;
                        const isRelated =
                          !selectedKgEntityId ||
                          isSelected ||
                          selectedKgEntityRelations.some(
                            (relation) =>
                              relation.source_entity_id === node.entity.id || relation.target_entity_id === node.entity.id,
                          );
                        return (
                          <g
                            key={node.entity.id}
                            onClick={() => setSelectedKgEntityId(isSelected ? null : node.entity.id)}
                            className="cursor-pointer"
                            opacity={isRelated ? 1 : 0.35}
                          >
                            <circle
                              cx={node.x}
                              cy={node.y}
                              r={isProject ? 38 : 18}
                              fill={color}
                              opacity="0.96"
                              stroke={isSelected ? "#0f172a" : "#ffffff"}
                              strokeWidth={isSelected ? 4 : 2}
                            />
                            {isProject ? (
                              <>
                                <text x={node.x} y={node.y - 3} textAnchor="middle" className="fill-white text-[11px] font-semibold">
                                  {shortLabel(node.entity.label, 10)}
                                </text>
                                <text x={node.x} y={node.y + 13} textAnchor="middle" className="fill-white text-[9px] opacity-90">
                                  项目
                                </text>
                              </>
                            ) : (
                              <>
                                <text x={node.x} y={node.y + 4} textAnchor="middle" className="fill-white text-[9px] font-bold">
                                  {kgEntityShortText[node.entity.entity_type] || "点"}
                                </text>
                                <text
                                  x={node.x}
                                  y={node.y + 34}
                                  textAnchor="middle"
                                  className="fill-slate-800 text-[10px] font-medium"
                                  style={{ paintOrder: "stroke", stroke: "#f8fafc", strokeWidth: 4, strokeLinejoin: "round" }}
                                >
                                  {shortLabel(node.entity.label, 10)}
                                </text>
                              </>
                            )}
                            <title>{kgTypeLabel(node.entity.entity_type)}：{node.entity.label}</title>
                          </g>
                        );
                      })}
                    </svg>
                  </div>
                )}
              </div>

              <div className={cardClass("p-5")}>
                <h3 className="font-semibold">实体类型分布</h3>
                <div className="mt-4 space-y-2 text-sm">
                  {kgEntityStats.length === 0 && <p className="text-muted">暂无实体统计。</p>}
                  {kgEntityStats.map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: kgEntityColors[type] || "#64748b" }} />
                        {kgTypeLabel(type)}
                      </span>
                      <span className="font-medium">{count}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-5 border-t border-border pt-4 text-sm">
                  <h4 className="font-semibold">实体详情</h4>
                  {!selectedKgEntity && <p className="mt-3 text-muted">点击图谱节点查看实体来源、属性和关联关系。</p>}
                  {selectedKgEntity && (
                    <div className="mt-3 space-y-3">
                      <div className="rounded-md border border-border px-3 py-2">
                        <p className="font-medium">{selectedKgEntity.label}</p>
                        <p className="mt-1 text-xs text-muted">
                          {kgTypeLabel(selectedKgEntity.entity_type)}
                          {selectedKgEntity.source_type ? ` · 来源 ${selectedKgEntity.source_type} #${selectedKgEntity.source_id}` : ""}
                        </p>
                        {selectedKgEntity.source_type === "note" && selectedKgEntity.source_id && (
                          <button
                            type="button"
                            onClick={() => {
                              const note = notes.find((item) => item.id === selectedKgEntity.source_id);
                              if (note) {
                                setActiveProjectTab("notes");
                                editNote(note);
                              }
                            }}
                            className="mt-2 rounded-md border border-brand px-3 py-1 text-xs text-brand"
                          >
                            跳转笔记
                          </button>
                        )}
                        {selectedKgEntity.source_type === "file" && selectedKgEntity.source_id && (
                          <button
                            type="button"
                            onClick={() => setActiveProjectTab("files")}
                            className="mt-2 rounded-md border border-brand px-3 py-1 text-xs text-brand"
                          >
                            查看资料库
                          </button>
                        )}
                      </div>
                      {Object.keys(selectedKgEntity.properties || {}).length > 0 && (
                        <pre className="max-h-32 overflow-auto rounded-md border border-border bg-surface px-3 py-2 text-xs text-muted">
                          {JSON.stringify(selectedKgEntity.properties, null, 2)}
                        </pre>
                      )}
                      <div className="max-h-44 space-y-2 overflow-auto">
                        {selectedKgEntityRelations.length === 0 && <p className="text-xs text-muted">暂无关联关系。</p>}
                        {selectedKgEntityRelations.map((relation) => {
                          const source = kgEntityById.get(relation.source_entity_id);
                          const target = kgEntityById.get(relation.target_entity_id);
                          return (
                            <div key={relation.id} className="rounded-md border border-border px-3 py-2 text-xs">
                              <p className="font-medium">{source?.label || relation.source_entity_id} → {target?.label || relation.target_entity_id}</p>
                              <p className="mt-1 text-muted">{kgRelationLabel(relation.relation_type)} · 置信度 {relation.confidence.toFixed(2)}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className={cardClass("p-5")}>
                <h3 className="font-semibold">笔记抽取入口</h3>
                <div className="mt-4 max-h-72 space-y-2 overflow-auto">
                  {notes.length === 0 && <p className="text-sm text-muted">当前项目还没有实验笔记。</p>}
                  {notes.map((note) => (
                    <div key={note.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
                      <button type="button" onClick={() => editNote(note)} className="min-w-0 text-left">
                        <span className="block truncate font-medium">{note.title}</span>
                        <span className="mt-1 block text-xs text-muted">{note.experiment_type} · {statusText[note.status] || note.status}</span>
                      </button>
                      {canWriteSelectedProject && (
                        <button
                          type="button"
                          disabled={kgBusy}
                          onClick={() => void handleExtractSelectedNoteKg(note)}
                          className="shrink-0 rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          抽取
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className={cardClass("p-5")}>
                <h3 className="font-semibold">关系明细</h3>
                <div className="mt-4 max-h-72 space-y-2 overflow-auto text-sm">
                  {filteredKgRelations.length === 0 && <p className="text-muted">暂无关系数据。</p>}
                  {filteredKgRelations.slice(0, 80).map((relation) => {
                    const source = kgEntityById.get(relation.source_entity_id);
                    const target = kgEntityById.get(relation.target_entity_id);
                    return (
                      <div key={relation.id} className="rounded-md border border-border px-3 py-2">
                        <p className="font-medium">{source?.label || relation.source_entity_id} → {target?.label || relation.target_entity_id}</p>
                        <p className="mt-1 text-xs text-muted">{kgRelationLabel(relation.relation_type)} · 置信度 {relation.confidence.toFixed(2)}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "reports" && selectedProjectId && (
          <div className="grid gap-4">
            <div className={cardClass("p-5")}>
              <h2 className="flex items-center gap-2 font-semibold"><BarChart size={18} />智能生成</h2>
              <p className="mt-1 text-sm text-muted">基于已审核实验笔记、资料库和知识图谱生成可追溯草稿。</p>
              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_150px_150px_auto]">
                <select
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={agentDraft.task_type}
                  onChange={(event) => setAgentDraft({ ...agentDraft, task_type: event.target.value })}
                >
                  {agentTaskOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <input
                  type="date"
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={agentDraft.date_from}
                  onChange={(event) => setAgentDraft({ ...agentDraft, date_from: event.target.value })}
                />
                <input
                  type="date"
                  className="rounded-md border border-border px-3 py-2 text-sm"
                  value={agentDraft.date_to}
                  onChange={(event) => setAgentDraft({ ...agentDraft, date_to: event.target.value })}
                />
                <button disabled={agentBusy} onClick={() => void handleGenerateAgent()} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60">
                  {agentBusy ? "生成中..." : "生成"}
                </button>
              </div>
              {agentRun && (
                <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span>任务：{agentTaskOptions.find((option) => option.value === agentRun.task_type)?.label || agentRun.task_type}</span>
                    <span>耗时：{agentRun.response_ms} ms</span>
                    <span>来源笔记：{agentRun.source_note_ids_json.length} 条</span>
                    <span>来源资料：{agentRun.source_file_ids_json.length} 份</span>
                    <span>图谱依据：{agentRun.source_graph_relation_ids_json.length} 条</span>
                  </div>
                  <h3 className="mt-3 font-semibold">{agentRun.title}</h3>
                  <pre className="mt-2 whitespace-pre-wrap text-muted">{agentRun.body}</pre>
                  {agentRun.message && <p className="mt-3 text-xs text-muted">{agentRun.message}</p>}
                </div>
              )}
            </div>

            <div className={cardClass("p-5")}>
              <h3 className="font-semibold">生成历史</h3>
              <div className="mt-4 max-h-80 space-y-2 overflow-auto">
                {agentRuns.length === 0 && <p className="text-sm text-muted">暂无智能体生成记录。</p>}
                {agentRuns.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setAgentRun(run)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm ${agentRun?.id === run.id ? "border-brand bg-[#eef8f6]" : "border-border hover:bg-surface"}`}
                  >
                    <span className="block font-medium">{run.title}</span>
                    <span className="mt-1 block text-xs text-muted">
                      {new Date(run.created_at).toLocaleString()} · {agentTaskOptions.find((option) => option.value === run.task_type)?.label || run.task_type} ·
                      笔记 {run.source_note_ids_json.length} · 图谱 {run.source_graph_relation_ids_json.length}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
          )}

          {workspaceView === "project" && activeProjectTab === "logs" && (
            <div className={cardClass("p-5")}>
              <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} />项目日志</h2>
              {!canAdmin && <p className="mt-4 text-sm text-muted">当前账号没有审计日志查看权限。</p>}
              {canAdmin && (
                <div className="mt-4 max-h-96 overflow-auto rounded-md border border-border">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead className="sticky top-0 bg-surface text-xs text-muted">
                      <tr>
                        <th className="px-3 py-2 font-medium">时间</th>
                        <th className="px-3 py-2 font-medium">用户</th>
                        <th className="px-3 py-2 font-medium">动作</th>
                        <th className="px-3 py-2 font-medium">对象</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projectAuditLogs.length === 0 && (
                        <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">当前项目暂无审计记录</td></tr>
                      )}
                      {projectAuditLogs.map((log) => (
                        <tr key={log.id} className="border-t border-border">
                          <td className="px-3 py-2">{new Date(log.created_at).toLocaleString("zh-CN")}</td>
                          <td className="px-3 py-2">{log.actor_user_id ? usersById.get(log.actor_user_id)?.display_name || log.actor_user_id : "-"}</td>
                          <td className="px-3 py-2">{log.action}</td>
                          <td className="px-3 py-2">{log.target_type || "-"} {log.target_id || ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
