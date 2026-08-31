import Link from 'next/link';
export default function NotFound() { return <div className="panel mx-auto max-w-xl p-10 text-center"><p className="eyebrow">404</p><h1 className="page-title">Record not found</h1><p className="page-copy mx-auto">The requested LabelGuard page or inspection does not exist.</p><Link href="/" className="button-primary mt-5">Return to overview</Link></div>; }
