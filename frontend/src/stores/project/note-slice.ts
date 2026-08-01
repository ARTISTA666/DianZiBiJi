import { StateCreator } from "zustand";
import {
  getProjectNotes,
  getPendingApprovals,
  createNote,
  updateNote,
  submitNote,
  approveNote,
  returnNote,
  archiveNote,
  voidNote,
  type Note,
} from "@/lib/api";
import type { NoteCreatePayload, NoteUpdatePayload } from "./types";
import { epochs, isCurrentProjectRequest } from "./request-epoch";
import type { ProjectStoreState } from "./index";

export interface NoteSlice {
  notes: Note[];
  notesTotal: number;
  pendingNotes: Note[];

  loadNotesPaginated: (token: string, projectId: number, params?: { skip?: number; limit?: number; status?: string }) => Promise<void>;
  createNote: (token: string, data: NoteCreatePayload) => Promise<Note>;
  updateNote: (token: string, noteId: number, data: NoteUpdatePayload) => Promise<Note>;
  submitNote: (token: string, noteId: number) => Promise<void>;
  approveNote: (token: string, noteId: number, comment: string) => Promise<void>;
  returnNote: (token: string, noteId: number, comment: string) => Promise<void>;
  archiveNote: (token: string, noteId: number) => Promise<void>;
  voidNote: (token: string, noteId: number, comment: string) => Promise<void>;
}

export const createNoteSlice: StateCreator<ProjectStoreState, [], [], NoteSlice> = (set, get) => ({
  notes: [],
  notesTotal: 0,
  pendingNotes: [],

  loadNotesPaginated: async (token, projectId, params) => {
    const requestEpoch = epochs.projectData;
    const result = await getProjectNotes(token, projectId, params);
    if (isCurrentProjectRequest(get, projectId, requestEpoch)) {
      set({ notes: result.items, notesTotal: result.total });
    }
  },

  createNote: async (token, data) => {
    const requestEpoch = epochs.projectData;
    const note = await createNote(token, data.project_id, {
      title: data.title,
      experiment_type: data.experiment_type,
      experiment_date: data.experiment_date,
      template_id: data.template_id ?? undefined,
      fixed_fields_json: data.fixed_fields_json ?? {},
      content_json: data.content_json ?? {},
    });
    if (isCurrentProjectRequest(get, data.project_id, requestEpoch)) {
      set((s) => ({ notes: [note, ...s.notes] }));
    }
    return note;
  },

  updateNote: async (token, noteId, data) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    const note = await updateNote(token, noteId, {
      title: data.title,
      experiment_type: data.experiment_type,
      experiment_date: data.experiment_date,
      fixed_fields_json: data.fixed_fields_json,
      content_json: data.content_json,
      change_summary: data.change_summary,
    });
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ notes: s.notes.map((n) => (n.id === noteId ? note : n)) }));
    }
    return note;
  },

  submitNote: async (token, noteId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await submitNote(token, noteId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ notes: s.notes.map((n) => (n.id === noteId ? { ...n, status: "submitted" } : n)) }));
    }
  },

  approveNote: async (token, noteId, comment) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await approveNote(token, noteId, comment);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const [notesResult, pendingNotes] = await Promise.all([
        getProjectNotes(token, selectedProjectId),
        getPendingApprovals(token),
      ]);
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
        set({ notes: notesResult.items, notesTotal: notesResult.total, pendingNotes });
      }
    }
  },

  returnNote: async (token, noteId, comment) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await returnNote(token, noteId, comment);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      const [notesResult, pendingNotes] = await Promise.all([
        getProjectNotes(token, selectedProjectId),
        getPendingApprovals(token),
      ]);
      if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
        set({ notes: notesResult.items, notesTotal: notesResult.total, pendingNotes });
      }
    }
  },

  archiveNote: async (token, noteId) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await archiveNote(token, noteId);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ notes: s.notes.filter((n) => n.id !== noteId) }));
    }
  },

  voidNote: async (token, noteId, comment) => {
    const { selectedProjectId } = get();
    const requestEpoch = epochs.projectData;
    await voidNote(token, noteId, comment);
    if (isCurrentProjectRequest(get, selectedProjectId, requestEpoch)) {
      set((s) => ({ notes: s.notes.map((n) => (n.id === noteId ? { ...n, status: "voided" } : n)) }));
    }
  },
});
