"""Génère deux reçus de don PDF pour tester le contrôle « Dons et libéralités »
de FiscAudit Pro :

  - dons_recu_CONFORME.pdf     : verdict attendu ELIGIBLE
  - dons_recu_NON_CONFORME.pdf : verdict attendu NON_ELIGIBLE
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)
from reportlab.pdfgen import canvas
from reportlab.platypus.flowables import HRFlowable
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

styles = getSampleStyleSheet()

H_ORG = ParagraphStyle("HOrg", parent=styles["Title"], fontSize=16, alignment=TA_CENTER, spaceAfter=4)
H_SUB = ParagraphStyle("HSub", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.grey)
H_TITLE = ParagraphStyle("HTitle", parent=styles["Heading1"], fontSize=14, alignment=TA_CENTER, spaceBefore=12, spaceAfter=12, textColor=colors.HexColor("#1e3a5f"))
P_BODY = ParagraphStyle("PBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
P_LBL = ParagraphStyle("PLbl", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
P_VAL = ParagraphStyle("PVal", parent=styles["Normal"], fontSize=11, leading=14)
P_FOOT = ParagraphStyle("PFoot", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER, textColor=colors.grey)


def kv_table(rows, col_widths=(5*cm, 11*cm)):
    """Build a label/value table."""
    data = [[Paragraph(label, P_LBL), Paragraph(value, P_VAL)] for label, value in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def stamp_on_canvas(text, color_hex, cx, cy, angle=-12):
    """Returns a callback to draw a 'stamp' on the canvas at first page end."""
    def _draw(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.translate(cx, cy)
        canvas_obj.rotate(angle)
        canvas_obj.setStrokeColor(colors.HexColor(color_hex))
        canvas_obj.setFillColor(colors.HexColor(color_hex))
        canvas_obj.setLineWidth(2)
        # Draw oval-ish stamp border
        canvas_obj.roundRect(-90, -28, 180, 56, 10, stroke=1, fill=0)
        canvas_obj.setFont("Helvetica-Bold", 13)
        canvas_obj.drawCentredString(0, 4, text)
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.drawCentredString(0, -10, "Cachet et signature")
        canvas_obj.restoreState()
    return _draw


# ─────────────────────────────────────────────────────────────────────────────
# Receipt 1 — CONFORME (verdict attendu : ELIGIBLE)
# ─────────────────────────────────────────────────────────────────────────────

def build_conforme():
    path = os.path.join(OUT_DIR, "dons_recu_CONFORME.pdf")
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Reçu de don - Fondation Espoir Cameroun",
    )

    story = []

    # Header — beneficiary org
    story.append(Paragraph("FONDATION ESPOIR CAMEROUN", H_ORG))
    story.append(Paragraph(
        "Œuvre d'intérêt général à caractère philanthropique et social<br/>"
        "Siège social : 1245, Rue Joss, BP 4321 — Douala, Cameroun<br/>"
        "Tél. : +237 233 42 56 78 — contact@fondation-espoir.cm",
        H_SUB,
    ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#1e3a5f")))
    story.append(Spacer(1, 6))

    # Document title
    story.append(Paragraph("REÇU DE DON N° RD-2026-0147", H_TITLE))

    # Receipt body
    story.append(kv_table([
        ("Date d'émission",      "15 mars 2026"),
        ("Date de réception du don", "12 mars 2026"),
        ("NIU bénéficiaire",     "M021800145672K"),
        ("RCCM",                 "RC/DLA/2018/B/0234"),
        ("Centre des impôts",    "Centre Spécialisé des Impôts de Bonanjo, Douala"),
        ("Agrément utilité publique", "N° 0345/MINATD/SG/DAP du 18 juillet 2019 — Ministère de l'Administration Territoriale (MINATD)"),
        ("Nature de l'organisme", "Fondation d'intérêt général — philanthropique et social"),
    ]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Donateur</b>", P_BODY))
    story.append(kv_table([
        ("Raison sociale",  "KISSYWEARS SARL"),
        ("NIU",             "M105929849503U"),
        ("Adresse",         "Deido, Douala, Cameroun"),
    ]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Don reçu</b>", P_BODY))
    story.append(kv_table([
        ("Montant en chiffres",  "<b>40 000 FCFA</b>"),
        ("Montant en lettres",   "Quarante mille francs CFA"),
        ("Mode de règlement",    "<b>Virement bancaire</b> — Référence : VIR-AFB-20260312-9981"),
        ("Banque émettrice",     "Afriland First Bank — Agence Akwa"),
        ("Compte bénéficiaire",  "11005-00012-23456789012-58 (Afriland First Bank)"),
        ("Objet du don",         "Soutien au programme d'alphabétisation des jeunes filles en zone rurale (exercice 2026)"),
    ]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Nous certifions par la présente avoir reçu de la société "
        "<b>KISSYWEARS SARL</b> le don ci-dessus mentionné, exclusivement "
        "affecté à nos missions d'intérêt général. Le présent reçu est délivré "
        "pour servir et valoir ce que de droit, notamment en application des "
        "dispositions de l'Article 7 du Code Général des Impôts du Cameroun.",
        P_BODY,
    ))

    story.append(Spacer(1, 30))

    # Two-column footer: donor signature placeholder + beneficiary stamp
    foot = Table([[
        Paragraph("<b>Pour le donateur</b><br/><br/><br/><br/>_______________________<br/>Signature et cachet", P_BODY),
        Paragraph("<b>Pour la Fondation Espoir Cameroun</b><br/><br/><br/><br/>_______________________<br/>Le Président — M. Eyenga Mbarga", P_BODY),
    ]], colWidths=[8*cm, 8*cm])
    foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(foot)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Fondation Espoir Cameroun · NIU M021800145672K · Agrément N° 0345/MINATD/SG/DAP du 18.07.2019 · "
        "Compte bancaire Afriland First Bank n° 11005-00012-23456789012-58",
        P_FOOT,
    ))

    doc.build(
        story,
        onFirstPage=stamp_on_canvas("FONDATION ESPOIR CM", "#0a7d3e", 16*cm, 5*cm),
    )
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Receipt 2 — NON CONFORME (verdict attendu : NON_ELIGIBLE)
# ─────────────────────────────────────────────────────────────────────────────

def build_non_conforme():
    path = os.path.join(OUT_DIR, "dons_recu_NON_CONFORME.pdf")
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Reçu - Association Loisirs Internationale",
    )

    story = []

    # Header — foreign / non-eligible beneficiary
    story.append(Paragraph("ASSOCIATION LOISIRS INTERNATIONALE", H_ORG))
    story.append(Paragraph(
        "Club privé de loisirs et de relations d'affaires<br/>"
        "Siège social : 12, Avenue des Champs-Élysées — 75008 PARIS, FRANCE<br/>"
        "Tél. : +33 1 42 56 78 90 — contact@loisirs-intl.fr",
        H_SUB,
    ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#8b0000")))
    story.append(Spacer(1, 6))

    # Document title — vague wording on purpose
    story.append(Paragraph("ATTESTATION DE VERSEMENT", H_TITLE))

    # Receipt body — note the deliberate red flags
    story.append(kv_table([
        ("Date d'émission",      "28 décembre 2025"),  # hors exercice 2026
        ("Date de versement",    "28 décembre 2025"),
        ("NIU bénéficiaire",     "<font color='#8b0000'><i>— (organisme non immatriculé au Cameroun)</i></font>"),
        ("RCCM",                 "Non applicable"),
        ("Pays du bénéficiaire", "<font color='#8b0000'><b>FRANCE</b></font>"),
        ("Agrément utilité publique", "<font color='#8b0000'><i>Aucun agrément délivré par les autorités camerounaises</i></font>"),
        ("Nature de l'organisme", "Association privée — activités récréatives, loisirs et networking entre dirigeants"),
    ]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Donateur</b>", P_BODY))
    story.append(kv_table([
        ("Raison sociale",  "KISSYWEARS SARL"),
        ("NIU",             "M105929849503U"),
        ("Adresse",         "Deido, Douala, Cameroun"),
        ("Représenté par",  "<font color='#8b0000'>M. le Gérant et son épouse (séjour personnel à Paris)</font>"),
    ]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Versement reçu</b>", P_BODY))
    story.append(kv_table([
        ("Montant en chiffres",  "<b>2 500 000 FCFA</b>"),
        ("Montant en lettres",   "Deux millions cinq cent mille francs CFA"),
        ("Mode de règlement",    "<font color='#8b0000'><b>Espèces remises de la main à la main</b></font> — aucun justificatif bancaire"),
        ("Bénéficiaire effectif", "Association Loisirs Internationale (compte personnel à Paris)"),
        ("Objet du versement",   "<font color='#8b0000'>Cotisation annuelle au club privé + participation aux frais de réception de fin d'année</font>"),
    ]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "La présente attestation est délivrée à titre de courtoisie au donateur. "
        "L'association ne dispose d'aucune existence légale au Cameroun et "
        "n'est inscrite à aucun registre fiscal local. Le versement a été reçu "
        "en espèces lors du séjour du Gérant à Paris en décembre 2025.",
        P_BODY,
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<font color='#8b0000'><i>Note interne (à ne pas communiquer à l'administration) : "
        "ce versement couvre également les frais d'hébergement et de loisirs "
        "personnels du Gérant lors de son séjour parisien.</i></font>",
        P_BODY,
    ))

    story.append(Spacer(1, 30))

    foot = Table([[
        Paragraph("<b>Pour le donateur</b><br/><br/><br/><br/>_______________________<br/>Signature manuscrite", P_BODY),
        Paragraph("<b>Pour l'Association Loisirs Internationale</b><br/><br/><br/><br/><i>(aucune signature officielle — attestation sur papier libre)</i>", P_BODY),
    ]], colWidths=[8*cm, 8*cm])
    foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(foot)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Association Loisirs Internationale · 12 Avenue des Champs-Élysées, Paris · "
        "Ni NIU camerounais, ni agrément d'utilité publique, ni justificatif bancaire fourni",
        P_FOOT,
    ))

    doc.build(story)  # No official stamp — deliberate
    return path


if __name__ == "__main__":
    p1 = build_conforme()
    p2 = build_non_conforme()
    print(f"OK  : {p1}")
    print(f"KO  : {p2}")
