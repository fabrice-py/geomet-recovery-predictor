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


def gravity_recovery(stream, d50, ep, densities=None):
    """
    Récupération par minéral pour un concentrateur gravimétrique, car c'est le produit
    final qu'attend separate() : ainsi on calcule, pour chaque minéral, sa densité
    effective (via la libération) puis sa probabilité de partage sur la courbe.

    d50, ep : paramètres de coupure fournis par la machine (calculés à partir de ses
    réglages), car c'est la machine qui fixe où et comment on coupe.
    """
    # Densites custom si fournies (mineraux hors base), sinon la base interne, car la
    # fonction doit accepter des mineraux que l'utilisateur definit lui-meme : ainsi on
    # complete par la base pour tout mineral non fourni.
    base_densities = get_densities()
    if densities is None:
        densities = base_densities
    else:
        # On fusionne : les proprietes custom priment, la base comble le reste.
        merged = dict(base_densities)
        for m, props in densities.items():
            merged[m] = props["density"] if isinstance(props, dict) else props
        densities = merged
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

def gold_gravity_recovery(stream, mineral_recovery, unit, d50=None, ep=None):
    """
    Recuperation de l'or au concentre gravimetrique, physiquement, car chaque mode d'or a
    une densite effective differente selon son hote : ainsi on traite chaque mode comme une
    particule et on lui applique la MEME courbe de partage que les mineraux (d50, ep issus
    des reglages machine). L'or devient donc sensible aux reglages ET a la liberation.

    - or natif : densite proche de l'or pur (~19), tres bien recupere ;
    - or gangue : densite effective = moyenne or/silicate ponderee par la liberation (mal
      libere -> tire vers la gangue legere -> moins recupere) ; en plus, seule la part
      liberee par le broyage est recuperable (Au_gangue_recoverable_gt) ;
    - or sulfures : densite effective = moyenne or/sulfure ; suit ses sulfures, qui en
      gravimetrie partent peu au concentre.

    Renvoie une fraction 0-1 de l'or TOTAL partant au concentre (ce qu'attend separate()).
    """
    total_au = stream.assays.get("Au_gt", None)
    if total_au is None or total_au <= 1e-9:
        return 0.0

    # Coupure imposee si fournie (mode direct), sinon calculee depuis la machine, car l'or
    # doit suivre la MEME coupure que les mineraux : ainsi il reste coherent avec la separation.
    if d50 is None:
        d50, ep = gravity_cutpoint(unit)
    rho_gold = 19.3
    rho_gangue = 2.65
    rho_sulfide = 5.5   # moyenne pyrite/arsenopyrite, hotes typiques de l'or

    # Libération moyenne (sert a moduler la densite effective de l'or gangue/sulfures).
    lib_gangue = stream.liberation.degree.get("gangue_silicate", 0.85)

    # Or natif : particule quasi pure d'or, tres dense.
    p_native = partition_probability(rho_gold, d50, ep)

    # Or gangue : densite effective tiree vers la gangue selon la liberation, car un grain
    # d'or mal degage de la silice se comporte comme un composite plus leger.
    rho_gangue_eff = lib_gangue * rho_gold + (1 - lib_gangue) * rho_gangue
    p_gangue = partition_probability(rho_gangue_eff, d50, ep)

    # Or sulfures : densite effective or/sulfure, mais on la pondere par la recuperation
    # gravimetrique reelle des sulfures hotes, car l'or suit ses hotes : si les sulfures ne
    # partent pas au concentre, leur or non plus.
    hosts = ["pyrite_co", "arsenopyrite"]
    host_mass = {h: stream.modal.get(h, 0.0) for h in hosts}
    total_host = sum(host_mass.values())
    host_grav = (sum(mineral_recovery.get(h, 0.0) * host_mass[h] for h in hosts)
                 / total_host) if total_host > 1e-9 else 0.0

    au_native = stream.assays.get("Au_native_gt", 0.0)
    au_gangue_recov = stream.assays.get("Au_gangue_recoverable_gt", 0.0)
    au_sulfide = stream.assays.get("Au_sulfide_gt", 0.0)

    recovered = (au_native * p_native
                 + au_gangue_recov * p_gangue
                 + au_sulfide * host_grav)
    return round(recovered / total_au, 4)

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