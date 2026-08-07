"""
train_model.py
Entrainement d'un premier modele data-driven (foret aleatoire), car une baseline simple
doit preceder tout modele complexe : ainsi on mesure une reference honnete de la
capacite a predire la silice du concentre a partir des conditions de conduite horaires.

La performance est evaluee sur le jeu de test chronologique (heures jamais vues), car
c'est la seule mesure non biaisee.
"""

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np

from prepare_ml_data import prepare_ml_data


def train_random_forest():
    """
    Entrainement et evaluation d'une foret aleatoire, car elle offre un bon compromis
    puissance/robustesse sans reglage delicat : ainsi on apprend sur le train et l'on
    mesure R2 et RMSE sur le test, jamais vu.
    """
    X_train, X_test, y_train, y_test = prepare_ml_data()

    model = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    # Evaluation sur le test, car la performance sur le train serait optimiste : ainsi on
    # predit des heures jamais vues et l'on compare aux vraies teneurs de silice.
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))

    print("=== Foret aleatoire (baseline) ===")
    print(f"  R2   sur le test : {r2:.3f}")
    print(f"  RMSE sur le test : {rmse:.3f} % silice")
    print(f"\n  (pour reference, l'ecart-type de la cible est "
          f"{y_test.std():.3f} % : un modele nul aurait un RMSE de cet ordre)")

    return model, (X_train, X_test, y_train, y_test)


if __name__ == "__main__":
    train_random_forest()