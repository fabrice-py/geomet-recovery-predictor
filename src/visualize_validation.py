"""
visualize_validation.py
Figure de validation : superposition des flux synthetiques calibres et des donnees
reelles de l'usine, car une validation ne vaut que si elle est visible : ainsi on trace
le nuage Fe/SiO2 reel et le nuage synthetique sur le meme graphe pour montrer leur
recouvrement.
"""

import matplotlib.pyplot as plt

from feed_generator import generate_feed, streams_to_dataframe
from load_real_data import load_real_data, real_iron_summary


def plot_synthetic_vs_real(n_real=5000, n_syn=500, save_dir="figures"):
    """
    Superposition synthetique / reel sur le plan Fe-SiO2, car c'est la que le calage se
    juge : ainsi on affiche les vraies teneurs d'alimentation de l'usine et celles du
    profil synthetique calibre, pour montrer qu'ils occupent la meme region.
    """
    # Donnees reelles : un echantillon suffit pour dessiner le nuage, car 737k points
    # satureraient la figure : ainsi on en prend n_real.
    from load_real_data import load_real_feed_unique
    real = load_real_feed_unique()

    # Flux synthetiques calibres sur cette usine.
    syn = streams_to_dataframe(generate_feed("iron_flotation_vale", n_samples=n_syn, assay_noise_pct=3.0))

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(real["fe_feed"], real["sio2_feed"], s=8, alpha=0.25,
               color="#1565C0", label=f"Usine reelle (n={len(real)})")
    ax.scatter(syn["Fe"], syn["SiO2"], s=18, alpha=0.6,
               color="#C62828", edgecolor="none", label=f"Synthetique calibre (n={n_syn})")

    ax.set_xlabel("Teneur en Fe a l'alimentation (%)")
    ax.set_ylabel("Teneur en SiO$_2$ a l'alimentation (%)")
    ax.set_title("Validation : flux synthetiques calibres vs usine reelle")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    import os
    os.makedirs(save_dir, exist_ok=True)
    fig.savefig(f"{save_dir}/synthetic_vs_real.png", dpi=150)
    print(f"Figure enregistree dans {save_dir}/synthetic_vs_real.png")
    return ax


if __name__ == "__main__":
    plot_synthetic_vs_real()
    plt.show()