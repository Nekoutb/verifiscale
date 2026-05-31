"""Category H — Procédure LPF (Livre des Procédures Fiscales du Cameroun).

Controls check procedural compliance: notice timing, verification duration,
notification deadlines, response delays, prescription status, and indicative
penalty computation.

Controls read from:
  ctx.extra["lpf_dates"]      — AuditCase procedural dates (injected by orchestrator)
  ctx.extra["tb_aggregates"]  — pre-computed TB aggregates (for penalty estimation)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.controls.base import ControlContext, Finding
from app.models.control_run import ControlSeverity

# ── LPF Cameroun — constantes procédurales ───────────────────────────────────
DELAI_AVIS_JOURS = 15               # L 13 al. 1 — délai minimum avis avant intervention
DUREE_MAX_VERIFICATION_MOIS = 3     # L 40 — durée max sur place (régime réel)
DUREE_MAX_PRIX_TRANSFERT_MOIS = 9   # L 40 al. 2 — extension si prix de transfert
DELAI_NOTIFICATION_JOURS = 60       # L 24 — délai notification après PV fin contrôle
DELAI_REPONSE_CONTRIBUABLE = 30     # L 24 — délai standard réponse contribuable
DELAI_REPONSE_CONTRIBUABLE_PROROGE = 60  # L 24 al. 2 — délai prorogé sur demande motivée
DELAI_REPONSE_ADMIN = 60            # L 26 — délai réponse admin sous peine de nullité
PRESCRIPTION_ANNEES = 4             # L 34 — droit de reprise IS/TVA/IRPP (4 ans)
CONSERVATION_ANNEES = 10            # L 4 + SYSCOHADA art. 24 — durée conservation
ALERTE_PRESCRIPTION_JOURS = 180     # Alerte si prescription < 6 mois

# ── LPF — pénalités ───────────────────────────────────────────────────────────
INTERET_RETARD_MENSUEL = Decimal("0.015")   # L 95 — 1,5 %/mois
INTERET_RETARD_PLAFOND = Decimal("0.50")    # L 95 — plafonné à 50 %
MAJORATION_BONNE_FOI = Decimal("0.30")      # L 96 al. 1
MAJORATION_MAUVAISE_FOI = Decimal("1.00")   # L 96 al. 2
MAJORATION_MANŒUVRES = Decimal("1.50")      # L 96 al. 3

IS_RETURN_DUE_MONTH = 3
IS_RETURN_DUE_DAY = 15


def _dates(ctx: ControlContext) -> dict:
    return ctx.extra.get("lpf_dates", {})


def _today(ctx: ControlContext) -> date:
    return ctx.extra.get("audit_date") or date.today()


# ── H1 — Prescription quadriennale (L 34 / L 35) ────────────────────────────
def h1_prescription(ctx: ControlContext) -> list[Finding]:
    """Prescription 4 ans — retenues à la source et TVA collectée imprescriptibles."""
    d = _dates(ctx)
    fiscal_year = d.get("fiscal_year")
    today = _today(ctx)

    if not fiscal_year:
        return [Finding(
            control_code="H1",
            title="Prescription — exercice fiscal non renseigné",
            description="Renseigner l'exercice fiscal du dossier pour calculer la date de prescription.",
            severity=ControlSeverity.INFO,
            legal_reference="LPF art. L 34",
        )]

    # "fin de la 4ème année suivant celle au titre de laquelle l'imposition est due"
    expiry = date(fiscal_year + PRESCRIPTION_ANNEES + 1, 1, 1) - timedelta(days=1)
    jours_restants = (expiry - today).days

    if jours_restants < 0:
        return [Finding(
            control_code="H1",
            title=f"PRESCRIPTION ATTEINTE — exercice {fiscal_year}",
            description=(
                f"Le droit de reprise de l'Administration sur l'exercice {fiscal_year} "
                f"est prescrit depuis le {expiry} (LPF art. L 34). "
                "Exception : les retenues à la source et la TVA collectée restent "
                "imprescriptibles (art. L 35)."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="LPF art. L 34 + L 35",
            evidence={
                "fiscal_year": fiscal_year,
                "expiry_date": str(expiry),
                "jours_depuis_expiration": -jours_restants,
            },
        )]

    severity = ControlSeverity.HIGH if jours_restants <= ALERTE_PRESCRIPTION_JOURS else ControlSeverity.INFO
    return [Finding(
        control_code="H1",
        title=f"Prescription — expire le {expiry} ({jours_restants} j restants)",
        description=(
            f"Le droit de reprise sur l'exercice {fiscal_year} expire le {expiry}. "
            f"Il reste {jours_restants} jours. "
            "Retenues à la source et TVA collectée : imprescriptibles (art. L 35)."
        ),
        severity=severity,
        legal_reference="LPF art. L 34 + L 35",
        evidence={"fiscal_year": fiscal_year, "expiry_date": str(expiry), "jours_restants": jours_restants},
    )]


# ── H2 — Délai avis de vérification (L 13) ───────────────────────────────────
def h2_delai_avis(ctx: ControlContext) -> list[Finding]:
    """Avis de vérification ≥ 15 jours avant début d'intervention — LPF art. L 13."""
    d = _dates(ctx)
    avis = d.get("avis_verification_date")
    debut = d.get("debut_intervention_date")

    if not avis:
        return [Finding(
            control_code="H2",
            title="Avis de vérification non renseigné",
            description=(
                "Renseigner la date d'envoi de l'avis de vérification. "
                "Le délai minimum de 15 jours avant l'intervention est obligatoire (LPF art. L 13 al. 1)."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="LPF art. L 13",
        )]

    if not debut:
        earliest = avis + timedelta(days=DELAI_AVIS_JOURS)
        return [Finding(
            control_code="H2",
            title=f"Début d'intervention possible à partir du {earliest}",
            description=(
                f"Avis envoyé le {avis}. "
                f"Délai minimum de {DELAI_AVIS_JOURS} jours → "
                f"début d'intervention autorisé à partir du {earliest}."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="LPF art. L 13",
            evidence={"avis_date": str(avis), "earliest_debut": str(earliest)},
        )]

    delta = (debut - avis).days
    if delta < DELAI_AVIS_JOURS:
        return [Finding(
            control_code="H2",
            title=f"Délai avis insuffisant : {delta} j < {DELAI_AVIS_JOURS} j — risque de NULLITÉ",
            description=(
                f"Avis envoyé le {avis}, intervention débutée le {debut} ({delta} jours d'écart). "
                f"Le délai minimum obligatoire est de {DELAI_AVIS_JOURS} jours (LPF art. L 13 al. 1). "
                "Cette irrégularité peut entraîner la nullité de la procédure."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="LPF art. L 13",
            evidence={"avis_date": str(avis), "debut_intervention": str(debut), "delta_jours": delta},
        )]

    return [Finding(
        control_code="H2",
        title=f"Délai avis respecté : {delta} jours ≥ {DELAI_AVIS_JOURS} jours",
        description=f"Avis du {avis}, début d'intervention le {debut} ({delta} jours d'écart).",
        severity=ControlSeverity.INFO,
        legal_reference="LPF art. L 13",
        evidence={"avis_date": str(avis), "debut_intervention": str(debut), "delta_jours": delta},
    )]


# ── H3 — Durée de vérification (L 40) ────────────────────────────────────────
def h3_duree_verification(ctx: ControlContext) -> list[Finding]:
    """Vérification sur place ≤ 3 mois (+9 mois si prix de transfert) — LPF art. L 40."""
    d = _dates(ctx)
    debut = d.get("debut_intervention_date")
    fin = d.get("fin_intervention_date")
    today = _today(ctx)

    if not debut:
        return []

    reference = fin or today
    delta_jours = (reference - debut).days
    max_std = DUREE_MAX_VERIFICATION_MOIS * 30
    max_pt = DUREE_MAX_PRIX_TRANSFERT_MOIS * 30
    en_cours = fin is None

    if delta_jours > max_pt:
        return [Finding(
            control_code="H3",
            title=f"Durée de vérification {'en cours ' if en_cours else ''}dépassée : {delta_jours} j > {max_pt} j",
            description=(
                f"L'intervention {'dure depuis' if en_cours else 'a duré'} {delta_jours} jours "
                f"({'depuis le' if en_cours else 'du'} {debut}{'' if en_cours else f' au {fin}'}), "
                f"dépassant même le maximum pour prix de transfert (9 mois ≈ {max_pt} jours). "
                "Risque de nullité de la procédure (LPF art. L 40)."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="LPF art. L 40",
            evidence={"debut": str(debut), "fin": str(fin or today), "delta_jours": delta_jours},
        )]

    if delta_jours > max_std:
        return [Finding(
            control_code="H3",
            title=f"Durée > 3 mois ({delta_jours} j) — vérifier prorogation prix de transfert",
            description=(
                f"L'intervention {'dure depuis' if en_cours else 'a duré'} {delta_jours} jours. "
                f"Le délai standard est de {max_std} jours (3 mois). "
                "Si des problèmes de prix de transfert justifient la prorogation (max 9 mois), "
                "s'assurer que cette prolongation est documentée."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="LPF art. L 40",
            evidence={"debut": str(debut), "fin": str(fin or today), "delta_jours": delta_jours, "max_standard": max_std},
        )]

    return [Finding(
        control_code="H3",
        title=f"Durée de vérification : {delta_jours} j / {max_std} j max{'(en cours)' if en_cours else ''}",
        description=(
            f"Intervention {'débutée le' if en_cours else 'du'} {debut}"
            f"{'' if en_cours else f' au {fin}'} — {delta_jours} jours ≤ 3 mois."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="LPF art. L 40",
        evidence={"debut": str(debut), "fin": str(fin or today), "delta_jours": delta_jours},
    )]


# ── H4 — Délai réponse contribuable (L 24) ───────────────────────────────────
def h4_reponse_contribuable(ctx: ControlContext) -> list[Finding]:
    """Contribuable : 30 j (prorogeable à 60 j) pour répondre à la notification — L 24."""
    d = _dates(ctx)
    notif = d.get("notification_date")
    reponse = d.get("reponse_contribuable_date")
    today = _today(ctx)

    if not notif:
        return []

    deadline_std = notif + timedelta(days=DELAI_REPONSE_CONTRIBUABLE)
    deadline_max = notif + timedelta(days=DELAI_REPONSE_CONTRIBUABLE_PROROGE)

    if reponse:
        delta = (reponse - notif).days
        if delta > DELAI_REPONSE_CONTRIBUABLE_PROROGE:
            return [Finding(
                control_code="H4",
                title=f"Réponse contribuable hors délai : {delta} j > {DELAI_REPONSE_CONTRIBUABLE_PROROGE} j",
                description=(
                    f"Notification le {notif}. Réponse reçue le {reponse} ({delta} jours). "
                    f"Le délai maximum prorogé est de {DELAI_REPONSE_CONTRIBUABLE_PROROGE} jours. "
                    "La réponse tardive peut être considérée comme irrecevable."
                ),
                severity=ControlSeverity.MEDIUM,
                legal_reference="LPF art. L 24",
                evidence={"notification": str(notif), "reponse": str(reponse), "delta_jours": delta},
            )]
        return [Finding(
            control_code="H4",
            title=f"Réponse contribuable reçue dans les délais ({delta} j)",
            description=f"Notification le {notif}, réponse le {reponse} ({delta} jours ≤ {DELAI_REPONSE_CONTRIBUABLE_PROROGE} j).",
            severity=ControlSeverity.INFO,
            legal_reference="LPF art. L 24",
            evidence={"notification": str(notif), "reponse": str(reponse), "delta_jours": delta},
        )]

    jours_ecoules = (today - notif).days
    if jours_ecoules > DELAI_REPONSE_CONTRIBUABLE_PROROGE:
        return [Finding(
            control_code="H4",
            title=f"Délai réponse contribuable expiré ({jours_ecoules} j depuis notification)",
            description=(
                f"Notification envoyée le {notif}. Le délai maximum de {DELAI_REPONSE_CONTRIBUABLE_PROROGE} jours "
                "est dépassé sans réponse enregistrée. L'Administration peut considérer le redressement "
                "tacitement accepté."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="LPF art. L 24",
            evidence={"notification": str(notif), "deadline_max": str(deadline_max), "jours_ecoules": jours_ecoules},
        )]

    jours_restants = (deadline_std - today).days
    return [Finding(
        control_code="H4",
        title=f"Délai réponse contribuable : {max(0, jours_restants)} j restants (standard 30 j)",
        description=(
            f"Notification envoyée le {notif}. "
            f"Délai standard : {deadline_std} ({max(0, jours_restants)} j restants). "
            f"Prorogeable sur demande motivée jusqu'au {deadline_max}."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="LPF art. L 24",
        evidence={
            "notification": str(notif),
            "deadline_std": str(deadline_std),
            "deadline_max": str(deadline_max),
            "jours_restants_std": max(0, jours_restants),
        },
    )]


# ── H5 — Délai réponse administration (L 26) ─────────────────────────────────
def h5_reponse_administration(ctx: ControlContext) -> list[Finding]:
    """Administration : 60 j pour répondre aux observations du contribuable — L 26."""
    d = _dates(ctx)
    reponse_contrib = d.get("reponse_contribuable_date")
    today = _today(ctx)

    if not reponse_contrib:
        return []

    deadline = reponse_contrib + timedelta(days=DELAI_REPONSE_ADMIN)
    jours_restants = (deadline - today).days

    if jours_restants < 0:
        return [Finding(
            control_code="H5",
            title=f"Délai réponse administration DÉPASSÉ ({-jours_restants} j de retard) — NULLITÉ",
            description=(
                f"Le contribuable a répondu le {reponse_contrib}. "
                f"L'Administration devait répondre avant le {deadline}. "
                f"Le délai de {DELAI_REPONSE_ADMIN} jours est dépassé de {-jours_restants} jours. "
                "Conformément à LPF art. L 26, ce dépassement entraîne la nullité du redressement."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="LPF art. L 26",
            evidence={
                "reponse_contribuable": str(reponse_contrib),
                "deadline": str(deadline),
                "retard_jours": -jours_restants,
            },
        )]

    severity = (
        ControlSeverity.HIGH if jours_restants <= 14
        else ControlSeverity.MEDIUM if jours_restants <= 30
        else ControlSeverity.INFO
    )
    return [Finding(
        control_code="H5",
        title=f"Réponse administration attendue avant le {deadline} ({jours_restants} j restants)",
        description=(
            f"Réponse contribuable reçue le {reponse_contrib}. "
            f"L'Administration dispose de {DELAI_REPONSE_ADMIN} jours pour répondre "
            f"(échéance : {deadline}, {jours_restants} j restants). "
            "Dépassement → nullité du redressement (LPF art. L 26)."
        ),
        severity=severity,
        legal_reference="LPF art. L 26",
        evidence={
            "reponse_contribuable": str(reponse_contrib),
            "deadline": str(deadline),
            "jours_restants": jours_restants,
        },
    )]


# ── H6 — Notification redressement 60 j après PV fin contrôle (L 24) ─────────
def h6_notification_redressement(ctx: ControlContext) -> list[Finding]:
    """Notification de redressement dans les 60 j suivant le PV de fin de contrôle — L 24."""
    d = _dates(ctx)
    fin = d.get("fin_intervention_date")
    notif = d.get("notification_date")
    today = _today(ctx)

    if not fin:
        return []

    deadline = fin + timedelta(days=DELAI_NOTIFICATION_JOURS)

    if notif:
        delta = (notif - fin).days
        if delta > DELAI_NOTIFICATION_JOURS:
            return [Finding(
                control_code="H6",
                title=f"Notification envoyée hors délai : {delta} j > {DELAI_NOTIFICATION_JOURS} j — NULLITÉ",
                description=(
                    f"Fin d'intervention le {fin}. Notification envoyée le {notif} ({delta} jours plus tard). "
                    f"Le délai maximum est de {DELAI_NOTIFICATION_JOURS} jours (LPF art. L 24). "
                    "Cette irrégularité expose la procédure à un risque de nullité."
                ),
                severity=ControlSeverity.BLOCKING,
                legal_reference="LPF art. L 24",
                evidence={"fin_intervention": str(fin), "notification": str(notif), "delta_jours": delta},
            )]
        return [Finding(
            control_code="H6",
            title=f"Notification dans les délais : {delta} j ≤ {DELAI_NOTIFICATION_JOURS} j",
            description=f"Fin d'intervention le {fin}, notification le {notif} ({delta} jours).",
            severity=ControlSeverity.INFO,
            legal_reference="LPF art. L 24",
            evidence={"fin_intervention": str(fin), "notification": str(notif), "delta_jours": delta},
        )]

    jours_restants = (deadline - today).days
    if jours_restants < 0:
        return [Finding(
            control_code="H6",
            title=f"Notification non envoyée — délai {DELAI_NOTIFICATION_JOURS} j DÉPASSÉ ({-jours_restants} j)",
            description=(
                f"Fin d'intervention le {fin}. L'échéance de notification était le {deadline}. "
                f"Le délai est dépassé de {-jours_restants} jours sans notification enregistrée. "
                "Risque de nullité de la procédure (LPF art. L 24)."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="LPF art. L 24",
            evidence={"fin_intervention": str(fin), "deadline": str(deadline), "retard_jours": -jours_restants},
        )]

    severity = (
        ControlSeverity.HIGH if jours_restants <= 14
        else ControlSeverity.MEDIUM if jours_restants <= 30
        else ControlSeverity.INFO
    )
    return [Finding(
        control_code="H6",
        title=f"Notification à envoyer avant le {deadline} ({jours_restants} j restants)",
        description=(
            f"Fin d'intervention le {fin}. "
            f"Notification de redressement à envoyer avant le {deadline} ({jours_restants} j restants)."
        ),
        severity=severity,
        legal_reference="LPF art. L 24",
        evidence={"fin_intervention": str(fin), "deadline": str(deadline), "jours_restants": jours_restants},
    )]


# ── H7 — Intérêts de retard (L 95) ───────────────────────────────────────────
def h7_interets_retard(ctx: ControlContext) -> list[Finding]:
    """Intérêt de retard 1,5 %/mois plafonné à 50 % — LPF art. L 95."""
    from app.controls import tax_params as T

    a = ctx.extra.get("tb_aggregates")
    d = _dates(ctx)
    fiscal_year = d.get("fiscal_year")
    today = _today(ctx)

    if not a or a.chiffre_affaires <= 0 or not fiscal_year:
        return []

    min_is = (a.chiffre_affaires * T.IS_MIN_PERCEPTION_RATE_REEL).quantize(Decimal("1"))
    due_date = date(fiscal_year + 1, IS_RETURN_DUE_MONTH, IS_RETURN_DUE_DAY)

    if today <= due_date:
        return []

    mois_retard = max(1, round((today - due_date).days / 30))
    taux = min(INTERET_RETARD_MENSUEL * mois_retard, INTERET_RETARD_PLAFOND)
    interets = (min_is * taux).quantize(Decimal("1"))

    return [Finding(
        control_code="H7",
        title=f"Intérêts de retard indicatifs : {interets:,.0f} FCFA ({float(taux * 100):.1f} %)",
        description=(
            f"Sur la base du minimum IS estimé ({min_is:,.0f} FCFA, 2 % CA) et d'un retard de "
            f"≈ {mois_retard} mois (dépôt dû le {due_date}), "
            f"les intérêts à 1,5 %/mois (plafonné à 50 %) s'élèvent indicativement à "
            f"{interets:,.0f} FCFA. "
            "À recalculer sur le montant d'IS définitif après redressement."
        ),
        severity=ControlSeverity.HIGH if interets > 0 else ControlSeverity.INFO,
        legal_reference="LPF art. L 95",
        evidence={
            "base_is_estimee": float(min_is),
            "due_date": str(due_date),
            "mois_retard": mois_retard,
            "taux_applique": float(taux),
            "interets_calcules": float(interets),
        },
        estimated_impact_xaf=float(interets),
    )]


# ── H8 — Majorations (L 96) ───────────────────────────────────────────────────
def h8_majorations(ctx: ControlContext) -> list[Finding]:
    """Majorations : 30 % bonne foi / 100 % mauvaise foi / 150 % manœuvres — L 96."""
    from app.controls import tax_params as T

    a = ctx.extra.get("tb_aggregates")
    d = _dates(ctx)
    fiscal_year = d.get("fiscal_year")

    if not a or a.chiffre_affaires <= 0 or not fiscal_year:
        return []

    min_is = (a.chiffre_affaires * T.IS_MIN_PERCEPTION_RATE_REEL).quantize(Decimal("1"))
    maj_bf = (min_is * MAJORATION_BONNE_FOI).quantize(Decimal("1"))
    maj_mf = (min_is * MAJORATION_MAUVAISE_FOI).quantize(Decimal("1"))
    maj_man = (min_is * MAJORATION_MANŒUVRES).quantize(Decimal("1"))

    return [Finding(
        control_code="H8",
        title="Majorations LPF indicatives — à qualifier après contradictoire",
        description=(
            f"Sur la base du minimum IS estimé ({min_is:,.0f} FCFA) — majorations possibles : "
            f"Bonne foi (30 %) : {maj_bf:,.0f} FCFA · "
            f"Mauvaise foi (100 %) : {maj_mf:,.0f} FCFA · "
            f"Manœuvres frauduleuses (150 %) : {maj_man:,.0f} FCFA. "
            "La qualification est arrêtée après la phase contradictoire."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="LPF art. L 96",
        evidence={
            "base_is_estimee": float(min_is),
            "majoration_bonne_foi": float(maj_bf),
            "majoration_mauvaise_foi": float(maj_mf),
            "majoration_manoeuvres": float(maj_man),
        },
    )]


# ── H9 — Conservation 10 ans (L 4 + SYSCOHADA art. 24) ──────────────────────
def h9_conservation_documents(ctx: ControlContext) -> list[Finding]:
    """Livres et pièces justificatives à conserver 10 ans — LPF art. L 4 + SYSCOHADA art. 24."""
    d = _dates(ctx)
    fiscal_year = d.get("fiscal_year")
    today = _today(ctx)

    if not fiscal_year:
        return []

    fin_conservation = date(fiscal_year + CONSERVATION_ANNEES + 1, 1, 1) - timedelta(days=1)
    jours_restants = (fin_conservation - today).days

    if jours_restants < 0:
        return [Finding(
            control_code="H9",
            title=f"Délai de conservation 10 ans expiré pour l'exercice {fiscal_year}",
            description=(
                f"Le délai légal de conservation de 10 ans des livres et pièces justificatives "
                f"de l'exercice {fiscal_year} a expiré le {fin_conservation}. "
                "Si des documents ont été détruits, cela peut affecter la procédure de vérification."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="LPF art. L 4 + SYSCOHADA art. 24",
            evidence={"fiscal_year": fiscal_year, "fin_conservation": str(fin_conservation)},
        )]

    return [Finding(
        control_code="H9",
        title=f"Conservation documents requise jusqu'au {fin_conservation}",
        description=(
            f"Les livres et pièces justificatives de l'exercice {fiscal_year} "
            f"doivent être conservés 10 ans (jusqu'au {fin_conservation}). "
            "Rappeler au contribuable l'obligation de présentation en cas de contrôle."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="LPF art. L 4 + SYSCOHADA art. 24",
        evidence={"fiscal_year": fiscal_year, "fin_conservation": str(fin_conservation), "jours_restants": jours_restants},
    )]


# ── Registry ──────────────────────────────────────────────────────────────────
CATEGORY_H_CONTROLS = [
    ("H1", "Prescription quadriennale (LPF L 34 / L 35)",             h1_prescription),
    ("H2", "Délai avis de vérification ≥ 15 j (LPF L 13)",            h2_delai_avis),
    ("H3", "Durée vérification ≤ 3 mois (LPF L 40)",                  h3_duree_verification),
    ("H4", "Délai réponse contribuable 30 j (LPF L 24)",              h4_reponse_contribuable),
    ("H5", "Délai réponse administration 60 j (LPF L 26)",            h5_reponse_administration),
    ("H6", "Notification redressement 60 j après PV (LPF L 24)",      h6_notification_redressement),
    ("H7", "Intérêts de retard 1,5 %/mois plafonné 50 % (LPF L 95)", h7_interets_retard),
    ("H8", "Majorations bonne foi/mauvaise foi/manœuvres (LPF L 96)", h8_majorations),
    ("H9", "Conservation documents 10 ans (LPF L 4 + SYSCOHADA 24)", h9_conservation_documents),
]


def run_category_h(ctx: ControlContext) -> list[Finding]:
    all_findings: list[Finding] = []
    for _, _, fn in CATEGORY_H_CONTROLS:
        try:
            all_findings.extend(fn(ctx))
        except Exception as e:  # noqa: BLE001
            all_findings.append(Finding(
                control_code="H-ERR",
                title=f"Erreur dans {fn.__name__}",
                description=str(e),
                severity=ControlSeverity.INFO,
                legal_reference="—",
            ))
    return all_findings
