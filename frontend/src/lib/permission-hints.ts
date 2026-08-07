import { ApiRequestError } from "@/lib/api";

// 会话过期标记定义在 api.ts（避免循环依赖），此处重导出以便调用方统一入口。
export { SESSION_EXPIRED_FLAG } from "@/lib/api";

/** 后端对敏感项目外发 AI 的固定拒绝文案（不得修改，仅做精确识别）。 */
export const SENSITIVE_EXTERNAL_AI_MESSAGE = "敏感项目未获准向外部 AI 服务发送数据";

/**
 * 根据 API 错误推导面向用户的处理指引。
 * 仅在前端映射层补充，不改动后端返回的任何文案。
 */
export function getPermissionHint(error: unknown): string | null {
  if (!(error instanceof ApiRequestError)) return null;
  if (error.status === 403) {
    if (error.message.includes(SENSITIVE_EXTERNAL_AI_MESSAGE)) {
      return "需管理员在部署配置中开启外部 AI 许可。";
    }
    return "请联系项目负责人或系统管理员调整成员权限。";
  }
  if (error.status === 404) {
    return "目标数据不存在或已被删除，请刷新页面后重试。";
  }
  if (error.status === 409) {
    return "当前状态不允许此操作，可能已被他人处理，请刷新页面后重试。";
  }
  return null;
}

/**
 * 将指引追加到既有错误文案后；若文案中已包含指引则不重复拼接。
 */
export function withPermissionHint(error: unknown, message: string): string {
  const hint = getPermissionHint(error);
  if (!hint || message.includes(hint)) return message;
  const separator = message.endsWith("。") || message.endsWith("！") || message.endsWith("？") ? "" : "。";
  return `${message}${separator}${hint}`;
}
