"""
shap_analysis.py
Interpretation du modele XGBoost par SHAP, car un modele qui predit sans expliquer reste
une boite noire : ainsi on quantifie l'influence de chaque variable de conduite sur la
silice du concentre, ce qui transforme la prediction en information actionnable (sur quels
leviers agir pour reduire l'impurete).
"""

import shap
import matplotlib.pyplot as plt

from train_xgboost import train_xgboost


def run_shap_analysis(max_display=15, sample_size=2000, save_dir="figures"):
    """
    Calcul et trace des valeurs SHAP, car on veut le classement des variables les plus
    influentes : ainsi on entraine le modele, on calcule les contributions SHAP sur un
    echantillon (pour la vitesse) et l'on trace l'importance globale des variables.
    """
    model, X, y = train_xgboost()

    # Echantillon pour SHAP, car calculer sur 122k lignes serait lent : ainsi on prend un
    # sous-ensemble representatif, suffisant pour un classement stable des variables.
    X_sample = X.sample(min(sample_size, len(X)), random_state=42)

    # TreeExplainer, car il est concu pour les modeles d'arbres (XGBoost) et rapide.
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # Figure d'importance globale (barres), car elle classe les variables par influence
    # moyenne : ainsi on voit d'un coup les principaux leviers de la silice.
    plt.figure()
    shap.summary_plot(shap_values, X_sample, plot_type="bar",
                      max_display=max_display, show=False)
    plt.tight_layout()

    import os
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(f"{save_dir}/shap_importance.png", dpi=150, bbox_inches="tight")
    print(f"\nFigure enregistree dans {save_dir}/shap_importance.png")
    plt.close()

    # Figure detaillee (beeswarm), car elle montre AUSSI le SENS de l'effet (une valeur
    # haute de la variable augmente-t-elle ou baisse-t-elle la silice ?) : ainsi on lit
    # non seulement quelles variables comptent, mais comment elles agissent.
    plt.figure()
    shap.summary_plot(shap_values, X_sample, max_display=max_display, show=False)
    plt.tight_layout()
    plt.savefig(f"{save_dir}/shap_beeswarm.png", dpi=150, bbox_inches="tight")
    print(f"Figure enregistree dans {save_dir}/shap_beeswarm.png")
    plt.close()

    print("\nAnalyse SHAP terminee : consulte les deux figures dans figures/.")


if __name__ == "__main__":
    run_shap_analysis()