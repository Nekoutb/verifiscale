"""Génère 3 contrats d'assurance PDF pour tester le module « Primes d'assurance ».

  1. contrat_CONFORME.pdf        → ELIGIBLE
     Multirisque magasin, assureur LOCAL (CM), bénéficiaire = entreprise.

  2. contrat_VIE_DIRIGEANT.pdf   → NON_ELIGIBLE
     Assurance-vie au profit du Gérant / sa famille = avantage en nature.

  3. contrat_ASSUREUR_ETRANGER.pdf → NON_ELIGIBLE + flag TSR
     Assurance santé du personnel souscrite auprès d'un assureur FRANÇAIS
     (Art. 7 A 4 exige une compagnie LOCALE pour la santé personnel).
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.flowables import HRFlowable

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
styles = getSampleStyleSheet()

H_ORG = ParagraphStyle("HOrg", parent=styles["Title"], fontSize=16, alignment=TA_CENTER, spaceAfter=2)
H_SUB = ParagraphStyle("HSub", parent=styles["Normal"], fontSize=8.5, alignment=TA_CENTER, textColor=colors.grey)
H_TITLE = ParagraphStyle("HTitle", parent=styles["Heading1"], fontSize=13, alignment=TA_CENTER, spaceBefore=10, spaceAfter=10, textColor=colors.HexColor("#1e3a5f"))
P_LBL = ParagraphStyle("PLbl", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
P_VAL = ParagraphStyle("PVal", parent=styles["Normal"], fontSize=11, leading=14)
P_BODY = ParagraphStyle("PBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
P_FOOT = ParagraphStyle("PFoot", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER, textColor=colors.grey)


def kv(rows, w=(6 * cm, 10.5 * cm)):
    data = [[Paragraph(l, P_LBL), Paragraph(v, P_VAL)] for l, v in rows]
    t = Table(data, colWidths=w)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_contract(path, *, insurer_name, insurer_niu, insurer_country, insurer_addr,
                   police_no, type_label, souscripteur, beneficiaire, beneficiaire_desc,
                   date_debut, date_fin, prime, objet, clause, test_note):
    doc = SimpleDocTemplate(
        path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Police {police_no} - {insurer_name}",
    )
    story = []
    story.append(Paragraph(insurer_name, H_ORG))
    story.append(Paragraph(
        f"Compagnie d'assurances<br/>{insurer_addr}<br/>"
        + (f"NIU : {insurer_niu}" if insurer_niu else "(NIU non communiqué)"),
        H_SUB,
    ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#1e3a5f")))
    story.append(Paragraph(f"CONTRAT D'ASSURANCE — POLICE N° {police_no}", H_TITLE))

    story.append(kv([
        ("Compagnie (assureur)", insurer_name),
        ("Pays de l'assureur", insurer_country),
        ("Type de garantie", type_label),
        ("Souscripteur", souscripteur),
        ("Bénéficiaire", beneficiaire),
        ("Précision bénéficiaire", beneficiaire_desc),
        ("Période de couverture", f"du {date_debut} au {date_fin}"),
        ("Prime annuelle TTC", f"<b>{prime:,.0f} FCFA</b>".replace(",", " ")),
    ]))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Objet du contrat</b>", P_BODY))
    story.append(Paragraph(objet, P_BODY))
    if clause:
        story.append(Paragraph("<b>Clause particulière</b>", P_BODY))
        story.append(Paragraph(clause, P_BODY))

    story.append(Spacer(1, 30))
    foot = Table([[
        Paragraph("<b>Le souscripteur</b><br/><br/><br/>______________________", P_BODY),
        Paragraph(f"<b>Pour {insurer_name}</b><br/><br/><br/>______________________<br/>L'agent général", P_BODY),
    ]], colWidths=[8 * cm, 8 * cm])
    foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(foot)
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"<font color='#8b0000'><i>— DOCUMENT FICTIF DE TEST FISCAUDIT PRO — {test_note} —</i></font>",
        P_FOOT,
    ))
    doc.build(story)
    return path


def main():
    files = []

    # 1 — CONFORME : multirisque, assureur local, bénéficiaire entreprise
    files.append(build_contract(
        os.path.join(OUT_DIR, "contrat_CONFORME.pdf"),
        insurer_name="ACTIVA ASSURANCES CAMEROUN SA",
        insurer_niu="M029800123456P",
        insurer_country="Cameroun (CM)",
        insurer_addr="Boulevard de la Liberté, Akwa, Douala, Cameroun",
        police_no="MR-2026-00412",
        type_label="Assurance multirisque professionnelle (incendie, vol, dégâts des eaux)",
        souscripteur="KISSYWEARS SARL — NIU M105929849503U",
        beneficiaire="KISSYWEARS SARL",
        beneficiaire_desc="L'entreprise souscriptrice elle-même",
        date_debut="01/01/2026", date_fin="31/12/2026",
        prime=850_000,
        objet="Couverture des locaux commerciaux, du stock de marchandises et "
              "du mobilier contre l'incendie, le vol et les dégâts des eaux. La "
              "réalisation du risque entraîne une diminution directe de l'actif net.",
        clause=None,
        test_note="cas CONFORME → ELIGIBLE attendu",
    ))

    # 2 — NON ELIGIBLE : assurance-vie dirigeant
    files.append(build_contract(
        os.path.join(OUT_DIR, "contrat_VIE_DIRIGEANT.pdf"),
        insurer_name="CHANAS ASSURANCES SA",
        insurer_niu="M030700654321Q",
        insurer_country="Cameroun (CM)",
        insurer_addr="Rue Joss, Douala, Cameroun",
        police_no="VIE-2026-00098",
        type_label="Assurance-vie individuelle (capital décès + épargne)",
        souscripteur="KISSYWEARS SARL",
        beneficiaire="M. le Gérant et son épouse",
        beneficiaire_desc="Le dirigeant à titre personnel et sa famille (capital "
                          "versé aux ayants droit en cas de décès)",
        date_debut="01/01/2026", date_fin="31/12/2026",
        prime=1_200_000,
        objet="Constitution d'une épargne et versement d'un capital décès au "
              "profit personnel du Gérant et de sa famille.",
        clause="Le capital est versé directement aux bénéficiaires désignés "
               "(conjoint, enfants) et non à l'entreprise.",
        test_note="cas avantage en nature dirigeant → NON_ELIGIBLE attendu",
    ))

    # 3 — NON ELIGIBLE : assureur étranger, santé personnel
    files.append(build_contract(
        os.path.join(OUT_DIR, "contrat_ASSUREUR_ETRANGER.pdf"),
        insurer_name="AXA FRANCE IARD SA",
        insurer_niu=None,
        insurer_country="France (FR)",
        insurer_addr="313 Terrasses de l'Arche, 92727 Nanterre Cedex, France",
        police_no="SANTE-INT-2026-7741",
        type_label="Assurance santé collective du personnel",
        souscripteur="KISSYWEARS SARL",
        beneficiaire="Personnel de KISSYWEARS SARL",
        beneficiaire_desc="Ensemble des salariés et leurs ayants droit",
        date_debut="01/01/2026", date_fin="31/12/2026",
        prime=2_500_000,
        objet="Couverture des frais médicaux du personnel auprès d'un assureur "
              "non agréé au Cameroun (souscription directe en France).",
        clause="Prime versée par virement international à AXA France. Aucune "
               "retenue à la source pratiquée par le souscripteur.",
        test_note="assureur étranger + santé personnel → NON_ELIGIBLE + flag TSR attendu",
    ))

    print(f"3 contrats générés dans {OUT_DIR} :")
    for f in files:
        print(f"  - {os.path.basename(f)}")


if __name__ == "__main__":
    main()
