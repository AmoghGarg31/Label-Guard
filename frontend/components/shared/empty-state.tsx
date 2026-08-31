import { Inbox } from 'lucide-react';
export function EmptyState({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center"><Inbox className="mx-auto mb-3 text-slate-400" /><h3 className="font-extrabold text-navy">{title}</h3><p className="mx-auto mt-1 max-w-md text-sm leading-6 text-slate-600">{description}</p>{action && <div className="mt-4">{action}</div>}</div>;
}
