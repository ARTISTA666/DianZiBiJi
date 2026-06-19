export const projectTabs = [
  { key: "overview", label: "项目概览", icon: "Database" },
  { key: "notes", label: "实验笔记", icon: "FileText" },
  { key: "files", label: "资料库", icon: "Upload" },
  { key: "search", label: "搜索", icon: "FileSearch" },
  { key: "kg", label: "知识图谱", icon: "Sparkles" },
  { key: "reports", label: "报告", icon: "BarChart" },
  { key: "approvals", label: "审批中心", icon: "ClipboardCheck" },
  { key: "members", label: "成员权限", icon: "Users" },
  { key: "logs", label: "项目日志", icon: "ShieldCheck" },
] as const;
export type ProjectTab = (typeof projectTabs)[number]["key"];

export const roleOptions = ["super_admin", "pi", "group_leader", "project_owner", "reviewer", "member"] as const;
export const projectRoleOptions = ["owner", "reviewer", "member", "viewer"] as const;

export const statusText: Record<string, string> = {
  draft: "草稿",
  submitted: "待审核",
  approved: "已审核",
  returned: "已退回",
  archived: "已归档",
  voided: "已作废",
};

export const knowledgeSyncText: Record<string, string> = {
  not_applicable: "不入库",
  pending_review: "待资料审核",
  pending_sync: "待同步",
  synced: "已入库",
  failed: "同步失败",
};

export const agentTaskOptions = [
  { value: "experiment_summary", label: "实验总结" },
  { value: "weekly_report", label: "周报" },
  { value: "stage_report", label: "项目阶段报告" },
  { value: "graph_overview", label: "实验过程图谱概览" },
];

export const kgEntityTypeText: Record<string, string> = {
  project: "项目",
  note: "实验笔记",
  user: "人员",
  file: "附件资料",
  experiment_type: "实验类型",
  reagent: "试剂",
  instrument: "仪器",
  sample: "样本",
  result: "实验结果",
};

export const kgRelationTypeText: Record<string, string> = {
  has_note: "包含笔记",
  created_by: "创建者",
  has_attachment: "关联附件",
  has_experiment_type: "实验类型",
  uses_reagent: "使用试剂",
  uses_instrument: "使用仪器",
  uses_sample: "使用样本",
  produces_result: "产生结果",
};

export const kgEntityColors: Record<string, string> = {
  project: "#0f766e",
  note: "#2563eb",
  user: "#7c3aed",
  file: "#ea580c",
  experiment_type: "#0891b2",
  reagent: "#16a34a",
  instrument: "#9333ea",
  sample: "#ca8a04",
  result: "#dc2626",
};

export const kgEntityShortText: Record<string, string> = {
  project: "项",
  note: "笔",
  user: "人",
  file: "附",
  experiment_type: "类",
  reagent: "试",
  instrument: "仪",
  sample: "样",
  result: "果",
};
