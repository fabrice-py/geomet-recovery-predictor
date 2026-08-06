"""
visualize_feed.py
Figures de caractérisation des flux générés, car un tableau de statistiques ne
« parle » pas à un lecteur : ainsi chaque fonction transforme un DataFrame en une
preuve visuelle, réutilisable telle quelle dans le script comme dans le notebook.
"""

import matplotlib.pyplot as plt

from feed_generator import generate_feed, streams_to_dataframe


def plot_fe_sio2_anticorrelation(df, ax=None):
    """
    Tracé de l'anti-corrélation Fe/SiO2, car elle prouve que la donnée synthétique
    respecte la physique du minerai : ainsi on montre que Fe et SiO2 se partagent la
    masse sans qu'on l'ait imposé explicitement.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    ax.scatter(df["Fe"], df["SiO2"], s=18, alpha=0.5, edgecolor="none", color="#B44A3C")
    ax.set_xlabel("Teneur en Fe à l'alimentation (%)")
    ax.set_ylabel("Teneur en SiO$_2$ à l'alimentation (%)")
    ax.set_title("Anti-corrélation Fe / SiO$_2$ (profil fer)")
    ax.grid(True, alpha=0.3)
    return ax


def plot_gold_refractory(df, ax=None):
    """
    Tracé de la part réfractaire de l'or en fonction des sulfures hôtes, car c'est la
    figure signature du projet : ainsi on visualise que plus le minerai contient de
    sulfures piégeurs (arsénopyrite + pyrite), plus l'or échappe à la récupération.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    # Reconstitution de la teneur en sulfures hôtes, car elle n'est pas stockée
    # directement : ainsi on l'approxime par la somme As + une part du fer sulfuré.
    host_proxy = df["As"] + df["Co"] * 10   # As trace l'arsénopyrite, Co trace la pyrite_co

    sc = ax.scatter(host_proxy, df["Au_refractory_frac"] * 100,
                    c=df["p80_um"], cmap="viridis", s=22, alpha=0.7, edgecolor="none")
    ax.set_xlabel("Indicateur de sulfures hôtes (As + 10·Co, %)")
    ax.set_ylabel("Part de l'or réfractaire (%)")
    ax.set_title("Or réfractaire vs sulfures piégeurs (profil polymétallique)")
    ax.grid(True, alpha=0.3)

    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("P80 (µm) — finesse de broyage")
    return ax


def build_all_figures(n_samples=500, seed=42, save_dir="figures"):
    """
    Génération des deux profils et sauvegarde des deux figures, car le script doit
    pouvoir produire les livrables tout seul : ainsi un simple lancement remplit le
    dossier figures/ utilisé par le README.
    """
    import os
    os.makedirs(save_dir, exist_ok=True)

    # Profil fer, car c'est lui qui porte l'anti-corrélation Fe/SiO2.
    df_iron = streams_to_dataframe(
        generate_feed("iron_flotation", n_samples=n_samples, seed=seed, assay_noise_pct=2.0))
    ax1 = plot_fe_sio2_anticorrelation(df_iron)
    ax1.figure.tight_layout()
    ax1.figure.savefig(f"{save_dir}/fe_sio2_anticorrelation.png", dpi=150)

    # Profil polymétallique, car c'est lui qui porte l'or réfractaire.
    df_poly = streams_to_dataframe(
        generate_feed("polymetallic_refractory_au", n_samples=n_samples, seed=seed))
    ax2 = plot_gold_refractory(df_poly)
    ax2.figure.tight_layout()
    ax2.figure.savefig(f"{save_dir}/gold_refractory.png", dpi=150)

    print(f"Deux figures enregistrées dans {save_dir}/")
    return df_iron, df_poly


if __name__ == "__main__":
    build_all_figures()
    plt.show()   # affichage à l'écran en plus de la sauvegarde