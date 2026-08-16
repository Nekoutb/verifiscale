'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Briefcase } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { AUDIT_TYPE_LABELS, SECTORS, type AuditCase, type AuditType } from '@/lib/types';

const AUDIT_TYPES: AuditType[] = ['VGC', 'VP', 'CSP', 'CI', 'CT', 'EF'];
const REGIMES = ['REEL', 'SIMPLIFIE', 'LIBERATOIRE'] as const;
const RISKS = ['FAIBLE', 'MOYEN', 'ELEVE'] as const;

interface QuickCreatePayload {
  niu: string;
  raison_sociale: string;
  address: string | null;
  sector: string | null;
  sector_code: string;
  regime: string;
  tax_center: string | null;
  legal_form: string | null;
  capital_social: number | null;
  activity_start_date: string | null;
  rccm: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  audit_type: AuditType;
  starting_year: number;
  number_of_years: number;
  risk_level: string;
  avis_verification_date: string | null;
}

export function NewCaseModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const qc = useQueryClient();
  const setCurrentCase = useApp((s) => s.setCurrentCase);

  const thisYear = new Date().getFullYear();
  const [niu, setNiu] = useState('');
  const [raisonSociale, setRaisonSociale] = useState('');
  const [address, setAddress] = useState('');
  const [sector, setSector] = useState('');
  const [sectorCode, setSectorCode] = useState('DROIT_COMMUN');
  const [regime, setRegime] = useState<string>('REEL');
  const [taxCenter, setTaxCenter] = useState('');
  const [legalForm, setLegalForm] = useState('');
  const [capitalSocial, setCapitalSocial] = useState('');
  const [activityStartDate, setActivityStartDate] = useState('');
  const [rccm, setRccm] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [auditType, setAuditType] = useState<AuditType>('VGC');
  const [startingYear, setStartingYear] = useState(thisYear - 1);
  const [numberOfYears, setNumberOfYears] = useState(1);
  const [riskLevel, setRiskLevel] = useState<string>('MOYEN');
  const [avisDate, setAvisDate] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const reset = () => {
    setNiu(''); setRaisonSociale(''); setAddress(''); setSector(''); setSectorCode('DROIT_COMMUN');
    setRegime('REEL'); setTaxCenter(''); setLegalForm(''); setCapitalSocial('');
    setActivityStartDate(''); setRccm(''); setContactName(''); setContactPhone('');
    setContactEmail(''); setAuditType('VGC'); setStartingYear(thisYear - 1);
    setNumberOfYears(1); setRiskLevel('MOYEN'); setAvisDate(''); setErr(null);
  };

  const create = useMutation({
    mutationFn: (body: QuickCreatePayload) =>
      api<AuditCase>('/audit-cases/quick', { method: 'POST', body }),
    onSuccess: (newCase) => {
      qc.invalidateQueries({ queryKey: ['audit-cases'] });
      setCurrentCase(newCase);
      reset();
      onClose();
    },
    onError: (e) => setErr((e as Error).message),
  });

  if (!open) return null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    create.mutate({
      niu: niu.trim().toUpperCase(),
      raison_sociale: raisonSociale.trim(),
      address: address.trim() || null,
      sector: sector.trim() || null,
      sector_code: sectorCode,
      regime,
      tax_center: taxCenter.trim() || null,
      legal_form: legalForm.trim() || null,
      capital_social: capitalSocial.trim() ? parseFloat(capitalSocial.replace(/[\s,]/g, '')) : null,
      activity_start_date: activityStartDate || null,
      rccm: rccm.trim() || null,
      contact_name: contactName.trim() || null,
      contact_phone: contactPhone.trim() || null,
      contact_email: contactEmail.trim() || null,
      audit_type: auditType,
      starting_year: startingYear,
      number_of_years: numberOfYears,
      risk_level: riskLevel,
      avis_verification_date: avisDate || null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-slate-200">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-black/10 text-black flex items-center justify-center flex-shrink-0">
              <Briefcase className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-display text-lg font-bold text-slate-900">{t('newcase.title')}</h2>
              <p className="text-xs text-slate-500 mt-0.5">{t('newcase.subtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={submit} className="px-6 py-5 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Taxpayer */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
              {t('newcase.sectionAuditee')}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label htmlFor="niu">{t('newcase.niu')}</Label>
                <Input
                  id="niu"
                  required
                  value={niu}
                  onChange={(e) => setNiu(e.target.value)}
                  placeholder="M021400123456A"
                  className="font-mono uppercase"
                />
                <p className="text-[10px] text-slate-500 mt-1">{t('newcase.niuHint')}</p>
              </div>
              <div>
                <Label htmlFor="raisonSociale">{t('newcase.raisonSociale')}</Label>
                <Input
                  id="raisonSociale"
                  required
                  value={raisonSociale}
                  onChange={(e) => setRaisonSociale(e.target.value)}
                  placeholder="Raison sociale de l'entreprise vérifiée"
                />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="address">{t('newcase.address')}</Label>
                <Input
                  id="address"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="BP 1234, Douala — Akwa"
                />
              </div>
              <div>
                <Label htmlFor="sectorCode">{t('newcase.sectorCode')}</Label>
                <select
                  id="sectorCode"
                  value={sectorCode}
                  onChange={(e) => setSectorCode(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-[#A3A3A3] bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:border-black"
                >
                  {SECTORS.map((s) => (
                    <option key={s.code} value={s.code}>{s.fr}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="sector">{t('newcase.sector')}</Label>
                <Input
                  id="sector"
                  value={sector}
                  onChange={(e) => setSector(e.target.value)}
                  placeholder="Confection / Prêt-à-porter"
                />
              </div>
              <div>
                <Label htmlFor="regime">{t('newcase.regime')}</Label>
                <select
                  id="regime"
                  value={regime}
                  onChange={(e) => setRegime(e.target.value)}
                  className="w-full h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
                >
                  {REGIMES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="taxCenter">{t('newcase.taxCenter')}</Label>
                <Input
                  id="taxCenter"
                  value={taxCenter}
                  onChange={(e) => setTaxCenter(e.target.value)}
                  placeholder={t('newcase.taxCenterHint')}
                />
              </div>
              <div>
                <Label htmlFor="legalForm">{t('newcase.legalForm')}</Label>
                <Input
                  id="legalForm"
                  value={legalForm}
                  onChange={(e) => setLegalForm(e.target.value)}
                  placeholder="SARL · SA · SAS · EI"
                />
              </div>
              <div>
                <Label htmlFor="capitalSocial">{t('newcase.capitalSocial')}</Label>
                <Input
                  id="capitalSocial"
                  value={capitalSocial}
                  onChange={(e) => setCapitalSocial(e.target.value)}
                  placeholder="10 000 000"
                  inputMode="numeric"
                />
              </div>
              <div>
                <Label htmlFor="activityStartDate">{t('newcase.activityStartDate')}</Label>
                <Input
                  id="activityStartDate"
                  type="date"
                  value={activityStartDate}
                  onChange={(e) => setActivityStartDate(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="rccm">{t('newcase.rccm')}</Label>
                <Input
                  id="rccm"
                  value={rccm}
                  onChange={(e) => setRccm(e.target.value)}
                  placeholder="RC/DLA/2020/B/1234"
                />
              </div>
            </div>
          </section>

          {/* Contact */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
              {t('newcase.sectionContact')}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label htmlFor="contactName">{t('newcase.contactName')}</Label>
                <Input
                  id="contactName"
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  placeholder="Nom et prénom du contact"
                />
              </div>
              <div>
                <Label htmlFor="contactPhone">{t('newcase.contactPhone')}</Label>
                <Input
                  id="contactPhone"
                  type="tel"
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  placeholder="+237 6XX XX XX XX"
                />
              </div>
              <div>
                <Label htmlFor="contactEmail">{t('newcase.contactEmail')}</Label>
                <Input
                  id="contactEmail"
                  type="email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  placeholder="contact@entreprise.cm"
                />
              </div>
            </div>
          </section>

          {/* Scope */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
              {t('newcase.sectionScope')}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label htmlFor="auditType">{t('newcase.auditType')}</Label>
                <select
                  id="auditType"
                  value={auditType}
                  onChange={(e) => setAuditType(e.target.value as AuditType)}
                  className="w-full h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
                >
                  {AUDIT_TYPES.map((tt) => (
                    <option key={tt} value={tt}>
                      {AUDIT_TYPE_LABELS[tt].short} — {AUDIT_TYPE_LABELS[tt].full} ({AUDIT_TYPE_LABELS[tt].ref})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="startingYear">{t('newcase.startingYear')}</Label>
                <Input
                  id="startingYear"
                  type="number"
                  required
                  min={2000}
                  max={2099}
                  value={startingYear}
                  onChange={(e) => setStartingYear(parseInt(e.target.value, 10) || thisYear)}
                />
              </div>
              <div>
                <Label htmlFor="numberOfYears">{t('newcase.numberOfYears')}</Label>
                <Input
                  id="numberOfYears"
                  type="number"
                  required
                  min={1}
                  max={10}
                  value={numberOfYears}
                  onChange={(e) => setNumberOfYears(parseInt(e.target.value, 10) || 1)}
                />
              </div>
              <div>
                <Label htmlFor="riskLevel">{t('newcase.riskLevel')}</Label>
                <select
                  id="riskLevel"
                  value={riskLevel}
                  onChange={(e) => setRiskLevel(e.target.value)}
                  className="w-full h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
                >
                  {RISKS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          {/* LPF — optional avis date */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
              {t('newcase.sectionLPF')}
            </h3>
            <div>
              <Label htmlFor="avisDate">{t('newcase.avisDate')}</Label>
              <Input
                id="avisDate"
                type="date"
                value={avisDate}
                onChange={(e) => setAvisDate(e.target.value)}
              />
              <p className="text-[10px] text-slate-500 mt-1">{t('newcase.avisDateHint')}</p>
            </div>
          </section>

          {err && (
            <div className="text-sm text-black font-bold underline decoration-2 bg-white border-2 border-black rounded-lg px-3 py-2">
              {err}
            </div>
          )}
        </form>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-slate-200 bg-slate-50">
          <Button type="button" variant="outline" onClick={onClose}>{t('newcase.cancel')}</Button>
          <Button type="submit" onClick={submit} disabled={create.isPending}>
            {create.isPending ? t('newcase.submitting') : t('newcase.submit')}
          </Button>
        </div>
      </div>
    </div>
  );
}
