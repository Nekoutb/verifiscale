# FiscAudit Pro — Tax Controls Design

**Status**: Design v1.0 · Last updated 2026-05-17
**Scope**: Full inventory of fiscal controls executable by FiscAudit Pro when the auditee provides: monthly tax returns (PDF), proof of payment, general ledger (GL), trial balance (TB), payroll register.
**Sources**: Code Général des Impôts du Cameroun éd. 2025 · LPF · SYSCOHADA Révisé.

---

## 1. Tax universe — what we audit

| Tax / Contribution | Periodicity | Filing deadline | GL accounts | CGI ref |
|---|---|---|---|---|
| **TVA** (Value Added Tax) | Monthly | 15 of N+1 | 4431 (collectée), 4452 (déd. BS), 4456 (déd. immo) | art. 125-149 |
| **IRPP/RAS Salaires** (PAYE) | Monthly | 15 of N+1 | 4471 | art. 30-36, 81 |
| **CNPS** (Social security) | Monthly | 15 of N+1 | 4311 | Code de prévoyance sociale |
| **TSR** (Special tax on services to non-residents) | Monthly | 15 of N+1 | 4475 / 622 / 6231 | art. 225 |
| **Précompte loyers** | Monthly | 15 of N+1 | 4473 / 622 | art. 92-93 |
| **Précompte achats** | Monthly | 15 of N+1 | 4476 | art. 21 bis |
| **IRCM** (Rev. mobiliers — dividends, interest) | Monthly | 15 of N+1 | 4474 | art. 70 |
| **Droit de timbre** | At occurrence | Variable | 4477 / 6478 | art. 358-557 |
| **Acomptes IS** | Quarterly | 15 of month following Q | 4445 | art. 21 |
| **IS** (Corporate income tax) | Annual | 15 March of N+1 | 4441, 891 | art. 17 + 17 bis |
| **Patente** (business license) | Annual | 28 February | 6411 | art. C 1-21 |
| **Taxe foncière** (property tax) | Annual | 30 June | 6412 | art. 577-585 |
| **CFC** (Crédit Foncier) | Monthly | 15 of N+1 | 4312 / 6414 | Loi 77/10 |
| **FNE** (Fonds National Emploi) | Monthly | 15 of N+1 | 4313 / 6415 | Loi 90/048 |
| **RAV** (Redevance audiovisuelle) | Monthly | 15 of N+1 | 4317 | Loi des finances |

---

## 2. Universal audit pattern — applied to each tax

For **every** tax above, FiscAudit Pro runs the same 8-step audit grid. This is the canonical pattern that drives the control catalog.

| # | Check | Risk addressed | Output if fails |
|---|---|---|---|
| 1 | **Existence** — return filed for every required period | Non-déclaration | BLOCKING — sanction CGI art. M 1 (25 % + 1.5%/mois) |
| 2 | **Timeliness of filing** — filed ≤ legal deadline | Retard de dépôt | HIGH — 25 % majoration + intérêt 1.5 %/mois |
| 3 | **Existence of payment proof** — quittance for every return | Défaut de paiement | BLOCKING — 100 % majoration LPF M 2 |
| 4 | **Timeliness of payment** — paid ≤ legal deadline | Retard de paiement | HIGH — intérêt 1.5 %/mois plafonné 50 % |
| 5 | **Filed = Paid** — declared amount matches payment | Sous-paiement | HIGH — différentiel exigible |
| 6 | **Declared ↔ GL reconciliation** — return matches book accounts | Sous-déclaration vs comptes | HIGH — redressement = différentiel |
| 7 | **Recalculation** — base × rate = declared amount | Erreur de calcul | MEDIUM/HIGH — différentiel |
| 8 | **Completeness** — no taxable event omitted from return | Omission volontaire | HIGH — redressement + majoration mauvaise foi 100 % |

That's **120 controls** generated systematically (8 × 15 taxes). The detailed catalog below applies this pattern, plus tax-specific deep-dive controls (exclusions, prorata, regimes, plafonds, etc.).

