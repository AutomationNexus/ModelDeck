import { useState, useCallback } from "react";

export interface Toast {
  id: number;
  kind: "success" | "error";
  title: string;
  message?: string;
}

let _id = 0;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((kind: Toast["kind"], title: string, message?: string) => {
    const id = ++_id;
    setToasts((prev) => [...prev, { id, kind, title, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}
