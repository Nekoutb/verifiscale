"""Generate a realistic SYSCOHADA trial balance for the first seeded audit case.

This makes the demo immediately runnable — you can launch the controls without
uploading any file.
"""
from __future__ import annotations

from decimal import Decimal

# (code, name, openD, openC, periodD, periodC, closeD, closeC)
SAMPLE_TB: list[tuple] = [
    ("101000", "Capital social",                        0,         200000000, 0,         0,         0,         200000000),
    ("106000", "Réserves",                              0,         45000000,  0,         12000000,  0,         57000000),
    ("121000", "Report à nouveau bénéficiaire",          0,         15000000,  0,         0,         0,         15000000),
    ("129000", "Report à nouveau déficitaire (N-5)",    8500000,   0,         0,         0,         8500000,   0),
    ("131000", "Résultat net de l'exercice",            0,         0,         0,         18420000,  0,         18420000),
    ("161000", "Emprunts auprès des établissements de crédit", 0,  80000000,  25000000,  0,         0,         55000000),
    ("211000", "Terrains",                              35000000,  0,         0,         0,         35000000,  0),
    ("231000", "Bâtiments",                             120000000, 0,         8500000,   0,         128500000, 0),
    ("2831000","Amortissements bâtiments",              0,         42000000,  0,         6420000,   0,         48420000),
    ("311000", "Marchandises",                          24500000,  0,         168400000, 165200000, 27700000,  0),
    ("401000", "Fournisseurs",                          0,         34500000,  182300000, 201800000, 0,         54000000),
    ("411000", "Clients",                               67800000,  0,         312400000, 285600000, 94600000,  0),
    ("4311000","CNPS à payer",                          0,         3100000,   18400000,  19200000,  0,         3900000),
    ("4431000","TVA facturée (collectée)",              0,         11400000,  48900000,  51200000,  0,         13700000),
    ("4452000","TVA déductible biens et services",      8200000,   0,         31200000,  32800000,  6600000,   0),
    ("4441000","État, impôt sur les sociétés",          0,         14200000,  14200000,  18500000,  0,         18500000),
    ("4471000","État, IRPP retenu sur salaires",        0,         2300000,   24800000,  25900000,  0,         3400000),
    ("478000", "Écart de conversion - actif",            1850000,   0,         0,         0,         1850000,   0),
    ("512000", "Banque - SGC",                           42100000,  0,         298000000, 267500000, 72600000,  0),
    ("571000", "Caisse",                                 1850000,   0,         8400000,   7900000,   2350000,   0),
    ("601000", "Achats de marchandises",                 0,         0,         168400000, 0,         168400000, 0),
    ("604000", "Achats stockés - matières & fournitures",0,         0,         42100000,  0,         42100000,  0),
    ("622000", "Locations et charges locatives",         0,         0,         18000000,  0,         18000000,  0),
    ("627000", "Services bancaires et assimilés",        0,         0,         2800000,   0,         2800000,   0),
    ("641000", "Impôts et taxes directs",                0,         0,         9400000,   0,         9400000,   0),
    ("6478000","Pénalités et amendes fiscales",          0,         0,         1850000,   0,         1850000,   0),
    ("658000", "Subventions accordées et dons",          0,         0,         2400000,   0,         2400000,   0),
    ("661000", "Rémunérations directes du personnel",    0,         0,         74600000,  0,         74600000,  0),
    ("671000", "Intérêts des emprunts",                  0,         0,         4800000,   0,         4800000,   0),
    ("681000", "Dotations aux amortissements d'exploitation", 0,    0,         6420000,   0,         6420000,   0),
    ("701000", "Ventes de marchandises",                 0,         0,         0,         298400000, 0,         298400000),
    ("706000", "Services vendus",                        0,         0,         0,         46200000,  0,         46200000),
    ("771000", "Revenus financiers",                     0,         0,         0,         1800000,   0,         1800000),
]
