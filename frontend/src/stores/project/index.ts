import { create } from "zustand";
import {
  getProjectMembers,
  getProjectNotes,
  getProjectFiles,
  getPendingApprovals,
  getTemplates,
  getProjectRagStatus,
  getProjectKnowledgeGraph,
  getProjectQueryLogs,
  getProjectQueryAnalytics,
  getRagExperiments,
  getAgentRuns,
  getBlindReviewBatches,
  getMaturityStatus,
  type ProjectMember,
  type Note,
  type StoredFile,
  type Template,
  type RagStatus,
  type KnowledgeGraph,
  type AIQueryLog,
  type AIQueryAnalytics,
  type AIExperimentRun,
  type AgentGenerationRun,
  type BlindReviewBatch,
  type MaturityStatus,
} from "@/lib/api";
import { createCoreSlice, type CoreSlice } from "./core-slice";
import { createNoteSlice, type NoteSlice } from "./note-slice";
import { createFileSlice, type FileSlice } from "./file-slice";
import { createAiSlice, type AiSlice } from "./ai-slice";
import { epochs, resetSessionEpoch } from "./request-epoch";

export * from "./types";

/** Cache TTL in milliseconds – skip refetch within this window. */
const CACHE_TTL_MS = 30_000;

// Per-tab cache timestamp fields.
interface TabCacheState {
  aiTabLastFetchedAt: number;
  kgTabLastFetchedAt: number;
  reportsTabLastFetchedAt: number;
  dataTabLastFetchedAt: number;
  blindReviewTabLastFetchedAt: number;
  settingsTabLastFetchedAt: number;
}

// Cross-slice actions that touch state owned by several slices at once.
interface CrossSliceActions extends TabCacheState {
  projectDataErrors: string[];
  /** Load base data shared across all tabs (members, notes, files, pending approvals). */
  loadBaseProjectData: (token: string, projectId: number) => Promise<void>;
  /** Load tab-specific data (templates, RAG, KG, experiments, etc.). */
  loadTabProjectData: (token: string, projectId: number) => Promise<void>;
  /** Load all project data (base + tab). Used for full refresh. */
  loadProjectData: (token: string, projectId: number) => Promise<void>;
  resetProjectState: () => void;

  // Per-tab loaders with 30-s cache
  loadAITabData: (token: string, projectId: number) => Promise<void>;
  loadKGTabData: (token: string, projectId: number) => Promise<void>;
  loadReportsTabData: (token: string, projectId: number) => Promise<void>;
  loadDataTabData: (token: string, projectId: number) => Promise<void>;
  loadBlindReviewTabData: (token: string, projectId: number) => Promise<void>;
  loadSettingsTabData: (token: string, projectId: number) => Promise<void>;
  /** Invalidate all tab caches so the next load always hits the network. */
  invalidateCache: () => void;
}

export type ProjectStoreState = CoreSlice & NoteSlice & FileSlice & AiSlice & CrossSliceActions;

