import { create } from "zustand";
import type { ProjectTab } from "@/components/constants";

interface UIState {
  workspaceView: "project" | "admin";
  activeProjectTab: ProjectTab;
  message: string | null;

  setWorkspaceView: (v: "project" | "admin") => void;
  setActiveProjectTab: (tab: ProjectTab) => void;
  setMessage: (msg: string | null) => void;
}

export const useUIStore = create<UIState>((set) => ({
  workspaceView: "project",
  activeProjectTab: "notes",
  message: null,

  setWorkspaceView: (v) => set({ workspaceView: v, activeProjectTab: "notes" }),
  setActiveProjectTab: (tab) => set({ activeProjectTab: tab }),
  setMessage: (msg) => set({ message: msg }),
}));
