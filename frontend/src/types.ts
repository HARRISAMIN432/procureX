export type ListResponse<T> = { items: T[]; total: number };

export type Organization = {
  id: string; slug: string; name: string; status: string; default_currency: string; timezone: string;
};
export type MembershipContext = { organization_id: string; user_id: string; membership_id: string; permissions: string[] };
export type Workspace = {
  organization_id: string; organization_slug: string; organization_name: string;
  organization_status: string; membership_id: string; membership_status: string;
  is_pending_invitation: boolean;
};
export type Requisition = {
  id: string; title: string; justification: string; department?: string; cost_center?: string;
  currency: string; need_by_date?: string; status: string; version: number; updated_at: string;
  lines: Array<{ id: string; line_number: number; description: string; quantity: string; unit: string; estimated_unit_price?: string }>;
  requirements: Array<{ id: string; priority: string; criterion: string }>;
};
export type Supplier = {
  id: string; legal_name: string; trading_name?: string; registration_country: string; registration_number: string;
  categories: string[]; status: string; version: number; updated_at: string;
  contacts: Array<{ id: string; name: string; email: string; is_primary: boolean }>;
  qualifications: Array<{ id: string; category: string; status: string; valid_to?: string }>;
  certificates: Array<{ id: string; certificate_type: string; status: string; expires_on?: string }>;
};
export type Rfq = {
  id: string; requisition_id: string; title: string; currency: string; submission_deadline: string;
  status: string; version: number; publication_number: number; updated_at: string;
  items: unknown[]; requirements: unknown[]; invitations: Array<{ id: string; status: string }>;
  submissions: Array<{ id: string; supplier_id: string; status: string; currency: string; valid_until: string }>;
  clarifications: Array<{ id: string; status: string }>;
};
export type DocumentRecord = {
  id: string; title: string; document_type: string; status: string; updated_at: string;
  versions: Array<{ id: string; version: number; original_filename: string; media_type: string; byte_size: number; status: string }>;
};
export type Budget = {
  id: string; code: string; name: string; currency: string; period_start: string; period_end: string;
  status: string; available: string; reserved: string; committed: string; consumed: string;
};
export type Role = { id: string; name: string; description?: string; is_system: boolean; permission_codes: string[] };
export type Member = { membership_id: string; user_id: string; email: string; display_name: string; status: string; role_ids: string[]; joined_at?: string };

export type Session = {
  mode: "dev" | "oidc";
  organizationId: string;
  userId?: string;
  accessToken?: string;
  displayName: string;
};