---

## 3. Required data sources from the auditee

| Document | Format | Use | Module |
|---|---|---|---|
| Balance générale 6 colonnes | xlsx/csv | TB-level reconciliation, aggregates | ✅ implemented |
| Grand-livre (GL) ligne par ligne | xlsx/csv/FEC | Line-level recoupement, sampling | ✅ implemented |
| **Déclarations mensuelles (DSF-M)** | **PDF** | All monthly tax recoupements | 🆕 to build |
| **Quittances / preuves de paiement** | **PDF / image** | Existence + timeliness of payment | 🆕 to build |
| **Déclaration annuelle DSF** | PDF | IS recoupement + financial statements | 🆕 to build |
| **DIPE** (état nominatif annuel) | PDF/xlsx | Salaries recoupement | 🆕 to build |
| **Livre de paie** (payroll register) | xlsx | IRPP + CNPS base verification | 🆕 to build |
| **Avis d'imposition Patente** | PDF | Patente reconciliation | 🆕 to build |
| **Conventions** (contrats, baux, prêts) | PDF | Précomptes loyers, TSR, intérêts CC | 🆕 to build |
| **Factures fournisseurs** (sample) | PDF | Fond et forme, FCA check | 🆕 to build |

**PDF parsing strategy** — Claude Vision API is used for all PDF extraction. Each tax return type gets a small prompt that returns a structured JSON (period, taxes due, taxes paid, base amounts). Cached per file hash.

---

## 4. Detailed control catalog by category

### 4.A — SYSCOHADA Intégrité (16 controls — 9 implemented)
*Already in catalog. See `packages/shared/controls-catalog.json`.*

### 4.B — SYSCOHADA Évaluation & SIG (14 controls — 3 implemented)
*Already in catalog.*

### 4.C — IS / Impôt sur les Sociétés (19 → expanded to 22)

Already in catalog: C1-C19. Additions:

| Code | Title | Method | Severity | Status |
|---|---|---|---|---|
| C20 | Acomptes IS trimestriels = 1/4 × IS N-1 | Recalcul + recoupement paiements | HIGH | 🆕 |
| C21 | Imputation correcte des crédits d'impôts (TSR subis, retenues à la source) | Recoupement annexes DSF | MEDIUM | 🆕 |
| C22 | Cohérence DSF annuel vs reconstitution TB | Recoupement totaux ligne-à-ligne | HIGH | 🆕 |

### 4.D — TVA (16 → expanded to 22)

Existing D1-D16 in catalog + the following detail:

| Code | Title | Data source | Severity |
|---|---|---|---|
| D1 | Existence — 12 déclarations TVA mensuelles | DSF-M PDFs | BLOCKING |
| D2 | Délai dépôt ≤ 15 du mois suivant | DSF-M métadonnées | HIGH |
| D3 | Existence quittance paiement pour chaque déclaration | Quittances PDFs | BLOCKING |
| D4 | Délai paiement ≤ 15 du mois suivant | Quittances dates | HIGH |
| D5 | Montant déclaré TVA nette = montant payé | DSF-M × Quittances | HIGH |
| D6 | TVA collectée déclarée = mouvements crédit GL 4431 | DSF-M × GL | HIGH |
| D7 | TVA déductible BS déclarée = mouvements débit GL 4452 | DSF-M × GL | HIGH |
| D8 | TVA déductible immo déclarée = mouvements débit GL 4456 | DSF-M × GL | HIGH |
| D9 | CA HT déclaré TVA = CA HT comptes 70 (mensuel/annuel) | DSF-M × TB | HIGH |
| D10 | Recalcul TVA collectée = CA HT × 17.5 % (par taux) | DSF-M base | MEDIUM |
| D11 | Exclusions droit à déduction (CGI art. 144 : véhicules tourisme, frais bouche/séjour, dons) | GL sample + DSF | HIGH |
| D12 | Prorata de déduction si activité mixte | DSF + CA répartition | MEDIUM |
| D13 | Autoliquidation TVA sur services importés (reverse charge) | GL cl. 622/6231 sur fournisseurs étrangers | HIGH |
| D14 | Crédit TVA reporté — Solde 4431 fin N-1 = report ouvert N | TB ouverture vs DSF janvier | HIGH |
| D15 | TVA sur opérations en devises — taux de change officiel | GL en devises + DSF | MEDIUM |
| D16 | Régularisation TVA sur biens cédés < 5 ans | Cessions immo + GL 4456 | HIGH |
| D17 | Mentions obligatoires factures de vente (NIU client + montants séparés) | Échantillon factures ventes | MEDIUM |
| D18 | Notes de débit/avoir traçables et numérotées | GL cl. 419 / 4119 + factures | MEDIUM |
| D19 | TVA sur acomptes encaissés — exigibilité immédiate | GL cl. 419 + DSF | MEDIUM |
| D20 | Synthèse — écart TVA non déclarée / sous-déclarée | Agrégation D5-D9 | HIGH |
| D21 | Vérification chronologie : déclarations dans l'ordre | DSF dates | LOW |
| D22 | Crédit TVA accumulé > 6 mois — demande de remboursement à initier | TB solde 4431 | INFO |

