import type { Metadata, Viewport } from 'next';
import { AppShell } from '@/components/shared/app-shell';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'LabelGuard', template: '%s · LabelGuard' },
  description: 'Deterministic packaged-commodity label screening with traceable evidence.',
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#071b20' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppShell>{children}</AppShell></body></html>;
}
