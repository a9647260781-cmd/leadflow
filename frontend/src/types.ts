export type LeadStatus = 'new' | 'in_progress' | 'won' | 'lost'

export type ExtractionStatus = 'not_requested' | 'pending' | 'processing' | 'succeeded' | 'failed' | 'not_configured'

export interface ExtractionEvidence {
  service: string | null
  budget: string | null
  timeframe: string | null
}

export interface LeadExtraction {
  status: ExtractionStatus
  service: string | null
  budget_min: number | null
  budget_max: number | null
  budget_currency: string | null
  budget_text: string | null
  timeframe: string | null
  evidence: ExtractionEvidence
  error_code: string | null
  attempts: number
  updated_at: string
  completed_at: string | null
  manually_edited: boolean
  revision: number
}

export interface LeadExtractionUpdate {
  expected_revision: number
  service: string | null
  budget_min: number | null
  budget_max: number | null
  budget_currency: string | null
  budget_text: string | null
  timeframe: string | null
  evidence: ExtractionEvidence
}

export interface User {
  id: number | string
  email: string
  name: string
}

export interface Lead {
  id: number | string
  name: string
  phone: string
  description: string
  status: LeadStatus
  created_at: string
  updated_at: string
}

export interface LeadEvent {
  id: number | string
  type: string
  message: string
  created_at: string
}

export interface LeadDetail extends Lead {
  history: LeadEvent[]
  extraction: LeadExtraction
}

export interface LeadsResponse {
  items: Lead[]
  total: number
  page: number
  page_size: number
}