### 4.E — IRPP / Retenues à la source / TSR (10 → expanded to 18)

| Code | Title | Data source | Severity |
|---|---|---|---|
| E1 | Existence — 12 déclarations IRPP retenue salaires | DSF-M PDFs | BLOCKING |
| E2 | Délai dépôt + paiement IRPP salaires | DSF + Quittances | HIGH |
| E3 | Réconciliation IRPP déclaré = mouvements crédit GL 4471 | DSF × GL | HIGH |
| E4 | Application correcte du barème IRPP progressif (0/10/15/25/35 %) | Livre de paie échantillon | HIGH |
| E5 | Abattement forfaitaire 30 % + CAC additionnel 10 % | Livre de paie | MEDIUM |
| E6 | Existence — 12 déclarations CNPS | DSF-CNPS PDFs | BLOCKING |
| E7 | Délai dépôt + paiement CNPS | DSF-CNPS + Quittances | HIGH |
| E8 | Réconciliation CNPS déclaré = GL 4311 mouvements | DSF × GL | HIGH |
| E9 | Calcul CNPS : 4.2 % AF (patronal) + 4.9 % PVID (patronal+salarial) sur masse plafonnée | Livre de paie | HIGH |
| E10 | Existence déclarations TSR (services à non-résidents) | DSF-M + GL cl. 622/6231 | HIGH |
| E11 | Taux TSR : 15 % services / 7.5 % matériel / 2.5 % commission publique | GL + contrats | HIGH |
| E12 | Réconciliation TSR déclaré = GL 4475 mouvements | DSF × GL | HIGH |
| E13 | Précompte loyers : 5 % (bailleurs particuliers) / 10 % (autres) | GL cl. 6232/622 + baux | MEDIUM |
| E14 | Précompte achats : 1 % / 5 % / 10 % selon nature et régime fournisseur | GL achats + factures | MEDIUM |
| E15 | Application conventions fiscales (DTA France-Cameroun, etc.) | Contrats + DSF | MEDIUM |
| E16 | Crédit d'impôt 10 % pour personnel expatrié | Livre de paie | LOW |
| E17 | CFC 1 % des salaires bruts — déclaration + paiement | DSF + GL 6414 | HIGH |
| E18 | FNE 1 % des salaires bruts — déclaration + paiement | DSF + GL 6415 | HIGH |

### 4.F — Factures fournisseurs : fond et forme (10 → expanded to 15)

