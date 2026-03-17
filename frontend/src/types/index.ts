export type User = {
  id: number;
  username: string;
  name: string;
  is_active: boolean;
};

export type Batch = {
  id: number;
  name: string;
  status: string;
  created_at: string;
  total_files: number;
  processed_files: number;
  review_count: number;
  failed_count: number;
  export_status: string;
  last_error: string | null;
};

export type FieldAudit = {
  field_name: string;
  raw_text: string | null;
  normalized_value: string | null;
  confidence: number;
  validation_issues: string[];
};

export type Row = {
  id: number;
  status: string;
  confidence_summary: number;
  data: Record<string, unknown>;
  reviewed_data: Record<string, unknown> | null;
  validation_issues: string[];
  source_file_name: string;
  last_edited_at: string | null;
  audits: FieldAudit[];
};
