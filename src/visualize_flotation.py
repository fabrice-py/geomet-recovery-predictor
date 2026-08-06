"""
visualize_flotation.py
Figure signature de la flottation : le compromis or / pyrite selon le pH, car c'est
l'argument central du minerai réfractaire : ainsi on montre que déprimer la pyrite pour
purifier le concentré fait chuter la récupération de l'or, qui suit ses sulfures hôtes.
"""

import numpy as np
import matplotlib.pyplot as plt

from feed_generator import generate_feed
from separation import SeparationUnit
from laws_flotation import flotation_recovery, gold_flotation_recovery


def plot_gold_pyrite_tradeoff(seed=3, save_dir="figures"):
    """
    Tracé des récupérations pyrite et or en fonction du pH, car leur évolution parallèle
    révèle le dilemme réfractaire : ainsi on balaie le pH et on relève les deux courbes.
    """
    flux = generate_feed("polymetallic_refractory_au", n_samples=1, seed=seed)[0]
    ph_values = np.linspace(8.0, 12.0, 25)

    pyrite_rec, gold_rec, chalco_rec = [], [], []
    for ph in ph_values:
        unit = SeparationUnit("flotation", {"collector_type": "xanthate_SIBX",
                                            "collector_gpt": 100, "pulp_ph": ph,
                                            "residence_min": 8, "rotor_speed_rpm": 1200})
        reco = flotation_recovery(flux, unit)
        pyrite_rec.append(reco["pyrite_co"] * 100)
        chalco_rec.append(reco["chalcopyrite"] * 100)
        gold_rec.append(gold_flotation_recovery(flux, reco, unit) * 100)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(ph_values, chalco_rec, "-", color="#2E7D32", lw=2, label="Chalcopyrite (Cu, voulue)")
    ax.plot(ph_values, pyrite_rec, "-", color="#C62828", lw=2, label="Pyrite (à déprimer)")
    ax.plot(ph_values, gold_rec, "--", color="#F9A825", lw=2.5, label="Or (suit les sulfures)")
    ax.set_xlabel("pH de la pulpe")
    ax.set_ylabel("Récupération (%)")
    ax.set_title("Dilemme réfractaire : déprimer la pyrite fait perdre l'or")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    import os
    os.makedirs(save_dir, exist_ok=True)
    fig.savefig(f"{save_dir}/gold_pyrite_tradeoff.png", dpi=150)
    print(f"Figure enregistrée dans {save_dir}/gold_pyrite_tradeoff.png")
    return ax


if __name__ == "__main__":
    plot_gold_pyrite_tradeoff()
    plt.show()