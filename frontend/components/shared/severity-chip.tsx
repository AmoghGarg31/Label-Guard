export function SeverityChip({ severity }: { severity: 'MAJOR' | 'MINOR' }) {
  return <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${severity === 'MAJOR' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>{severity}</span>;
}
