# FiscAudit Pro

**Plateforme d'audit fiscal pour la Direction Générale des Impôts du Cameroun**

Automatise les contrôles comptables et fiscaux que doivent réaliser les auditeurs DGI sur les comptabilités des contribuables, en s'appuyant sur le Code Général des Impôts 2025 et le SYSCOHADA Révisé (OHADA).

---

## Stack

| Couche      | Technologie                                       |
|-------------|---------------------------------------------------|
| Frontend    | Next.js 15 + React 19 + TypeScript + Tailwind     |
| UI          | Radix + shadcn-style components + TanStack Query  |
| Backend     | FastAPI (Python 3.12) + SQLAlchemy 2 + Alembic    |
| Données     | PostgreSQL 16 (UUID, JSONB, partitionnable)       |
| Cache/Queue | Redis 7                                           |
| Stockage    | MinIO (S3-compatible, sovereign)                  |
| Auth        | JWT (Keycloak prévu en production)                |
| OCR factures| Claude Vision API (à brancher)                    |

Tout est conteneurisé — **un seul prérequis local : Docker**.

---

## Démarrage rapide

```bash
# 1. Copier le fichier d'environnement et le configurer
cp .env.example .env
# (laisser les valeurs par défaut pour la démo)

# 2. Démarrer toute la stack
docker compose up --build

# 3. Dans un autre terminal — créer le schéma de DB
docker compose exec api alembic upgrade head

# 4. Charger les données de démonstration (brigades, utilisateurs, dossiers)
docker compose exec api python -m scripts.seed
```

Une fois prêt :
- **Web app** : http://localhost:3000
- **API docs** : http://localhost:8000/docs (Swagger interactif)
- **MinIO console** : http://localhost:9001 (user/pass dans `.env`)

### Comptes de démonstration

| Email             | Rôle              | Mot de passe   |
|-------------------|-------------------|----------------|
| `admin@dgi.cm`    | Admin             | `Password123!` |
| `b.etoundi@dgi.cm`| Auditeur (DGE)    | `Password123!` |
| `s.ngono@dgi.cm`  | Superviseur (DGE) | `Password123!` |
| `j.mbarga@dgi.cm` | Auditeur (CIME)   | `Password123!` |

---

## Première utilisation

Après `docker compose exec api python -m scripts.seed`, un **dossier de démonstration** (2026-DGE-001) est créé avec une balance SYSCOHADA réaliste déjà chargée — vous pouvez lancer les contrôles sans rien uploader.

1. Se connecter avec `b.etoundi@dgi.cm` / `Password123!`
2. Aller dans **Dossiers d'audit** → ouvrir `2026-DGE-001`
3. Onglet **Données & contrôles** : trois cartes catégorie permettent de lancer
   - **A · Intégrité SYSCOHADA** (équilibre, partie double, chronologie, rollforward)
   - **B · Évaluation & SIG** (Soldes Intermédiaires de Gestion, résultat = compte 13, devises)
   - **C · IS** (taux, minimum de perception, plafonds, charges non déductibles, report déficitaire)
4. Onglet **Anomalies consolidées** : vue agrégée multi-catégories avec impact estimé
5. **Référentiel des contrôles** dans la sidebar : catalogue complet des 80+ contrôles avec filtres

Pour vos propres données :
- Glisser-déposer une **balance 6 colonnes** Excel/CSV (Compte · Libellé · Ouv.D/C · Mvt.D/C · Clô.D/C — matching FR/EN tolérant)
- Optionnel : déposer un **grand-livre** (Date · Pièce · Journal · Compte · Libellé · Débit · Crédit)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│         Auditeurs / Superviseurs (navigateur)                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────────────┐
│  Next.js 15 (App Router) — port 3000                            │
│   ├─ Pages app/(app)/dossiers, /balance, /factures, …           │
│   └─ TanStack Query → API REST                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ JSON (JWT bearer)
┌──────────────────────▼──────────────────────────────────────────┐
│  FastAPI — port 8000                                            │
│   ├─ routers/ (auth, dossiers, datasets, controls)              │
│   ├─ controls/category_a.py  (moteur de contrôles SYSCOHADA)    │
│   ├─ parsers/ (TB + GL en pandas, mapping FR/EN tolérant)       │
│   └─ models/ + alembic/      (SQLAlchemy 2.x)                   │
└────────┬─────────────────┬────────────────────────┬─────────────┘
         │                 │                        │
   ┌─────▼─────┐     ┌─────▼─────┐           ┌─────▼─────┐
   │ Postgres  │     │  Redis    │           │  MinIO    │
   │ port 5432 │     │ port 6379 │           │ port 9000 │
   └───────────┘     └───────────┘           └───────────┘
