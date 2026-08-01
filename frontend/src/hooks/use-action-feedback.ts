import { useCallback, useMemo } from "react";
import { toast } from "sonner";

export function useActionFeedback() {
  const success = useCallback((message: string) => toast.success(message), []);
  const error = useCallback((message: string) => toast.error(message), []);
  return useMemo(() => ({ success, error }), [success, error]);
}
