'use client';
import Link from 'next/link';
import { ClipboardCheck } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { EmptyState } from '@/components/shared/empty-state';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { StatusBadge } from '@/components/shared/status-badge';
import { getReviewQueue } from '@/lib/api-client';
import { formatDate, REVIEW_LABELS } from '@/lib/format';
import type { HistoryItem } from '@/lib/types';

export default function ReviewQueuePage() {
  const [items, setItems] = useState<HistoryItem[]>(); const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getReviewQueue().then(setItems).catch((reason: Error) => setError(reason.message)); }, []);
  useEffect(load, [load]);
  return <div className="animate-enter"><div className="page-header"><div><p className="eyebrow">Human oversight</p><h1 className="page-title">Review queue</h1><p className="page-copy">Inspections needing attention because of an uncertain automated result, missing review, correction request, or reinspection request.</p></div></div>{error ? <ErrorState message={error} onRetry={load} /> : !items ? <LoadingState /> : !items.length ? <EmptyState title="Review queue is clear" description="All saved inspections have a completed inspector review state." /> : <div className="grid gap-4 xl:grid-cols-2">{items.map((item) => <article className="panel p-5" key={item.id}><div className="flex items-start gap-4"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-800"><ClipboardCheck size={19} /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="truncate font-extrabold text-navy">#{item.id} · {item.original_filename}</h2><StatusBadge status={item.overall_status} /></div><p className="mt-2 text-xs text-slate-500">{formatDate(item.created_at)} · {item.package_scope} · {item.ocr_engine.toUpperCase()}</p><p className="mt-3 text-sm text-slate-700">Inspector state: <strong>{REVIEW_LABELS[item.review_status]}</strong></p><Link href={`/inspections/${item.id}`} className="button-primary mt-4">Open evidence and review</Link></div></div></article>)}</div>}</div>;
}
