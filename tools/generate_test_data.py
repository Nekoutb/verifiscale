# -*- coding: utf-8 -*-
"""Generate 3 coherent test companies × every dataset the tool ingests.

Output: C:\\Users\\UltraBook 3.1\\Documents\\FiscAudit Test Data\\<COMPANY>\\
Files per company: balance générale (6 col), grand-livre, balance âgée
fournisseurs, balance âgée clients, registre des immobilisations (rollforward),
inventaire, relevé bancaire. Internally coherent: TB balanced, GL debit=credit,
GL carries classe-66 lines that exercise the Art. 7 A 1 module (jetons,
allocations forfaitaires, chasse/bateau, retraite expatrié).
"""
import os
import random
from datetime import date

import openpyxl

OUT = r"C:\Users\UltraBook 3.1\Documents\FiscAudit Test Data"
YEAR = 2025

COMPANIES = [
    ("SOTRACAM SA",        "M021700111222A", 1.00),
    ("BOULANGERIE DU MFOUNDI SARL", "M021800333444B", 0.35),
    ("TECHNIPLUS CAMEROUN", "M021900555666C", 2.40),
]

def w(path, header, rows, title=None):
    wb = openpyxl.Workbook(); ws = wb.active
    if title: ws.append([title]); ws.append([])
    ws.append(header)
    for r in rows: ws.append(r)
    wb.save(path)

