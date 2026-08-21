"""Physique des particules mixtes (chemin 2), car la fraction NON liberee d'un mineral est
accolee a des mineraux specifiques (donnee MEB) et se comporte selon la MOYENNE de la
particule mixte, non selon la moyenne du minerai : ainsi une propriete effective realiste
en decoule. Module partage par les trois voies (gravite, magnetique, flottation).

Fallback (D4) : sans association pour un mineral, on retombe sur le comportement actuel
(melange vers la moyenne du minerai), gere par l'appelant."""


def mixed_density(rho_a, rho_b, w_a=0.5):
    """Densite d'une particule mixte A-B, car les VOLUMES s'additionnent (pas les densites) :
    ainsi pour des fractions massiques, la densite du melange est la moyenne HARMONIQUE.
    1/rho = w_a/rho_a + w_b/rho_b. Par defaut 50/50 en masse (hypothese D2, raffinable)."""
    w_b = 1.0 - w_a
    inv = w_a / rho_a + w_b / rho_b
    return 1.0 / inv if inv > 1e-12 else rho_a


def effective_density_assoc(mineral, rho_pur, lib, mean_density, associations, densities,
                            w_host=0.5):
    """Densite effective d'un mineral tenant compte de ses ASSOCIATIONS.

    - part liberee (lib) : densite pure du mineral.
    - part non liberee (1-lib) : repartie selon les associations MEB ; chaque association
      contribue par la densite de la particule mixte mineral/mineral_associe (moyenne
      harmonique, D2).
    - fallback : si le mineral n'a PAS d'association, on retombe sur la moyenne du minerai
      (comportement actuel), gere ici en renvoyant None pour signaler a l'appelant.

    Retour : la densite effective, ou None si pas d'association (l'appelant applique alors
    la formule historique).
    """
    assoc = (associations or {}).get(mineral)
    if not assoc:
        return None   # pas de donnee -> fallback gere par l'appelant

    # Normalise les fractions d'association (par securite, si elles ne somment pas a 1).
    total = sum(assoc.values())
    if total <= 1e-12:
        return None
    fracs = {k: v / total for k, v in assoc.items()}

    # Densite moyenne de la part NON liberee = somme ponderee des densites de particules
    # mixtes mineral/associe.
    rho_locked = 0.0
    for assoc_mineral, frac in fracs.items():
        rho_assoc = densities.get(assoc_mineral, mean_density)  # densite de l'associe (ou moyenne si inconnu)
        rho_mix = mixed_density(rho_pur, rho_assoc, w_a=w_host)
        rho_locked += frac * rho_mix

    return lib * rho_pur + (1.0 - lib) * rho_locked