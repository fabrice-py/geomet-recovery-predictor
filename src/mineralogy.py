"""
mineralogy.py
Base de données de reference : stoechiometrie (mineral -> elements) et profils
de minerai. C'est de la DONNEE, pas de la logique : on l'enrichit sans toucher
au reste du code.

Valeurs stoechiometriques = approximations de manuel (suffisant pour de la donnee
synthetique ; la sphalerite reelle contient du Fe en substitution, le Co de la
pyrite varie, etc.).
"""

# --- Stoechiometrie : fraction massique de chaque element par mineral ---------
# Cle = nom du mineral ; valeur = {element: fraction massique}.
MINERALS = {
    "hematite":        {"Fe": 0.699},                           # Fe2O3
    "magnetite":       {"Fe": 0.724},                           # Fe3O4
    "quartz":          {"SiO2": 1.000},                         # SiO2
    "chalcopyrite":    {"Cu": 0.346, "Fe": 0.304, "S": 0.349},  # CuFeS2
    "sphalerite":      {"Zn": 0.670, "S": 0.330},               # ZnS
    "pyrite_co":       {"Fe": 0.465, "S": 0.535, "Co": 0.010},  # FeS2 cobaltifere
    "arsenopyrite":    {"Fe": 0.343, "As": 0.460, "S": 0.197},  # FeAsS
    "gangue_silicate": {"SiO2": 0.900},                         # albite/silicates
    "galena":          {"Pb": 0.866, "S": 0.134},              # PbS
}

# --- Profils de minerai : les "types" sont de la donnee -----------------------
# modal_alpha = concentrations de la loi de Dirichlet (proportions moyennes
# relatives des mineraux ; plus la valeur est grande, plus le mineral domine).
ORE_PROFILES = {
    "iron_flotation": {
        "minerals":     ["hematite", "magnetite", "quartz"],
        "modal_alpha":  [6.0, 2.0, 4.0],
        "gold_bearing": False,
    },
"iron_flotation_vale": {
        # Profil cale sur les teneurs REELLES de l'usine sur toute la periode (~54.7 % Fe,
        # ~16.5 % SiO2), car les premieres lignes du fichier ne montraient qu'une fenetre
        # non representative : ainsi on cale sur les 307 mesures distinctes, plus pauvres et
        # plus variables. Mineralogie inferee des teneurs (Fe = hematite, SiO2 = quartz).
        "minerals":     ["hematite", "magnetite", "quartz"],
        "modal_alpha":  [30.0, 2.0, 7.0],
        "gold_bearing": False,
    },
    "polymetallic_refractory_au": {
        "minerals":     ["chalcopyrite", "sphalerite", "pyrite_co",
                         "arsenopyrite", "gangue_silicate"],
        "modal_alpha":  [0.6, 0.5, 1.2, 0.4, 12.0],   # sulfures minoritaires
        "gold_bearing": True,
        "au_gt_range":  (0.5, 8.0),                   # or a l'alimentation (g/t)
        "au_hosts":     ["arsenopyrite", "pyrite_co"],# sulfures piegeant l'or
        "au_native_frac": 0.2,
        "au_gangue_frac": 0.1,
    },
    "polymetallic_pb_cu_zn": {
        "minerals":     ["galena", "chalcopyrite", "sphalerite", "pyrite_co",
                         "gangue_silicate"],
        "modal_alpha":  [0.5, 0.6, 0.9, 1.0, 12.0],
        "gold_bearing": False,
    },
    "polymetallic_au_cu_zn_pb": {
        "minerals": ["galena", "chalcopyrite", "sphalerite", "pyrite_co",
                     "arsenopyrite", "gangue_silicate"],
        "modal_alpha": [0.5, 0.6, 0.7, 1.0, 0.4, 12.0],
        "gold_bearing": True,
        "au_gt_range": (0.5, 6.0),
        "au_hosts": ["arsenopyrite", "pyrite_co"],
        # Repartition de la part NON-sulfures de l'or (native vs gangue). A CALIBRER sur
        # donnees de litterature ; valeurs de depart plausibles pour un gisement type Abitibi.
        "au_native_frac": 0.5,
        "au_gangue_frac": 0.5,
    },
}

def assays_from_modal(modal: dict) -> dict:
    """
    Reconstruit les teneurs elementaires (%) a partir de la mineralogie modale (%).
    C'est le coeur du passage mineral -> element : pour chaque mineral present,
    on repartit sa masse sur ses elements selon la stoechiometrie.
    """
    assays = {}
    for mineral, pct in modal.items():
        if mineral not in MINERALS:
            raise ValueError(f"Mineral inconnu dans la base : {mineral}")
        for element, frac in MINERALS[mineral].items():
            assays[element] = assays.get(element, 0.0) + pct * frac
    return {el: round(v, 3) for el, v in assays.items()}


if __name__ == "__main__":
    # Mini-test : on part d'une mineralogie modale connue et on verifie les teneurs.
    print("=== Test stoechiometrie : mineral -> element ===\n")

    exemple = {"chalcopyrite": 10.0, "sphalerite": 5.0, "gangue_silicate": 85.0}
    print("Mineralogie modale d'entree :")
    for m, p in exemple.items():
        print(f"  {m:18s} {p:5.1f} %")

    teneurs = assays_from_modal(exemple)
    print("\nTeneurs reconstruites :")
    for el, v in sorted(teneurs.items()):
        print(f"  {el:6s} {v:6.3f} %")

    # Verification manuelle rapide : 10 % chalcopyrite -> 10 * 0.346 = 3.46 % Cu
    print(f"\nVerif : Cu attendu = 10 x 0.346 = 3.46 %  |  obtenu = {teneurs['Cu']} %")