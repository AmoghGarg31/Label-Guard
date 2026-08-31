export type OverallStatus = 'compliant' | 'potential_non_compliance' | 'manual_review_required';
export type FindingStatus = 'PASS' | 'FAIL' | 'UNCERTAIN';
export type ReviewStatus = 'NOT_REVIEWED' | 'VERIFIED' | 'CORRECTION_REQUIRED' | 'VIOLATION_CONFIRMED' | 'REINSPECTION_REQUIRED';
export type PackageScope = 'unknown' | 'domestic' | 'imported';
export type BoundingBox = [number, number, number, number];

export interface ExtractedField {
  text: string;
  confidence: number;
  bounding_box?: BoundingBox | null;
  source?: 'ocr' | 'gemini' | 'human_correction';
}

export type VerificationState = 'GEMINI_VALIDATED' | 'CONFLICT' | 'UNREADABLE' | 'MISSING' | 'MANUALLY_CORRECTED';

export interface FieldVerification {
  /** Present only on historical two-reader records. */
  ocr_value?: string | null;
  gemini_value?: string | null;
  gemini_values?: string[];
  gemini_model_score?: number | null;
  verification_state: VerificationState;
  verification_source?: string | null;
  accepted_source?: string | null;
  review_required?: boolean;
}

export interface VerificationResult {
  status?: string;
  review_required?: boolean;
  fields?: Record<string, FieldVerification>;
}

export interface Finding {
  rule_id: string;
  field: string;
  status: FindingStatus;
  severity: 'MAJOR' | 'MINOR';
  confidence: number;
  bounding_box: BoundingBox;
  description: string;
  source_citation: string;
  rule_version: string;
  applicability: 'applicable' | 'unknown';
}

export interface QualityResult {
  status?: string;
  details?: string;
  is_decodable?: boolean;
  blur_score?: number;
  glare_ratio?: number;
  local_contrast?: number;
  width?: number;
  height?: number;
  format?: string;
  mime_type?: string;
  orientation_degrees?: number;
  ocr_warning?: string | null;
  warnings?: string[];
  guidance_notes?: string[];
  [key: string]: unknown;
}

export interface ReviewInfo {
  review_status: ReviewStatus;
  reviewed_by?: string | null;
  review_notes?: string | null;
  reviewed_at?: string | null;
}

export interface FieldCorrection {
  id: number;
  field: string;
  original_text: string;
  corrected_text: string;
  reason: string;
  actor: string;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  event_type: string;
  description: string;
  actor: string;
  created_at: string;
}

export interface Inspection {
  id: number;
  overall_status: OverallStatus;
  extracted_fields: Record<string, ExtractedField>;
  findings: Finding[];
  rule_engine_version: string;
  quality: QualityResult;
  ocr_engine: string;
  orientation_degrees: 0 | 90 | 180 | 270;
  image_url: string;
  context: { package_scope?: PackageScope; commodity_category?: string | null };
  original_filename?: string;
  mime_type?: string | null;
  file_size_bytes?: number;
  created_at?: string;
  ocr_text?: string;
  evidence_filename?: string | null;
  report_url?: string;
  review?: ReviewInfo;
  corrections?: FieldCorrection[];
  audit_trail?: AuditEvent[];
  original_overall_status?: OverallStatus | null;
  verification?: VerificationResult;
  gemini_status?: {
    enabled?: boolean;
    configured?: boolean;
    status?: string;
    model?: string;
    image_readability?: string | null;
    candidate_count?: number;
    explanation_status?: string;
    external_processing_disclosure?: string;
    [key: string]: unknown;
  };
  ai_summary?: string;
  recommendation?: string[];
  performance?: Record<string, number>;
}

export interface HistoryItem {
  id: number;
  original_filename: string;
  created_at: string;
  overall_status: OverallStatus;
  quality_status: string;
  ocr_engine: string;
  review_status: ReviewStatus;
  package_scope: PackageScope;
}

export interface RuleInfo {
  rule_id: string;
  field: string;
  source_citation: string;
  description: string;
  severity: 'MAJOR' | 'MINOR';
  confidence_floor: number;
  check_type: string;
  rule_version: string;
  applicability: string;
  legal_verification_required: boolean;
}

export interface Analytics {
  total_inspections: number;
  status_counts: Record<OverallStatus, number>;
  quality_counts: Record<string, number>;
  review_counts: Record<string, number>;
  daily_counts: Array<{ date: string; count: number }>;
  sample_limit: number;
  is_complete_history: boolean;
}

export interface SystemStatus {
  status: 'ok' | 'degraded';
  service: string;
  database: { available: boolean; inspection_count?: number; path?: string; error?: string };
  extraction: {
    mode: 'gemini_only';
    reader: 'gemini_vision';
    available: boolean;
    local_ocr_in_inspection_path: boolean;
    deterministic_field_validation: boolean;
  };
  gemini: {
    enabled: boolean;
    configured: boolean;
    available: boolean;
    model: string;
    fast_model?: string;
    quality_model?: string;
    fallback_models?: string[];
    explanation_model?: string;
    explanation_enabled?: boolean;
    rate_limit?: { limit_per_minute: number; used_in_current_window: number; remaining_in_current_window: number; max_concurrent_requests: number; max_attempts_per_model?: number };
    last_route?: { reason?: string; models?: string[]; selected_model?: string | null } | null;
    timeout_seconds: number;
    sdk: string;
    last_error?: string | null;
    external_processing_disclosure?: string;
  };
  rule_engine: {
    available: boolean;
    version: string;
    active_rule_count: number;
    verdict_source: string;
  };
}
