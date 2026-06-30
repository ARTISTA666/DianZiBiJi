import {
  BookOpen,
  BarChart,
  BookOpenIcon,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  FolderPlus,
  LayoutDashboard,
  Lock,
  LogOut,
  Paperclip,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";
import { kgEntityTypeText, kgRelationTypeText } from "../constants";

// Re-export all icons so consumers don't need to import lucide-react directly
export {
  BookOpen,
  BarChart,
  BookOpenIcon,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  FolderPlus,
  LayoutDashboard,
  Lock,
  LogOut,
  Paperclip,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  UserPlus,
  Users,
  XCircle,
};

export function cardClass(extra = "") {
  return `rounded-md border border-border bg-white shadow-panel ${extra}`;
}

export function kgTypeLabel(type: string) {
  return kgEntityTypeText[type] || type;
}

export function kgRelationLabel(type: string) {
  return kgRelationTypeText[type] || type;
}

export function shortLabel(label: string, maxLength = 14) {
  return label.length > maxLength ? `${label.slice(0, maxLength)}...` : label;
}

export function ragModeLabel(mode: string) {
  if (mode === "kg_enhanced_rag") return "知识图谱增强 RAG";
  if (mode === "project_rag") return "项目级 RAG";
  return "自动选择";
}

export function formatRate(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return `${Math.round(value * 100)}%`;
}

export function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return value.toFixed(2).replace(/\.00$/, "");
}
