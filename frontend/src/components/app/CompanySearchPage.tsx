import React, { useState } from 'react';
import { Search, Building2, TrendingUp, Users, FileText, Newspaper, Globe, Sparkles, Bookmark, ExternalLink, Linkedin, Award, Briefcase, Mail, Phone } from 'lucide-react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { ProgressBar } from '../ui/ProgressBar';
import { fetchCompanyEmployees, subscribeCompanyStream } from '../../services/api';
import { CompanyDossier } from '../../types';

const ensureUrl = (url?: string) => {
  if (!url) return '';
  let u = url.trim();
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  return u;
};

const cleanDomain = (url?: string) => {
  if (!url) return '';
  try {
    let u = url.trim();
    if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
    const parsed = new URL(u);
    return parsed.hostname.replace(/^www\./i, '');
  } catch (_) {
    return url.replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];
  }
};

const cleanEmail = (raw?: string) => {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s) return null;
  if (
    /@company\.com$/i.test(s) ||
    s.toLowerCase().includes('company.com') ||
    s.toLowerCase().includes('example.com') ||
    s.toLowerCase().includes('domain.com') ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)
  ) {
    return null;
  }
  return s;
};

const formatPhone = (raw?: string) => {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s || /company\.com/i.test(s) || /incomplete/i.test(s)) return null;

  const digits = s.replace(/\D/g, '');
  if (digits.length < 10 || digits.length > 15) return null;

  const hasPlus = s.startsWith('+');

  if (hasPlus && digits.startsWith('91') && digits.length === 12) {
    return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  }
  if (!hasPlus && digits.length === 10 && /^[6-9]/.test(digits)) {
    return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
  }

  if (hasPlus && digits.startsWith('1') && digits.length === 11) {
    return `+1 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }
  if (!hasPlus && digits.length === 10) {
    return `+1 ${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }

  if (hasPlus) {
    if (digits.length > 10) {
      const ccLen = digits.length - 10;
      return `+${digits.slice(0, ccLen)} ${digits.slice(ccLen, ccLen + 5)} ${digits.slice(ccLen + 5)}`;
    }
    return `+${digits}`;
  }

  return `+${digits.slice(0, digits.length - 10)} ${digits.slice(digits.length - 10, digits.length - 5)} ${digits.slice(digits.length - 5)}`;
};

const cleanLinkedIn = (raw?: string) => {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s || s === '#' || !s.toLowerCase().includes('linkedin.com')) return null;

  const cleanDisplay = s
    .replace(/^https?:\/\//i, '')
    .replace(/^www\./i, '')
    .replace(/\/$/, '')
    .split('?')[0];

  const fullUrl = /^https?:\/\//i.test(s) ? s : `https://${s}`;
  return { display: cleanDisplay, href: fullUrl };
};

