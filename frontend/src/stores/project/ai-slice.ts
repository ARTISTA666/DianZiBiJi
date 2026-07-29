import { StateCreator } from "zustand";
import {
  getProjectRagStatus,
  getProjectKnowledgeGraph,
  getRagExperiments,
  getAgentRuns,
  initProjectRag,
  queryProjectRag,
  extractNoteKnowledgeGraph,
  rebuildProjectKnowledgeGraph,
  runRagExperiment,
  resumeRagExperiment,
  generateAgentOutput,
  searchDocuments,
  evaluateBlindReviewItem,
  evaluateQueryLog,
  type RagStatus,
  type RagQueryResponse,
  type KnowledgeGraph,
  type AIQueryLog,
  type AIQueryAnalytics,
  type AIExperimentRun,
  type AgentGenerationRun,
  type BlindReviewBatch,
  type MaturityStatus,
  type SearchResult,
} from "@/lib/api";
import type {
  AgentPayload,
  BlindReviewEvalPayload,
  ExperimentPayload,
  QueryLogEvalPayload,
} from "./types";
import { epochs, isCurrentProjectRequest } from "./request-epoch";
import type { ProjectStoreState } from "./index";

export interface AiSlice {
  ragStatus: RagStatus | null;
  ragAnswer: RagQueryResponse | null;
  kgGraph: KnowledgeGraph | null;
  queryLogs: AIQueryLog[];
  queryAnalytics: AIQueryAnalytics | null;
  experimentRuns: AIExperimentRun[];
  agentRuns: AgentGenerationRun[];
  blindReviewBatches: BlindReviewBatch[];
  maturityStatus: MaturityStatus | null;

  initRag: (token: string, projectId: number) => Promise<void>;
  queryRag: (token: string, projectId: number, question: string, mode: string) => Promise<RagQueryResponse>;
  extractNoteKg: (token: string, noteId: number) => Promise<void>;
  rebuildKg: (token: string, projectId: number) => Promise<void>;
  runExperiment: (token: string, projectId: number, data: ExperimentPayload) => Promise<void>;
  resumeExperiment: (token: string, runId: number) => Promise<void>;
  refreshExperimentRuns: (token: string, projectId: number) => Promise<AIExperimentRun[] | null>;
  generateAgent: (token: string, projectId: number, data: AgentPayload) => Promise<AgentGenerationRun>;
  evaluateBlindReview: (token: string, projectId: number, itemId: string, data: BlindReviewEvalPayload) => Promise<void>;
  evaluateQueryLog: (token: string, logId: number, data: QueryLogEvalPayload) => Promise<void>;
  searchDocuments: (token: string, query: string, projectId?: number) => Promise<SearchResult[]>;
}

export const createAiSlice: StateCreator<ProjectStoreState, [], [], AiSlice> = (set, get) => ({
  ragStatus: null,
  ragAnswer: null,
  kgGraph: null,
  queryLogs: [],
  queryAnalytics: null,
  experimentRuns: [],
  agentRuns: [],
  blindReviewBatches: [],
  maturityStatus: null,

  initRag: async (token, projectId) => {
    const requestEpoch = epochs.projectData;
    await initProjectRag(token, projectId);
    const ragStatus = await getProjectRagStatus(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ ragStatus });
  },

  queryRag: async (token, projectId, question, mode) => {
    const requestEpoch = epochs.projectData;
    const queryEpoch = ++epochs.ragQuery;
    const answer = await queryProjectRag(token, projectId, question, mode);
    if (
      queryEpoch === epochs.ragQuery
      && isCurrentProjectRequest(get, projectId, requestEpoch)
    ) {
      set({ ragAnswer: answer });
    }
    return answer;
  },

  extractNoteKg: async (token, noteId) => {
    await extractNoteKnowledgeGraph(token, noteId);
  },

  rebuildKg: async (token, projectId) => {
    const requestEpoch = epochs.projectData;
    await rebuildProjectKnowledgeGraph(token, projectId);
    const kgGraph = await getProjectKnowledgeGraph(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ kgGraph });
  },

  runExperiment: async (token, projectId, data) => {
    const requestEpoch = epochs.projectData;
    await runRagExperiment(token, projectId, data);
    const experimentRuns = await getRagExperiments(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ experimentRuns });
  },

  resumeExperiment: async (token, runId) => {
    await resumeRagExperiment(token, runId);
  },

  refreshExperimentRuns: async (token, projectId) => {
    const requestEpoch = epochs.projectData;
    const experimentRuns = await getRagExperiments(token, projectId);
    if (!isCurrentProjectRequest(get, projectId, requestEpoch)) return null;
    set({ experimentRuns });
    return experimentRuns;
  },

  generateAgent: async (token, projectId, data) => {
    const requestEpoch = epochs.projectData;
    const run = await generateAgentOutput(token, { project_id: projectId, ...data });
    const agentRuns = await getAgentRuns(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ agentRuns });
    return run;
  },

  evaluateBlindReview: async (token, projectId, itemId, data) => {
    await evaluateBlindReviewItem(token, projectId, itemId, data);
  },

  evaluateQueryLog: async (token, logId, data) => {
    await evaluateQueryLog(token, logId, data);
  },

  searchDocuments: async (token, query, projectId?) => {
    return searchDocuments(token, query, projectId);
  },
});
