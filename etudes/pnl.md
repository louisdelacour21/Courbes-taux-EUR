# PnL explain quotidien, 2025-10-31 → 2026-10-29 (254 jours)

**Marché synthétique** : cotations reconstituées depuis la BCE et bruitées (0,2 à 0,5 bp), fixings EURIBOR 6M reconstitués (cotation DEPOT 6M du jour). La composante fixings est construite par hypothèse. Ce résultat valide la mécanique de décomposition, pas un comportement de marché.

| Composante | Moyenne (EUR) | Moyenne des valeurs absolues (EUR) | Max absolu (EUR) |
|---|---:|---:|---:|
| total | 1 404 | 110 972 | 478 072 |
| portage | 367 | 385 | 1 510 |
| fixings | 0 | 2 | 163 |
| delta | -2 819 | 110 920 | 473 019 |
| gamma | -465 | 465 | 9 668 |
| residuel | 4 319 | 5 468 | 62 247 |

- Résiduel moyen en valeur absolue : 4,93% du PnL moyen en valeur absolue ; médiane jour par jour de |résiduel| / |PnL| : 3,15% ; variance expliquée 1 − var(résiduel) / var(PnL) : 99,6345%.
- Pire jour : 2026-05-04 (résiduel 62 247 EUR, PnL 244 111 EUR).
- **Origine du résiduel** : la non-dérivabilité de Hagan-West. Sa monotone convexe change de région quand les cotations bougent, V n'est pas lisse et le développement au premier ordre décroche (le 2026-08-06, la pente le long du chemin q_c → q1 passe de −54 610 à +9 128 EUR pour un mouvement d'environ 1 bp). Témoin log-linéaire, mêmes jours : |résiduel| moyen 289 EUR, max 5 366 EUR (0,26% du PnL moyen en valeur absolue).
- Jours de fixing (composante non nulle) : 7.
- Saut de base IRS 10Y (+2,5 bp à partir du 2026-05-04, 5 jours) : |résiduel| max 62 247 EUR ces jours-là. Un mouvement isolé d'une cotation déplace la courbe Hagan-West hors de sa région, d'où le pire jour de l'année.
- Temps de calcul : 631 s pour 254 jours (2,5 s par jour, Hagan-West, cinq constructions de courbes par jour).

Série complète : [`pnl_serie.csv`](pnl_serie.csv).
