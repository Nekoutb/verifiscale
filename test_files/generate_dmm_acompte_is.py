"""Génère 3 DMM fictives mirroir du formulaire officiel DGI Cameroun.

Cas d'usage : tester le contrôle « Acomptes mensuels IS » de FiscAudit Pro
(taux 2,2 % CGI Art. 21) contre le grand-livre KISSYWEARS.

  - Janvier 2026 : CA déclaré = CA GL  (alignement parfait)
  - Février 2026 : CA déclaré = 50 % × CA GL  (sous-déclaration 50 %)
  - Mars    2026 : CA déclaré = 70 % × CA GL  (sous-déclaration 30 %)

La mise en page reproduit fidèlement la DMM officielle (titres, sections,
codes de ligne L1..L83) — elle peut aussi servir de maquette pour un futur
écran SaaS de saisie/visualisation des DMM.
"""
from decimal import Decimal
from datetime import date
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Données du contribuable (KISSYWEARS) ─────────────────────────────────────
TAXPAYER = {
    "raison_sociale": "KISSYWEARS SARL",
    "sigle": "KSY",
    "niu": "M105929849503U",
    "regime": "RÉEL",
    "rattachement": "CIME DOUALA BONANJO",
    "ville": "DOUALA",
    "quartier": "",
    "commune": "",
    "lieu_dit": "DEIDO",
    "bp": "",
    "tel_fixe": "237 233 42 11 22",
    "tel_mobile": "237 698 78 56 34",
    "fax": "",
    "email": "contact@kissywears.cm",
}

YEAR = 2026
TAX_RATE_ACOMPTE = Decimal("0.02")          # 2 % IS
CAC_RATE         = Decimal("0.10")          # 10 % CAC
TVA_RATE         = Decimal("0.1925")        # 19,25 % TVA Cameroun
TVA_DEDUCTIBLE_RATIO = Decimal("0.50")      # hypothèse : 50 % du CA en achats taxables
# Charges sociales / salariales mensuelles supposées pour KISSYWEARS (3 employés)
MONTHLY_GROSS_PAYROLL = Decimal("950000")   # masse salariale brute / mois
IRPP_RATE_AVG         = Decimal("0.22")     # taux moyen IRPP retenu à la source
CFC_SALARIAL_RATE     = Decimal("0.01")     # 1 % CFC part salariale
FNE_RATE              = Decimal("0.01")     # 1 % FNE patronale
RAV_MONTHLY           = Decimal("3000")     # Redevance audio-visuelle (forfait par employé)
EMPLOYEES_COUNT       = 3

# ── Trois mois à générer (CA GL ↔ CA déclaré) ────────────────────────────────
TEST_MONTHS = [
    {
        "month_no": 1,
        "month_label": "Janvier",
        "ca_gl": Decimal("3116179"),
        "declared_ratio": Decimal("1.00"),     # alignement parfait
        "filing_date": date(2026, 2, 14),       # avant J+15
        "doc_number": "44011401001",
    },
    {
        "month_no": 2,
        "month_label": "Février",
        "ca_gl": Decimal("1208261"),
        "declared_ratio": Decimal("0.50"),     # -50 %
        "filing_date": date(2026, 3, 14),
        "doc_number": "44011401002",
    },
    {
        "month_no": 3,
        "month_label": "Mars",
        "ca_gl": Decimal("1922674"),
        "declared_ratio": Decimal("0.70"),     # -30 %
        "filing_date": date(2026, 4, 14),
        "doc_number": "44011401003",
    },
]

