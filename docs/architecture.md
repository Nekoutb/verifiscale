# Architecture — FiscAudit Pro

## Vue d'ensemble

FiscAudit Pro est une plateforme SaaS multi-tenant (multi-brigade DGI) qui assiste les auditeurs fiscaux dans l'exécution de leurs contrôles sur la comptabilité des contribuables.

## Choix techniques majeurs

### Pourquoi Python pour le backend
- L'écosystème data (pandas, polars) est imbattable pour l'analyse de gros volumes comptables (un grand-livre peut faire 500 000 lignes).
- Les bibliothèques de parsing PDF/OCR (pdfplumber, layoutLM) sont matures pour les factures.
- Anthropic SDK Python pour l'intégration Claude Vision.

### Pourquoi Next.js pour le frontend
- Server Components et streaming pour afficher rapidement les KPI puis charger les tables lourdes.
- App Router pour la composition de layouts (sidebar + topbar persistants).
- Excellent DX avec TypeScript et Tailwind.

### Pourquoi PostgreSQL
- ACID strict — indispensable pour la traçabilité fiscale.
- JSONB pour le stockage flexible des évidences de contrôle.
- Partitionnement natif par `audit_case_id` pour les tables de lignes (TB, GL).
- Row-level security pour cloisonner les brigades.

### Pourquoi MinIO
- API S3-compatible mais déployable on-premise (souveraineté des données fiscales).
- Versioning natif pour conserver les fichiers originaux remis par le contribuable.
- Performant pour les gros fichiers (FEC, scans de factures).

## Flux de données : un audit type

```
1. Auditeur crée un dossier (taxpayer + période + brigade)
2. Auditeur dépose la balance 6 colonnes (Excel)
   └─> /datasets POST -> stocke MinIO + parse pandas + insère trial_balance_lines
3. Auditeur dépose le grand-livre
   └─> idem + groupage par pièce -> journal_entries / journal_entry_lines
4. Auditeur clique « Lancer les contrôles SYSCOHADA Catégorie A »
   └─> /control-runs POST
       └─> ControlContext chargé depuis la DB
       └─> chaque contrôle (A1, A2, A3, A5, A8, A9, A13, A13b, A13c) émet 0..n Finding
       └─> findings persistés avec evidence JSONB
5. Frontend affiche les findings groupés par sévérité avec impact estimé
```

## Modèle de données

### Tables principales

- **brigades** — Unités DGI (DGE, CIME, CDI)
- **users** — Comptes auditeurs (RBAC: AUDITEUR / SUPERVISEUR / CHEF_BRIGADE / ADMIN)
- **taxpayers** — Contribuables sous audit (NIU unique)
- **audit_cases** — Une mission = un contribuable × un exercice fiscal
- **datasets** — Fichiers uploadés (TB, GL, factures, déclarations…)
- **trial_balance_lines** — Lignes de balance 6 colonnes parsées
- **journal_entries / journal_entry_lines** — Écritures comptables parsées
- **control_runs** — Exécution d'un batch de contrôles
- **control_findings** — Anomalies détectées (avec evidence JSONB)
- **audit_logs** — Piste d'audit immuable signée HMAC

### Relations clés

```
brigades 1───* users
brigades 1───* audit_cases
taxpayers 1───* audit_cases
audit_cases 1───* datasets
audit_cases 1───* control_runs
datasets 1───* trial_balance_lines
datasets 1───* journal_entries
journal_entries 1───* journal_entry_lines
control_runs 1───* control_findings
```

## Moteur de contrôles

Chaque contrôle est une fonction pure `Control(ctx: ControlContext) -> list[Finding]`.

### Caractéristiques
- **Pas de couplage** entre contrôles : chacun ne lit que ses données dans le contexte.
- **Composables** : on peut exécuter A1 seul, ou tout A, ou un mix A+B+C…
- **Testables en isolation** : injecter un ControlContext mocké, vérifier les findings.
- **Idempotents** : même input → même findings.
- **Référencent toujours un article** : `legal_reference` obligatoire sur chaque Finding.

### Ajouter un contrôle

```python
# apps/api/app/controls/category_b.py
from app.controls.base import Finding, ControlContext
from app.models.control_run import ControlSeverity

def b1_stock_method(ctx: ControlContext) -> list[Finding]:
    """B1 — Stocks valorisés en PEPS ou CMP uniquement (art. 44)."""
    # Logique de détection
    return []
```

Puis l'enregistrer dans le registre `CATEGORY_B_CONTROLS` et brancher la catégorie dans le router `/control-runs`.

## Sécurité

| Aspect              | Implémentation actuelle      | Cible production              |
|---------------------|------------------------------|-------------------------------|
| Auth                | JWT custom + bcrypt          | Keycloak + MFA obligatoire    |
| Sessions            | Token 4h en localStorage     | httpOnly cookies + refresh    |
| RBAC                | Decorator `require_role`     | + ABAC pour règles fines      |
| Audit log           | Table `audit_logs` HMAC      | Append-only + export quotidien|
| Encryption at rest  | Postgres natif               | + LUKS sur disques + KMS MinIO|
| Transport           | HTTP en dev                  | TLS 1.3 obligatoire           |
| Multi-tenancy       | Filtre dans queries          | Row-level security Postgres   |

## Intégrations DGI futures

Trois connecteurs API critiques (à négocier avec DGI) :

1. **API FCA (Fichier des Contribuables Actifs)** — vérifier au jour d'une facture qu'un NIU est actif et en régime réel (CGI art. 143 + 8 bis (2))
2. **API Facturation électronique DGI** — valider qu'une facture est dans le système officiel (LPF art. L 8 bis)
3. **API DSV (Déclaration Sommaire Virtuelle)** — pour rapprocher la TVA à l'import

Module prévu : `apps/api/app/services/dgi/` avec cache Redis 24 h pour limiter les appels.

## Observabilité (production)

- **Logs** : structured JSON via stdlib `logging` → collectés par Vector/Loki
- **Métriques** : Prometheus endpoint `/metrics`
- **Traces** : OpenTelemetry FastAPI middleware + Jaeger
- **Erreurs** : Sentry SDK
- **Uptime** : alertes Grafana sur SLA 99,5 %

## Performance

| Opération                      | Cible     | Stratégie                                   |
|-------------------------------|-----------|---------------------------------------------|
| Upload balance 10 000 comptes | < 5 s     | Parsing pandas + bulk insert SQLAlchemy     |
| Upload GL 500 000 lignes      | < 60 s    | Streaming + Celery worker                   |
| Run Catégorie A complet       | < 10 s    | Index sur `dataset_id`, agrégations en SQL  |
| Affichage table 100k lignes   | fluide    | TanStack Table virtualization               |

## Roadmap technique

- [ ] Worker Celery pour les jobs > 30 s (parsing volumineux, génération PDF)
- [ ] Tests Playwright e2e des parcours critiques
- [ ] Suite pytest sur le moteur de contrôles (test cases avec balances déséquilibrées connues)
- [ ] Caching Redis pour les agrégations GL par compte
- [ ] Export PDF natif des rapports avec signature électronique
