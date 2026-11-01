# Courbes de taux EUR multi-courbes et pricer de swaps

Bootstrapper une courbe d'actualisation €STR et une courbe de projection EURIBOR 6M, pricer un portefeuille
de swaps (DV01, risques par pilier, PnL explain), le tout reproduit à l'identique par QuantLib.

Fiche projet : `projets-cv/fiches/pdf/09-courbes-taux-swaps.pdf` (dossier Application Linkedin).

## Avancement

| # | Étape | État |
|---|-------|------|
| 1 | Moteur de dates comparé jour par jour à QuantLib (2000-2060) | fait |
| 2 | Données BCE, reconstitution, `hypotheses.md` | fait |
| 3 | Courbe €STR log-linéaire, Newton global | fait |
| 4 | Banc QuantLib €STR (écarts < 1e-10 en CI) | fait |
| 5 | Courbe EURIBOR 6M + banc QuantLib | à faire |
| 6 | Hagan-West + leave-one-out | à faire |
| 7 | NSS | à faire |
| 8 | Pricer, buckets, couverture, IRRBB | à faire |
| 9 | PnL explain | à faire |
| 10 | Démo, rapport, LinkedIn | à faire |

## Moteur de dates (`courbes/dates.py`)

- Calendrier **TARGET2** (week-ends, 1er janvier, Vendredi saint, lundi de Pâques, 1er mai, 25 et 26 décembre).
- Conventions de jour ouvré : following, modified following, preceding, modified preceding, non ajusté.
- Ténors (`"2D"`, `"1W"`, `"6M"`, `"10Y"`) avec règle de fin de mois.
- Décompte des jours : ACT/360, ACT/365F, 30/360 Bond Basis.
- Échéanciers générés à rebours depuis la maturité (stub court en tête), avec ou sans fin de mois.

**Validation** (`tests/test_dates.py`, 48 tests) : comparaison à QuantLib sur chaque jour de 2000 à 2060
(jours ouvrés, ajustements, fins de mois), sur des milliers de ténors, de paires de dates et
d'échéanciers tirés au hasard (graine fixe). Aucun écart toléré.

Écart de comportement noté : avec la règle de fin de mois, QuantLib 1.44 ajuste les dates intermédiaires
à partir du dernier jour *calendaire* du mois ; en convention following, un 31 octobre tombant un dimanche
devient donc le 1er novembre. Le moteur reproduit ce comportement.

## Données (`courbes/donnees.py`, `courbes/cotations.py`)

> Niveaux reconstitués le 01/11/2026 ; validation QuantLib indépendante de la provenance ; études d'interpolation
> et PnL explain sur données synthétiques.

`data/cotations.csv` contient un an de cotations quotidiennes (€STR, OIS 1W-30Y, dépôt 6M, FRA, IRS 2Y-30Y contre
6M). Elles sont reconstituées à partir de séries BCE gratuites (courbe AAA, €STR, EURIBOR 6M mensuel), car aucune
source gratuite ne publie de cotations de swaps. Méthode, hypothèses et impact estimé : [`hypotheses.md`](hypotheses.md).
Le même format accepte de vraies cotations (`source = reel`).

## Courbe €STR (`courbes/curves.py`, `courbes/instruments.py`)

- Inconnues : x_k = ln P(T_k), un pilier par OIS (dernière date pertinente = dernier paiement, J+1 ouvré).
- Interpolation log-linéaire en t = ACT/365F, forward constant au-delà du dernier pilier.
- **Newton global** à jacobien analytique : la courbe renvoie des nombres duaux (valeur + gradient) que les
  formules des instruments propagent exactement. Arrêt à max|taux implicite − cotation| < 1e-13.
- Le jacobien dR/dx est conservé pour les risques par pilier (étape 8).

**Validation** (`tests/test_curves.py`) :
- repricing au pair à moins de 1e-13 sur un jour sur dix de l'année de cotations ;
- jacobien égal aux différences finies à 1e-6 près ;
- sur cotations non bruitées, la courbe retombe sur la courbe génératrice aux piliers (~1e-6 jusqu'à 10 ans).
  Entre deux piliers éloignés (25-30 ans), le log-linéaire s'en écarte jusqu'à ~2e-3 en DF : c'est ce que
  l'étape 6 doit mesurer.

**Banc QuantLib** (`tests/test_quantlib_estr.py`, écart toléré 1e-10) : la même courbe est construite avec
`OISRateHelper` (spot 2, paiement J+1 MF TARGET, fin de mois, pilier `LastRelevantDate`) et
`PiecewiseLogLinearDiscount` en ACT/365F (précision du bootstrap 1e-14). Les jours testés sont un sur dix, tous ceux dont le
spot tombe en fin de mois, et le dernier. Pour chacun, le banc compare :
- les piliers ;
- les facteurs d'actualisation sur 500 dates jusqu'à 40 ans ;
- les taux au pair des instruments de calage ;
- 200 OIS aléatoires (`MakeOIS.fairRate`, départ décalé jusqu'à 5 ans, ténor de 1W à 30Y).

Deux conventions comptent pour obtenir des écarts de l'ordre de 1e-15 :
- l'échéancier se génère depuis la maturité **non ajustée** (spot + ténor) ;
- quand le spot est un dernier jour ouvré du mois, la maturité est reportée au dernier jour du mois (règle de fin de mois).

## Lancer les tests

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Outils gratuits et open source uniquement (Python, NumPy, pandas, QuantLib, pytest) et données publiques BCE.