# ── Styles ───────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()
ST_HDR_LR   = ParagraphStyle("HdrLR", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER, leading=10)
ST_TITLE    = ParagraphStyle("TitleBig", parent=styles["Title"], fontSize=14, alignment=TA_CENTER, textColor=colors.HexColor("#0a4480"), spaceBefore=4, spaceAfter=4)
ST_INFO     = ParagraphStyle("Info", parent=styles["Normal"], fontSize=8.5, leading=11)
ST_SECTION  = ParagraphStyle("Section", parent=styles["Normal"], fontSize=9, textColor=colors.white, leftIndent=4)
ST_CELL     = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10)
ST_CELL_R   = ParagraphStyle("CellR", parent=styles["Normal"], fontSize=8, leading=10, alignment=2)
ST_TOTAL    = ParagraphStyle("Total", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold")
ST_FOOT     = ParagraphStyle("Foot", parent=styles["Normal"], fontSize=7.5, alignment=TA_CENTER, textColor=colors.grey)
ST_STAMP    = ParagraphStyle("Stamp", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#0a7d3e"), alignment=2)


def fmt(n: Decimal) -> str:
    """Format à la française : 3 116 179."""
    s = f"{int(n):,}".replace(",", " ")
    return s


def num_cell(n: Decimal | int | str, line_code: str | None = None) -> Table:
    """Cellule numérique avec code de ligne à droite (style DMM)."""
    body_value = fmt(Decimal(str(n))) if not isinstance(n, str) else n
    if line_code is None:
        return Paragraph(body_value, ST_CELL_R)
    t = Table(
        [[Paragraph(body_value, ST_CELL_R), Paragraph(line_code, ST_CELL)]],
        colWidths=[3.2*cm, 0.7*cm],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (0, 0), 0.4, colors.grey),
        ("BOX", (1, 0), (1, 0), 0.4, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f0f0f0")),
    ]))
    return t


