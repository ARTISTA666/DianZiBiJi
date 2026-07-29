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

// Cross-slice actions that touch state owned by several slices at once.
interface CrossSliceActions {
  projectDataErrors: string[];
  /** Load base data shared across all tabs (members, notes, files, pending approvals). */
  loadBaseProjectData: (token: string, projectId: number) => Promise<void>;
  /** Load tab-specific data (templates, RAG, KG, experiments, etc.). */
  loadTabProjectData: (token: string, projectId: number) => Promise<void>;
  /** Load all project data (base + tab). Used for full refresh. */
  loadProjectData: (token: string, projectId: number) => Promise<void>;
  resetProjectState: () => void;
}

export type ProjectStoreState = CoreSlice & NoteSlice & FileSlice & AiSlice & CrossSliceActions;

export const useProjectStore = create<ProjectStoreState>()((set, get, store) => ({
  ...createCoreSlice(set, get, store),
  ...createNoteSlice(set, get, store),
  ...createFileSlice(set, get, store),
  ...createAiSlice(set, get, store),
  projectDataErrors: [],

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

      set({
        members: unwrap(results[0], [] as ProjectMember[]),
        notes: unwrap(results[1], [] as Note[]),
        files: unwrap(results[2], [] as StoredFile[]),
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
    });
  },

  loadProjectData: async (token, projectId) => {
    await get().loadBaseProjectData(token, projectId);
    if (get().selectedProjectId === projectId) {
      await get().loadTabProjectData(token, projectId);
    }
  },
}));