export const CompanySearchPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ pct: number; step: string }>({ pct: 0, step: '' });
  const [activeTab, setActiveTab] = useState<'overview' | 'financials' | 'leadership' | 'news' | 'filings'>('overview');
  const [dossier, setDossier] = useState<CompanyDossier | null>(null);
  const [employees, setEmployees] = useState<any[]>([]);
  const [employeesLoaded, setEmployeesLoaded] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setEmployees([]);
    setEmployeesLoaded(false);
    setProgress({ pct: 10, step: 'Initializing AI Pipeline...' });

    subscribeCompanyStream(
      query,
      (msg) => {
        if (msg.pct) setProgress({ pct: msg.pct, step: msg.step || 'Processing data...' });
        if (msg.done) {
          setLoading(false);
          if (msg.error) {
            alert(`Backend Error: ${msg.error}`);
          }
          if (msg.dossier) {
            setDossier(msg.dossier);
            fetchCompanyEmployees(query.trim())
              .then((data) => setEmployees(Array.isArray(data.employees) ? data.employees : []))
              .catch(() => setEmployees([]))
              .finally(() => setEmployeesLoaded(true));
          }
        }
      },
      (err) => {
        setLoading(false);
        console.error('Company search error:', err);
        alert('Connection error. Could not reach backend.');
      }
    );
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Search Header */}
      <div className="text-center space-y-4 max-w-2xl mx-auto py-4">
        <h1 className="text-3xl font-extrabold text-[#111827]">Company Intelligence Search</h1>
        <p className="text-sm text-[#6B7280]">
          Enter any company name, stock ticker, or domain to generate an AI-powered financial and market dossier.
        </p>

        <form onSubmit={handleSearch} className="flex gap-3 pt-2">
          <Input
            placeholder="Search any company (e.g. Tesla, Apple, Nvidia)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            icon={<Search className="w-5 h-5" />}
          />
          <Button variant="primary" size="lg" loading={loading} icon={<Sparkles className="w-4 h-4" />}>
            Generate Dossier
          </Button>
        </form>

        {loading && (
          <div className="pt-4">
            <ProgressBar pct={progress.pct} step={progress.step} />
          </div>
        )}
      </div>

      {/* Dossier Display */}
      {dossier ? (() => {
        const resolved = dossier.resolved || {};
        const overview = dossier.overview || {};
        const financials = dossier.financials || {};
        const linkedinInsights = dossier.linkedin_insights || (dossier as any).linkedin || {};
        const aiSummary = dossier.ai_summary || {};
        const filings = dossier.sec_filings || dossier.filings || [];
        const newsArticles = Array.isArray(dossier.news) ? dossier.news : (dossier.news?.articles || []);

        const name = resolved.name || overview.legal_name || overview.name || dossier.query;
        const ticker = resolved.ticker || overview.ticker;
        const logo = overview.logo_url || overview.thumbnail_url;
        const website = overview.website?.trim() || null;
        let linkedinUrl = overview.linkedin_url || overview.linkedin || linkedinInsights.url || dossier.linkedin_url;
        
        // Manual override for specific company LinkedIn profiles that fail to resolve correctly
        const lowerName = (name || '').toLowerCase();
        if (lowerName.includes('business gateways international')) {
          linkedinUrl = 'https://www.linkedin.com/company/business-gateways-international-llc/';
        }
        
        const industry = overview.industry || overview.sector;
        const founded = overview.founded || dossier.registry?.incorporated;
        const companyType = overview.company_type || (ticker ? 'Public' : (overview.share_class ? 'Public' : 'Private'));
        const hq = overview.headquarters || overview.address || dossier.registry?.address || [overview.city, overview.country].filter(Boolean).join(', ');

        const cik = resolved.cik || (dossier as any).cik;
        const secUrl = cik ? `https://www.sec.gov/edgar/browse/?CIK=${cik}` : (dossier.sec_url || (filings[0] && filings[0].url));
        const wikiUrl = overview.wikipedia_url || (resolved.wiki_title ? `https://en.wikipedia.org/wiki/${encodeURIComponent(resolved.wiki_title)}` : dossier.wikipedia_url);

        // Executives data
        const execs = dossier.leadership || dossier.executives || dossier.people || dossier.registry?.directors || [];

        // LinkedIn Insights Data
        const followers = linkedinInsights.followers || overview.linkedin_followers;
        const empCount = linkedinInsights.employee_count || overview.employees;
        const liMembers = linkedinInsights.linkedin_members || overview.linkedin_members;
        const hiringStatus = linkedinInsights.hiring_status || overview.hiring_status;
        const globalOffices = linkedinInsights.global_offices || overview.global_offices;
        const companySize = linkedinInsights.company_size || overview.company_size;

        const hasLinkedinInsights = Boolean(followers || empCount || liMembers || hiringStatus || globalOffices || companySize);

        // AI Summary Data
        const desc = overview.description || overview.short_description || aiSummary.business_description;
        const offerings = overview.core_offerings || overview.products || aiSummary.products || dossier.funding?.products || (dossier as any).products;
        const targetInd = overview.target_industry || aiSummary.target_industry || overview.industry || overview.sector;
        const globalPres = overview.global_presence || aiSummary.global_presence || [hq, overview.country].filter(Boolean).join(', ');
        const aiOverview = (!Array.isArray(dossier.news) && dossier.news?.digest_summary) || overview.ai_overview || overview.summary || aiSummary.overview || desc;

        return (
          <div className="space-y-6">
            {/* 1. Company Main Header Card */}
            <Card className="flex flex-col gap-6 bg-[#F8FAFC]">
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                <div className="flex items-center gap-4">
                  {logo ? (
                    <img
                      src={logo}
                      alt={name}
                      className="w-14 h-14 rounded-2xl object-contain bg-white border border-[#E5E7EB] p-1 shadow-xs"
                      onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
                    />
                  ) : (
                    <div className="w-14 h-14 rounded-2xl bg-[#0EA5E9] text-white font-bold flex items-center justify-center text-xl shadow-xs">
                      {(ticker || name).slice(0, 2).toUpperCase()}
                    </div>
                  )}

                  <div className="space-y-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h2 className="text-2xl font-extrabold text-[#111827]">{name}</h2>
                      {ticker && <Badge variant="primary">{ticker}</Badge>}
                      {resolved.exchanges && resolved.exchanges.length > 0 && (
                        <Badge variant="secondary">{resolved.exchanges.join(', ')}</Badge>
                      )}
                      {companyType && <Badge variant="info">{companyType}</Badge>}
                    </div>
                    <p className="text-xs text-[#6B7280] flex items-center gap-2 flex-wrap">
                      {[industry && `Industry: ${industry}`, founded && `Founded: ${founded}`, hq && `HQ: ${hq}`].filter(Boolean).join(' • ')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Button variant="outline" size="sm" icon={<Bookmark className="w-4 h-4" />}>
                    Bookmark
                  </Button>
                </div>
              </div>

              {/* Header Links Row */}
              {(website || linkedinUrl) && (
                <div className="pt-3 border-t border-[#E5E7EB] flex flex-wrap gap-4 text-xs font-medium text-[#4B5563]">
                  {website && (
                    <div className="flex items-center gap-1.5">
                      <Globe className="w-4 h-4 text-[#0EA5E9]" />
                      <span className="text-[#6B7280]">Website:</span>
                      <a href={ensureUrl(website)} target="_blank" rel="noreferrer" className="text-[#0EA5E9] hover:underline font-semibold">
                        {cleanDomain(website)}
                      </a>
                    </div>
                  )}
                  {linkedinUrl && (
                    <div className="flex items-center gap-1.5">
                      <Linkedin className="w-4 h-4 text-[#0A66C2]" />
                      <span className="text-[#6B7280]">LinkedIn:</span>
                      <a href={ensureUrl(linkedinUrl)} target="_blank" rel="noreferrer" className="text-[#0EA5E9] hover:underline font-semibold">
                        {cleanDomain(linkedinUrl)}
                      </a>
                    </div>
                  )}
                </div>
              )}
            </Card>

            {/* 5. Company Quick Links Section */}
            <Card className="space-y-3">
              <h3 className="text-sm font-bold text-[#111827] uppercase tracking-wider">Company Quick Links</h3>
              <div className="flex flex-wrap gap-3">
                {website && (
                  <a href={ensureUrl(website)} target="_blank" rel="noreferrer">
                    <Button variant="secondary" size="sm" icon={<Globe className="w-4 h-4" />}>
                      Visit Website <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  </a>
                )}
                {linkedinUrl && (
                  <a href={ensureUrl(linkedinUrl)} target="_blank" rel="noreferrer">
                    <Button variant="secondary" size="sm" icon={<Linkedin className="w-4 h-4 text-[#0A66C2]" />}>
                      LinkedIn Company <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  </a>
                )}
                {secUrl && (ticker || cik || companyType === 'Public') && (
                  <a href={ensureUrl(secUrl)} target="_blank" rel="noreferrer">
                    <Button variant="secondary" size="sm" icon={<FileText className="w-4 h-4" />}>
                      SEC Profile <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  </a>
                )}
                {wikiUrl && (
                  <a href={ensureUrl(wikiUrl)} target="_blank" rel="noreferrer">
                    <Button variant="secondary" size="sm" icon={<Building2 className="w-4 h-4" />}>
                      Wikipedia <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  </a>
                )}
              </div>
            </Card>

            {/* 2. LinkedIn Company Insights Section */}
            {hasLinkedinInsights && (
              <Card className="space-y-4">
                <div className="flex items-center gap-2">
                  <Linkedin className="w-5 h-5 text-[#0A66C2]" />
                  <h3 className="text-sm font-bold text-[#111827] uppercase tracking-wider">LinkedIn Company Insights</h3>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
                  {followers && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">Followers</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{typeof followers === 'number' ? followers.toLocaleString() : followers}</p>
                    </div>
                  )}
                  {empCount && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">Employee Count</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{typeof empCount === 'number' ? empCount.toLocaleString() : empCount}</p>
                    </div>
                  )}
                  {liMembers && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">LinkedIn Members</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{typeof liMembers === 'number' ? liMembers.toLocaleString() : liMembers}</p>
                    </div>
                  )}
                  {hiringStatus && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">Hiring Status</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{hiringStatus}</p>
                    </div>
                  )}
                  {globalOffices && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">Global Offices</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{globalOffices}</p>
                    </div>
                  )}
                  {companySize && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[11px] font-medium text-[#6B7280] uppercase">Company Size</p>
                      <p className="text-base font-bold text-[#111827] mt-0.5">{companySize}</p>
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* 7. Company Highlights Section */}
            {(() => {
              const ceoName = overview.ceo || (dossier as any).ceo || execs.find((e: any) => {
                const r = (e.role || e.title || e.designation || '').toLowerCase();
                return r.includes('ceo') || r.includes('chief executive') || r.includes('founder & ceo');
              })?.name;

              const highlightsList = [
                founded && { label: 'Founded', val: founded },
                ceoName && { label: 'CEO', val: ceoName },
                hq && { label: 'Headquarters', val: hq },
                industry && { label: 'Industry', val: industry },
                companySize && { label: 'Company Size', val: companySize },
                companyType && { label: 'Ownership', val: companyType },
                ticker && { label: 'Stock Symbol', val: ticker },
                globalPres && { label: 'Operating Countries', val: globalPres }
              ].filter(Boolean) as { label: string; val: string }[];

              if (highlightsList.length === 0) return null;

              return (
                <Card className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Award className="w-5 h-5 text-[#0EA5E9]" />
                    <h3 className="text-sm font-bold text-[#111827] uppercase tracking-wider">Company Highlights</h3>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {highlightsList.map((h, idx) => (
                      <div key={idx} className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                        <p className="text-[11px] font-medium text-[#6B7280] uppercase">{h.label}</p>
                        <p className="text-sm font-bold text-[#111827] mt-0.5">{h.val}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })()}

            {/* Dossier Tabbed Navigation */}
            <div className="flex items-center gap-2 border-b border-[#E5E7EB] pb-2 overflow-x-auto">
              {[
                { id: 'overview', label: 'Overview', icon: <Building2 className="w-4 h-4" /> },
                { id: 'financials', label: 'Financials & Metrics', icon: <TrendingUp className="w-4 h-4" /> },
                { id: 'leadership', label: 'Leadership', icon: <Users className="w-4 h-4" /> },
                { id: 'news', label: 'Recent News', icon: <Newspaper className="w-4 h-4" /> },
                { id: 'filings', label: 'SEC Filings', icon: <FileText className="w-4 h-4" /> },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-semibold whitespace-nowrap transition-all ${
                    activeTab === tab.id
                      ? 'bg-[#0EA5E9] text-white shadow-xs'
                      : 'text-[#6B7280] hover:text-[#111827] hover:bg-slate-100'
                  }`}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            {/* Tab Content Panels */}
            {activeTab === 'overview' && (
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                {/* 2. ABOUT COMPANY Section */}
                <Card className="md:col-span-8 space-y-6">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-[#0EA5E9]" />
                    <h3 className="text-base font-bold text-[#111827]">ABOUT COMPANY</h3>
                  </div>

                  {desc && (
                    <div className="space-y-1">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">Business Description</h4>
                      <p className="text-sm text-[#4B5563] leading-relaxed">{desc}</p>
                    </div>
                  )}

                  {offerings && (
                    <div className="space-y-1 pt-3 border-t border-[#E5E7EB]">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">Core Products & Services</h4>
                      <p className="text-sm text-[#4B5563] leading-relaxed">
                        {Array.isArray(offerings) ? offerings.join(', ') : offerings}
                      </p>
                    </div>
                  )}

                  {targetInd && (
                    <div className="space-y-1 pt-3 border-t border-[#E5E7EB]">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">Target Industry</h4>
                      <p className="text-sm text-[#4B5563] leading-relaxed">{targetInd}</p>
                    </div>
                  )}

                  {globalPres && (
                    <div className="space-y-1 pt-3 border-t border-[#E5E7EB]">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">Global Presence</h4>
                      <p className="text-sm text-[#4B5563] leading-relaxed">{globalPres}</p>
                    </div>
                  )}

                  {aiOverview && aiOverview !== desc && (
                    <div className="space-y-1 pt-3 border-t border-[#E5E7EB]">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">AI Overview</h4>
                      <p className="text-sm text-[#4B5563] leading-relaxed">{aiOverview}</p>
                    </div>
                  )}

                  {dossier.competitors && dossier.competitors.length > 0 && (
                    <div className="pt-3 border-t border-[#E5E7EB]">
                      <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider mb-3">Key Competitors</h4>
                      <div className="flex flex-wrap gap-2">
                        {dossier.competitors.map((comp, idx) => (
                          <Badge key={idx} variant="info">{comp}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>

                <Card className="md:col-span-4 space-y-4">
                  <h3 className="text-base font-bold text-[#111827]">Company Metadata</h3>
                  <div className="space-y-3 text-xs">
                    {industry && (
                      <div className="flex justify-between border-b border-[#E5E7EB] pb-2">
                        <span className="text-[#6B7280]">Industry</span>
                        <span className="font-semibold text-[#111827]">{industry}</span>
                      </div>
                    )}
                    {companyType && (
                      <div className="flex justify-between border-b border-[#E5E7EB] pb-2">
                        <span className="text-[#6B7280]">Company Type</span>
                        <span className="font-semibold text-[#111827]">{companyType}</span>
                      </div>
                    )}
                    {founded && (
                      <div className="flex justify-between border-b border-[#E5E7EB] pb-2">
                        <span className="text-[#6B7280]">Founded</span>
                        <span className="font-semibold text-[#111827]">{founded}</span>
                      </div>
                    )}
                    {hq && (
                      <div className="flex justify-between border-b border-[#E5E7EB] pb-2">
                        <span className="text-[#6B7280]">Headquarters</span>
                        <span className="font-semibold text-[#111827]">{hq}</span>
                      </div>
                    )}
                    {ticker && (
                      <div className="flex justify-between border-b border-[#E5E7EB] pb-2">
                        <span className="text-[#6B7280]">Stock Ticker</span>
                        <span className="font-semibold text-[#111827]">{ticker}</span>
                      </div>
                    )}
                  </div>
                </Card>
              </div>
            )}

            {/* 3. Tab: Key Company Metrics & Financials */}
            {activeTab === 'financials' && (() => {
              const fin = financials;
              const metrics = [
                fin.market_cap && { label: 'Market Cap', val: fin.market_cap },
                fin.revenue && { label: 'Revenue', val: fin.revenue },
                fin.net_income && { label: 'Net Income', val: fin.net_income },
                fin.ebitda && { label: 'EBITDA', val: fin.ebitda },
                overview.employees && { label: 'Employees', val: typeof overview.employees === 'number' ? overview.employees.toLocaleString() : overview.employees },
                liMembers && { label: 'LinkedIn Members', val: typeof liMembers === 'number' ? liMembers.toLocaleString() : liMembers },
                founded && { label: 'Founded', val: founded },
                hq && { label: 'Headquarters', val: hq },
                industry && { label: 'Industry', val: industry },
                website && { label: 'Website', val: cleanDomain(website), link: ensureUrl(website) }
              ].filter(Boolean) as { label: string; val: any; link?: string }[];

              if (metrics.length === 0 && !fin.pe_ratio && !fin.eps && !fin.range_52w) {
                return (
                  <Card className="text-center py-8">
                    <p className="text-sm text-[#6B7280]">Financial data not available for this company.</p>
                  </Card>
                );
              }

              return (
                <div className="space-y-6">
                  <Card className="space-y-4">
                    <h3 className="text-base font-bold text-[#111827]">Key Company Metrics</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                      {metrics.map((m, idx) => (
                        <div key={idx} className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
                          <p className="text-[11px] font-medium text-[#6B7280] uppercase">{m.label}</p>
                          {m.link ? (
                            <a href={m.link} target="_blank" rel="noreferrer" className="text-base font-bold text-[#0EA5E9] hover:underline mt-0.5 block">
                              {m.val}
                            </a>
                          ) : (
                            <p className="text-base font-bold text-[#111827] mt-0.5">{m.val}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>

                  {(fin.pe_ratio || fin.eps || fin.range_52w) && (
                    <Card className="space-y-4">
                      <h3 className="text-base font-bold text-[#111827]">Detailed Financial Ratios</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        {fin.pe_ratio && (
                          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
                            <p className="text-[11px] font-medium text-[#6B7280] uppercase">P/E Ratio</p>
                            <p className="text-xl font-bold text-[#111827] mt-0.5">{fin.pe_ratio}</p>
                          </div>
                        )}
                        {fin.eps && (
                          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
                            <p className="text-[11px] font-medium text-[#6B7280] uppercase">EPS</p>
                            <p className="text-xl font-bold text-[#111827] mt-0.5">{fin.eps}</p>
                          </div>
                        )}
                        {fin.range_52w && (
                          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
                            <p className="text-[11px] font-medium text-[#6B7280] uppercase">52-Week Range</p>
                            <p className="text-lg font-bold text-[#111827] mt-0.5">{fin.range_52w}</p>
                          </div>
                        )}
                      </div>
                    </Card>
                  )}
                </div>
              );
            })()}

            {/* 4. Tab: Executive Cards / Leadership */}
            {activeTab === 'leadership' && (() => {
              if (!execs || execs.length === 0) {
                return (
                  <Card className="text-center py-8">
                    <p className="text-sm text-[#6B7280]">No executive information available.</p>
                  </Card>
                );
              }
              return (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-bold text-[#111827]">Key Decision Makers & Executive Leadership</h3>
                    <Badge variant="secondary">{execs.length} Executives</Badge>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {execs.map((exec: any, idx: number) => {
                      const execName = exec.name || exec.full_name || 'Executive';
                      const role = exec.role || exec.title || exec.designation || 'Decision Maker';
                      const dept = exec.department || exec.dept;
                      const photo = exec.photo || exec.avatar_url || exec.avatar || exec.image || exec.profile_photo;
                      const execLiUrl = exec.linkedin_url || exec.url || exec.linkedin_profile || exec.linkedin;
                      const email = exec.email || exec.work_email;
                      const phone = exec.phone || exec.work_phone || exec.phone_number;

                      return (
                        <Card key={idx} className="flex flex-col justify-between space-y-4 hover:border-[#0EA5E9]/50 transition-all">
                          <div className="flex items-start gap-4">
                            {photo ? (
                              <img
                                src={photo}
                                alt={execName}
                                className="w-12 h-12 rounded-full object-cover border border-[#E5E7EB] flex-shrink-0"
                                onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
                              />
                            ) : (
                              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#0EA5E9] to-indigo-600 text-white font-bold flex items-center justify-center text-lg flex-shrink-0">
                                {execName.charAt(0)}
                              </div>
                            )}

                            <div className="space-y-1 min-w-0 flex-1">
                              <h4 className="font-bold text-[#111827] text-base truncate">{execName}</h4>
                              <p className="text-xs text-[#0EA5E9] font-medium">{role}</p>
                              {dept && <p className="text-xs text-[#6B7280]">{dept}</p>}
                            </div>
                          </div>

                          {(() => {
                            const validEmail = cleanEmail(email);
                            const validPhone = formatPhone(phone);
                            const validLi = cleanLinkedIn(execLiUrl);

                            if (!validEmail && !validPhone && !validLi) return null;

                            return (
                              <div className="pt-3 border-t border-[#E5E7EB] space-y-2.5 text-xs">
                                {validEmail && (
                                  <div className="space-y-0.5">
                                    <span className="text-[#6B7280] font-medium block">Email</span>
                                    <a href={`mailto:${validEmail}`} className="font-semibold text-[#0EA5E9] hover:underline truncate block">
                                      {validEmail}
                                    </a>
                                  </div>
                                )}
                                {validPhone && (
                                  <div className="space-y-0.5">
                                    <span className="text-[#6B7280] font-medium block">Phone</span>
                                    <a href={`tel:${validPhone.replace(/\s+/g, '')}`} className="font-bold text-[#16A34A] hover:underline block">
                                      {validPhone}
                                    </a>
                                  </div>
                                )}
                                {validLi && (
                                  <div className="space-y-0.5">
                                    <span className="text-[#6B7280] font-medium block">LinkedIn</span>
                                    <a href={validLi.href} target="_blank" rel="noreferrer" className="font-semibold text-[#0EA5E9] hover:underline truncate block">
                                      {validLi.display}
                                    </a>
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </Card>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {activeTab === 'leadership' && employeesLoaded && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-[#111827]">People Working at This Company</h3>
                  <Badge variant="secondary">{employees.length} Employees</Badge>
                </div>
                {employees.length === 0 ? (
                  <Card className="text-center py-8">
                    <p className="text-sm text-[#6B7280]">No public employee profiles found.</p>
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {employees.map((employee: any, idx: number) => {
                      const employeeName = employee.full_name || employee.name || 'Employee';
                      const linkedin = cleanLinkedIn(employee.linkedin_url);
                      const email = cleanEmail(employee.work_email || employee.email);
                      const phone = formatPhone(employee.phone);
                      return (
                        <Card key={employee.linkedin_url || idx} className="space-y-4">
                          <div className="flex items-start gap-4">
                            {employee.profile_photo ? (
                              <img src={employee.profile_photo} alt={employeeName} className="w-12 h-12 rounded-full object-cover border border-[#E5E7EB] flex-shrink-0" />
                            ) : (
                              <div className="w-12 h-12 rounded-full bg-slate-100 text-[#0EA5E9] font-bold flex items-center justify-center text-lg flex-shrink-0">{employeeName.charAt(0)}</div>
                            )}
                            <div className="space-y-1 min-w-0 flex-1">
                              <h4 className="font-bold text-[#111827] text-base truncate">{employeeName}</h4>
                              {employee.designation && <p className="text-xs text-[#0EA5E9] font-medium">{employee.designation}</p>}
                              {employee.department && <p className="text-xs text-[#6B7280]">{employee.department}</p>}
                              {employee.location && <p className="text-xs text-[#6B7280]">{employee.location}</p>}
                            </div>
                          </div>
                          {linkedin && (
                            <div className="space-y-2 text-xs">
                              <a href={linkedin.href} target="_blank" rel="noreferrer" className="font-semibold text-[#0EA5E9] hover:underline inline-flex items-center gap-1">
                                <Linkedin className="w-3.5 h-3.5" /> LinkedIn
                              </a>
                              {email && <a href={`mailto:${email}`} className="font-semibold text-[#0EA5E9] hover:underline block">{email}</a>}
                              {phone && <a href={`tel:${phone.replace(/\s+/g, '')}`} className="font-semibold text-[#16A34A] hover:underline block">{phone}</a>}
                            </div>
                          )}
                          {!linkedin && (email || phone) && (
                            <div className="space-y-2 text-xs">
                              {email && <a href={`mailto:${email}`} className="font-semibold text-[#0EA5E9] hover:underline block">{email}</a>}
                              {phone && <a href={`tel:${phone.replace(/\s+/g, '')}`} className="font-semibold text-[#16A34A] hover:underline block">{phone}</a>}
                            </div>
                          )}
                        </Card>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Tab: Recent News */}
            {activeTab === 'news' && (
              <div className="space-y-4">
                {newsArticles.length > 0 ? (
                  newsArticles.map((n: any, idx: number) => (
                    <Card key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="space-y-1">
                        <h4 className="font-bold text-[#111827] text-sm">
                          {n.url ? (
                            <a href={n.url} target="_blank" rel="noreferrer" className="hover:text-[#0EA5E9]">
                              {n.title}
                            </a>
                          ) : (
                            n.title
                          )}
                        </h4>
                        <p className="text-xs text-[#6B7280]">
                          {[n.source || n.source_name, n.date || n.published_at].filter(Boolean).join(' • ')}
                        </p>
                        {n.summary && <p className="text-xs text-[#4B5563] mt-1">{n.summary}</p>}
                      </div>
                      <Badge variant="primary" size="sm">{n.relevance || 'Relevant'}</Badge>
                    </Card>
                  ))
                ) : (
                  <Card className="text-center py-8">
                    <p className="text-sm text-[#6B7280]">No recent news found.</p>
                  </Card>
                )}
              </div>
            )}

            {/* Tab: SEC Filings */}
            {activeTab === 'filings' && (() => {
              if (!filings || filings.length === 0) {
                return (
                  <Card className="text-center py-8">
                    <p className="text-sm text-[#6B7280]">This company does not publish SEC filings.</p>
                  </Card>
                );
              }
              return (
                <div className="space-y-4">
                  {filings.map((f: any, idx: number) => (
                    <Card key={idx} className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <FileText className="w-5 h-5 text-[#0EA5E9]" />
                        <div>
                          <h4 className="font-bold text-[#111827] text-sm">{f.title || f.form || 'Regulatory Filing'}</h4>
                          <p className="text-xs text-[#6B7280]">Date: {f.date || f.filed_at || 'N/A'}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" size="sm">{f.form_type || f.form || 'Filing'}</Badge>
                        {f.url && (
                          <a href={f.url} target="_blank" rel="noreferrer">
                            <Button variant="ghost" size="sm" icon={<ExternalLink className="w-3.5 h-3.5" />}>
                              View
                            </Button>
                          </a>
                        )}
                      </div>
                    </Card>
                  ))}
                </div>
              );
            })()}
          </div>
        );
      })() : (
        <Card className="text-center py-12 space-y-3">
          <Building2 className="w-12 h-12 text-[#0EA5E9] mx-auto opacity-40" />
          <h3 className="text-lg font-bold text-[#111827]">No Company Loaded</h3>
          <p className="text-sm text-[#6B7280] max-w-md mx-auto">
            Enter any company name, stock ticker, or domain above to generate a real-time AI company dossier.
          </p>
        </Card>
      )}
    </div>
  );
};

