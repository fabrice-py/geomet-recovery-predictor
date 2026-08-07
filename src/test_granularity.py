"""
test_granularity.py
Test de l'hypothese : l'agregation horaire detruit-elle du signal fin ? Car on veut une
reponse chiffree et non une opinion : ainsi on compare un modele sur donnees agregees a
l'heure a un modele sur donnees fines (20 s) evalue par split PAR GROUPE (heure entiere
d'un seul cote), seul decoupage qui evite la fuite tout en gardant la variation fine.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score

from load_real_data import DATA_PATH
from prepare_ml_data import FEATURE_COLS, TARGET_COL, prepare_ml_data


def evaluate_fine_grained(rows_per_hour=30, random_state=42):
    """
    Evaluation sur donnees fines avec split par groupe, car la granularite fine ne vaut
    que si l'heure reste indivisible entre train et test : ainsi on sous-echantillonne
    chaque heure puis on evalue par GroupKFold ou le groupe est l'heure (anti-fuite).
    """
    df = pd.read_csv(DATA_PATH, decimal=",")
    df.columns = [c.strip() for c in df.columns]

  # Sous-echantillonnage par heure, car 737k lignes seraient trop lentes : ainsi on
    # garde quelques lignes par heure, suffisant pour porter la variation fine. On passe
    # par sample d'index pour ne PAS perdre la colonne date (necessaire comme groupe).
    sampled_idx = (df.groupby("date", group_keys=False)
                     .apply(lambda g: g.sample(min(len(g), rows_per_hour),
                                               random_state=random_state))
                     .index)
    df = df.loc[sampled_idx].reset_index(drop=True)

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]
    groups = df["date"]                      # le groupe = l'heure : indivisible train/test

    gkf = GroupKFold(n_splits=5)
    r2_scores = []
    for train_idx, test_idx in gkf.split(X, y, groups):
        model = RandomForestRegressor(n_estimators=150, random_state=random_state, n_jobs=-1)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[test_idx])
        r2_scores.append(r2_score(y.iloc[test_idx], pred))

    return np.mean(r2_scores), np.std(r2_scores)


if __name__ == "__main__":
    # Modele A : agrege a l'heure (aleatoire), car c'est notre reference actuelle.
    from sklearn.metrics import r2_score as r2s
    Xtr, Xte, ytr, yte = prepare_ml_data(shuffle=True)
    mA = RandomForestRegressor(n_estimators=150, random_state=42, n_jobs=-1)
    mA.fit(Xtr, ytr)
    r2_hourly = r2s(yte, mA.predict(Xte))

    print("=== Test de l'hypothese : granularite fine vs agregation horaire ===\n")
    print(f"Modele A - agrege a l'heure        : R2 = {r2_hourly:.3f}")

    # Modele B : fin, split par groupe (heure indivisible).
    print("\nModele B - fin (20 s), split par groupe (heure indivisible)...")
    print("  (calcul un peu plus long, patience)")
    mean_r2, std_r2 = evaluate_fine_grained()
    print(f"Modele B - granularite fine         : R2 = {mean_r2:.3f} (+/- {std_r2:.3f})")

    print("\n--- Verdict ---")
    if mean_r2 > r2_hourly + 0.05:
        print("La granularite fine apporte un signal supplementaire : l'agregation")
        print("horaire lissait de l'information utile. Intuition confirmee.")
    else:
        print("La granularite fine n'apporte pas de gain net : l'information etait")
        print("bien a l'echelle horaire, l'agregation n'a rien perdu d'essentiel.")