```

---

## Modules

### Implémentés (fonctionnels)
- **Authentification** : JWT, rôles RBAC (Auditeur / Superviseur / Chef Brigade / Admin)
- **Gestion des dossiers d'audit** : taxpayer, brigade, période fiscale, statut, risque
- **Upload + parsing** : Excel/CSV pour balance et grand-livre (mapping de colonnes tolérant FR/EN)
- **Balance & Rollforward** : import, affichage 6 colonnes, totaux
- **Référentiel des contrôles** : 80+ contrôles avec filtres et statut d'implémentation
- **Catégorie A — SYSCOHADA Intégrité** (9 contrôles automatisés) :
  - A1 — Équilibre individuel des écritures (partie double) — *art. 17.2*
  - A2 — Présence pièce et date — *art. 17.3*
  - A3 — Chronologie sans rupture — *art. 16 + 22*
  - A5 — Conformité plan comptable OHADA — *art. 18 + Titre VII*
  - A8 — Bilan ouverture = clôture N-1 — *art. 34*
  - A9 — Non-compensation comptes de tiers — *art. 34*
  - A13 — Équilibre global Σ Débits = Σ Crédits — *art. 17.2 + 34*
  - A13b — Rollforward par compte
  - A13c — Balance ↔ Grand-livre
- **Catégorie B — SYSCOHADA Évaluation & SIG** (3 contrôles) :
  - B-SIG — Reconstitution SIG (Marge commerciale → Valeur ajoutée → EBE → RE) — *Titre IX Chap. 4*
  - B9   — Écart de conversion 478 → provision pour pertes de change obligatoire — *art. 54-58*
  - B13  — Résultat net comptabilisé au compte 13 — *Titre IX*
- **Catégorie C — Fiscal IS** (8 contrôles) :
  - C0  — Synthèse résultat & IS reconstitués
  - C1  — Recalcul IS : 25 % si CA ≤ 3 Mrd, sinon 30 % — *CGI art. 17 + 17 bis*
  - C3  — Minimum de perception 2 % CA — *CGI art. 22-23*
  - C9  — Plafond dons 0,5 % CA — *CGI art. 7-A-5*
  - C11 — Frais siège / assistance technique (alerte) — *CGI art. 7-A-1-d*
  - C14 — Plafond intérêts CC associés — *CGI art. 7-B*
  - C17 — Report déficitaire ≤ 4 ans — *CGI art. 12*
  - C19 — Charges fiscalement non déductibles à réintégrer — *CGI art. 7-A-3*
- **Catégorie H — Procédure LPF** (9 contrôles — ne nécessite pas de balance) :
  - H1  — Prescription quadriennale IS/TVA/IRPP + imprescriptibilité retenues — *LPF art. L 34 + L 35*
  - H2  — Délai avis de vérification ≥ 15 jours avant intervention — *LPF art. L 13*
  - H3  — Durée vérification ≤ 3 mois (+ 9 mois si prix de transfert) — *LPF art. L 40*
  - H4  — Délai réponse contribuable 30 j (60 j prorogé) — *LPF art. L 24*
  - H5  — Délai réponse administration 60 j sous peine de nullité — *LPF art. L 26*
  - H6  — Notification de redressement dans les 60 j après PV fin contrôle — *LPF art. L 24*
  - H7  — Intérêts de retard 1,5 %/mois plafonné 50 % (indicatif) — *LPF art. L 95*
  - H8  — Majorations bonne foi 30 % / mauvaise foi 100 % / manœuvres 150 % — *LPF art. L 96*
  - H9  — Conservation documents 10 ans — *LPF art. L 4 + SYSCOHADA art. 24*

Tous les paramètres fiscaux (taux IS, plafonds, seuils) sont centralisés dans
[apps/api/app/controls/tax_params.py](apps/api/app/controls/tax_params.py) — à mettre à jour à chaque Loi de Finances.

### Définis dans le référentiel — implémentation à venir
Voir `packages/shared/controls-catalog.json` pour les 80+ contrôles couvrant :
- **Catégorie B** — Évaluation et règles comptables SYSCOHADA (14 contrôles)
- **Catégorie C** — Impôt sur les Sociétés (19 contrôles)
- **Catégorie D** — TVA (16 contrôles)
- **Catégorie E** — IRPP, retenues à la source, TSR (10 contrôles)
- **Catégorie F** — Factures fournisseurs : fond et forme (10 contrôles)
- **Catégorie G** — Cross-controls et cohérence (9 contrôles)
- **Catégorie H** — Procédure LPF (9 contrôles)

---

## Structure du dépôt

```
.
├── apps/
│   ├── api/                  # FastAPI + SQLAlchemy + Alembic + pandas
│   │   ├── app/
│   │   │   ├── controls/     # Moteur de contrôles
│   │   │   ├── models/       # ORM
│   │   │   ├── parsers/      # Excel/CSV/FEC
│   │   │   ├── routers/      # Endpoints HTTP
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── main.py
│   │   │   ├── schemas.py
│   │   │   ├── security.py
│   │   │   └── storage.py    # MinIO wrapper
│   │   ├── alembic/          # Migrations
│   │   ├── scripts/seed.py   # Données de démo
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── web/                  # Next.js 15
│       ├── src/
│       │   ├── app/          # Pages (App Router)
│       │   ├── components/   # UI + dropzone
│       │   └── lib/          # api, store, types, utils
│       ├── package.json
│       └── Dockerfile
├── packages/
│   └── shared/
│       └── controls-catalog.json   # Référentiel complet des 80+ contrôles
├── infra/
│   └── postgres/init.sql     # Extensions Postgres
├── docs/                     # Documentation produit
├── .references/              # PDF sources + textes extraits (gitignored)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Sources juridiques