| Code | Title | Method | Severity |
|---|---|---|---|
| F1 | Présence NIU fournisseur sur la facture | OCR factures | HIGH |
| F2 | Validité NIU fournisseur via FCA (Fichier des Contribuables Actifs) | API DGI FCA | HIGH |
| F3 | Adresse fournisseur complète (rue, ville, BP) | OCR | MEDIUM |
| F4 | Régime fiscal fournisseur indiqué (réel/simplifié/libératoire) | OCR | MEDIUM |
| F5 | Numéro de facture séquentiel et unique | OCR + cross-check GL | HIGH |
| F6 | Date facture cohérente avec la période d'audit | OCR | HIGH |
| F7 | Désignation des biens/services suffisamment précise | OCR + LLM judgment | MEDIUM |
| F8 | Quantités, prix unitaires HT et totaux présents | OCR | HIGH |
| F9 | Montants HT / TVA / TTC clairement séparés | OCR | HIGH |
| F10 | Mention « facture » + numéro visible | OCR | LOW |
| F11 | Cohérence imputation comptable vs nature de la charge | LLM matching | MEDIUM |
| F12 | Existence d'une pièce justificative pour chaque écriture | GL × Datasets factures | HIGH |
| F13 | Plafond paiement en espèces ≤ 100 000 FCFA — CGI art. 7-A-3 | GL cl. 571 + factures | HIGH |
| F14 | Mentions importation (DAU, transitaire, valeur en douane) pour factures étrangères | OCR | MEDIUM |
| F15 | Factures > 1 M FCFA — vérification documentation contractuelle | GL filter + contrats | LOW |

### 4.G — Cross-controls / cohérence (9 → expanded to 14)

| Code | Title | Data sources crossed | Severity |
|---|---|---|---|
| G1 | Base salaires : CNPS = IRPP = CFC = FNE = DIPE | DSF-CNPS, DSF-IRPP, DIPE | HIGH |
| G2 | CA déclaré TVA annuel ≡ CA comptes 70 annuel | 12 DSF-M × TB | HIGH |
| G3 | Achats déclarés TVA ≡ Achats GL cl. 60/61 | 12 DSF-M × GL | HIGH |
| G4 | Salaires comptabilisés cl. 66 = total DIPE | TB × DIPE | HIGH |
| G5 | Stocks SF N-1 = SI N (rollforward inter-exercices) | TB N + TB N-1 | HIGH |
| G6 | Capitaux propres : KP N = KP N-1 + Résultat N − Dividendes N | TB × DSF | HIGH |
| G7 | Coefficient marge brute — comparaison sectorielle | TB × référentiel | LOW |
| G8 | Ratio frais financiers / CA > 5 % → alerte | TB | LOW |
| G9 | Ratio charges personnel / CA — alerte si > seuil sectoriel | TB | LOW |
| G10 | Taux d'effort fiscal = total impôts / CA — alerte si écart sectoriel | TB + DSF | LOW |
| G11 | Acomptes IS payés ≡ acomptes calculés (1/4 × IS N-1) | DSF + Quittances | HIGH |
| G12 | Dividendes payés → IRCM retenu et déclaré | GL 6587 + DSF IRCM | HIGH |
| G13 | Loyers payés → précompte appliqué | GL 622/6232 + DSF | MEDIUM |
| G14 | Services étrangers cl. 622/6231 → TSR appliqué | GL + DSF | HIGH |

### 4.H — Procédure LPF (9 controls — 9 implemented ✅)
*Already implemented. See `apps/api/app/controls/category_h.py`.*

### 4.I — Autres impôts annuels (NEW — 8 controls)

| Code | Title | Method | Severity |
|---|---|---|---|
| I1 | Patente — existence avis + paiement | DSF Patente + Quittance | BLOCKING |
| I2 | Patente — recalcul : CA × taux selon classe d'activité | DSF + CGI annexe | HIGH |
| I3 | Taxe foncière — existence pour terrains/bâtiments (cl. 21, 23) | TB + Avis foncier | HIGH |
| I4 | Taxe foncière — recalcul : 0.1 % valeur administrative | Avis × TB | MEDIUM |
| I5 | RAV (Redevance audiovisuelle) — sur salaires | Livre paie + DSF | MEDIUM |
| I6 | Acomptes IS trimestriels — 4 paiements effectués | DSF-M + Quittances | HIGH |
| I7 | Crédit foncier 1 % salariés (CFC employé) — déclaration | Livre paie + DSF | MEDIUM |
| I8 | Droit de timbre sur formalités — exhaustivité | GL cl. 6478 / 4477 | LOW |

