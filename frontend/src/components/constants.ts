export const projectTabs = [
  { key: "notes", label: "笔记" },
  { key: "approvals", label: "审批" },
  { key: "data", label: "资料" },
  { key: "ai", label: "AI 问答" },
  { key: "kg", label: "图谱" },
  { key: "reports", label: "报告" },
  { key: "settings", label: "设置" },
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

/**
 * 审计动作中文映射表：枚举后端全部 audit 写入点
 * （backend/src/audit.rs 与 api/*.rs 中的 write_audit/AuditEvent）。
 * 后端新增 action 时前端回退展示原代码，不会报错。
 */
export const auditActionText: Record<string, string> = {
  approve_note: "通过笔记",
  archive_file: "归档文件",
  archive_note: "归档笔记",
  auto_extract_note_kg: "自动提取笔记图谱",
  change_password: "修改密码",
  change_permission: "变更成员权限",
  confirm_file_ocr: "确认 OCR 校对",
  create_group: "创建小组",
  create_note: "创建笔记",
  create_project: "创建项目",
  create_user: "创建账号",
  download_file: "下载文件",
  evaluate_ai_query: "评价 AI 问答",
  evaluate_ai_query_blind: "盲评 AI 问答",
  export_blind_review_batch: "导出盲评批次",
  extract_file_text: "提取文件文本",
  extract_note_kg: "提取笔记图谱",
  generate_agent_output: "生成智能体报告",
  generate_agent_output_failed: "智能体报告生成失败",
  index_rag_document: "RAG 文档入库",
  index_rag_document_failed: "RAG 文档入库失败",
  init_local_rag: "初始化本地知识库",
  login: "登录",
  logout: "登出",
  query_local_rag: "本地知识库问答",
  rebuild_project_kg: "重建项目图谱",
  return_note: "退回笔记",
  review_document: "审核资料",
  run_rag_experiment: "运行 RAG 对照实验",
  submit_note: "提交笔记审核",
  update_file: "更新文件",
  update_group: "更新小组",
  update_group_member: "更新小组成员",
  update_note: "更新笔记",
  update_project: "更新项目",
  update_project_member: "更新项目成员",
  update_user: "更新账号",
  upload_file: "上传文件",
  void_note: "作废笔记",
};

export const agentTaskOptions = [
  { value: "experiment_summary", label: "实验总结" },
  { value: "weekly_report", label: "周报" },
  { value: "stage_report", label: "项目阶段报告" },
  { value: "graph_overview", label: "实验过程图谱概览" },
  { value: "literature_review", label: "文献综述草稿" },
  { value: "anomaly_detection", label: "实验异常检测" },
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
