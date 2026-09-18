export interface CompanyOverview {
  name?: string;
  legal_name?: string;
  ticker?: string;
  exchange?: string;
  share_class?: string;
  ceo?: string;
  description?: string;
  short_description?: string;
  industry?: string;
  sector?: string;
  founded?: string;
  headquarters?: string;
  website?: string;
  logo_url?: string;
  thumbnail_url?: string;
  linkedin_url?: string;
  linkedin?: string;
  company_type?: string;
  employees?: string | number;
  phone?: string;
  address?: string;
  country?: string;
  city?: string;
  wikipedia_url?: string;
  core_offerings?: string | string[];
  products?: string | string[];
  target_industry?: string;
  global_presence?: string;
  ai_overview?: string;
  summary?: string;
  linkedin_followers?: string | number;
  linkedin_members?: string | number;
  hiring_status?: string;
  global_offices?: string | number;
  company_size?: string;
}

export interface FinancialMetrics {
  market_cap?: string | number;
  revenue?: string | number;
  net_income?: string | number;
  ebitda?: string | number;
  pe_ratio?: string | number;
  range_52w?: string;
  eps?: string | number;
  dividend_yield?: string | number;
  week_52_high?: number;
  week_52_low?: number;
  beta?: number;
}

export interface SecFiling {
  title?: string;
  date?: string;
  url?: string;
  form?: string;
  form_type?: string;
  filed_at?: string;
}

export interface NewsArticle {
  title?: string;
  source?: string;
  source_name?: string;
  url?: string;
  date?: string;
  published_at?: string;
  snippet?: string;
  summary?: string;
  relevance?: string;
}

export interface Executive {
  name: string;
  full_name?: string;
  role?: string;
  title?: string;
  designation?: string;
  department?: string;
  dept?: string;
  linkedin_url?: string;
  url?: string;
  linkedin_profile?: string;
  avatar_url?: string;
  photo?: string;
  image?: string;
  profile_photo?: string;
  email?: string;
  work_email?: string;
  phone?: string;
  work_phone?: string;
  phone_number?: string;
}

export interface LinkedinInsights {
  followers?: string | number;
  employee_count?: string | number;
  linkedin_members?: string | number;
  hiring_status?: string;
  global_offices?: string | number;
  company_size?: string;
  url?: string;
}

export interface AiSummary {
  business_description?: string;
  products?: string | string[];
  target_industry?: string;
  global_presence?: string;
  overview?: string;
}

export interface CompanyDossier {
  query: string;
  overview?: CompanyOverview;
  financials?: FinancialMetrics;
  leadership?: Executive[];
  executives?: Executive[];
  people?: Executive[];
  competitors?: string[];
  sec_filings?: SecFiling[];
  filings?: SecFiling[];
  news?: NewsArticle[] | { articles?: NewsArticle[]; digest_summary?: string };
  sources?: string[];
  resolved?: {
    ticker?: string;
    name?: string;
    website?: string;
    cik?: string;
    wiki_title?: string;
    exchanges?: string[];
  };
  registry?: any;
  funding?: any;
  reputation?: any;
  linkedin_insights?: LinkedinInsights;
  ai_summary?: AiSummary;
  sec_url?: string;
  wikipedia_url?: string;
  linkedin_url?: string;
}

export interface LeadClassification {
  email: string;
  parsed: {
    domain?: string;
    company_guess?: string;
    name_guess?: string;
    is_corporate?: boolean;
  };
}

export interface PersonCandidate {
  name: string;
  role?: string;
  company?: string;
  location?: string;
  url: string;
  photo_url?: string;
  banner_url?: string;
  linkedin_profile_url?: string;
  email?: string;
  phone?: string;
  headline?: string;
}

export interface SystemHealth {
  status: string;
  service: string;
  timestamp: string;
  supabase_connected: boolean;
  environment: string;
}
