import { AlertTriangle } from 'lucide-react';
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="notice border-rose-200 bg-rose-50 text-rose-900"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 shrink-0" size={20} /><div><strong className="block">Could not load LabelGuard data</strong><p className="mt-1">{message}</p>{onRetry && <button className="button-secondary mt-3 !min-h-9" onClick={onRetry}>Retry</button>}</div></div></div>;
}
