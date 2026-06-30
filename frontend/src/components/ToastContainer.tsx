import type { Toast } from "../hooks/useToasts";

interface Props {
  toasts: Toast[];
  onRemove: (id: number) => void;
}

export function ToastContainer({ toasts, onRemove }: Props) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span className="toast-icon">{t.kind === "success" ? "✓" : "✕"}</span>
          <div className="toast-body">
            <div className="toast-title">{t.title}</div>
            {t.message && <div className="toast-msg">{t.message}</div>}
          </div>
          <button className="btn btn-ghost btn-icon" onClick={() => onRemove(t.id)}>×</button>
        </div>
      ))}
    </div>
  );
}
