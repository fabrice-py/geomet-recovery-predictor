"""
train_xgboost.py
Modele principal : XGBoost sur donnees fines avec split par groupe, car c'est l'approche
retenue (variation fine + anti-fuite) : ainsi on entraine un gradient boosting, evalue par
GroupKFold ou l'heure est indivisible, puis on garde un modele entraine pour l'interpretation
SHAP.

XGBoost construit les arbres sequentiellement (chacun corrige le precedent), ce qui en fait
un standard performant sur donnees tabulaires.
"""

import numpy as np
from xgboost import XGBRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score, mean_squared_error

from prepare_ml_data import prepare_ml_data_grouped


def train_xgboost():
    """
    Entrainement et evaluation de XGBoost par split par groupe, car l'heure doit rester
    indivisible pour eviter la fuite : ainsi on mesure R2 et RMSE sur des heures jamais
    vues, puis on reentraine sur l'ensemble pour disposer d'un modele complet a interpreter.
    """
    X, y, groups = prepare_ml_data_grouped()

    gkf = GroupKFold(n_splits=5)
    r2_scores, rmse_scores = [], []
    for train_idx, test_idx in gkf.split(X, y, groups):
        model = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.1,
                             random_state=42, n_jobs=-1)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[test_idx])
        r2_scores.append(r2_score(y.iloc[test_idx], pred))
        rmse_scores.append(np.sqrt(mean_squared_error(y.iloc[test_idx], pred)))

    print("=== XGBoost (donnees fines, split par groupe) ===")
    print(f"  R2   : {np.mean(r2_scores):.3f} (+/- {np.std(r2_scores):.3f})")
    print(f"  RMSE : {np.mean(rmse_scores):.3f} % silice (+/- {np.std(rmse_scores):.3f})")

    # Modele final entraine sur TOUT, car SHAP a besoin d'un modele complet : ainsi on
    # reentraine sur l'ensemble apres avoir mesure la performance en validation.
    final_model = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.1,
                               random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    return final_model, X, y


if __name__ == "__main__":
    train_xgboost()