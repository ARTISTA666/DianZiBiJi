import { StateCreator } from "zustand";
import {
  getAllProjectFiles,
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
  filesTotal: number;
  filesComplete: boolean;

  uploadFile: (token: string, projectId: number, file: File, category?: string) => Promise<StoredFile>;
  updateFile: (token: string, fileId: number, filename: string) => Promise<void>;
  reviewFile: (token: string, fileId: number, action: "approve" | "reject", comment: string) => Promise<StoredFile>;
  archiveFile: (token: string, fileId: number) => Promise<void>;
  syncFileToRag: (token: string, fileId: number) => Promise<void>;
}

export const createFileSlice: StateCreator<ProjectStoreState, [], [], FileSlice> = (set, get) => ({
  files: [],
  filesTotal: 0,
  filesComplete: false,

  uploadFile: async (token, projectId, file, category) => {
    const requestEpoch = epochs.projectData;
    const f = await uploadFile(token, projectId, file, null, category);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) {
      set((s) => ({ files: [f, ...s.files.filter((file) => file.id !== f.id)], filesTotal: s.filesTotal + 1 }));
    }
    return f;
  },

  updateFile: async (token, fileId, filename) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await updateFile(token, fileId, { original_filename: filename });
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const result = await getAllProjectFiles(token, selectedProjectId, () => isCurrentProjectRequest(get, selectedProjectId, requestEpoch));
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items, filesTotal: result.total, filesComplete: result.items.length >= result.total });
    }
  },

  reviewFile: async (token, fileId, action, comment) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    const reviewed = await reviewFile(token, fileId, action, comment);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ files: s.files.map((file) => file.id === reviewed.id ? reviewed : file) }));
      try {
        const result = await getAllProjectFiles(token, selectedProjectId, () => isCurrentProjectRequest(get, selectedProjectId, requestEpoch));
        if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items, filesTotal: result.total, filesComplete: result.items.length >= result.total });
      } catch {
        // The review is committed even if refreshing metadata fails.
        if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set((s) => ({
          filesComplete: false, projectDataErrors: [...new Set([...s.projectDataErrors, "项目资料"])],
        }));
      }
    }
    return reviewed;
  },

  archiveFile: async (token, fileId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    const archived = await archiveFile(token, fileId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ files: s.files.map((file) => file.id === fileId ? archived : file) }));
    }
  },

  syncFileToRag: async (token, fileId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    const ragStatus = await syncFileToRag(token, fileId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const result = await getAllProjectFiles(token, selectedProjectId, () => isCurrentProjectRequest(get, selectedProjectId, requestEpoch));
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) set({ files: result.items, filesTotal: result.total, filesComplete: result.items.length >= result.total, ragStatus });
    }
  },
});