- **Code Général des Impôts du Cameroun, édition 2025** (DGI)
- **SYSCOHADA Révisé** — Acte Uniforme OHADA portant droit comptable et information financière
- **LPF** — Livre des Procédures Fiscales (Livre Deuxième du CGI)

Les références d'articles sont indiquées sur chaque anomalie détectée et dans le référentiel des contrôles.

---

## Roadmap (extrait)

| Phase  | Durée  | Contenu                                                                 |
|--------|--------|-------------------------------------------------------------------------|
| ✅ P0  | —      | Cadrage, plan, référentiel contrôles                                     |
| ✅ P1  | —      | Foundations : auth, RBAC, dossiers, parseur TB/GL                        |
| ✅ P2  | —      | Catégorie A SYSCOHADA (9 contrôles)                                      |
| ✅ P2b | —      | Catégories B (SIG, devises) + C (IS, 8 contrôles)                       |
| ✅ P2c | —      | Catégorie H : procédure LPF (9 contrôles, délais + pénalités)            |
| 🚧 P3 | 6 sem  | Catégorie B complète : évaluation, SIG, TFT                              |
| ⏳ P4 | 7 sem  | Catégorie D : TVA + intégration **API DGI FCA + facturation électronique** |
| ⏳ P5 | 6 sem  | Catégories C + E : IS et retenues à la source                            |
| ⏳ P6 | 8 sem  | Catégorie F : OCR factures (Claude Vision) + conditions fond/forme       |
| ⏳ P7 | 5 sem  | Catégorie G : cross-controls + détection d'anomalies par IA              |
| ⏳ P8 | 6 sem  | Catégorie H : procédure LPF + génération notifications conformes         |
| ⏳ P9 | 4 sem  | Restitution + piste d'audit forensique                                   |

---

## Sécurité (à compléter avant production)

- [ ] Remplacer JWT custom par **Keycloak** avec MFA obligatoire
- [ ] Activer **TLS 1.3** en frontal (reverse proxy)
- [ ] Configurer Postgres avec **row-level security** par brigade
- [ ] Audit log immuable signé HMAC (modèle déjà en place)
- [ ] Chiffrement au repos pour MinIO (KMS)
- [ ] Sauvegardes 3-2-1 chiffrées
- [ ] Pentest annuel et certification ISO 27001
- [ ] Hébergement sur sol camerounais (loi sur la cybersécurité)

---

## Développement

```bash
# Reset complet (perd toutes les données)
docker compose down -v
docker compose up --build

# Voir les logs d'un service
docker compose logs -f api

# Shell dans le conteneur API
docker compose exec api bash

# Créer une nouvelle migration après modification d'un modèle
docker compose exec api alembic revision --autogenerate -m "ma_migration"
docker compose exec api alembic upgrade head
```

---

## Licence

Propriétaire — Direction Générale des Impôts du Cameroun.

## Production
- Live at: https://verifiscale.com
- Hosted on Vultr Paris (45.32.150.96)
- SSL by Let's Encrypt (renews 2026-08-29)