export const useProjectStore = create<ProjectStoreState>()((set, get, store) => ({
  ...createCoreSlice(set, get, store),
  ...createNoteSlice(set, get, store),
  ...createFileSlice(set, get, store),
  ...createAiSlice(set, get, store),
  projectDataErrors: [],

  // Cache timestamps – initial value 0 means "never fetched".
  aiTabLastFetchedAt: 0,
  kgTabLastFetchedAt: 0,
  reportsTabLastFetchedAt: 0,
  dataTabLastFetchedAt: 0,
  blindReviewTabLastFetchedAt: 0,
  settingsTabLastFetchedAt: 0,

  resetProjectState: () => {
    resetSessionEpoch();
    set({
      projects: [],
      projectTotal: 0,
      projectSkip: 0,
      projectLimit: 20,
      templates: [],
      selectedProjectId: null,
      selectedProject: null,
      members: [],
      notes: [],
      notesTotal: 0,
      pendingNotes: [],
      files: [],
      ragStatus: null,
      ragAnswer: null,
      kgGraph: null,
      queryLogs: [],
      queryAnalytics: null,
      experimentRuns: [],
      agentRuns: [],
      blindReviewBatches: [],
      maturityStatus: null,
      projectDataErrors: [],
      projectLoadError: null,
      busy: false,
      aiTabLastFetchedAt: 0,
      kgTabLastFetchedAt: 0,
      reportsTabLastFetchedAt: 0,
      dataTabLastFetchedAt: 0,
      blindReviewTabLastFetchedAt: 0,
      settingsTabLastFetchedAt: 0,
    });
  },

  loadBaseProjectData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    const requestEpoch = ++epochs.projectData;
    set({ busy: true, projectDataErrors: [] });
    try {
      const results = await Promise.allSettled([
        getProjectMembers(token, projectId),
        getProjectNotes(token, projectId),
        getProjectFiles(token, projectId),
        getPendingApprovals(token),
      ]);
      if (
        requestEpoch !== epochs.projectData
        || get().selectedProjectId !== projectId
      ) return;

      const unwrap = <T>(r: PromiseSettledResult<T>, fallback: T): T =>
        r.status === "fulfilled" ? r.value : fallback;
      const labels = ["项目成员", "实验笔记", "项目资料", "待审批笔记"];
      const projectDataErrors = results.flatMap((result, index) =>
        result.status === "rejected" ? [labels[index]] : [],
      );

      const notesResult = unwrap(results[1], { items: [] as Note[], total: 0 });
      const filesResult = unwrap(results[2], { items: [] as StoredFile[], total: 0 });

      set({
        members: unwrap(results[0], [] as ProjectMember[]),
        notes: notesResult.items,
        notesTotal: notesResult.total,
        files: filesResult.items,
        pendingNotes: unwrap(results[3], [] as Note[]),
        projectDataErrors,
      });
    } finally {
      if (
        requestEpoch === epochs.projectData
        && get().selectedProjectId === projectId
      ) {
        set({ busy: false });
      }
    }
  },

  // ── Per-tab loaders with cache ────────────────────────────────────────

  loadAITabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().aiTabLastFetchedAt < CACHE_TTL_MS) return;
    const [ragStatus, queryLogs, queryAnalytics, experimentRuns] = (await Promise.allSettled([
      getProjectRagStatus(token, projectId),
      getProjectQueryLogs(token, projectId),
      getProjectQueryAnalytics(token, projectId),
      getRagExperiments(token, projectId),
    ])).map((r) => r.status === "fulfilled" ? r.value : null) as [
      RagStatus | null, AIQueryLog[] | null, AIQueryAnalytics | null, AIExperimentRun[] | null,
    ];
    if (get().selectedProjectId !== projectId) return;
    set({
      ragStatus: ragStatus ?? null,
      ragAnswer: null,
      queryLogs: queryLogs ?? [],
      queryAnalytics: queryAnalytics ?? null,
      experimentRuns: experimentRuns ?? [],
      aiTabLastFetchedAt: Date.now(),
    });
  },

  loadKGTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().kgTabLastFetchedAt < CACHE_TTL_MS) return;
    const kgGraph = await getProjectKnowledgeGraph(token, projectId).catch(() => null);
    if (get().selectedProjectId !== projectId) return;
    set({ kgGraph: kgGraph ?? null, kgTabLastFetchedAt: Date.now() });
  },

  loadReportsTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().reportsTabLastFetchedAt < CACHE_TTL_MS) return;
    const agentRuns = await getAgentRuns(token, projectId).catch(() => []);
    if (get().selectedProjectId !== projectId) return;
    set({ agentRuns: agentRuns ?? [], reportsTabLastFetchedAt: Date.now() });
  },

  loadDataTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().dataTabLastFetchedAt < CACHE_TTL_MS) return;
    const filesResult = await getProjectFiles(token, projectId).catch(() => ({ items: [] as StoredFile[], total: 0 }));
    if (get().selectedProjectId !== projectId) return;
    set({ files: filesResult.items, dataTabLastFetchedAt: Date.now() });
  },

  loadBlindReviewTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().blindReviewTabLastFetchedAt < CACHE_TTL_MS) return;
    const blindReviewBatches = await getBlindReviewBatches(token, projectId).catch(() => []);
    if (get().selectedProjectId !== projectId) return;
    set({ blindReviewBatches: blindReviewBatches ?? [], blindReviewTabLastFetchedAt: Date.now() });
  },

  loadSettingsTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    if (Date.now() - get().settingsTabLastFetchedAt < CACHE_TTL_MS) return;
    const templates = await getTemplates(token).catch(() => []);
    const maturityStatus = await getMaturityStatus(token).catch(() => null);
    if (get().selectedProjectId !== projectId) return;
    set({
      templates: templates ?? [],
      maturityStatus: maturityStatus ?? null,
      settingsTabLastFetchedAt: Date.now(),
    });
  },

  invalidateCache: () => {
    set({
      aiTabLastFetchedAt: 0,
      kgTabLastFetchedAt: 0,
      reportsTabLastFetchedAt: 0,
      dataTabLastFetchedAt: 0,
      blindReviewTabLastFetchedAt: 0,
      settingsTabLastFetchedAt: 0,
    });
  },

  loadTabProjectData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    const results = await Promise.allSettled([
      getTemplates(token),
      getProjectRagStatus(token, projectId),
      getProjectKnowledgeGraph(token, projectId),
      getProjectQueryLogs(token, projectId),
      getProjectQueryAnalytics(token, projectId),
      getRagExperiments(token, projectId),
      getAgentRuns(token, projectId),
      getBlindReviewBatches(token, projectId),
      getMaturityStatus(token),
    ]);
    if (get().selectedProjectId !== projectId) return;

    const unwrap = <T>(r: PromiseSettledResult<T>, fallback: T): T =>
      r.status === "fulfilled" ? r.value : fallback;
    const now = Date.now();

    set({
      templates: unwrap(results[0], [] as Template[]),
      ragStatus: unwrap(results[1], null as RagStatus | null),
      ragAnswer: null,
      kgGraph: unwrap(results[2], null as KnowledgeGraph | null),
      queryLogs: unwrap(results[3], [] as AIQueryLog[]),
      queryAnalytics: unwrap(results[4], null as AIQueryAnalytics | null),
      experimentRuns: unwrap(results[5], [] as AIExperimentRun[]),
      agentRuns: unwrap(results[6], [] as AgentGenerationRun[]),
      blindReviewBatches: unwrap(results[7], [] as BlindReviewBatch[]),
      maturityStatus: unwrap(results[8], null as MaturityStatus | null),
      aiTabLastFetchedAt: now,
      kgTabLastFetchedAt: now,
      reportsTabLastFetchedAt: now,
      blindReviewTabLastFetchedAt: now,
      settingsTabLastFetchedAt: now,
    });
  },

  loadProjectData: async (token, projectId) => {
    await get().loadBaseProjectData(token, projectId);
    if (get().selectedProjectId === projectId) {
      await get().loadTabProjectData(token, projectId);
    }
  },
}));
