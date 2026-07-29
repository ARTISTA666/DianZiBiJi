--
-- PostgreSQL database dump
--


-- Dumped from database version 16.14 (Debian 16.14-1.pgdg12+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: filecategory; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.filecategory AS ENUM (
    'NOTE_ATTACHMENT',
    'KNOWLEDGE_DOCUMENT'
);


--
-- Name: filestatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.filestatus AS ENUM (
    'UPLOADED',
    'APPROVED',
    'REJECTED',
    'ARCHIVED'
);


--
-- Name: notestatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.notestatus AS ENUM (
    'DRAFT',
    'SUBMITTED',
    'APPROVED',
    'RETURNED',
    'ARCHIVED',
    'VOIDED'
);


--
-- Name: projectrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.projectrole AS ENUM (
    'OWNER',
    'REVIEWER',
    'MEMBER',
    'VIEWER'
);


--
-- Name: projectstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.projectstatus AS ENUM (
    'ACTIVE',
    'ARCHIVED'
);


--
-- Name: userrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userrole AS ENUM (
    'SUPER_ADMIN',
    'PI',
    'GROUP_LEADER',
    'PROJECT_OWNER',
    'REVIEWER',
    'MEMBER'
);


--
-- Name: userstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userstatus AS ENUM (
    'ACTIVE',
    'DISABLED'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_generation_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_generation_runs (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    task_type character varying(60) NOT NULL,
    input_params_json json NOT NULL,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    source_note_ids_json json NOT NULL,
    source_file_ids_json json NOT NULL,
    source_graph_relation_ids_json json NOT NULL,
    provider character varying(40) NOT NULL,
    model_name character varying(120),
    prompt_version character varying(40) NOT NULL,
    usage_json json NOT NULL,
    status character varying(40) NOT NULL,
    response_ms integer NOT NULL,
    message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_generation_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_generation_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_generation_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_generation_runs_id_seq OWNED BY public.agent_generation_runs.id;


--
-- Name: ai_experiment_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_experiment_runs (
    id integer NOT NULL,
    project_id integer NOT NULL,
    created_by integer NOT NULL,
    name character varying(255) NOT NULL,
    status character varying(40) NOT NULL,
    questions_json json NOT NULL,
    modes_json json NOT NULL,
    config_snapshot_json json NOT NULL,
    summary_json json NOT NULL,
    total_cases integer NOT NULL,
    completed_cases integer NOT NULL,
    failed_cases integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    worker_id character varying(80),
    heartbeat_at timestamp with time zone,
    lease_expires_at timestamp with time zone
);


--
-- Name: ai_experiment_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_experiment_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_experiment_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_experiment_runs_id_seq OWNED BY public.ai_experiment_runs.id;


--
-- Name: ai_query_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_query_evaluations (
    id integer NOT NULL,
    query_log_id integer NOT NULL,
    evaluator_user_id integer NOT NULL,
    score integer NOT NULL,
    is_accurate boolean NOT NULL,
    is_traceable boolean NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    review_protocol character varying(40) DEFAULT 'unblinded'::character varying NOT NULL
);


--
-- Name: ai_query_evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_query_evaluations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_query_evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_query_evaluations_id_seq OWNED BY public.ai_query_evaluations.id;


--
-- Name: ai_query_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_query_logs (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    question text NOT NULL,
    answer text,
    rag_mode character varying(40) NOT NULL,
    graph_hit_count integer NOT NULL,
    source_count integer NOT NULL,
    response_ms integer NOT NULL,
    conversation_id character varying(160),
    graph_context_json json NOT NULL,
    sources_json json NOT NULL,
    provider character varying(40) NOT NULL,
    model_name character varying(120),
    prompt_version character varying(40) NOT NULL,
    retrieval_config_json json NOT NULL,
    usage_json json NOT NULL,
    fallback_reason text,
    error_message text,
    experiment_run_id integer,
    experiment_case_index integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    experiment_repetition_index integer,
    experiment_execution_order integer
);


--
-- Name: ai_query_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_query_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_query_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_query_logs_id_seq OWNED BY public.ai_query_logs.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    actor_user_id integer,
    project_id integer,
    action character varying(80) NOT NULL,
    target_type character varying(80),
    target_id integer,
    detail_json json NOT NULL,
    ip_address character varying(80),
    user_agent character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: experiment_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.experiment_notes (
    id integer NOT NULL,
    project_id integer NOT NULL,
    template_id integer,
    title character varying(200) NOT NULL,
    experiment_type character varying(120) NOT NULL,
    experiment_date date,
    owner_user_id integer NOT NULL,
    status public.notestatus NOT NULL,
    current_version_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: experiment_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.experiment_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: experiment_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.experiment_notes_id_seq OWNED BY public.experiment_notes.id;


--
-- Name: experiment_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.experiment_templates (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    experiment_type character varying(120) NOT NULL,
    schema_json json NOT NULL,
    default_content_json json NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: experiment_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.experiment_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: experiment_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.experiment_templates_id_seq OWNED BY public.experiment_templates.id;


--
-- Name: file_ocr_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_ocr_results (
    id integer NOT NULL,
    file_id integer NOT NULL,
    project_id integer NOT NULL,
    created_by integer NOT NULL,
    file_hash character varying(64) NOT NULL,
    raw_text text NOT NULL,
    corrected_text text NOT NULL,
    extraction_method character varying(80) NOT NULL,
    character_count integer NOT NULL,
    truncated boolean NOT NULL,
    review_status character varying(40) NOT NULL,
    reviewed_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    reviewed_at timestamp with time zone
);


--
-- Name: file_ocr_results_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_ocr_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: file_ocr_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_ocr_results_id_seq OWNED BY public.file_ocr_results.id;


--
-- Name: files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.files (
    id integer NOT NULL,
    project_id integer NOT NULL,
    note_id integer,
    uploaded_by integer NOT NULL,
    file_category public.filecategory NOT NULL,
    original_filename character varying(255) NOT NULL,
    storage_path character varying(500) NOT NULL,
    mime_type character varying(160),
    file_size integer NOT NULL,
    file_hash character varying(64) NOT NULL,
    status public.filestatus NOT NULL,
    knowledge_sync_status character varying(40) NOT NULL,
    knowledge_synced_at timestamp with time zone,
    knowledge_sync_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.files_id_seq OWNED BY public.files.id;


--
-- Name: group_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.group_members (
    id integer NOT NULL,
    group_id integer NOT NULL,
    user_id integer NOT NULL,
    group_role character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: group_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.group_members_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: group_members_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.group_members_id_seq OWNED BY public.group_members.id;


--
-- Name: group_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.group_projects (
    id integer NOT NULL,
    group_id integer NOT NULL,
    project_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: group_projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.group_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: group_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.group_projects_id_seq OWNED BY public.group_projects.id;


--
-- Name: groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.groups (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    description text,
    leader_user_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.groups_id_seq OWNED BY public.groups.id;


--
-- Name: kg_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kg_entities (
    id integer NOT NULL,
    project_id integer NOT NULL,
    entity_type character varying(40) NOT NULL,
    label character varying(255) NOT NULL,
    normalized_label character varying(255) NOT NULL,
    natural_key character varying(320) NOT NULL,
    source_type character varying(40),
    source_id integer,
    properties json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kg_entities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kg_entities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kg_entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kg_entities_id_seq OWNED BY public.kg_entities.id;


--
-- Name: kg_extraction_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kg_extraction_runs (
    id integer NOT NULL,
    project_id integer NOT NULL,
    note_id integer NOT NULL,
    triggered_by integer NOT NULL,
    status character varying(40) NOT NULL,
    extracted_entities integer NOT NULL,
    extracted_relations integer NOT NULL,
    message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kg_extraction_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kg_extraction_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kg_extraction_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kg_extraction_runs_id_seq OWNED BY public.kg_extraction_runs.id;


--
-- Name: kg_relations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kg_relations (
    id integer NOT NULL,
    project_id integer NOT NULL,
    source_entity_id integer NOT NULL,
    target_entity_id integer NOT NULL,
    relation_type character varying(60) NOT NULL,
    source_type character varying(40),
    source_id integer,
    confidence double precision NOT NULL,
    properties json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kg_relations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kg_relations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kg_relations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kg_relations_id_seq OWNED BY public.kg_relations.id;


--
-- Name: note_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_approvals (
    id integer NOT NULL,
    note_id integer NOT NULL,
    version_id integer NOT NULL,
    reviewer_user_id integer NOT NULL,
    action character varying(40) NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: note_approvals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_approvals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_approvals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_approvals_id_seq OWNED BY public.note_approvals.id;


--
-- Name: note_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_versions (
    id integer NOT NULL,
    note_id integer NOT NULL,
    version_number integer NOT NULL,
    fixed_fields_json json NOT NULL,
    content_json json NOT NULL,
    created_by integer NOT NULL,
    change_summary text,
    is_locked boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: note_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_versions_id_seq OWNED BY public.note_versions.id;


--
-- Name: project_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_members (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    project_role public.projectrole NOT NULL,
    can_read boolean NOT NULL,
    can_write boolean NOT NULL,
    can_review boolean NOT NULL,
    can_manage boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    can_evaluate boolean DEFAULT false NOT NULL
);


--
-- Name: project_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.project_members_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: project_members_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.project_members_id_seq OWNED BY public.project_members.id;


--
-- Name: project_rag_datasets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_rag_datasets (
    id integer NOT NULL,
    project_id integer NOT NULL,
    dify_dataset_id character varying(120) NOT NULL,
    dify_dataset_name character varying(255) NOT NULL,
    status character varying(40) NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    provider character varying(40) DEFAULT 'local_deepseek'::character varying NOT NULL,
    embedding_model character varying(160) DEFAULT 'BAAI/bge-small-zh-v1.5'::character varying NOT NULL,
    generation_model character varying(120) DEFAULT 'deepseek-v4-flash'::character varying NOT NULL
);


--
-- Name: project_rag_datasets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.project_rag_datasets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: project_rag_datasets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.project_rag_datasets_id_seq OWNED BY public.project_rag_datasets.id;


--
-- Name: project_reviewers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_reviewers (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    review_scope character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: project_reviewers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.project_reviewers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: project_reviewers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.project_reviewers_id_seq OWNED BY public.project_reviewers.id;


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id integer NOT NULL,
    name character varying(160) NOT NULL,
    description text,
    is_sensitive boolean NOT NULL,
    status public.projectstatus NOT NULL,
    approval_enabled boolean NOT NULL,
    owner_user_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- Name: rag_document_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_document_chunks (
    id integer NOT NULL,
    project_id integer NOT NULL,
    file_id integer NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    content_hash character varying(64) NOT NULL,
    character_count integer NOT NULL,
    embedding public.vector(512) NOT NULL,
    metadata_json json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_document_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_document_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_document_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_document_chunks_id_seq OWNED BY public.rag_document_chunks.id;


--
-- Name: rag_file_syncs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_file_syncs (
    id integer NOT NULL,
    file_id integer NOT NULL,
    project_id integer NOT NULL,
    dify_dataset_id character varying(120) NOT NULL,
    dify_document_id character varying(120),
    sync_status character varying(40) NOT NULL,
    sync_message text,
    synced_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    chunk_count integer DEFAULT 0 NOT NULL,
    content_hash character varying(64)
);


--
-- Name: rag_file_syncs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_file_syncs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_file_syncs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_file_syncs_id_seq OWNED BY public.rag_file_syncs.id;


--
-- Name: search_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_documents (
    id integer NOT NULL,
    note_id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(300) NOT NULL,
    search_text text NOT NULL,
    source_ids text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: search_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.search_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: search_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.search_documents_id_seq OWNED BY public.search_documents.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(64) NOT NULL,
    password_hash character varying(255) NOT NULL,
    display_name character varying(120) NOT NULL,
    email character varying(255),
    role public.userrole NOT NULL,
    status public.userstatus NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    auth_version integer DEFAULT 0 NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: agent_generation_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_generation_runs ALTER COLUMN id SET DEFAULT nextval('public.agent_generation_runs_id_seq'::regclass);


--
-- Name: ai_experiment_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_experiment_runs ALTER COLUMN id SET DEFAULT nextval('public.ai_experiment_runs_id_seq'::regclass);


--
-- Name: ai_query_evaluations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_evaluations ALTER COLUMN id SET DEFAULT nextval('public.ai_query_evaluations_id_seq'::regclass);


--
-- Name: ai_query_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_logs ALTER COLUMN id SET DEFAULT nextval('public.ai_query_logs_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: experiment_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_notes ALTER COLUMN id SET DEFAULT nextval('public.experiment_notes_id_seq'::regclass);


--
-- Name: experiment_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_templates ALTER COLUMN id SET DEFAULT nextval('public.experiment_templates_id_seq'::regclass);


--
-- Name: file_ocr_results id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results ALTER COLUMN id SET DEFAULT nextval('public.file_ocr_results_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files ALTER COLUMN id SET DEFAULT nextval('public.files_id_seq'::regclass);


--
-- Name: group_members id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_members ALTER COLUMN id SET DEFAULT nextval('public.group_members_id_seq'::regclass);


--
-- Name: group_projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_projects ALTER COLUMN id SET DEFAULT nextval('public.group_projects_id_seq'::regclass);


--
-- Name: groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.groups ALTER COLUMN id SET DEFAULT nextval('public.groups_id_seq'::regclass);


--
-- Name: kg_entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_entities ALTER COLUMN id SET DEFAULT nextval('public.kg_entities_id_seq'::regclass);


--
-- Name: kg_extraction_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_extraction_runs ALTER COLUMN id SET DEFAULT nextval('public.kg_extraction_runs_id_seq'::regclass);


--
-- Name: kg_relations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations ALTER COLUMN id SET DEFAULT nextval('public.kg_relations_id_seq'::regclass);


--
-- Name: note_approvals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_approvals ALTER COLUMN id SET DEFAULT nextval('public.note_approvals_id_seq'::regclass);


--
-- Name: note_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_versions ALTER COLUMN id SET DEFAULT nextval('public.note_versions_id_seq'::regclass);


--
-- Name: project_members id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members ALTER COLUMN id SET DEFAULT nextval('public.project_members_id_seq'::regclass);


--
-- Name: project_rag_datasets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_rag_datasets ALTER COLUMN id SET DEFAULT nextval('public.project_rag_datasets_id_seq'::regclass);


--
-- Name: project_reviewers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_reviewers ALTER COLUMN id SET DEFAULT nextval('public.project_reviewers_id_seq'::regclass);


--
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- Name: rag_document_chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunks ALTER COLUMN id SET DEFAULT nextval('public.rag_document_chunks_id_seq'::regclass);


--
-- Name: rag_file_syncs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_file_syncs ALTER COLUMN id SET DEFAULT nextval('public.rag_file_syncs_id_seq'::regclass);


--
-- Name: search_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_documents ALTER COLUMN id SET DEFAULT nextval('public.search_documents_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: agent_generation_runs agent_generation_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_generation_runs
    ADD CONSTRAINT agent_generation_runs_pkey PRIMARY KEY (id);


--
-- Name: ai_experiment_runs ai_experiment_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_experiment_runs
    ADD CONSTRAINT ai_experiment_runs_pkey PRIMARY KEY (id);


--
-- Name: ai_query_evaluations ai_query_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_evaluations
    ADD CONSTRAINT ai_query_evaluations_pkey PRIMARY KEY (id);


--
-- Name: ai_query_logs ai_query_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_logs
    ADD CONSTRAINT ai_query_logs_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: experiment_notes experiment_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_notes
    ADD CONSTRAINT experiment_notes_pkey PRIMARY KEY (id);


--
-- Name: experiment_templates experiment_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_templates
    ADD CONSTRAINT experiment_templates_pkey PRIMARY KEY (id);


--
-- Name: file_ocr_results file_ocr_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results
    ADD CONSTRAINT file_ocr_results_pkey PRIMARY KEY (id);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: group_members group_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_pkey PRIMARY KEY (id);


--
-- Name: group_projects group_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_projects
    ADD CONSTRAINT group_projects_pkey PRIMARY KEY (id);


--
-- Name: groups groups_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_name_key UNIQUE (name);


--
-- Name: groups groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);


--
-- Name: kg_entities kg_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_entities
    ADD CONSTRAINT kg_entities_pkey PRIMARY KEY (id);


--
-- Name: kg_extraction_runs kg_extraction_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_extraction_runs
    ADD CONSTRAINT kg_extraction_runs_pkey PRIMARY KEY (id);


--
-- Name: kg_relations kg_relations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations
    ADD CONSTRAINT kg_relations_pkey PRIMARY KEY (id);


--
-- Name: note_approvals note_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_approvals
    ADD CONSTRAINT note_approvals_pkey PRIMARY KEY (id);


--
-- Name: note_versions note_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_versions
    ADD CONSTRAINT note_versions_pkey PRIMARY KEY (id);


--
-- Name: project_members project_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_pkey PRIMARY KEY (id);


--
-- Name: project_rag_datasets project_rag_datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_rag_datasets
    ADD CONSTRAINT project_rag_datasets_pkey PRIMARY KEY (id);


--
-- Name: project_reviewers project_reviewers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_reviewers
    ADD CONSTRAINT project_reviewers_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: rag_document_chunks rag_document_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunks
    ADD CONSTRAINT rag_document_chunks_pkey PRIMARY KEY (id);


--
-- Name: rag_file_syncs rag_file_syncs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_file_syncs
    ADD CONSTRAINT rag_file_syncs_pkey PRIMARY KEY (id);


--
-- Name: search_documents search_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_documents
    ADD CONSTRAINT search_documents_pkey PRIMARY KEY (id);


--
-- Name: ai_query_evaluations uq_ai_query_evaluation_log_evaluator; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_evaluations
    ADD CONSTRAINT uq_ai_query_evaluation_log_evaluator UNIQUE (query_log_id, evaluator_user_id);


--
-- Name: kg_entities uq_kg_entity_project_natural_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_entities
    ADD CONSTRAINT uq_kg_entity_project_natural_key UNIQUE (project_id, natural_key);


--
-- Name: kg_relations uq_kg_relation_project_source_target_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations
    ADD CONSTRAINT uq_kg_relation_project_source_target_type UNIQUE (project_id, source_entity_id, target_entity_id, relation_type);


--
-- Name: project_members uq_project_member; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT uq_project_member UNIQUE (project_id, user_id);


--
-- Name: project_rag_datasets uq_project_rag_dataset; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_rag_datasets
    ADD CONSTRAINT uq_project_rag_dataset UNIQUE (project_id);


--
-- Name: project_reviewers uq_project_reviewer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_reviewers
    ADD CONSTRAINT uq_project_reviewer UNIQUE (project_id, user_id);


--
-- Name: rag_document_chunks uq_rag_chunk_file_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunks
    ADD CONSTRAINT uq_rag_chunk_file_index UNIQUE (file_id, chunk_index);


--
-- Name: rag_file_syncs uq_rag_file_sync_file; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_file_syncs
    ADD CONSTRAINT uq_rag_file_sync_file UNIQUE (file_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_agent_generation_runs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_generation_runs_project_id ON public.agent_generation_runs USING btree (project_id);


--
-- Name: ix_agent_generation_runs_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_generation_runs_provider ON public.agent_generation_runs USING btree (provider);


--
-- Name: ix_agent_generation_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_generation_runs_status ON public.agent_generation_runs USING btree (status);


--
-- Name: ix_agent_generation_runs_task_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_generation_runs_task_type ON public.agent_generation_runs USING btree (task_type);


--
-- Name: ix_agent_generation_runs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_generation_runs_user_id ON public.agent_generation_runs USING btree (user_id);


--
-- Name: ix_ai_experiment_runs_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_experiment_runs_created_by ON public.ai_experiment_runs USING btree (created_by);


--
-- Name: ix_ai_experiment_runs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_experiment_runs_project_id ON public.ai_experiment_runs USING btree (project_id);


--
-- Name: ix_ai_experiment_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_experiment_runs_status ON public.ai_experiment_runs USING btree (status);


--
-- Name: uq_ai_experiment_runs_one_active_per_project; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_ai_experiment_runs_one_active_per_project ON public.ai_experiment_runs USING btree (project_id) WHERE ((status)::text IN ('queued'::text, 'running'::text));


--
-- Name: ix_ai_experiment_runs_lease; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_experiment_runs_lease ON public.ai_experiment_runs USING btree (status, lease_expires_at);


--
-- Name: ix_ai_query_evaluations_evaluator_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_evaluations_evaluator_user_id ON public.ai_query_evaluations USING btree (evaluator_user_id);


--
-- Name: ix_ai_query_evaluations_query_log_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_evaluations_query_log_id ON public.ai_query_evaluations USING btree (query_log_id);


--
-- Name: ix_ai_query_evaluations_review_protocol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_evaluations_review_protocol ON public.ai_query_evaluations USING btree (review_protocol);


--
-- Name: ix_ai_query_logs_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_conversation_id ON public.ai_query_logs USING btree (conversation_id);


--
-- Name: ix_ai_query_logs_experiment_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_experiment_run_id ON public.ai_query_logs USING btree (experiment_run_id);


--
-- Name: ix_ai_query_logs_model_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_model_name ON public.ai_query_logs USING btree (model_name);


--
-- Name: ix_ai_query_logs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_project_id ON public.ai_query_logs USING btree (project_id);


--
-- Name: ix_ai_query_logs_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_provider ON public.ai_query_logs USING btree (provider);


--
-- Name: ix_ai_query_logs_rag_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_rag_mode ON public.ai_query_logs USING btree (rag_mode);


--
-- Name: ix_ai_query_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_query_logs_user_id ON public.ai_query_logs USING btree (user_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_actor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_actor_user_id ON public.audit_logs USING btree (actor_user_id);


--
-- Name: ix_audit_logs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_project_id ON public.audit_logs USING btree (project_id);


--
-- Name: ix_experiment_notes_experiment_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_notes_experiment_type ON public.experiment_notes USING btree (experiment_type);


--
-- Name: ix_experiment_notes_owner_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_notes_owner_user_id ON public.experiment_notes USING btree (owner_user_id);


--
-- Name: ix_experiment_notes_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_notes_project_id ON public.experiment_notes USING btree (project_id);


--
-- Name: ix_experiment_notes_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_notes_status ON public.experiment_notes USING btree (status);


--
-- Name: ix_experiment_notes_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_notes_title ON public.experiment_notes USING btree (title);


--
-- Name: ix_experiment_templates_experiment_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_experiment_templates_experiment_type ON public.experiment_templates USING btree (experiment_type);


--
-- Name: ix_experiment_templates_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_experiment_templates_name ON public.experiment_templates USING btree (name);


--
-- Name: ix_file_ocr_results_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_created_by ON public.file_ocr_results USING btree (created_by);


--
-- Name: ix_file_ocr_results_file_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_file_hash ON public.file_ocr_results USING btree (file_hash);


--
-- Name: ix_file_ocr_results_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_file_id ON public.file_ocr_results USING btree (file_id);


--
-- Name: ix_file_ocr_results_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_project_id ON public.file_ocr_results USING btree (project_id);


--
-- Name: ix_file_ocr_results_review_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_review_status ON public.file_ocr_results USING btree (review_status);


--
-- Name: ix_file_ocr_results_reviewed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_ocr_results_reviewed_by ON public.file_ocr_results USING btree (reviewed_by);


--
-- Name: ix_files_file_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_file_hash ON public.files USING btree (file_hash);


--
-- Name: ix_files_knowledge_sync_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_knowledge_sync_status ON public.files USING btree (knowledge_sync_status);


--
-- Name: ix_files_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_note_id ON public.files USING btree (note_id);


--
-- Name: ix_files_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_project_id ON public.files USING btree (project_id);


--
-- Name: ix_files_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_status ON public.files USING btree (status);


--
-- Name: ix_files_uploaded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_files_uploaded_by ON public.files USING btree (uploaded_by);


--
-- Name: ix_group_members_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_group_members_group_id ON public.group_members USING btree (group_id);


--
-- Name: ix_group_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_group_members_user_id ON public.group_members USING btree (user_id);


--
-- Name: ix_group_projects_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_group_projects_group_id ON public.group_projects USING btree (group_id);


--
-- Name: ix_group_projects_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_group_projects_project_id ON public.group_projects USING btree (project_id);


--
-- Name: ix_kg_entities_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_entity_type ON public.kg_entities USING btree (entity_type);


--
-- Name: ix_kg_entities_label; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_label ON public.kg_entities USING btree (label);


--
-- Name: ix_kg_entities_natural_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_natural_key ON public.kg_entities USING btree (natural_key);


--
-- Name: ix_kg_entities_normalized_label; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_normalized_label ON public.kg_entities USING btree (normalized_label);


--
-- Name: ix_kg_entities_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_project_id ON public.kg_entities USING btree (project_id);


--
-- Name: ix_kg_entities_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_source_id ON public.kg_entities USING btree (source_id);


--
-- Name: ix_kg_entities_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_entities_source_type ON public.kg_entities USING btree (source_type);


--
-- Name: ix_kg_extraction_runs_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_extraction_runs_note_id ON public.kg_extraction_runs USING btree (note_id);


--
-- Name: ix_kg_extraction_runs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_extraction_runs_project_id ON public.kg_extraction_runs USING btree (project_id);


--
-- Name: ix_kg_extraction_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_extraction_runs_status ON public.kg_extraction_runs USING btree (status);


--
-- Name: ix_kg_extraction_runs_triggered_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_extraction_runs_triggered_by ON public.kg_extraction_runs USING btree (triggered_by);


--
-- Name: ix_kg_relations_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_project_id ON public.kg_relations USING btree (project_id);


--
-- Name: ix_kg_relations_relation_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_relation_type ON public.kg_relations USING btree (relation_type);


--
-- Name: ix_kg_relations_source_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_source_entity_id ON public.kg_relations USING btree (source_entity_id);


--
-- Name: ix_kg_relations_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_source_id ON public.kg_relations USING btree (source_id);


--
-- Name: ix_kg_relations_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_source_type ON public.kg_relations USING btree (source_type);


--
-- Name: ix_kg_relations_target_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kg_relations_target_entity_id ON public.kg_relations USING btree (target_entity_id);


--
-- Name: ix_note_approvals_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_approvals_action ON public.note_approvals USING btree (action);


--
-- Name: ix_note_approvals_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_approvals_note_id ON public.note_approvals USING btree (note_id);


--
-- Name: ix_note_approvals_reviewer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_approvals_reviewer_user_id ON public.note_approvals USING btree (reviewer_user_id);


--
-- Name: ix_note_approvals_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_approvals_version_id ON public.note_approvals USING btree (version_id);


--
-- Name: ix_note_versions_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_versions_note_id ON public.note_versions USING btree (note_id);


--
-- Name: ix_project_members_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_members_project_id ON public.project_members USING btree (project_id);


--
-- Name: ix_project_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_members_user_id ON public.project_members USING btree (user_id);


--
-- Name: ix_project_rag_datasets_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_rag_datasets_created_by ON public.project_rag_datasets USING btree (created_by);


--
-- Name: ix_project_rag_datasets_dify_dataset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_rag_datasets_dify_dataset_id ON public.project_rag_datasets USING btree (dify_dataset_id);


--
-- Name: ix_project_rag_datasets_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_rag_datasets_project_id ON public.project_rag_datasets USING btree (project_id);


--
-- Name: ix_project_rag_datasets_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_rag_datasets_provider ON public.project_rag_datasets USING btree (provider);


--
-- Name: ix_project_rag_datasets_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_rag_datasets_status ON public.project_rag_datasets USING btree (status);


--
-- Name: ix_project_reviewers_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_reviewers_project_id ON public.project_reviewers USING btree (project_id);


--
-- Name: ix_project_reviewers_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_reviewers_user_id ON public.project_reviewers USING btree (user_id);


--
-- Name: ix_projects_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_projects_name ON public.projects USING btree (name);


--
-- Name: ix_rag_chunks_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_chunks_embedding_hnsw ON public.rag_document_chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: ix_rag_document_chunks_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_document_chunks_content_hash ON public.rag_document_chunks USING btree (content_hash);


--
-- Name: ix_rag_document_chunks_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_document_chunks_file_id ON public.rag_document_chunks USING btree (file_id);


--
-- Name: ix_rag_document_chunks_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_document_chunks_project_id ON public.rag_document_chunks USING btree (project_id);


--
-- Name: ix_rag_file_syncs_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_content_hash ON public.rag_file_syncs USING btree (content_hash);


--
-- Name: ix_rag_file_syncs_dify_dataset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_dify_dataset_id ON public.rag_file_syncs USING btree (dify_dataset_id);


--
-- Name: ix_rag_file_syncs_dify_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_dify_document_id ON public.rag_file_syncs USING btree (dify_document_id);


--
-- Name: ix_rag_file_syncs_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_file_id ON public.rag_file_syncs USING btree (file_id);


--
-- Name: ix_rag_file_syncs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_project_id ON public.rag_file_syncs USING btree (project_id);


--
-- Name: ix_rag_file_syncs_sync_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_file_syncs_sync_status ON public.rag_file_syncs USING btree (sync_status);


--
-- Name: ix_search_documents_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_search_documents_note_id ON public.search_documents USING btree (note_id);


--
-- Name: ix_search_documents_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_search_documents_project_id ON public.search_documents USING btree (project_id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: agent_generation_runs agent_generation_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_generation_runs
    ADD CONSTRAINT agent_generation_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: agent_generation_runs agent_generation_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_generation_runs
    ADD CONSTRAINT agent_generation_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: ai_experiment_runs ai_experiment_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_experiment_runs
    ADD CONSTRAINT ai_experiment_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: ai_experiment_runs ai_experiment_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_experiment_runs
    ADD CONSTRAINT ai_experiment_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: ai_query_evaluations ai_query_evaluations_evaluator_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_evaluations
    ADD CONSTRAINT ai_query_evaluations_evaluator_user_id_fkey FOREIGN KEY (evaluator_user_id) REFERENCES public.users(id);


--
-- Name: ai_query_evaluations ai_query_evaluations_query_log_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_evaluations
    ADD CONSTRAINT ai_query_evaluations_query_log_id_fkey FOREIGN KEY (query_log_id) REFERENCES public.ai_query_logs(id);


--
-- Name: ai_query_logs ai_query_logs_experiment_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_logs
    ADD CONSTRAINT ai_query_logs_experiment_run_id_fkey FOREIGN KEY (experiment_run_id) REFERENCES public.ai_experiment_runs(id);


--
-- Name: ai_query_logs ai_query_logs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_logs
    ADD CONSTRAINT ai_query_logs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: ai_query_logs ai_query_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_query_logs
    ADD CONSTRAINT ai_query_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: audit_logs audit_logs_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: audit_logs audit_logs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: experiment_notes experiment_notes_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_notes
    ADD CONSTRAINT experiment_notes_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id);


--
-- Name: experiment_notes experiment_notes_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.experiment_notes
    ADD CONSTRAINT experiment_notes_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: file_ocr_results file_ocr_results_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results
    ADD CONSTRAINT file_ocr_results_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: file_ocr_results file_ocr_results_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results
    ADD CONSTRAINT file_ocr_results_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id);


--
-- Name: file_ocr_results file_ocr_results_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results
    ADD CONSTRAINT file_ocr_results_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: file_ocr_results file_ocr_results_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ocr_results
    ADD CONSTRAINT file_ocr_results_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: files files_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.experiment_notes(id);


--
-- Name: files files_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: files files_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


--
-- Name: group_members group_members_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id);


--
-- Name: group_members group_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: group_projects group_projects_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_projects
    ADD CONSTRAINT group_projects_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id);


--
-- Name: group_projects group_projects_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_projects
    ADD CONSTRAINT group_projects_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: groups groups_leader_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_leader_user_id_fkey FOREIGN KEY (leader_user_id) REFERENCES public.users(id);


--
-- Name: kg_entities kg_entities_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_entities
    ADD CONSTRAINT kg_entities_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: kg_extraction_runs kg_extraction_runs_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_extraction_runs
    ADD CONSTRAINT kg_extraction_runs_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.experiment_notes(id);


--
-- Name: kg_extraction_runs kg_extraction_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_extraction_runs
    ADD CONSTRAINT kg_extraction_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: kg_extraction_runs kg_extraction_runs_triggered_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_extraction_runs
    ADD CONSTRAINT kg_extraction_runs_triggered_by_fkey FOREIGN KEY (triggered_by) REFERENCES public.users(id);


--
-- Name: kg_relations kg_relations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations
    ADD CONSTRAINT kg_relations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: kg_relations kg_relations_source_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations
    ADD CONSTRAINT kg_relations_source_entity_id_fkey FOREIGN KEY (source_entity_id) REFERENCES public.kg_entities(id);


--
-- Name: kg_relations kg_relations_target_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kg_relations
    ADD CONSTRAINT kg_relations_target_entity_id_fkey FOREIGN KEY (target_entity_id) REFERENCES public.kg_entities(id);


--
-- Name: note_approvals note_approvals_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_approvals
    ADD CONSTRAINT note_approvals_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.experiment_notes(id);


--
-- Name: note_approvals note_approvals_reviewer_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_approvals
    ADD CONSTRAINT note_approvals_reviewer_user_id_fkey FOREIGN KEY (reviewer_user_id) REFERENCES public.users(id);


--
-- Name: note_approvals note_approvals_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_approvals
    ADD CONSTRAINT note_approvals_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.note_versions(id);


--
-- Name: note_versions note_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_versions
    ADD CONSTRAINT note_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: note_versions note_versions_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_versions
    ADD CONSTRAINT note_versions_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.experiment_notes(id);


--
-- Name: project_members project_members_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_members project_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: project_rag_datasets project_rag_datasets_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_rag_datasets
    ADD CONSTRAINT project_rag_datasets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: project_rag_datasets project_rag_datasets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_rag_datasets
    ADD CONSTRAINT project_rag_datasets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_reviewers project_reviewers_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_reviewers
    ADD CONSTRAINT project_reviewers_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_reviewers project_reviewers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_reviewers
    ADD CONSTRAINT project_reviewers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: projects projects_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id);


--
-- Name: rag_document_chunks rag_document_chunks_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunks
    ADD CONSTRAINT rag_document_chunks_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id);


--
-- Name: rag_document_chunks rag_document_chunks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunks
    ADD CONSTRAINT rag_document_chunks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: rag_file_syncs rag_file_syncs_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_file_syncs
    ADD CONSTRAINT rag_file_syncs_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id);


--
-- Name: rag_file_syncs rag_file_syncs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_file_syncs
    ADD CONSTRAINT rag_file_syncs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: search_documents search_documents_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_documents
    ADD CONSTRAINT search_documents_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.experiment_notes(id);


--
-- Name: search_documents search_documents_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_documents
    ADD CONSTRAINT search_documents_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- PostgreSQL database dump complete
--
