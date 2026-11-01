# Courbes de taux EUR multi-courbes et pricer de swaps

Bootstrapper une courbe d'actualisation €STR et une courbe de projection EURIBOR 6M, pricer un portefeuille
de swaps (DV01, risques par pilier, PnL explain), le tout reproduit à l'identique par QuantLib.

Fiche projet : `projets-cv/fiches/pdf/09-courbes-taux-swaps.pdf` (dossier Application Linkedin).

## Avancement

| # | Étape | État |
|---|-------|------|
| 1 | Moteur de dates comparé jour par jour à QuantLib (2000-2060) | fait |
| 2 | Données BCE, reconstitution, `hypotheses.md` | à faire |
| 3 | Courbe €STR log-linéaire, Newton global | à faire |
| 4 | Banc QuantLib €STR (écarts < 1e-10 en CI) | à faire |
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

## Lancer les tests

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Outils gratuits et open source uniquement (Python, NumPy, QuantLib, pytest).