def section_header(title: str) -> Table:
    t = Table([[Paragraph(f"<b>{title}</b>", ST_SECTION)]], colWidths=[18*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1c3d6e")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1c3d6e")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def build_dmm(month_no: int, month_label: str, ca_gl: Decimal,
              declared_ratio: Decimal, filing_date: date, doc_number: str) -> str:
    """Génère une DMM PDF multi-impôts pour un mois donné.

    Sections renseignées :
      - 3/6  : TVA (collectée − déductible)
      - 10   : Acompte IS (L50)
      - 14   : RTS / IRPP salaires (L76)
      - Récapitulatif final consolidé
    """
    # ── Acompte IS ──────────────────────────────────────────────────────────
    ca_declared = (ca_gl * declared_ratio).quantize(Decimal("1"))
    acompte_principal = (ca_declared * TAX_RATE_ACOMPTE).quantize(Decimal("1"))
    acompte_cac       = (acompte_principal * CAC_RATE).quantize(Decimal("1"))
    acompte_total     = acompte_principal + acompte_cac

    # ── TVA ─────────────────────────────────────────────────────────────────
    tva_collectee   = (ca_declared * TVA_RATE).quantize(Decimal("1"))
    tva_base_deduc  = (ca_declared * TVA_DEDUCTIBLE_RATIO).quantize(Decimal("1"))
    tva_deductible  = (tva_base_deduc * TVA_RATE).quantize(Decimal("1"))
    tva_a_payer     = max(Decimal("0"), tva_collectee - tva_deductible)

    # ── RTS salaires (IRPP + CFC + FNE + RAV) ───────────────────────────────
    irpp_principal = (MONTHLY_GROSS_PAYROLL * IRPP_RATE_AVG).quantize(Decimal("1"))
    irpp_cac       = (irpp_principal * CAC_RATE).quantize(Decimal("1"))
    cfc_principal  = (MONTHLY_GROSS_PAYROLL * CFC_SALARIAL_RATE).quantize(Decimal("1"))
    fne_principal  = (MONTHLY_GROSS_PAYROLL * FNE_RATE).quantize(Decimal("1"))
    rav_principal  = (RAV_MONTHLY * EMPLOYEES_COUNT).quantize(Decimal("1"))
    rts_principal_total = irpp_principal + cfc_principal + fne_principal + rav_principal
    rts_cac_total       = irpp_cac
    rts_total           = rts_principal_total + rts_cac_total

    # ── Total à payer (récapitulatif) ───────────────────────────────────────
    grand_principal = acompte_principal + tva_a_payer + rts_principal_total
    grand_cac       = acompte_cac + rts_cac_total
    grand_total     = grand_principal + grand_cac

    suffix = "ALIGNE" if declared_ratio == 1 else (
        f"ECART_{int((1 - declared_ratio) * 100)}PCT"
    )
    fname = f"DMM_{YEAR}_{month_no:02d}_{month_label}_{suffix}.pdf"
    path = os.path.join(OUT_DIR, fname)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1*cm, bottomMargin=1*cm,
        title=f"DMM {month_label} {YEAR} - {TAXPAYER['raison_sociale']}",
    )

    story = []

    # ── Bandeau République / Ministère ──────────────────────────────────────
    bandeau = Table([[
        Paragraph(
            "<b>RÉPUBLIQUE DU CAMEROUN</b><br/>"
            "Paix - Travail - Patrie<br/>"
            "---------<br/>"
            "<b>MINISTÈRE DES FINANCES</b><br/>"
            "---------<br/>"
            "<b>DIRECTION GÉNÉRALE DES IMPÔTS</b><br/>"
            "---------<br/>"
            f"<b>{TAXPAYER['rattachement']}</b>",
            ST_HDR_LR,
        ),
        Paragraph(
            "<b>REPUBLIC OF CAMEROON</b><br/>"
            "Peace - Work - Fatherland<br/>"
            "---------<br/>"
            "<b>MINISTRY OF FINANCE</b><br/>"
            "---------<br/>"
            "<b>DIRECTORATE GENERAL OF TAXATION</b><br/>"
            "---------<br/>",
            ST_HDR_LR,
        ),
    ]], colWidths=[9*cm, 9*cm])
    bandeau.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(bandeau)

    # ── Numéro + statut ─────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>N° {doc_number}</b><br/>[Déclaration réceptionnée]", ST_STAMP))
    story.append(Spacer(1, 4))

    # ── Titre ───────────────────────────────────────────────────────────────
    story.append(Paragraph(
        "DÉCLARATION DES TAXES SUR LE CHIFFRE D'AFFAIRES ET<br/>"
        "DES IMPÔTS SUR LE REVENU", ST_TITLE,
    ))
    story.append(Spacer(1, 4))

    # ── Identification du contribuable ──────────────────────────────────────
    info_left = (
        f"<b>Régime d'imposition :</b> {TAXPAYER['regime']}<br/>"
        f"<b>Numéro Identifiant Unique (NIU) :</b> {TAXPAYER['niu']}<br/>"
        f"<b>Nom ou Raison sociale :</b> {TAXPAYER['raison_sociale']}<br/>"
        f"<b>Ville :</b> {TAXPAYER['ville']}    "
        f"<b>Commune :</b> {TAXPAYER['commune']}    "
        f"<b>Quartier :</b> {TAXPAYER['quartier']}<br/>"
        f"<b>BP :</b> {TAXPAYER['bp']}    "
        f"<b>Tél. fixe :</b> {TAXPAYER['tel_fixe']}<br/>"
        f"<b>Email :</b> {TAXPAYER['email']}<br/>"
        f"<b>Rattachement :</b> {TAXPAYER['rattachement']}"
    )
    info_right = (
        f"<b>Exercice fiscal :</b> {YEAR}<br/>"
        f"<b>Mois de :</b> {month_label}<br/>"
        f"<b>Prénom/Sigle :</b> {TAXPAYER['sigle']}<br/>"
        f"<b>Lieu-dit :</b> {TAXPAYER['lieu_dit']}<br/>"
        f"<b>Tél. mobile :</b> {TAXPAYER['tel_mobile']}<br/>"
        f"<b>Fax :</b> {TAXPAYER['fax']}<br/>"
    )
    ident = Table([[Paragraph(info_left, ST_INFO), Paragraph(info_right, ST_INFO)]],
                  colWidths=[12*cm, 6*cm])
    ident.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(ident)
    story.append(Spacer(1, 10))

    # ── Section 1 - TSR (vide) ──────────────────────────────────────────────
    story.append(section_header("1 - PRÉLÈVEMENT SPÉCIAL SUR LES REVENUS VERSÉS À L'ÉTRANGER (TSR)"))
    tsr = Table([
        ["", "BASE", "TAUX (%)", "PRINCIPAL", "PÉNALITÉS", "TOTAL", ""],
        ["TSR retenue 1", "0", "15",  "0", "0", "0", "L0.1"],
        ["TSR retenue 2", "0", "10",  "0", "0", "0", "L0.2"],
        ["TSR retenue 3", "0", "7,5", "0", "0", "0", "L0.3"],
        ["TSR retenue 4", "0", "",    "0", "0", "0", "L0.4"],
        ["Total TSR retenue", "", "", "0", "", "0", "L1"],
    ], colWidths=[4.5*cm, 2*cm, 2*cm, 3*cm, 2.5*cm, 3*cm, 1*cm])
    tsr.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(tsr)
    story.append(Spacer(1, 10))

    # ── Section 3 - TVA (CA réalisé) ────────────────────────────────────────
    story.append(section_header("3 - TAXE SUR LA VALEUR AJOUTÉE (TVA) — CHIFFRE D'AFFAIRES RÉALISÉ"))
    tva = Table([
        ["", "CA", "TAUX (%)", "MONTANT DE LA TAXE", ""],
        ["Opérations taxables au taux normal",   fmt(ca_declared), "19,25", fmt(tva_collectee), "L10"],
        ["Autres opérations taxables",           "0", "",      "0", "L12"],
        ["Exportations (taxables au taux zéro)", "0", "0",     "0", "L13"],
        ["Chiffre d'affaires exonéré",           "0", "",      "",  "L14"],
        ["CA global hors taxes = L10+L11+L12+L13", fmt(ca_declared), "", fmt(tva_collectee), "L15"],
    ], colWidths=[7.5*cm, 4*cm, 2*cm, 3.5*cm, 1*cm])
    tva.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-2, -1), colors.HexColor("#fffae0")),
    ]))
    story.append(tva)
    story.append(Spacer(1, 8))

    # ── Section 6 - TVA à payer / Crédit ───────────────────────────────────
    story.append(section_header("6 - TVA À PAYER OU CRÉDIT DE TVA"))
    tva_pay = Table([
        ["", "", "MONTANT"],
        ["TVA collectée (L10 + L11 + L12)", "L28", fmt(tva_collectee)],
        ["TVA déductible (L22)",            "L29", fmt(tva_deductible)],
        ["TVA à payer (L28 − L29)",         "L32", fmt(tva_a_payer)],
    ], colWidths=[11.5*cm, 1.2*cm, 5.3*cm])
    tva_pay.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fffae0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(tva_pay)
    story.append(Spacer(1, 8))

    # ── Section 7 - Total TVA à payer ───────────────────────────────────────
    story.append(section_header("7 - TOTAL DE TVA À PAYER"))
    tva_total = Table([
        ["", "", "PRINCIPAL", "CAC", "TOTAL"],
        ["TVA à payer (L32)", "L36", fmt(tva_a_payer), "0", fmt(tva_a_payer)],
        ["Montant à payer (L36 + L37 + L38)", "L39", fmt(tva_a_payer), "0", fmt(tva_a_payer)],
    ], colWidths=[8*cm, 1.2*cm, 3*cm, 2*cm, 3.8*cm])
    tva_total.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fffae0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(tva_total)
    story.append(Spacer(1, 10))

    # ── Section 10 - Liquidation acompte IS ─────────────────────────────────
    story.append(section_header("10 - LIQUIDATION ACOMPTE IMPÔTS SUR LE REVENU (Art. 21 CGI)"))
    liq = Table([
        ["", "", "PRINCIPAL", "CAC", "PÉNALITÉS", "TOTAL"],
        ["Acompte sur CA déclaré", "L50", fmt(acompte_principal), fmt(acompte_cac), "0", fmt(acompte_total)],
        ["Acompte de 15 % sur loyers perçus", "L51", "0", "", "", "0"],
        ["Déductions à opérer = L49", "L52", "0", "", "", "0"],
        ["Crédit antérieur = L55 déclaration précédente", "L53", "0", "0", "", "0"],
        ["Acompte à payer = Solde [(L50+L51) − (L52+L53)]", "L54", fmt(acompte_principal), fmt(acompte_cac), "0", fmt(acompte_total)],
        ["Crédit d'impôt à reporter = (Solde négatif L54)", "L55", "0", "0", "0", "0"],
    ], colWidths=[7.5*cm, 1.2*cm, 2.6*cm, 2.2*cm, 2*cm, 2.5*cm])
    liq.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fffae0")),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#fffae0")),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
    ]))
    story.append(liq)
    story.append(Spacer(1, 10))

    # ── Section 14 - RTS / IRPP salaires ────────────────────────────────────
    story.append(section_header("14 - IMPÔTS RETENUS SUR SALAIRES (RTS / IRPP)"))
    rts = Table([
        ["", "", "PRINCIPAL", "CAC (10 %)", "PÉNALITÉS", "TOTAL"],
        ["IRPP sur traitements et salaires", "L70", fmt(irpp_principal), fmt(irpp_cac), "0", fmt(irpp_principal + irpp_cac)],
        ["Crédit Foncier du Cameroun (part salariale)", "L71", fmt(cfc_principal), "", "", fmt(cfc_principal)],
        ["Fonds National de l'Emploi", "L73", fmt(fne_principal), "", "", fmt(fne_principal)],
        ["Redevance audiovisuelle", "L74", fmt(rav_principal), "", "", fmt(rav_principal)],
        ["TOTAL = (Somme L70 à L75)", "L76", fmt(rts_principal_total), fmt(rts_cac_total), "0", fmt(rts_total)],
    ], colWidths=[7.5*cm, 1.2*cm, 2.6*cm, 2.2*cm, 2*cm, 2.5*cm])
    rts.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fffae0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(rts)
    story.append(Spacer(1, 10))

    # ── Récapitulatif consolidé ─────────────────────────────────────────────
    story.append(section_header("RÉCAPITULATIF"))
    recap = Table([
        ["", "PRINCIPAL", "CAC", "PÉNALITÉS", "TOTAL"],
        ["TSR (L1)",                  "0", "", "0", "0"],
        ["Droit d'Accises (L9)",      "0", "", "0", "0"],
        ["TVA (L39)",                 fmt(tva_a_payer), "0", "0", fmt(tva_a_payer)],
        ["AC/IR + Précomptes (L44)",  "0", "0", "0", "0"],
        ["Acompte à payer (L54)",     fmt(acompte_principal), fmt(acompte_cac), "0", fmt(acompte_total)],
        ["IRCM (L62)",                "0", "0", "0", "0"],
        ["RTS / salaires (L76)",      fmt(rts_principal_total), fmt(rts_cac_total), "0", fmt(rts_total)],
        ["TOTAL À PAYER",             fmt(grand_principal), fmt(grand_cac), "0", fmt(grand_total)],
    ], colWidths=[7*cm, 2.8*cm, 2.5*cm, 2.5*cm, 3.2*cm])
    recap.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#1c3d6e")),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 9),
    ]))
    story.append(recap)
    story.append(Spacer(1, 14))

    # ── Footer / saisie ─────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.grey))
    footer = (
        f"Date saisie : {filing_date.strftime('%d/%m/%Y')} 14:30:22"
        f"                                       "
        f"Document édité sur Harmony par {TAXPAYER['niu']} "
        f"le {filing_date.strftime('%d/%m/%Y')} 14:35:00"
    )
    story.append(Paragraph(footer, ST_FOOT))

    # ── Bande "fictif" pour bien marquer que ce sont des tests ──────────────
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"<font color='#8b0000'><i>— DOCUMENT FICTIF GÉNÉRÉ POUR TEST FISCAUDIT PRO — "
        f"ratio CA déclaré / CA réel = {declared_ratio * 100:.0f} % —</i></font>",
        ST_FOOT,
    ))

    doc.build(story)
    return path


