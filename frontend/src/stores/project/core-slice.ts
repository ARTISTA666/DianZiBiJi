import { StateCreator } from "zustand";
import {
  getProject,
  getProjectsPaginated,
  getProjectMembers,
  getTemplates,
  createProject,
  updateProject,
  addProjectMember,
  updateProjectMember,
  removeProjectMember,
  addProjectReviewer,
  removeProjectReviewer,
  ApiRequestError,
  type Project,
  type ProjectMember,
  type Template,
} from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type {
  MemberAddPayload,
  MemberUpdatePayload,
  ProjectCreatePayload,
  ProjectUpdatePayload,
} from "./types";
import {
  epochs,
  bumpAllEpochs,
  isCurrentProjectRequest,
  isCurrentSessionRequest,
} from "./request-epoch";
import type { ProjectStoreState } from "./index";

export interface CoreSlice {
  projects: Project[];
  projectTotal: number;
  projectSkip: number;
  projectLimit: number;
  templates: Template[];
  selectedProjectId: number | null;
  selectedProject: Project | null;
  members: ProjectMember[];
  busy: boolean;
  projectLoadError: string | null;

  loadProjects: (token: string, skip?: number, limit?: number) => Promise<void>;
  loadNextProjectsPage: (token: string) => Promise<void>;
  loadPrevProjectsPage: (token: string) => Promise<void>;
  loadTemplates: (token: string) => Promise<void>;
  selectProject: (id: number | null) => void;
  loadProject: (token: string, projectId: number) => Promise<void>;
  refreshProjectList: (token: string) => Promise<void>;

  createProject: (token: string, data: ProjectCreatePayload) => Promise<Project>;
  updateProject: (token: string, projectId: number, data: ProjectUpdatePayload) => Promise<void>;
  addMember: (token: string, projectId: number, data: MemberAddPayload) => Promise<void>;
  updateMember: (token: string, projectId: number, memberId: number, data: MemberUpdatePayload) => Promise<void>;
  removeMember: (token: string, projectId: number, memberId: number) => Promise<void>;
  addReviewer: (token: string, projectId: number, userId: number) => Promise<void>;
  setBusy: (v: boolean) => void;
}

export const createCoreSlice: StateCreator<ProjectStoreState, [], [], CoreSlice> = (set, get) => ({
  projects: [],
  projectTotal: 0,
  projectSkip: 0,
  projectLimit: 20,
  templates: [],
  selectedProjectId: null,
  selectedProject: null,
  members: [],
  busy: false,
  projectLoadError: null,

  loadProjects: async (token, skip = 0, limit = 20) => {
    const sessionEpoch = epochs.session;
    const data = await getProjectsPaginated(token, skip, limit);
    if (isCurrentSessionRequest(sessionEpoch)) {
      set({ projects: data.items, projectTotal: data.total, projectSkip: data.skip, projectLimit: data.limit });
    }
  },

  loadNextProjectsPage: async (token) => {
    const { projectSkip, projectLimit, projectTotal } = get();
    const next = projectSkip + projectLimit;
    if (next < projectTotal) {
      get().loadProjects(token, next, projectLimit);
    }
  },

  loadPrevProjectsPage: async (token) => {
    const { projectSkip, projectLimit } = get();
    const prev = Math.max(0, projectSkip - projectLimit);
    if (prev !== projectSkip) {
      get().loadProjects(token, prev, projectLimit);
    }
  },

  loadTemplates: async (token) => {
    const sessionEpoch = epochs.session;
    const templates = await getTemplates(token);
    if (isCurrentSessionRequest(sessionEpoch)) set({ templates });
  },

  selectProject: (id) => {
    if (get().selectedProjectId === id) return;
    bumpAllEpochs();
    set({
      selectedProjectId: id,
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

  loadProject: async (token, projectId) => {
    const sessionEpoch = epochs.session;
    const requestEpoch = ++epochs.projectDetail;
    set({ projectLoadError: null });
    try {
      const project = await getProject(token, projectId);
      if (
        isCurrentSessionRequest(sessionEpoch)
        && requestEpoch === epochs.projectDetail
        && get().selectedProjectId === projectId
      ) {
        set({ selectedProject: project });
      }
    } catch (error) {
      if (
        isCurrentSessionRequest(sessionEpoch)
        && requestEpoch === epochs.projectDetail
        && get().selectedProjectId === projectId
      ) {
        const message = getErrorMessage(error, "项目加载失败");
        const status = error instanceof ApiRequestError ? error.status : null;
        set({
          selectedProject: null,
          projectLoadError: status === 403 || message.includes("403") || message.includes("Forbidden")
            ? "你没有权限访问此项目。"
            : status === 401 || message.includes("401") || message.includes("Unauthorized")
              ? "登录状态已失效，请重新登录。"
              : message,
        });
      }
    }
  },

  refreshProjectList: async (token) => {
    get().loadProjects(token, get().projectSkip, get().projectLimit);
  },

  createProject: async (token, data) => {
    const sessionEpoch = epochs.session;
    const project = await createProject(token, data);
    if (isCurrentSessionRequest(sessionEpoch)) {
      set((s) => ({ projects: [project, ...s.projects] }));
    }
    return project;
  },

  updateProject: async (token, projectId, data) => {
    const sessionEpoch = epochs.session;
    const project = await updateProject(token, projectId, data);
    if (isCurrentSessionRequest(sessionEpoch)) {
      set((s) => ({
        projects: s.projects.map((p) => (p.id === projectId ? project : p)),
        selectedProject: s.selectedProjectId === projectId ? project : s.selectedProject,
      }));
    }
  },

  addMember: async (token, projectId, data) => {
    const requestEpoch = epochs.projectData;
    await addProjectMember(token, projectId, data);
    const members = await getProjectMembers(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ members });
  },

  updateMember: async (token, projectId, memberId, data) => {
    const requestEpoch = epochs.projectData;
    const { members } = get();
    const member = members.find((m) => m.id === memberId);
    if (!member) return;
    await updateProjectMember(token, projectId, member.user_id, data);
    const refreshed = await getProjectMembers(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ members: refreshed });
  },

  removeMember: async (token, projectId, memberId) => {
    const requestEpoch = epochs.projectData;
    const { members } = get();
    const member = members.find((m) => m.id === memberId);
    if (!member) return;
    if (member.is_independent_reviewer) {
      await removeProjectReviewer(token, projectId, member.user_id);
    } else {
      await removeProjectMember(token, projectId, member.user_id);
    }
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) {
      set((s) => ({ members: s.members.filter((m) => m.id !== memberId) }));
    }
  },

  addReviewer: async (token, projectId, userId) => {
    const requestEpoch = epochs.projectData;
    await addProjectReviewer(token, projectId, { user_id: userId });
    const members = await getProjectMembers(token, projectId);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) set({ members });
  },

  setBusy: (v: boolean) => set({ busy: v }),
});
