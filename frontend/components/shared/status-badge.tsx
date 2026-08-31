import { STATUS_LABELS } from '@/lib/format';
import type { OverallStatus } from '@/lib/types';

const styles: Record<OverallStatus, string> = {
  compliant: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  potential_non_compliance: 'border-rose-200 bg-rose-50 text-rose-800',
  manual_review_required: 'border-amber-200 bg-amber-50 text-amber-900',
};
export function StatusBadge({ status, className = '' }: { status: OverallStatus; className?: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${styles[status]} ${className}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{STATUS_LABELS[status]}</span>;
}
