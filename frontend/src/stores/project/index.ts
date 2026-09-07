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
} from "@/lib/api";
import { createCoreSlice, type CoreSlice } from "./core-slice";
import { createNoteSlice, type NoteSlice } from "./note-slice";
import { createFileSlice, type FileSlice } from "./file-slice";
import { createAiSlice, type AiSlice } from "./ai-slice";
import { epochs, isCurrentSessionRequest, resetSessionEpoch } from "./request-epoch";

export * from "./types";

/** Cache TTL in milliseconds – skip refetch within this window. */
const CACHE_TTL_MS = 30_000;

function mergeProjectDataErrors(
  current: string[],
  labels: readonly string[],
  results: readonly { status: "fulfilled" | "rejected" }[],
): string[] {
  const known = new Set(labels);
  return [
    ...current.filter((error) => !known.has(error)),
    ...labels.filter((_, index) => results[index]?.status === "rejected"),
  ];
}

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

/**
 * 单资源 tab 加载器工厂：四个结构一致的加载器共享同一实现。
 * 行为与原逐个实现完全一致（项目守卫 → 30s 缓存 → 会话纪元校验 →
 * 按成功与否写入字段/错误标签/缓存时间戳）。
 */
const singleTabLoader = <Data>(config: {
  cacheKey: keyof TabCacheState;
  label: string;
  fetcher: (token: string, projectId: number) => Promise<Data>;
  apply: (data: Data) => Partial<ProjectStoreState>;
}) => {
  return async (token: string, projectId: number) => {
    const state = useProjectStore.getState();
    if (state.selectedProjectId !== projectId) return;
    const sessionEpoch = epochs.session;
    if (Date.now() - state[config.cacheKey] < CACHE_TTL_MS) return;
    const result = await Promise.allSettled([config.fetcher(token, projectId)]);
    const current = useProjectStore.getState();
    if (!isCurrentSessionRequest(sessionEpoch) || current.selectedProjectId !== projectId) return;
    useProjectStore.setState({
      ...(result[0].status === "fulfilled" ? config.apply(result[0].value) : {}),
      projectDataErrors: mergeProjectDataErrors(current.projectDataErrors, [config.label], result),
      [config.cacheKey]: result[0].status === "fulfilled" ? Date.now() : 0,
    } as Partial<ProjectStoreState>);
  };
};

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
    const sessionEpoch = epochs.session;
    const requestEpoch = ++epochs.projectData;
    set({ busy: true, projectDataErrors: [] });
    try {
      const results = await Promise.allSettled([
        getProjectMembers(token, projectId),
        getProjectNotes(token, projectId),
        getProjectFiles(token, projectId),
        getPendingApprovals(token),
        getTemplates(token),
      ]);
      if (
        !isCurrentSessionRequest(sessionEpoch)
        ||
        requestEpoch !== epochs.projectData
        || get().selectedProjectId !== projectId
      ) return;

      const unwrap = <T>(r: PromiseSettledResult<T>, fallback: T): T =>
        r.status === "fulfilled" ? r.value : fallback;
      const labels = ["项目成员", "实验笔记", "项目资料", "待审批笔记", "模板"];
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
        templates: unwrap(results[4], []),
        projectDataErrors,
      });
    } finally {
      if (
        isCurrentSessionRequest(sessionEpoch)
        &&
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
    const sessionEpoch = epochs.session;
    if (Date.now() - get().aiTabLastFetchedAt < CACHE_TTL_MS) return;
    const results = await Promise.allSettled([
      getProjectRagStatus(token, projectId),
      getProjectQueryLogs(token, projectId),
      getProjectQueryAnalytics(token, projectId),
      getRagExperiments(token, projectId),
    ]);
    if (!isCurrentSessionRequest(sessionEpoch) || get().selectedProjectId !== projectId) return;
    const labels = ["AI/RAG状态", "AI/查询日志", "AI/查询统计", "AI/实验记录"] as const;
    set({
      ...(results[0].status === "fulfilled" ? { ragStatus: results[0].value } : {}),
      ...(results[1].status === "fulfilled" ? { queryLogs: results[1].value } : {}),
      ...(results[2].status === "fulfilled" ? { queryAnalytics: results[2].value } : {}),
      ...(results[3].status === "fulfilled" ? { experimentRuns: results[3].value } : {}),
      projectDataErrors: mergeProjectDataErrors(get().projectDataErrors, labels, results),
      aiTabLastFetchedAt: results.every((result) => result.status === "fulfilled") ? Date.now() : 0,
    });
  },

  loadKGTabData: singleTabLoader({
    cacheKey: "kgTabLastFetchedAt",
    label: "知识图谱",
    fetcher: getProjectKnowledgeGraph,
    apply: (graph) => ({ kgGraph: graph }),
  }),

  loadReportsTabData: singleTabLoader({
    cacheKey: "reportsTabLastFetchedAt",
    label: "报告记录",
    fetcher: getAgentRuns,
    apply: (runs) => ({ agentRuns: runs }),
  }),

  loadDataTabData: singleTabLoader({
    cacheKey: "dataTabLastFetchedAt",
    label: "项目资料",
    fetcher: getProjectFiles,
    apply: (result) => ({ files: result.items }),
  }),

  loadBlindReviewTabData: singleTabLoader({
    cacheKey: "blindReviewTabLastFetchedAt",
    label: "盲评",
    fetcher: getBlindReviewBatches,
    apply: (batches) => ({ blindReviewBatches: batches }),
  }),

  loadSettingsTabData: async (token, projectId) => {
    if (get().selectedProjectId !== projectId) return;
    const sessionEpoch = epochs.session;
    if (Date.now() - get().settingsTabLastFetchedAt < CACHE_TTL_MS) return;
    const results = await Promise.allSettled([
      getTemplates(token),
      getMaturityStatus(token),
    ]);
    if (!isCurrentSessionRequest(sessionEpoch) || get().selectedProjectId !== projectId) return;
    set({
      ...(results[0].status === "fulfilled" ? { templates: results[0].value } : {}),
      ...(results[1].status === "fulfilled" ? { maturityStatus: results[1].value } : {}),
      projectDataErrors: mergeProjectDataErrors(
        get().projectDataErrors,
        ["模板", "成熟度"],
        results,
      ),
      settingsTabLastFetchedAt: results.every((result) => result.status === "fulfilled") ? Date.now() : 0,
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
    const sessionEpoch = epochs.session;
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
    if (!isCurrentSessionRequest(sessionEpoch) || get().selectedProjectId !== projectId) return;

    const now = Date.now();
    const labels = [
      "模板", "AI/RAG状态", "知识图谱", "AI/查询日志", "AI/查询统计",
      "AI/实验记录", "报告记录", "盲评", "成熟度",
    ] as const;

    set({
      ...(results[0].status === "fulfilled" ? { templates: results[0].value } : {}),
      ...(results[1].status === "fulfilled" ? { ragStatus: results[1].value } : {}),
      ...(results[2].status === "fulfilled" ? { kgGraph: results[2].value } : {}),
      ...(results[3].status === "fulfilled" ? { queryLogs: results[3].value } : {}),
      ...(results[4].status === "fulfilled" ? { queryAnalytics: results[4].value } : {}),
      ...(results[5].status === "fulfilled" ? { experimentRuns: results[5].value } : {}),
      ...(results[6].status === "fulfilled" ? { agentRuns: results[6].value } : {}),
      ...(results[7].status === "fulfilled" ? { blindReviewBatches: results[7].value } : {}),
      ...(results[8].status === "fulfilled" ? { maturityStatus: results[8].value } : {}),
      projectDataErrors: mergeProjectDataErrors(get().projectDataErrors, labels, results),
      aiTabLastFetchedAt: [1, 3, 4, 5].every((index) => results[index].status === "fulfilled") ? now : 0,
      kgTabLastFetchedAt: results[2].status === "fulfilled" ? now : 0,
      reportsTabLastFetchedAt: results[6].status === "fulfilled" ? now : 0,
      blindReviewTabLastFetchedAt: results[7].status === "fulfilled" ? now : 0,
      settingsTabLastFetchedAt: [0, 8].every((index) => results[index].status === "fulfilled") ? now : 0,
    });
  },

  loadProjectData: async (token, projectId) => {
    const sessionEpoch = epochs.session;
    await get().loadBaseProjectData(token, projectId);
    if (isCurrentSessionRequest(sessionEpoch) && get().selectedProjectId === projectId) {
      await get().loadTabProjectData(token, projectId);
    }
  },
}));
