import { create } from "zustand";
import {
  login as apiLogin,
  logoutSession as apiLogout,
  getMe,
  changeOwnPassword as apiChangeOwnPassword,
  ApiRequestError,
  type CurrentUser,
} from "@/lib/api";
import { useProjectStore } from "./project";
import { getErrorMessage } from "@/lib/utils";

// Authentication relies on the HttpOnly cookie managed by the backend; the
// token field is only an in-memory "session active" marker kept for the
// many `if (!token)` guards across pages. It is never sent to the API.
const SESSION_ACTIVE = "cookie-session";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  hydrated: boolean;
  error: string | null;
  busy: boolean;

  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  setError: (error: string | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  hydrated: false,
  error: null,
  busy: false,

  login: async (username, password) => {
    useProjectStore.getState().resetProjectState();
    set({ token: null, user: null, hydrated: true, busy: true, error: null });
    try {
      await apiLogin(username, password);
      set({ token: SESSION_ACTIVE, error: null });
      const user = await getMe(SESSION_ACTIVE);
      set({ user, hydrated: true, busy: false });
    } catch (e) {
      const msg = getErrorMessage(e, "登录失败");
      set({ token: null, user: null, hydrated: true, error: msg, busy: false });
      throw e;
    }
  },

  logout: async () => {
    const { token } = get();
    if (!token) {
      useProjectStore.getState().resetProjectState();
      set({ token: null, user: null, hydrated: true, error: null, busy: false });
      return;
    }
    set({ hydrated: true, error: null, busy: true });
    try {
      await apiLogout(token);
    } catch (error) {
      if (!(error instanceof ApiRequestError && error.status === 401)) {
        const message = getErrorMessage(error, "退出登录失败");
        set({ hydrated: true, error: message, busy: false });
        throw error;
      }
    }
    useProjectStore.getState().resetProjectState();
    set({ token: null, user: null, hydrated: true, error: null, busy: false });
  },

  refreshUser: async () => {
    // Probe the cookie session; succeeds after a reload without any JS token.
    try {
      const user = await getMe(SESSION_ACTIVE);
      if (get().user?.id !== user.id) {
        useProjectStore.getState().resetProjectState();
      }
      set({ token: SESSION_ACTIVE, user, hydrated: true });
    } catch {
      useProjectStore.getState().resetProjectState();
      set({ token: null, user: null, hydrated: true });
    }
  },

  changePassword: async (currentPassword, newPassword) => {
    const { token } = get();
    if (!token) throw new Error("未登录");
    await apiChangeOwnPassword(token, currentPassword, newPassword);
  },

  setError: (error) => set({ error }),
}));