def gen_company(name, niu, k):
    d = os.path.join(OUT, name.replace(" ", "_"))
    os.makedirs(d, exist_ok=True)
    M = lambda v: round(v * k)
    rnd = random.Random(niu)

    # ── Grand livre ─────────────────────────────────────────────────────────
    gl = []
    piece = 0
    def entry(jr, dt, lines):
        nonlocal piece; piece += 1
        pid = f"{jr}/{YEAR}/{piece:05d}"
        for code, nm, lib, dr, cr in lines:
            gl.append([code, nm, f"{pid} {lib}", dt, dr or None, cr or None])
    # ventes mensuelles + achats + salaires
    for m in range(1, 13):
        dt = date(YEAR, m, 25).isoformat()
        ca = M(12_000_000) + rnd.randint(0, M(3_000_000))
        entry("VTE", dt, [("411100", "Clients", f"Ventes {m:02d}/{YEAR}", round(ca*1.1925), 0),
                          ("701100", "Ventes de marchandises", f"Ventes {m:02d}/{YEAR}", 0, ca),
                          ("443100", "TVA collectée", f"TVA {m:02d}", 0, round(ca*0.1925))])
        ach = M(5_000_000) + rnd.randint(0, M(1_500_000))
        entry("ACH", dt, [("601100", "Achats de marchandises", f"Achats {m:02d}", ach, 0),
                          ("445200", "TVA déductible", f"TVA {m:02d}", round(ach*0.1925), 0),
                          ("401100", "Fournisseurs", f"Achats {m:02d}", 0, round(ach*1.1925))])
        sal = M(3_200_000)
        entry("PAI", dt, [("661100", "Rémunérations personnel national", f"Salaires {m:02d}/{YEAR}", sal, 0),
                          ("664100", "Charges sociales CNPS", f"CNPS {m:02d}", round(sal*0.169), 0),
                          ("421100", "Personnel — rémunérations dues", f"Salaires {m:02d}", 0, sal + round(sal*0.169))])
    # lignes 7A1 « pièges »
    entry("OD", date(YEAR, 6, 30).isoformat(), [
        ("658100", "Charges diverses", "Jetons de présence CA — 1er semestre", M(6_000_000), 0),
        ("471100", "Débiteurs divers", "Jetons de présence", 0, M(6_000_000))])
    entry("OD", date(YEAR, 7, 15).isoformat(), [
        ("663100", "Indemnités forfaitaires", "Allocation forfaitaire de représentation DG", M(4_800_000), 0),
        ("421100", "Personnel", "Alloc DG", 0, M(4_800_000))])
    entry("OD", date(YEAR, 8, 20).isoformat(), [
        ("663200", "Indemnités forfaitaires", "Frais de déplacement remboursés sur justificatifs DG", M(2_100_000), 0),
        ("421100", "Personnel", "Remb DG", 0, M(2_100_000))])
    entry("OD", date(YEAR, 9, 10).isoformat(), [
        ("662100", "Rémunérations personnel non national", "Cotisation retraite expatrié versée à l'étranger (CFE)", M(5_400_000), 0),
        ("421200", "Personnel expatrié", "Retraite exp", 0, M(5_400_000))])
    entry("OD", date(YEAR, 10, 5).isoformat(), [
        ("661900", "Autres rémunérations", "Location bateau de plaisance séminaire direction", M(3_500_000), 0),
        ("571100", "Caisse", "Bateau", 0, M(3_500_000))])
    # intérêts associé + immobilisation + dotation
    entry("OD", date(YEAR, 12, 31).isoformat(), [
        ("671300", "Intérêts des dettes liées aux participations", "Intérêts CC associé NGUEMA", M(2_400_000), 0),
        ("462100", "Comptes courants associés", "Intérêts CC", 0, M(2_400_000))])

    # ── Comptes 46 : le compte passe DÉBITEUR (avance à l'associé) ──────────
    entry("OD", date(YEAR, 5, 12).isoformat(), [
        ("462100", "Comptes courants associés", "Avance de trésorerie à l'associé NGUEMA", M(9_000_000), 0),
        ("521100", "Banque", "Avance associé", 0, M(9_000_000))])
    entry("OD", date(YEAR, 8, 22).isoformat(), [
        ("521100", "Banque", "Remboursement partiel associé", M(6_000_000), 0),
        ("462100", "Comptes courants associés", "Remboursement associé", 0, M(6_000_000))])
    # paire qui s'annule (détection contrepassation)
    entry("OD", date(YEAR, 9, 5).isoformat(), [
        ("462100", "Comptes courants associés", "Écriture à contrepasser", M(1_750_000), 0),
        ("521100", "Banque", "Écriture à contrepasser", 0, M(1_750_000))])
    entry("OD", date(YEAR, 9, 6).isoformat(), [
        ("521100", "Banque", "Contrepassation", M(1_750_000), 0),
        ("462100", "Comptes courants associés", "Contrepassation", 0, M(1_750_000))])

    # ── Comptes divers 4711 / 4712 : tiers non identifiés ───────────────────
    entry("OD", date(YEAR, 3, 18).isoformat(), [
        ("471100", "Débiteurs divers", "Décaissement tiers non identifié", M(1_500_000), 0),
        ("571100", "Caisse", "Décaissement divers", 0, M(1_500_000))])
    entry("OD", date(YEAR, 4, 9).isoformat(), [
        ("521100", "Banque", "Encaissement d'origine inconnue", M(2_300_000), 0),
        ("471200", "Créditeurs divers", "Encaissement tiers non identifié", 0, M(2_300_000))])

    # ── Provisions : dotations (69XX) et reprises (79XX) ────────────────────
    entry("OD", date(YEAR, 12, 31).isoformat(), [
        ("691000", "Dotations aux provisions d'exploitation", "Dotation dépréciation stocks", M(1_500_000), 0),
        ("391000", "Provisions dépréciation des stocks", "Dotation dépréciation stocks", 0, M(1_500_000))])
    entry("OD", date(YEAR, 12, 31).isoformat(), [
        ("419100", "Provisions créances douteuses", "Reprise provision client soldé", M(1_000_000), 0),
        ("791000", "Reprises de provisions d'exploitation", "Reprise provision client soldé", 0, M(1_000_000))])
    entry("OD", date(YEAR, 3, 1).isoformat(), [
        ("244100", "Matériel et outillage", "Acquisition machine conditionnement", M(18_000_000), 0),
        ("404100", "Fournisseurs d'immobilisations", "Machine", 0, M(18_000_000))])
    entry("OD", date(YEAR, 12, 31).isoformat(), [
        ("681200", "Dotations amortissements", f"Dotation {YEAR}", M(6_550_000), 0),
        ("284410", "Amortissements matériel", f"Dotation {YEAR}", 0, M(6_550_000))])
    w(os.path.join(d, f"grand_livre_{YEAR}.xlsx"),
      ["Compte", "Intitulé du compte", "Libellé", "Date", "Débit", "Crédit"],
      gl, f"GRAND LIVRE — {name} — EXERCICE {YEAR}")

    # ── Balance 6 colonnes (équilibrée par construction: dérivée du GL) ─────
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0])
    names = {}
    for code, nm, _lib, _dt, dr, cr in gl:
        agg[code][0] += dr or 0; agg[code][1] += cr or 0; names[code] = nm
    opening = {"101100": (0, M(50_000_000)), "244100": (M(30_000_000), 0),
               "284410": (0, M(12_000_000)), "311100": (M(9_000_000), 0),
               "411100": (M(7_500_000), 0), "401100": (0, M(6_200_000)),
               "521100": (M(21_700_000), 0),
               # comptes d'associés : créditeur à l'ouverture (position normale)
               "462100": (0, M(5_000_000)),
               # provisions à l'ouverture (rollforward)
               "391000": (0, M(3_000_000)), "419100": (0, M(2_000_000))}
    tb_rows = []
    codes = sorted(set(list(agg.keys()) + list(opening.keys())))
    for c in codes:
        od, oc = opening.get(c, (0, 0))
        md, mc = agg.get(c, (0, 0))
        cd, cc_ = od + md, oc + mc
        net = cd - cc_
        tb_rows.append([c, names.get(c, "Compte " + c), od or None, oc or None,
                        md or None, mc or None,
                        net if net > 0 else None, -net if net < 0 else None])
    # équilibre l'ouverture via 121 report à nouveau
    od_sum = sum(r[2] or 0 for r in tb_rows); oc_sum = sum(r[3] or 0 for r in tb_rows)
    if od_sum != oc_sum:
        diff = od_sum - oc_sum
        tb_rows.append(["121100", "Report à nouveau", None if diff > 0 else -diff,
                        diff if diff > 0 else None, None, None,
                        None if diff > 0 else -diff, diff if diff > 0 else None])
    w(os.path.join(d, f"balance_generale_{YEAR}.xlsx"),
      ["Compte", "Intitulé", "Ouverture Débit", "Ouverture Crédit",
       "Mouvements Débit", "Mouvements Crédit", "Clôture Débit", "Clôture Crédit"],
      tb_rows, f"BALANCE GÉNÉRALE — {name} — {YEAR}")

    # ── Balances âgées ──────────────────────────────────────────────────────
    w(os.path.join(d, f"balance_agee_fournisseurs_{YEAR}.xlsx"),
      ["Fournisseur", "NIU", "Total dû", "0-30 j", "31-60 j", "61-90 j", "> 90 j"],
      [["ENEO CAMEROON SA", "M021500987654B", M(2_800_000), M(1_800_000), M(600_000), M(400_000), 0],
       ["CIMENCAM SA", "M021700333444D", M(2_100_000), M(900_000), M(700_000), 0, M(500_000)],
       ["QUINCAILLERIE BEN ETS", "P021800555666E", M(1_300_000), M(1_300_000), 0, 0, 0]],
      f"BALANCE ÂGÉE FOURNISSEURS — {name} — 31/12/{YEAR}")
    w(os.path.join(d, f"balance_agee_clients_{YEAR}.xlsx"),
      ["Client", "NIU", "Total à recevoir", "0-30 j", "31-60 j", "61-90 j", "> 90 j"],
      [["SUPERMARCHÉS MAHIMA", "M021600777888F", M(4_200_000), M(2_500_000), M(1_000_000), M(700_000), 0],
       ["HÔTEL LA FALAISE", "M021500222333G", M(2_900_000), M(1_400_000), M(900_000), 0, M(600_000)]],
      f"BALANCE ÂGÉE CLIENTS — {name} — 31/12/{YEAR}")

    # ── Registre des immobilisations (rollforward) ──────────────────────────
    w(os.path.join(d, f"registre_immobilisations_{YEAR}.xlsx"),
      ["N° de compte", "N° immobilisation", "Désignation", "Date d'acquisition", "Date de cession",
       "Valeur brute à l'ouverture", "Acquisitions", "Cessions", "Transferts", "Valeur brute à la clôture",
       "Amort. cumulés à l'ouverture", "Dotation de la période", "Amort. repris sur cessions",
       "Amort. transférés", "Amort. cumulés en fin de période", "VNC à l'ouverture", "VNC à la clôture", "Taux"],
      [["244100", "IMM-001", "Ligne de production A", f"{YEAR-3}-05-10", None,
        M(30_000_000), 0, 0, 0, M(30_000_000),
        M(12_000_000), M(3_000_000), 0, 0, M(15_000_000), M(18_000_000), M(15_000_000), 0.10],
       ["244100", "IMM-002", "Machine conditionnement", f"{YEAR}-03-01", None,
        0, M(18_000_000), 0, 0, M(18_000_000),
        0, M(1_500_000), 0, 0, M(1_500_000), 0, M(16_500_000), 0.10],
       ["245100", "IMM-003", "Camionnette de livraison", f"{YEAR-2}-08-01", None,
        M(8_200_000), 0, 0, 0, M(8_200_000),
        M(4_100_000), M(2_050_000), 0, 0, M(6_150_000), M(4_100_000), M(2_050_000), 0.25]],
      f"REGISTRE DES IMMOBILISATIONS — {name} — {YEAR}")

    # ── Inventaire ──────────────────────────────────────────────────────────
    w(os.path.join(d, f"inventaire_{YEAR}.xlsx"),
      ["Référence", "Désignation", "Quantité", "Coût unitaire", "Valeur totale"],
      [["ART-001", "Marchandise A", 1200, M(2_500), 1200 * M(2_500)],
       ["ART-002", "Marchandise B", 640, M(5_800), 640 * M(5_800)],
       ["ART-003", "Emballages", 3000, M(300), 3000 * M(300)]],
      f"ÉTAT D'INVENTAIRE PHYSIQUE — {name} — 31/12/{YEAR}")

    # ── Relevé bancaire ─────────────────────────────────────────────────────
    w(os.path.join(d, f"releve_bancaire_{YEAR}.xlsx"),
      ["Date", "Libellé", "Débit", "Crédit", "Solde"],
      [[f"{YEAR}-01-01", "Solde d'ouverture", None, None, M(21_700_000)],
       [f"{YEAR}-06-15", "Virement clients", None, M(35_000_000), M(56_700_000)],
       [f"{YEAR}-09-20", "Règlements fournisseurs", M(28_400_000), None, M(28_300_000)],
       [f"{YEAR}-12-31", "Solde de clôture", None, None, M(28_300_000)]],
      f"RELEVÉ BANCAIRE — SGC 521100 — {name} — {YEAR}")

    return d

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, niu, k in COMPANIES:
        d = gen_company(name, niu, k)
        n = len(os.listdir(d))
        print(f"{name}: {n} fichiers -> {d}")
    print("OK")
