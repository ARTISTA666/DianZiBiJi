// Compatibility layer: the project store now lives in ./project as
// domain-focused slices (core / notes / files / AI). Existing imports of
// `useProjectStore` and the payload types keep working unchanged.

export { useProjectStore, type ProjectStoreState } from "./project";
export type {
  NoteCreatePayload,
  NoteUpdatePayload,
  ProjectCreatePayload,
  ProjectUpdatePayload,
  MemberAddPayload,
  MemberUpdatePayload,
  ExperimentPayload,
  AgentPayload,
  BlindReviewEvalPayload,
  QueryLogEvalPayload,
} from "./project";
