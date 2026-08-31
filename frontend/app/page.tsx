'use client';
import Link from 'next/link';
import { ArrowRight, Camera, CheckCircle2, ClipboardCheck, Database, Plus, ShieldAlert } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { StatusBadge } from '@/components/shared/status-badge';
import { getAnalytics, getHistory, getReviewQueue, getSystemStatus } from '@/lib/api-client';
import { formatDate } from '@/lib/format';
import type { Analytics, HistoryItem, SystemStatus } from '@/lib/types';

export default function DashboardPage() {
  const [data, setData] = useState<{ analytics: Analytics; recent: HistoryItem[]; queue: HistoryItem[]; system: SystemStatus }>();
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    Promise.all([getAnalytics(), getHistory({ limit: 6 }), getReviewQueue(100), getSystemStatus()])
      .then(([analytics, recent, queue, system]) => setData({ analytics, recent, queue, system }))
      .catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingState message="Reading inspections, review queue, and engine status…" />;
  const { analytics, recent, queue, system } = data;
  return <div className="animate-enter">
    <div className="page-header"><div><p className="eyebrow">Operations console</p><h1 className="page-title">Evidence first. Verdict second.</h1><p className="page-copy">Screen packaged-commodity labels, inspect Gemini-localized evidence behind every declaration, and keep human review separate from the deterministic result.</p></div><div className="flex gap-2"><Link className="button-secondary" href="/history">View history</Link><Link className="button-primary" href="/inspections/new"><Plus size={18} />Inspect label</Link></div></div>

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Inspection metrics">
      <Metric label="Inspections" value={analytics.total_inspections} icon={<Database />} detail={analytics.is_complete_history ? 'Complete saved history' : `Latest ${analytics.sample_limit} records`} />
      <Metric label="Potential issues" value={analytics.status_counts.potential_non_compliance ?? 0} icon={<ShieldAlert />} detail="Rule-engine FAIL present" tone="rose" />
      <Metric label="Needs manual review" value={analytics.status_counts.manual_review_required ?? 0} icon={<ClipboardCheck />} detail={`${queue.length} item${queue.length === 1 ? '' : 's'} in review queue`} tone="amber" />
      <Metric label="No issue flagged" value={analytics.status_counts.compliant ?? 0} icon={<CheckCircle2 />} detail="All active checks passed" tone="green" />
    </section>

    <section className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(290px,.7fr)]">
      <div className="panel"><div className="panel-head"><div><h2 className="section-title">Recent inspections</h2><p className="mt-1 text-xs text-slate-500">Current records from the backend—no mock fallback</p></div><Link href="/history" className="text-sm font-bold text-teal-800">All history <ArrowRight className="inline" size={15} /></Link></div>
        {recent.length ? <div className="divide-y">{recent.map((item) => <Link key={item.id} href={`/inspections/${item.id}`} className="focus-ring flex flex-col gap-3 p-4 transition hover:bg-slate-50 sm:flex-row sm:items-center"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Camera size={18} /></div><div className="min-w-0 flex-1"><p className="truncate text-sm font-extrabold text-navy">{item.original_filename}</p><p className="mt-1 text-xs text-slate-500">#{item.id} · {formatDate(item.created_at)} · {item.package_scope} package</p></div><StatusBadge status={item.overall_status} /></Link>)}</div> : <p className="p-8 text-center text-sm text-slate-500">No saved inspections yet.</p>}
      </div>
      <div className="space-y-6">
        <div className="panel p-5"><div className="flex items-center justify-between"><h2 className="section-title">System readiness</h2><span className={`rounded-full px-2 py-1 text-xs font-bold ${system.status === 'ok' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`}>{system.status.toUpperCase()}</span></div><dl className="mt-4 space-y-3 text-sm"><Row name="Database" value={system.database.available ? 'Available' : 'Unavailable'} /><Row name="Gemini extraction" value={system.extraction.available ? 'Ready' : 'Configuration required'} /><Row name="Rule engine" value={`${system.rule_engine.active_rule_count} active rules`} /><Row name="Engine version" value={system.rule_engine.version} /></dl><Link className="button-secondary mt-5 w-full" href="/system">Open diagnostics</Link></div>
        <div className="rounded-2xl bg-navy p-5 text-white shadow-panel"><p className="text-xs font-bold uppercase tracking-[.15em] text-mint">Workflow</p><ol className="mt-4 space-y-3 text-sm text-slate-300"><li><b className="text-white">1.</b> Capture a legible label</li><li><b className="text-white">2.</b> Confirm package context</li><li><b className="text-white">3.</b> Review localized evidence</li><li><b className="text-white">4.</b> Record inspector decision</li></ol><Link href="/inspections/new" className="button-primary mt-5 w-full">Start inspection <ArrowRight size={16} /></Link></div>
      </div>
    </section>
  </div>;
}

function Metric({ label, value, detail, icon, tone = 'teal' }: { label: string; value: number; detail: string; icon: React.ReactNode; tone?: 'teal' | 'rose' | 'amber' | 'green' }) {
  const colors = { teal: 'bg-teal-50 text-teal-800', rose: 'bg-rose-50 text-rose-700', amber: 'bg-amber-50 text-amber-800', green: 'bg-emerald-50 text-emerald-700' };
  return <div className="metric"><div className={`absolute right-4 top-4 grid h-10 w-10 place-items-center rounded-xl ${colors[tone]}`}>{icon}</div><p className="metric-label">{label}</p><p className="metric-value">{value}</p><p className="mt-2 pr-8 text-xs text-slate-500">{detail}</p></div>;
}
function Row({ name, value }: { name: string; value: string }) { return <div className="flex justify-between gap-4 border-b border-slate-100 pb-2"><dt className="text-slate-500">{name}</dt><dd className="text-right font-bold text-navy">{value}</dd></div>; }