---

## 5. Control catalog summary (after redesign)

| Cat | Name | Controls | Implemented |
|---|---|---:|---:|
| A | SYSCOHADA Intégrité | 16 | 9 |
| B | SYSCOHADA Évaluation & SIG | 14 | 3 |
| C | Impôt sur les Sociétés | 22 | 8 |
| **D** | **TVA** | **22** | **0** |
| **E** | **IRPP / Retenues / TSR** | **18** | **0** |
| **F** | **Factures fournisseurs** | **15** | **0** |
| **G** | **Cross-controls** | **14** | **0** |
| H | Procédure LPF | 9 | 9 |
| **I** | **Autres impôts annuels** | **8** | **0** |
| | **TOTAL** | **138** | **29 (21 %)** |

---

## 6. Data model additions required

### 6.1 New SQLAlchemy models

**`MonthlyReturn`** — one row per declared period × tax type
```python
class TaxType(str, Enum):
    TVA, IRPP_SALAIRES, CNPS, TSR, PRECOMPTE_LOYERS,
    PRECOMPTE_ACHATS, IRCM, ACOMPTE_IS, CFC, FNE, RAV,
    DROIT_TIMBRE, PATENTE_ANNUEL, FONCIER_ANNUEL, IS_ANNUEL

class ReturnStatus(str, Enum):
    PENDING, FILED, PAID, AMENDED, LITIGATION

class MonthlyReturn:
    id: UUID
    audit_case_id: FK
    tax_type: TaxType
    period_year: int            # 2024
    period_month: int | None    # 1-12 (null for annual taxes)
    period_quarter: int | None  # 1-4 (for acomptes IS)
    filing_date: date | None
    filing_deadline: date       # computed: period_end + 15 days
    declared_amount: Decimal    # tax payable as filed
    base_amount: Decimal        # taxable base (e.g. CA HT for TVA)
    source_dataset_id: FK → datasets  # the PDF
    extracted_data: JSONB       # raw Claude Vision extraction
    status: ReturnStatus
    notes: str | None
    created_at, updated_at
```

**`PaymentProof`** — one row per quittance/receipt
```python
class PaymentMethod(str, Enum):
    VIREMENT, ESPECES, CHEQUE, MOBILE_MONEY, COMPENSATION

class PaymentProof:
    id: UUID
    monthly_return_id: FK
    payment_date: date
    amount_paid: Decimal
    reference: str              # numéro de quittance / bordereau
    method: PaymentMethod
    bank: str | None
    source_dataset_id: FK → datasets  # the PDF receipt
    extracted_data: JSONB
    created_at
```

### 6.2 New DatasetKind values

```python
class DatasetKind(str, Enum):
    # ... existing ...
    MONTHLY_RETURN_TVA = "MONTHLY_RETURN_TVA"
    MONTHLY_RETURN_IRPP = "MONTHLY_RETURN_IRPP"
    MONTHLY_RETURN_CNPS = "MONTHLY_RETURN_CNPS"
    MONTHLY_RETURN_OTHER = "MONTHLY_RETURN_OTHER"
    PAYMENT_PROOF = "PAYMENT_PROOF"
    ANNUAL_RETURN_DSF = "ANNUAL_RETURN_DSF"
    PAYROLL_REGISTER = "PAYROLL_REGISTER"
    DIPE = "DIPE"
    PATENTE_AVIS = "PATENTE_AVIS"
    FONCIER_AVIS = "FONCIER_AVIS"
    CONTRACT = "CONTRACT"
```

### 6.3 PDF parsing pipeline

```
PDF upload → store as Dataset
   ↓
Background job: Claude Vision extraction
   ↓
Parse result → MonthlyReturn or PaymentProof row
   ↓
Available for controls engine
```

