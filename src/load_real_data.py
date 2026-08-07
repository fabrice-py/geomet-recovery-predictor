"""
load_real_data.py
Chargement et nettoyage du jeu de donnees reel (usine de flottation de fer, Kaggle),
car ce fichier a des pieges de format qu'il faut traiter des la lecture : ainsi on gere
les decimales a la virgule (format bresilien) et l'on isole les colonnes utiles, pour
fournir un DataFrame propre au reste du projet.

Le fichier n'est PAS versionne (trop lourd, ~183 Mo) : il doit etre telecharge depuis
Kaggle et place dans data/, comme documente dans le README.
"""

import os
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(_PROJECT_ROOT, "data", "MiningProcess_Flotation_Plant_Database.csv")


def load_real_data(path=DATA_PATH, nrows=None):
    """
    Lecture du CSV reel avec gestion du format, car les nombres y sont ecrits avec des
    virgules decimales : ainsi decimal=',' evite que pandas lise les colonnes comme du
    texte, et nrows permet de limiter la taille pour une exploration rapide.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Fichier introuvable : {path}\n"
            "Telecharge le dataset depuis Kaggle (edumagalhaes/"
            "quality-prediction-in-a-mining-process) et place le CSV dans data/.")

    df = pd.read_csv(path, decimal=",", nrows=nrows)
    # Nettoyage des noms de colonnes, car ils contiennent des espaces et % genants :
    # ainsi on obtient des noms manipulables sans casser leur sens.
    df.columns = [c.strip() for c in df.columns]
    return df


def real_iron_summary(df):
    """
    Extraction des colonnes cle cote fer, car on veut comparer le reel a nos flux
    synthetiques : ainsi on isole le fer et la silice a l'alimentation et au concentre.
    """
    cols = {
        "% Iron Feed": "fe_feed",
        "% Silica Feed": "sio2_feed",
        "% Iron Concentrate": "fe_conc",
        "% Silica Concentrate": "sio2_conc",
    }
    available = {k: v for k, v in cols.items() if k in df.columns}
    sub = df[list(available.keys())].rename(columns=available)
    return sub
def load_real_feed_unique(path=DATA_PATH):
    """
    Extraction des teneurs d'alimentation DISTINCTES sur toute la periode, car les lignes
    de 20 s repetent la meme mesure horaire de labo : ainsi charger les premieres lignes
    ne donne que quelques valeurs uniques, et il faut lire tout le fichier puis dedupliquer
    pour retrouver la vraie variabilite de l'usine.

    On ne lit que les colonnes utiles, car charger les 24 colonnes serait inutilement lourd.
    """
    cols = ["% Iron Feed", "% Silica Feed", "% Iron Concentrate", "% Silica Concentrate"]
    df = pd.read_csv(path, decimal=",", usecols=cols)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "% Iron Feed": "fe_feed", "% Silica Feed": "sio2_feed",
        "% Iron Concentrate": "fe_conc", "% Silica Concentrate": "sio2_conc"})
    # Deduplication sur les teneurs d'alimentation, car ce sont elles qui se repetent :
    # ainsi on obtient une ligne par mesure horaire reelle plutot que par releve de 20 s.
    df_unique = df.drop_duplicates(subset=["fe_feed", "sio2_feed"]).reset_index(drop=True)
    return df_unique

if __name__ == "__main__":
    # Exploration sur un echantillon, car charger 737k lignes a chaque test serait lent :
    # ainsi on lit les 50 000 premieres lignes, suffisant pour voir la structure.
    print("Chargement d'un echantillon (50 000 lignes)...")
    df = load_real_data(nrows=50000)

    print(f"\nDimensions : {df.shape[0]} lignes x {df.shape[1]} colonnes")
    print(f"\nColonnes disponibles :")
    for c in df.columns:
        print(f"  - {c}")

    print("\n--- Cote fer : statistiques ---")
    iron = real_iron_summary(df)
    print(iron.describe().round(2).to_string())
    print("\n--- Teneurs d'alimentation DISTINCTES sur toute la periode ---")
    uniq = load_real_feed_unique()
    print(f"Nombre de mesures horaires distinctes : {len(uniq)}")
    print(uniq[["fe_feed", "sio2_feed"]].describe().round(2).to_string())