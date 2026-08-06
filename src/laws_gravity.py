"""
laws_gravity.py
Loi de séparation gravimétrique commune aux concentrateurs (table, spirale, Falcon),
car ils partagent tous la même physique — un partage selon la densité — et ne diffèrent
que par leurs réglages et leur plage de taille : ainsi une seule loi, déclinée par
machine, produit la récupération par minéral qu'attend la machinerie separate().
"""

import math

from mineral_properties import get_densities

RHO_WATER = 1.0


def partition_probability(density, d50, ep):
    """
    Probabilité qu'une particule de densité donnée parte au concentré, car la séparation
    réelle n'est jamais franche : ainsi on utilise une courbe de partage logistique
    centrée sur le d50, dont la pente est fixée par l'Ep (netteté de coupure).
    """
    # Un Ep faible rend la transition raide, car la coupure est nette : ainsi on relie
    # la pente à l'Ep, en le bornant pour éviter une division par zéro.
    ep = max(ep, 0.05)
    # Facteur 1.099 = ln(3), car l'Ep est par définition la demi-distance entre les
    # densités à 25 % et 75 % de récupération : ainsi la logistique respecte cette norme.
    k = 1.099 / ep
    return 1.0 / (1.0 + math.exp(-k * (density - d50)))


def effective_density(mineral_density, liberation_degree, mean_density):
    """
    Densité effective d'un minéral compte tenu de sa libération, car une particule mal
    libérée reste accrochée à sa gangue et voit sa densité tirée vers la moyenne : ainsi
    une mauvaise libération rapproche les densités et rend le tri plus difficile.
    """
    # liberation = 1 -> densité pure ; liberation = 0 -> densité moyenne du minerai.
    return liberation_degree * mineral_density + (1 - liberation_degree) * mean_density


def gravity_recovery(stream, d50, ep):
    """
    Récupération par minéral pour un concentrateur gravimétrique, car c'est le produit
    final qu'attend separate() : ainsi on calcule, pour chaque minéral, sa densité
    effective (via la libération) puis sa probabilité de partage sur la courbe.

    d50, ep : paramètres de coupure fournis par la machine (calculés à partir de ses
    réglages), car c'est la machine qui fixe où et comment on coupe.
    """
    densities = get_densities()

    # Densité moyenne du solide, car elle sert de point d'attraction pour les particules
    # mal libérées : ainsi on la calcule sur la minéralogie réelle du flux.
    w = {m: stream.modal[m] / 100.0 for m in stream.modal}
    mean_density = sum(w[m] * densities[m] for m in w)

    recovery = {}
    for m in stream.modal:
        lib = stream.liberation.degree.get(m, 1.0)
        rho_eff = effective_density(densities[m], lib, mean_density)
        recovery[m] = round(partition_probability(rho_eff, d50, ep), 4)
    return recovery
def gravity_cutpoint(unit):
    """
    Traduction des réglages d'un concentrateur en paramètres de coupure (d50, Ep), car
    l'utilisateur règle une machine et non une densité : ainsi chaque type de
    concentrateur interprète ses propres réglages pour positionner le d50 dans sa plage
    et fixer l'Ep, la même loi de partage étant ensuite appliquée à tous.

    Relations phénoménologiques : sens de variation corrects et ordres de grandeur
    réalistes, mais non calibrées sur des essais, comme prévu au cahier des charges.
    """
    from separation import SEPARATION_SPECS
    spec = SEPARATION_SPECS[unit.unit_type]
    d50_lo, d50_hi = spec["_d50_range"]
    ep_base = spec["_ep_base"]
    s = unit.settings

    if unit.unit_type == "shaking_table":
        # Plus la table est inclinée, plus le d50 monte (plus sélectif), car seules les
        # particules très denses restent : ainsi on place le d50 selon l'inclinaison.
        frac = (s["deck_slope_deg"] - 1.5) / (6.0 - 1.5)
        d50 = d50_lo + frac * (d50_hi - d50_lo)
        # Une fréquence loin de l'optimum (~5.5 Hz) dégrade l'Ep, car le tri devient flou.
        ep = ep_base + 0.15 * abs(s["stroke_freq_hz"] - 5.5) / 1.5

    elif unit.unit_type == "spiral":
        # La position des splitters règle le d50, car elle décide où l'on coupe le ruban.
        frac = (s["splitter_pos"] - 0.2) / (0.8 - 0.2)
        d50 = d50_lo + frac * (d50_hi - d50_lo)
        # Un débit élevé surcharge la spirale et dégrade l'Ep.
        ep = ep_base + 0.10 * (s["feed_rate_tph"] - 3.0) / 3.0

    elif unit.unit_type == "falcon":
        # Plus la force G est élevée, plus on capte les particules légères/fines, donc
        # le d50 accessible BAISSE : ainsi une forte rotation abaisse le d50.
        frac = (s["rotation_g"] - 50.0) / (300.0 - 50.0)
        d50 = d50_hi - frac * (d50_hi - d50_lo)   # inversé : plus de G -> d50 plus bas
        ep = ep_base

    else:
        raise ValueError(f"{unit.unit_type} n'est pas un concentrateur gravimétrique")

    return round(d50, 3), round(max(ep, 0.05), 3)

if __name__ == "__main__":
    # Test : le MÊME flux séparé par trois concentrateurs différents, car on veut voir
    # que le choix de machine et ses réglages changent réellement le résultat.
    from feed_generator import generate_feed
    from separation import separate, SeparationUnit

    flux = generate_feed("iron_flotation", n_samples=1, seed=1)[0]
    print(f"Alimentation : Fe = {flux.assays['Fe']:.1f} %  (100 t/h)\n")

    machines = [
        SeparationUnit("shaking_table", {"deck_slope_deg": 3.0}),
        SeparationUnit("shaking_table", {"deck_slope_deg": 5.5}),   # plus sélective
        SeparationUnit("spiral"),
        SeparationUnit("falcon", {"rotation_g": 250}),
    ]

    for unit in machines:
        d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(flux, d50=d50, ep=ep)
        conc, rejet = separate(flux, reco)
        label = f"{unit.unit_type}"
        if unit.unit_type == "shaking_table":
            label += f" (pente {unit.settings['deck_slope_deg']}°)"
        print(f"{label:28s} d50={d50:.2f} Ep={ep:.2f} | "
              f"Fe conc={conc.assays['Fe']:.1f}% masse={conc.solids_tph:.1f}t/h | "
              f"Fe rejet={rejet.assays['Fe']:.1f}%")