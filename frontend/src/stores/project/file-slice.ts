import { StateCreator } from "zustand";
import {
  getProjectFiles,
  uploadFile,
  updateFile,
  reviewFile,
  archiveFile,
  syncFileToRag,
  type StoredFile,
} from "@/lib/api";
import { epochs, isCurrentProjectRequest } from "./request-epoch";
import type { ProjectStoreState } from "./index";

export interface FileSlice {
  files: StoredFile[];

  uploadFile: (token: string, projectId: number, file: File, category?: string) => Promise<StoredFile>;
  updateFile: (token: string, fileId: number, filename: string) => Promise<void>;
  reviewFile: (token: string, fileId: number, action: "approve" | "reject", comment: string) => Promise<void>;
  archiveFile: (token: string, fileId: number) => Promise<void>;
  syncFileToRag: (token: string, fileId: number) => Promise<void>;
}

export const createFileSlice: StateCreator<ProjectStoreState, [], [], FileSlice> = (set, get) => ({
  files: [],

  uploadFile: async (token, projectId, file, category) => {
    const requestEpoch = epochs.projectData;
    const f = await uploadFile(token, projectId, file, null, category);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) {
      set((s) => ({ files: [f, ...s.files] }));
    }
    return f;
  },

  updateFile: async (token, fileId, filename) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await updateFile(token, fileId, { original_filename: filename });
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const result = await getProjectFiles(token, selectedProjectId);
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items });
    }
  },

  reviewFile: async (token, fileId, action, comment) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await reviewFile(token, fileId, action, comment);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const result = await getProjectFiles(token, selectedProjectId);
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items });
    }
  },

  archiveFile: async (token, fileId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await archiveFile(token, fileId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ files: s.files.filter((f) => f.id !== fileId) }));
    }
  },

  syncFileToRag: async (token, fileId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    const ragStatus = await syncFileToRag(token, fileId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const result = await getProjectFiles(token, selectedProjectId);
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items, ragStatus });
    }
  },
});
