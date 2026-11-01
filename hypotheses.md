# Hypothèses de données

> **Niveaux reconstitués le 01/11/2026** à partir de séries publiques BCE. La validation contre QuantLib ne dépend
> pas de la provenance des cotations ; les études d'interpolation et le PnL explain portent sur des données
> synthétiques. Le fichier accepte aussi de vraies cotations (`source = reel`).

## Pourquoi reconstituer

Aucune source gratuite ne publie de cotations de swaps EUR (OIS €STR, IRS contre EURIBOR 6M). Les seules
données libres sont celles de la BCE. Les cotations de `data/cotations.csv` en sont donc **reconstituées**.
Elles ont des niveaux et une dynamique réalistes, mais ce ne sont pas des prix de marché.

## Sources (API gratuite data-api.ecb.europa.eu, cache versionné dans `data/bce/`)

| Série | Code BCE | Usage |
|-------|----------|-------|
| €STR | `EST.B.EU000A2X2A25.WT` | fixing ON, ancrage du court terme |
| Courbe AAA zone euro (Svensson) | `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.BETA0…BETA3, TAU1, TAU2` | forme de la courbe |
| Taux zéro AAA 1 an et 10 ans | `…SV_C_YM.SR_1Y`, `…SR_10Y` | contrôle de la formule de Svensson |
| EURIBOR 6M, moyenne mensuelle | `FM.M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA` | ancrage de la base 6M |
| Facilité de dépôt | `FM.D.U2.EUR.4F.KR.DFR.LEV` | contrôle de cohérence de l'€STR |

Fenêtre : 255 jours de cotation, du 30/10/2025 au 29/10/2026. Ce sont les jours où la courbe AAA et l'€STR sont
tous deux publiés.

## Reconstitution, étape par étape

1. **Courbe d'actualisation €STR.**
   - On part du zéro AAA de Svensson (composition continue).
   - On lui ajoute l'écart entre l'€STR (converti en composition continue) et le zéro AAA instantané (β0 + β1).
   - Cet écart s'éteint en exp(−t / 1 an).
   - Ainsi, le court terme colle à l'€STR et le long terme reste la courbe AAA.
2. **Cotations OIS** (1W à 30Y), calculées au pair avec les vraies conventions.
   - Départ spot T+2.
   - Un seul flux jusqu'à 1 an, puis des flux annuels.
   - Décompte ACT/360.
   - Convention MF avec règle de fin de mois.
   - Paiement décalé d'un jour ouvré.
3. **Base EURIBOR 6M − OIS** : elle vaut, chaque mois, la moyenne mensuelle BCE de l'EURIBOR 6M moins la moyenne
   du forward OIS 6M reconstitué sur les mêmes jours.
   - La base est la même pour toutes les maturités et constante dans le mois.
   - Octobre 2026 n'est pas encore publié : on y garde la base de septembre.
4. **Cotations EURIBOR 6M** : forward OIS + base.
   - Dépôt 6M.
   - FRA de 1x7 à 18x24.
   - IRS de 2Y à 30Y : fixe annuel 30/360, variable semestriel ACT/360, MF, échéancier à rebours.
5. **Bruit et événement.**
   - Bruit gaussien, avec une graine fixe (20261101) et un écart-type par instrument :
     - OIS : 0,2 bp ;
     - IRS : 0,3 bp ;
     - FRA : 0,4 bp ;
     - dépôt : 0,5 bp.
   - Saut de base de +2,5 bp sur l'IRS 10Y pendant 5 jours de cotation, à partir du 04/05/2026. Il sert à tester
     la détection d'anomalies et le PnL explain.
   - Le fixing €STR est la donnée publiée, non bruitée.

## Hypothèses et leur impact estimé

| Hypothèse | Validable ? | Impact estimé |
|-----------|-------------|---------------|
| Courbe €STR = courbe AAA + écart court terme éteint en 1 an | **Non** : pas de cotations OIS gratuites | Écart moyen sur l'année : +2,4 bp à 3 mois, +1,1 bp à 1 an, +0,4 bp à 2 ans, nul au-delà de 5 ans. Extrêmes : −14,4 / +19,5 bp à 3 mois. Au-delà de 5 ans, la courbe OIS est la courbe souveraine AAA ; en réalité, l'écart swap-souverain long terme vaut quelques dizaines de bp. |
| Base 6M plate en maturité, constante dans le mois | Partiellement : la moyenne mensuelle du dépôt 6M reconstitué retombe sur l'EURIBOR BCE (testé) | Base mensuelle entre 14,0 et 26,8 bp. En réalité, la structure par terme de la base est absente et la base saute au changement de mois. |
| Forward EURIBOR pris sur la période de calcul, pas sur la période de fixing (J−2) | Oui, en ordre de grandeur | Moins de 0,1 bp |
| Fenêtre = jours où la courbe AAA et l'€STR sont tous deux publiés | Oui | Aucun impact sur les niveaux |

Contrôles automatiques (`tests/test_cotations.py`) :
- la formule de Svensson reproduit les zéros BCE 1 an et 10 ans à 1e-6 % près ;
- l'€STR reste entre 0 et 15 bp sous la facilité de dépôt ;
- la base IRS − OIS reste positive et inférieure à 40 bp ;
- la régénération reproduit le fichier versionné à l'identique ;
- les fichiers mal formés sont rejetés.

## Régénérer

```bash
python -m courbes.cotations   # réécrit data/cotations.csv et affiche les chiffres ci-dessus
```

Pour retélécharger les séries BCE : `from courbes.donnees import SERIES, serie; [serie(n, refresh=True) for n in SERIES]`.
