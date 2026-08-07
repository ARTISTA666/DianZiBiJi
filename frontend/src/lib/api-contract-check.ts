/**
 * Compile-time API contract drift guard.
 *
 * `src/lib/api-schema.d.ts` is generated from the backend OpenAPI contract
 * via `npm run generate:api`. Each assertion below verifies that a backend
 * response schema stays assignable to the hand-written frontend type used
 * across the app. When the backend contract changes, regenerate the schema
 * and `npm run lint` (tsc) will fail here instead of at runtime.
 */

import type { components } from "./api-schema";
import type {
  AgentGenerationRun,
  AIExperimentRun,
  AIQueryAnalytics,
  AIQueryEvaluation,
  AIQueryLog,
  AIQueryModeStats,
  AuditLog,
  BlindReviewBatch,
  BlindReviewEvaluation,
  BlindReviewEvidence,
  BlindReviewItem,
  CurrentUser,
  Group,
  GroupMember,
  KnowledgeEntity,
  KnowledgeGraph,
  KnowledgeRelation,
  LoginResponse,
  Note,
  NoteApproval,
  NoteVersion,
  OcrJobResult,
  Project,
  ProjectListResponse,
  ProjectMember,
  RagDataset,
  RagQueryResponse,
  RagStatus,
  SearchResult,
  StoredFile,
  Template,
  User,
} from "./api";

type Schemas = components["schemas"];

/**
 * FastAPI serializes every field of a response model, so fields that merely
 * have defaults (and are therefore missing from the OpenAPI `required` list)
 * are still always present at runtime. Normalize that away before comparing.
 */
type DeepRequired<T> = T extends (infer U)[]
  ? DeepRequired<U>[]
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<T[K]> }
    : T;

type Response<Name extends keyof Schemas> = DeepRequired<Schemas[Name]>;

/** Fails to compile unless the backend schema is assignable to the frontend type. */
type Expect<T extends true> = T;
type IsAssignable<Backend, Frontend> = Backend extends Frontend ? true : false;

export type ApiContractChecks = [
  // auth / users
  Expect<IsAssignable<Response<"TokenResponse">, LoginResponse>>,
  Expect<IsAssignable<Response<"CurrentUserResponse">, CurrentUser>>,
  Expect<IsAssignable<Response<"UserRead">, User>>,
  // projects / groups / templates
  Expect<IsAssignable<Response<"ProjectRead">, Project>>,
  Expect<IsAssignable<Response<"ProjectListResponse">, ProjectListResponse>>,
  Expect<IsAssignable<Response<"ProjectMemberRead">, ProjectMember>>,
  Expect<IsAssignable<Response<"GroupRead">, Group>>,
  Expect<IsAssignable<Response<"GroupMemberRead">, GroupMember>>,
  Expect<IsAssignable<Response<"TemplateRead">, Template>>,
  // notes / files
  Expect<IsAssignable<Response<"NoteRead">, Note>>,
  // JSON passthrough fields are weakly typed in the backend contract
  // (dict/list of Any); the frontend intentionally narrows them, so they
  // are excluded from the drift comparison.
  Expect<
    IsAssignable<
      Omit<Response<"NoteVersionRead">, "fixed_fields_json" | "content_json">,
      Omit<NoteVersion, "fixed_fields_json" | "content_json">
    >
  >,
  Expect<IsAssignable<Response<"NoteApprovalRead">, NoteApproval>>,
  Expect<IsAssignable<Response<"FileRead">, StoredFile>>,
  Expect<IsAssignable<Response<"OcrJobResult">, OcrJobResult>>,
  // knowledge graph
  Expect<IsAssignable<Response<"KnowledgeEntityRead">, KnowledgeEntity>>,
  Expect<IsAssignable<Response<"KnowledgeRelationRead">, KnowledgeRelation>>,
  Expect<IsAssignable<Response<"KnowledgeGraphRead">, KnowledgeGraph>>,
  // RAG / AI
  Expect<IsAssignable<Response<"RagDatasetRead">, RagDataset>>,
  Expect<IsAssignable<Response<"RagStatusRead">, RagStatus>>,
  Expect<IsAssignable<Response<"RagQueryResponse">, RagQueryResponse>>,
  Expect<
    IsAssignable<
      Omit<Response<"AIQueryLogRead">, "graph_context_json" | "sources_json">,
      Omit<AIQueryLog, "graph_context_json" | "sources_json">
    >
  >,
  Expect<IsAssignable<Response<"AIQueryEvaluationRead">, AIQueryEvaluation>>,
  Expect<IsAssignable<Response<"AIQueryModeStats">, AIQueryModeStats>>,
  Expect<IsAssignable<Response<"AIQueryAnalyticsRead">, AIQueryAnalytics>>,
  Expect<IsAssignable<Response<"AIExperimentRunRead">, AIExperimentRun>>,
  Expect<IsAssignable<Response<"AgentGenerationRunRead">, AgentGenerationRun>>,
  // blind review
  Expect<IsAssignable<Response<"BlindReviewBatchRead">, BlindReviewBatch>>,
  Expect<IsAssignable<Response<"BlindReviewEvidenceRead">, BlindReviewEvidence>>,
  Expect<IsAssignable<Response<"BlindReviewEvaluationRead">, BlindReviewEvaluation>>,
  Expect<IsAssignable<Response<"BlindReviewItemRead">, BlindReviewItem>>,
  // search
  Expect<IsAssignable<Response<"SearchResult">, SearchResult>>,
  // audit
  Expect<IsAssignable<Response<"AuditLogRead">, AuditLog>>,
];
