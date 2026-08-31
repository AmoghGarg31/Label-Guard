'use client';
import Link from 'next/link';
import { Download, Filter, Search } from 'lucide-react';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { EmptyState } from '@/components/shared/empty-state';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { StatusBadge } from '@/components/shared/status-badge';
import { exportUrl, getHistory } from '@/lib/api-client';
import { formatDate, REVIEW_LABELS } from '@/lib/format';
import type { HistoryItem } from '@/lib/types';

type Filters = { search: string; status: string; review_status: string; created_from: string; created_to: string };
const initial: Filters = { search: '', status: '', review_status: '', created_from: '', created_to: '' };

export default function HistoryPage() {
  const [draft, setDraft] = useState(initial);
  const [filters, setFilters] = useState(initial);
  const [items, setItems] = useState<HistoryItem[]>();
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    getHistory({ ...filters, created_to: filters.created_to ? `${filters.created_to}T23:59:59` : '' })
      .then(setItems).catch((reason: Error) => setError(reason.message));
  }, [filters]);
  useEffect(load, [load]);
  function submit(event: FormEvent) { event.preventDefault(); setFilters(draft); }

  return <div className="animate-enter">
    <div className="page-header"><div><p className="eyebrow">Saved evidence</p><h1 className="page-title">Inspection history</h1><p className="page-copy">Filter the preserved inspection ledger and export the current backend history for analysis.</p></div><div className="flex gap-2"><a className="button-secondary" href={exportUrl('json')}><Download size={16} />JSON</a><a className="button-secondary" href={exportUrl('csv')}><Download size={16} />CSV</a></div></div>
    <form onSubmit={submit} className="panel mb-6 p-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.4fr_repeat(4,minmax(130px,.7fr))_auto]">
        <label><span className="field-label">Search</span><span className="relative block"><Search className="absolute left-3 top-3 text-slate-400" size={17} /><input className="field-input pl-9" value={draft.search} onChange={(e) => setDraft({ ...draft, search: e.target.value })} placeholder="ID, filename, or detected text" /></span></label>
        <label><span className="field-label">Automated result</span><select className="field-input" value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}><option value="">All results</option><option value="compliant">No issue flagged</option><option value="potential_non_compliance">Potential non-compliance</option><option value="manual_review_required">Manual review required</option></select></label>
        <label><span className="field-label">Review</span><select className="field-input" value={draft.review_status} onChange={(e) => setDraft({ ...draft, review_status: e.target.value })}><option value="">All review states</option>{Object.entries(REVIEW_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span className="field-label">From</span><input type="date" className="field-input" value={draft.created_from} onChange={(e) => setDraft({ ...draft, created_from: e.target.value })} /></label>
        <label><span className="field-label">To</span><input type="date" className="field-input" value={draft.created_to} onChange={(e) => setDraft({ ...draft, created_to: e.target.value })} /></label>
        <button className="button-primary self-end" type="submit"><Filter size={16} />Apply</button>
      </div>
    </form>
    {error ? <ErrorState message={error} onRetry={load} /> : !items ? <LoadingState /> : !items.length ? <EmptyState title="No matching inspections" description="Change the filters or run a new inspection." action={<button onClick={() => { setDraft(initial); setFilters(initial); }} className="button-secondary">Clear filters</button>} /> : <HistoryTable items={items} />}
  </div>;
}

function HistoryTable({ items }: { items: HistoryItem[] }) {
  return <div className="panel table-wrap"><table className="data-table"><thead><tr><th>ID & file</th><th>Created</th><th>Package</th><th>Image / reader</th><th>Automated result</th><th>Inspector review</th><th></th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong className="block text-navy">#{item.id}</strong><span className="block max-w-[240px] truncate text-xs text-slate-500">{item.original_filename}</span></td><td className="whitespace-nowrap text-xs text-slate-600">{formatDate(item.created_at)}</td><td className="capitalize">{item.package_scope}</td><td><span className="block capitalize">{item.quality_status}</span><span className="text-xs uppercase text-slate-400">{item.ocr_engine}</span></td><td><StatusBadge status={item.overall_status} /></td><td><span className="text-xs font-bold text-slate-700">{REVIEW_LABELS[item.review_status] ?? item.review_status}</span></td><td><Link href={`/inspections/${item.id}`} className="text-sm font-bold text-teal-800">Inspect →</Link></td></tr>)}</tbody></table></div>;
}
