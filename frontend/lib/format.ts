import type { FindingStatus, OverallStatus, ReviewStatus } from './types';

export const FIELD_LABELS: Record<string, string> = {
  common_or_generic_name: 'Common / generic name', manufacturer_name: 'Manufacturer name',
  manufacturer_address: 'Manufacturer address', packer_name: 'Packer name',
  packer_address: 'Packer address', importer_name: 'Importer name', importer_address: 'Importer address',
  marketer_name: 'Marketer name', marketer_address: 'Marketer address',
  responsible_party_name_and_address: 'Responsible party name and address', net_quantity: 'Net quantity',
  mrp: 'Maximum retail price', date_of_manufacture: 'Manufacture / pre-pack date',
  consumer_care_contact: 'Consumer care contact', country_of_origin: 'Country of origin',
};

export function fieldLabel(value: string): string {
  return FIELD_LABELS[value] ?? value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export const STATUS_LABELS: Record<OverallStatus, string> = {
  compliant: 'No issue flagged', potential_non_compliance: 'Potential non-compliance',
  manual_review_required: 'Manual review required',
};
export const FINDING_LABELS: Record<FindingStatus, string> = {
  PASS: 'Declaration found', FAIL: 'Potential issue', UNCERTAIN: 'Needs review',
};
export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  NOT_REVIEWED: 'Not reviewed', VERIFIED: 'Verified', CORRECTION_REQUIRED: 'Correction required',
  VIOLATION_CONFIRMED: 'Violation confirmed', REINSPECTION_REQUIRED: 'Reinspection required',
};
export function formatDate(value?: string | null): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
export function confidence(value: number): string { return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`; }
export function formatBytes(value?: number): string {
  if (value === undefined) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
