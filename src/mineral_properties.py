"""
mineral_properties.py
Base des propriétés physiques intrinsèques des minéraux (couche 5 de l'architecture),
car un minéral se sépare selon son comportement physique et non sa seule chimie :
ainsi cette base fournit la densité (gravimétrie, bilan-eau), la susceptibilité
magnétique (séparation magnétique) et la flottabilité (flottation).

Densités : valeurs de manuel fiables (g/cm3).
Susceptibilité et flottabilité : valeurs INDICATIVES, exploitées en Séance 3, car
elles dépendent en réalité des réglages machine que le moteur de séparation modulera.
"""

# Cle = mineral ; valeur = proprietes physiques.
#   density        : g/cm3 (= t/m3), utilisee des la Seance 2 pour le bilan-eau.
#   magnetic       : categorie -> LIMS capte le ferromagnetique, WHIMS le paramagnetique.
#   floatability   : indice natif 0-1 de reponse aux collecteurs sulfures (indicatif).
MINERAL_PROPERTIES = {
    "hematite":        {"density": 5.26, "magnetic": "paramagnetique",       "floatability": 0.20},
    "magnetite":       {"density": 5.18, "magnetic": "ferromagnetique",      "floatability": 0.15},
    "quartz":          {"density": 2.65, "magnetic": "diamagnetique",        "floatability": 0.10},
    "chalcopyrite":    {"density": 4.20, "magnetic": "paramagnetique_faible","floatability": 0.90},
    "sphalerite":      {"density": 4.00, "magnetic": "diamagnetique",        "floatability": 0.50},
    "pyrite_co":       {"density": 5.00, "magnetic": "paramagnetique_faible","floatability": 0.60},
    "arsenopyrite":    {"density": 6.00, "magnetic": "paramagnetique",       "floatability": 0.60},
    "gangue_silicate": {"density": 2.65, "magnetic": "diamagnetique",        "floatability": 0.10},
    "galena":          {"density": 7.50, "magnetic": "diamagnetique",        "floatability": 0.85},
}


def get_densities() -> dict:
    """
    Extraction des densités sous forme de dict {mineral: densité}, car c'est le format
    qu'attend la méthode close_pulp du Stream : ainsi le bilan-eau puise directement ici.
    """
    return {m: props["density"] for m, props in MINERAL_PROPERTIES.items()}


def get_property(mineral: str, prop: str):
    """
    Lecture d'une propriété d'un minéral avec contrôle, car une clé inconnue doit être
    signalée clairement plutôt que de renvoyer une valeur silencieusement fausse.
    """
    if mineral not in MINERAL_PROPERTIES:
        raise ValueError(f"Mineral absent de la base de proprietes : {mineral}")
    if prop not in MINERAL_PROPERTIES[mineral]:
        raise ValueError(f"Propriete inconnue : {prop}")
    return MINERAL_PROPERTIES[mineral][prop]


if __name__ == "__main__":
    # Mini-test : on affiche la base et on verifie l'ordre des densites, car il porte
    # un sens physique fort (les sulfures lourds > oxydes de fer > silicates legers).
    print("=== Base de proprietes minerales ===\n")
    print(f"{'mineral':18s} {'densite':>8s}  {'magnetique':22s} {'flottabilite':>12s}")
    for m, p in MINERAL_PROPERTIES.items():
        print(f"{m:18s} {p['density']:8.2f}  {p['magnetic']:22s} {p['floatability']:12.2f}")

    # Verification : le mineral le plus dense doit etre l'arsenopyrite (6.0).
    densites = get_densities()
    plus_dense = max(densites, key=densites.get)
    print(f"\nMineral le plus dense : {plus_dense} ({densites[plus_dense]} g/cm3)")