# NSS ajusté aux zéros bootstrapés (Hagan-West)

255 jours de cotations bruitées ; contrôle sans bruit un jour sur dix (26 jours). Ajustement aux zéros des piliers, poids égaux.

| Courbe | Cotations | RMSE moyen (bp) | RMSE max (bp) | Résidu max (bp) |
|---|---|---|---|---|
| €STR | bruité | 0.55 | 1.86 | 6.17 |
| 6M | bruité | 0.67 | 1.87 | 6.02 |
| €STR | sans bruit | 0.44 | 1.61 | 5.46 |
| 6M | sans bruit | 0.50 | 1.70 | 5.34 |

Stabilité jour à jour (cotations bruitées) : écart-type des variations quotidiennes, en bp, et nombre de jours où un λ varie de plus de 50 %.

| Courbe | Δ zéro 10Y | Δ β0 (niveau) | Δ β1 (−pente) | Δ β2 (courbure) | Δ β3 | sauts de λ |
|---|---|---|---|---|---|---|
| €STR | 3.4 | 52.8 | 52.9 | 50.6 | 211.6 | 19 |
| 6M | 3.5 | 75.8 | 76.6 | 82.0 | 288.9 | 32 |

Extrapolation à 40 ans, NSS moins forward plat prolongé (bp) : €STR moyenne -5.5, min -16.6, max +15.9 ; 6M moyenne -5.7, min -17.3, max +15.9