The Vision prompt per tax type is a small JSON schema instructing the model:
> "Extract: period (YYYY-MM), tax type, declared amount, base amount, filing date if visible. Return strict JSON only."

---

## 7. UI additions required

| Page | Purpose | Priority |
|---|---|---|
| `/dossiers/[id]` — new tab **"Déclarations mensuelles"** | Grid 12 mois × N taxes — green if filed+paid, red if missing, amber if late | **High** |
| `/dossiers/[id]` — new tab **"Paiements"** | Quittances browser with PDF preview, amount, date | **High** |
| Upload zones for each new DatasetKind in the dossier page | Drag-drop PDFs for each tax | **High** |
| `/declarations-mensuelles` (sidebar already wired) | Cross-dossier monthly returns dashboard | Medium |
| Audit case overview KPIs: "X/Y returns filed, Z FCFA total tax" | At-a-glance compliance | Medium |

---

## 8. Engineering roadmap — concrete next steps

### Sprint 1 (Foundation — ~3 days)
1. ✅ Write this design doc (`docs/tax-controls-design.md`)
2. ✅ Update `packages/shared/controls-catalog.json` with all 138 controls
3. 🚧 Add `MonthlyReturn`, `PaymentProof`, `TaxType`, `ReturnStatus`, `PaymentMethod` to models
4. 🚧 Extend `DatasetKind` enum with new return/proof kinds
5. 🚧 Alembic migration `0003_monthly_returns.py`

### Sprint 2 (PDF parsing — ~1 week)
6. Build `apps/api/app/parsers/pdf_returns.py` — Claude Vision wrapper with per-tax prompts
7. Add Anthropic SDK call with prompt caching keyed on file SHA-256
8. Background job (FastAPI BackgroundTasks for now, Celery later) to parse PDFs after upload
9. Add `POST /monthly-returns` admin endpoint to manually correct extracted values

### Sprint 3 (Category D — TVA — ~5 days)
10. Implement `apps/api/app/controls/category_d.py` with all D1-D22
11. Each control follows the universal pattern (existence / délai / réconciliation)
12. Wire into registry
13. Add Category D card to dossier page

### Sprint 4 (Category E — IRPP/RAS/TSR — ~5 days)
14. Implement `category_e.py` with E1-E18
15. Add payroll register parser (`parsers/payroll.py`)
16. Wire into registry

### Sprint 5 (Categories F + G + I — ~2 weeks)
17. Category F — Claude Vision invoice OCR + FCA API stub
18. Category G — cross-source coherence checks
19. Category I — annual taxes (Patente, Foncier, RAV)

### Sprint 6 (UI — ~1 week)
20. New "Déclarations mensuelles" tab in dossier page: 12-month × N-tax grid
21. PDF preview pane (PDF.js)
22. Bulk upload zone — drop a folder of PDFs, system classifies them
23. Calendar view showing all upcoming/past deadlines per dossier

### Sprint 7 (Production hardening — ~2 weeks)
24. Replace JWT with Keycloak SSO
25. Row-level security per brigade
26. Audit log signing (HMAC already scaffolded)
27. Backup / restore procedures
28. Pen test prep

---

## 9. Out of scope for v1

- Online filing integration with DGI portal (no public API exists yet)
- Automated remediation letters (Phase 9)
- Mobile app
- Multi-tenant DGI deployment (single-instance for now)
- Foreign GAAP support (SYSCOHADA only)

---

## 10. Risks & assumptions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Claude Vision PDF extraction may be imperfect for hand-stamped/scanned quittances | Manual correction UI; confidence threshold; fall back to admin entry |
| 2 | DSF-M format may vary year to year | Prompt versioning per fiscal year; flag unexpected fields for review |
| 3 | Tax rate changes (Loi de Finances annuelle) | All rates centralized in `tax_params.py` — single annual update |
| 4 | Auditees may submit incomplete data | UI surfaces missing pieces clearly; controls degrade gracefully (INFO finding instead of crash) |
| 5 | Bilingual variations in column headers and PDFs | French/English tolerant matching already in TB/GL parsers; same approach for returns |
