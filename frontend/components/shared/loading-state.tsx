import { LoaderCircle } from 'lucide-react';
export function LoadingState({ message = 'Loading current data…' }: { message?: string }) {
  return <div className="panel grid min-h-56 place-items-center p-8 text-center"><div><LoaderCircle className="mx-auto mb-3 animate-spin text-teal-700" /><p className="text-sm font-semibold text-slate-600">{message}</p></div></div>;
}