def main():
    print(f"Génération de {len(TEST_MONTHS)} DMM fictives — KISSYWEARS SARL, exercice {YEAR}")
    print(f"Sortie : {OUT_DIR}")
    print()
    print(f"{'Mois':<12} {'CA decl':>11} {'Acompte':>9} {'TVA':>10} {'RTS':>10} {'TOTAL':>11}  Fichier")
    print("-" * 110)
    for tm in TEST_MONTHS:
        path = build_dmm(**tm)
        ca_declared = (tm["ca_gl"] * tm["declared_ratio"]).quantize(Decimal("1"))
        acompte = (ca_declared * TAX_RATE_ACOMPTE * (Decimal("1") + CAC_RATE)).quantize(Decimal("1"))
        tva_col = (ca_declared * TVA_RATE).quantize(Decimal("1"))
        tva_ded = (ca_declared * TVA_DEDUCTIBLE_RATIO * TVA_RATE).quantize(Decimal("1"))
        tva_pay = max(Decimal("0"), tva_col - tva_ded)
        rts = ((MONTHLY_GROSS_PAYROLL * IRPP_RATE_AVG * (Decimal("1") + CAC_RATE))
               + MONTHLY_GROSS_PAYROLL * (CFC_SALARIAL_RATE + FNE_RATE)
               + RAV_MONTHLY * EMPLOYEES_COUNT).quantize(Decimal("1"))
        total = acompte + tva_pay + rts
        print(f"{tm['month_label']:<12} {fmt(ca_declared):>11} "
              f"{fmt(acompte):>9} {fmt(tva_pay):>10} {fmt(rts):>10} {fmt(total):>11}  "
              f"{os.path.basename(path)}")


if __name__ == "__main__":
    main()
