// Shared payload types for the project store slices.

export type NoteCreatePayload = {
  project_id: number;
  title: string;
  experiment_type: string;
  experiment_date?: string;
  template_id?: number | null;
  fixed_fields_json?: Record<string, string>;
  content_json?: Record<string, unknown>;
};

export type NoteUpdatePayload = {
  title?: string;
  experiment_type?: string;
  experiment_date?: string;
  fixed_fields_json?: Record<string, string>;
  content_json?: Record<string, unknown>;
  change_summary?: string;
};

export type ProjectCreatePayload = { name: string; description?: string | null; is_sensitive?: boolean; approval_enabled?: boolean; owner_user_id?: number | null; status?: string };
export type ProjectUpdatePayload = { name?: string; description?: string | null; is_sensitive?: boolean; approval_enabled?: boolean; owner_user_id?: number | null; status?: string };

export type MemberAddPayload = { user_id: number; project_role: string; can_read: boolean; can_write: boolean; can_review: boolean; can_evaluate: boolean; can_manage: boolean };
export type MemberUpdatePayload = { project_role?: string; can_read?: boolean; can_write?: boolean; can_review?: boolean; can_evaluate?: boolean; can_manage?: boolean };

export type ExperimentPayload = { name: string; questions: string[]; modes?: string[]; repetitions?: number; randomize_order?: boolean; random_seed?: number | null };
export type AgentPayload = { task_type: string; date_from?: string | null; date_to?: string | null };

export type BlindReviewEvalPayload = { score: number; is_accurate: boolean; is_traceable: boolean; comment?: string | null };
export type QueryLogEvalPayload = { score: number; is_accurate: boolean; is_traceable: boolean; comment?: string | null };
