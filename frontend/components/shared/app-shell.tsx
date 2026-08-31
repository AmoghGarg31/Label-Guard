'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, BarChart3, ClipboardCheck, FileSearch, History, Menu, Plus, Scale, ShieldCheck, X } from 'lucide-react';
import { useState } from 'react';

const links = [
  { href: '/', label: 'Overview', icon: BarChart3 }, { href: '/review', label: 'Review queue', icon: ClipboardCheck },
  { href: '/history', label: 'Inspection history', icon: History }, { href: '/rules', label: 'Rule explorer', icon: Scale },
  { href: '/analytics', label: 'Analytics', icon: Activity }, { href: '/system', label: 'System status', icon: FileSearch },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-navy/95 text-white backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-4 px-4 sm:px-6">
          <button className="focus-ring rounded-lg p-2 lg:hidden" onClick={() => setOpen(!open)} aria-label="Toggle navigation">{open ? <X size={20} /> : <Menu size={20} />}</button>
          <Link href="/" className="focus-ring flex items-center gap-3 rounded-lg" onClick={() => setOpen(false)}>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-mint text-navy shadow-glow"><ShieldCheck size={21} strokeWidth={2.4} /></span>
            <span><span className="block text-base font-extrabold tracking-tight">LabelGuard</span><span className="hidden text-[10px] uppercase tracking-[0.2em] text-slate-400 sm:block">Evidence-led screening</span></span>
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs text-emerald-200 md:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />Deterministic engine</span>
            <Link href="/inspections/new" className="button-primary !min-h-10"><Plus size={17} />New inspection</Link>
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1500px] lg:grid-cols-[230px_minmax(0,1fr)]">
        <aside className={`${open ? 'block' : 'hidden'} fixed inset-x-0 top-16 z-40 border-b bg-white p-3 shadow-xl lg:sticky lg:top-16 lg:block lg:h-[calc(100vh-4rem)] lg:border-b-0 lg:border-r lg:shadow-none`}>
          <nav aria-label="Primary" className="space-y-1">
            {links.map(({ href, label, icon: Icon }) => {
              const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
              return <Link key={href} href={href} onClick={() => setOpen(false)} className={`nav-link ${active ? 'nav-link-active' : ''}`}><Icon size={17} />{label}</Link>;
            })}
          </nav>
          <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-950"><strong className="block font-bold">Screening, not certification</strong>Findings support inspector review and require legal verification.</div>
        </aside>
        <main className="min-w-0 px-4 py-6 sm:px-7 sm:py-8 xl:px-10">{children}</main>
      </div>
      <footer className="border-t bg-white px-4 py-4 text-center text-xs text-slate-500 lg:ml-[230px]">LabelGuard · Backend-owned deterministic verdicts · No generative model decides compliance</footer>
    </div>
  );
}
