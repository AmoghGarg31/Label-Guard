'use client';
import { Search, ShieldAlert } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { SeverityChip } from '@/components/shared/severity-chip';
import { getRules } from '@/lib/api-client';
import { confidence, fieldLabel } from '@/lib/format';
import type { RuleInfo } from '@/lib/types';

export default function RulesPage() {
  const [rules, setRules] = useState<RuleInfo[]>(); const [query, setQuery] = useState(''); const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getRules().then(setRules).catch((reason: Error) => setError(reason.message)); }, []);
  useEffect(load, [load]);
  const visible = useMemo(() => rules?.filter((rule) => `${rule.rule_id} ${rule.field} ${rule.description} ${rule.source_citation}`.toLowerCase().includes(query.toLowerCase())), [query, rules]);
  return <div className="animate-enter"><div className="page-header"><div><p className="eyebrow">Versioned policy</p><h1 className="page-title">Deterministic rule explorer</h1><p className="page-copy">These backend rules alone produce declaration findings. Citations are traceability aids and remain subject to formal legal verification.</p></div></div>
    <div className="notice mb-6 flex items-start gap-3 border-amber-200 bg-amber-50 text-amber-950"><ShieldAlert className="mt-0.5 shrink-0" size={20} /><p><strong>Legal verification required.</strong> Rule metadata reflects the project handbook and checked government references, but LabelGuard is a screening prototype—not an authoritative interpretation or certification service.</p></div>
    <label className="relative mb-5 block max-w-xl"><span className="sr-only">Search rules</span><Search className="absolute left-3 top-3 text-slate-400" size={18} /><input className="field-input pl-10" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search rule ID, declaration, or citation" /></label>
    {error ? <ErrorState message={error} onRetry={load} /> : !visible ? <LoadingState /> : <div className="grid gap-4 xl:grid-cols-2">{visible.map((rule) => <article key={rule.rule_id} className="panel overflow-hidden"><div className="panel-head"><div className="flex items-center gap-2"><code className="rounded bg-navy px-2 py-1 text-xs font-bold text-mint">{rule.rule_id}</code><span className="text-xs font-bold text-slate-500">v{rule.rule_version}</span></div><SeverityChip severity={rule.severity} /></div><div className="panel-body"><h2 className="text-lg font-extrabold text-navy">{fieldLabel(rule.field)}</h2><p className="mt-2 text-sm leading-6 text-slate-700">{rule.description}</p><dl className="mt-4 grid gap-3 text-xs sm:grid-cols-3"><Item term="Check" value={rule.check_type.replaceAll('_', ' ')} /><Item term="Confidence floor" value={confidence(rule.confidence_floor)} /><Item term="Applicability" value={rule.applicability.replaceAll('_', ' ')} /></dl><div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600"><span className="font-bold text-navy">Source citation</span><br />{rule.source_citation}</div></div></article>)}</div>}
  </div>;
}
function Item({ term, value }: { term: string; value: string }) { return <div><dt className="font-bold uppercase tracking-wider text-slate-400">{term}</dt><dd className="mt-1 capitalize text-slate-700">{value}</dd></div>; }
