"""
prepare_ml_data.py
Preparation des donnees pour le modele data-driven par AGREGATION HORAIRE, car les
releves de 20 s repetent la meme mesure de labo sur toute l'heure : ainsi on regroupe
par heure (colonne date) et l'on moyenne chaque variable, ce qui donne une observation
independante par heure et elimine la fuite de donnees, avant un decoupage chronologique.

Cible : % Silica Concentrate (l'impurete a minimiser), predite a partir des conditions
moyennes de conduite de l'heure (teneurs, reactifs, pH, air et niveaux des colonnes).
"""

import os
import pandas as pd

from load_real_data import DATA_PATH

FEATURE_COLS = [
    "% Iron Feed", "% Silica Feed", "Starch Flow", "Amina Flow",
    "Ore Pulp Flow", "Ore Pulp pH", "Ore Pulp Density",
    "Flotation Column 01 Air Flow", "Flotation Column 02 Air Flow",
    "Flotation Column 03 Air Flow", "Flotation Column 04 Air Flow",
    "Flotation Column 05 Air Flow", "Flotation Column 06 Air Flow",
    "Flotation Column 07 Air Flow",
    "Flotation Column 01 Level", "Flotation Column 02 Level",
    "Flotation Column 03 Level", "Flotation Column 04 Level",
    "Flotation Column 05 Level", "Flotation Column 06 Level",
    "Flotation Column 07 Level",
]
TARGET_COL = "% Silica Concentrate"


def prepare_ml_data(path=DATA_PATH, test_fraction=0.25, shuffle=False):
    """
    Agregation horaire puis decoupage chronologique, car chaque heure est une observation
    reelle unique : ainsi on moyenne les variables par date (= par heure), puis on reserve
    la derniere fraction temporelle au test, jamais vue a l'entrainement.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}\nTelecharge le dataset Kaggle.")

    df = pd.read_csv(path, decimal=",")
    df.columns = [c.strip() for c in df.columns]

    # Agregation par heure, car la date identifie l'heure : ainsi on moyenne toutes les
    # variables utiles sur chaque heure pour obtenir une ligne par observation reelle.
    cols_to_keep = FEATURE_COLS + [TARGET_COL]
    hourly = df.groupby("date")[cols_to_keep].mean().reset_index()

    # Tri chronologique explicite, car groupby ne garantit pas l'ordre temporel : ainsi
    # le decoupage train/test respectera bien la fleche du temps.
    hourly["date"] = pd.to_datetime(hourly["date"])
    hourly = hourly.sort_values("date").reset_index(drop=True)

    # Decoupage : chronologique par defaut (revele le drift), ou aleatoire pour mesurer
    # le signal hors drift : ainsi on peut comparer les deux regimes.
    if shuffle:
        shuffled = hourly.sample(frac=1.0, random_state=42).reset_index(drop=True)
        cut = int(len(shuffled) * (1 - test_fraction))
        train, test = shuffled.iloc[:cut], shuffled.iloc[cut:]
    else:
        n = len(hourly)
        cut = int(n * (1 - test_fraction))
        train, test = hourly.iloc[:cut], hourly.iloc[cut:]

    X_train, y_train = train[FEATURE_COLS], train[TARGET_COL]
    X_test, y_test = test[FEATURE_COLS], test[TARGET_COL]
    return X_train, X_test, y_train, y_test

def prepare_ml_data_grouped(path=DATA_PATH, rows_per_hour=30, random_state=42):
    """
    Preparation des donnees FINES (20 s) avec les groupes horaires, car c'est l'approche
    retenue (R2 ~0.53, supérieure a l'agregation horaire ~0.37) : ainsi on sous-echantillonne
    chaque heure puis on renvoie X, y ET les groupes (heures), pour un decoupage par groupe
    qui garde la variation fine sans fuite (une heure ne peut etre coupee entre train et test).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}\nTelecharge le dataset Kaggle.")

    df = pd.read_csv(path, decimal=",")
    df.columns = [c.strip() for c in df.columns]

    # Sous-echantillonnage par heure sans perdre la colonne date (necessaire au groupe).
    sampled_idx = (df.groupby("date", group_keys=False)
                     .apply(lambda g: g.sample(min(len(g), rows_per_hour),
                                               random_state=random_state))
                     .index)
    df = df.loc[sampled_idx].reset_index(drop=True)

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]
    groups = df["date"]          # le groupe = l'heure, indivisible entre train et test
    return X, y, groups

if __name__ == "__main__":
    X_train, X_test, y_train, y_test = prepare_ml_data()
    print(f"Observations horaires : {len(X_train) + len(X_test)}")
    print(f"  Train : {len(X_train)} heures")
    print(f"  Test  : {len(X_test)} heures")
    print(f"\nVariables d'entree : {X_train.shape[1]}")
    print(f"Cible : {TARGET_COL}")
    print(f"\nStatistiques de la cible (train) :")
    print(y_train.describe().round(3).to_string())