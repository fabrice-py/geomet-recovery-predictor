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

def mixed_susceptibility(chi_a, chi_b, w_a=0.5):
    """Susceptibilite d'une particule mixte A-B, car la susceptibilite MASSIQUE d'un melange
    est la moyenne ARITHMETIQUE ponderee par la masse (les moments magnetiques s'additionnent
    par unite de masse) : ainsi, contrairement a la densite, ce n'est PAS une moyenne
    harmonique. Par defaut 50/50 en masse (D2)."""
    w_b = 1.0 - w_a
    return w_a * chi_a + w_b * chi_b


def effective_susceptibility_assoc(mineral, chi_pur, lib, associations, susceptibilities,
                                   w_host=0.5):
    """Susceptibilite effective d'un mineral tenant compte de ses ASSOCIATIONS.

    - part liberee (lib) : susceptibilite pure du mineral.
    - part non liberee (1-lib) : repartie selon les associations MEB ; chaque association
      contribue par la susceptibilite de la particule mixte (moyenne arithmetique massique).
    - fallback : si pas d'association, renvoie None (l'appelant applique la formule historique,
      qui tire vers le diamagnetique).

    susceptibilities : dict {mineral: chi} pour retrouver la susceptibilite des associes.
    """
    assoc = (associations or {}).get(mineral)
    if not assoc:
        return None

    total = sum(assoc.values())
    if total <= 1e-12:
        return None
    fracs = {k: v / total for k, v in assoc.items()}

    chi_locked = 0.0
    for assoc_mineral, frac in fracs.items():
        chi_assoc = susceptibilities.get(assoc_mineral, 0.0)   # susceptibilite de l'associe
        chi_mix = mixed_susceptibility(chi_pur, chi_assoc, w_a=w_host)
        chi_locked += frac * chi_mix

    return lib * chi_pur + (1.0 - lib) * chi_locked

def mixed_floatability(f_a, f_b, w_bias=0.6):
    """Flottabilite d'une particule mixte A-B (modele C, biaise vers le composant le plus
    flottable), car la flottation est un phenomene de SURFACE : un peu d'hydrophobe suffit a
    accrocher la particule a une bulle, mais la gangue accolee dilue le concentre. Ainsi la
    particule mixte flotte MIEUX que la moyenne, sans atteindre le pur.
    f_mixte = w_bias * max + (1 - w_bias) * moyenne. w_bias a caler."""
    return w_bias * max(f_a, f_b) + (1.0 - w_bias) * (f_a + f_b) / 2.0


def effective_floatability_assoc(mineral, f_pur, lib, associations, floatabilities,
                                 w_bias=0.6):
    """Flottabilite effective d'un mineral tenant compte de sa LIBERATION et de ses
    ASSOCIATIONS, car la flottabilite d'une particule depend de son degre de liberation.

    - part liberee (lib) : flottabilite pure du mineral.
    - part non liberee (1-lib) : flottabilite des particules mixtes (modele C), repartie
      selon les associations MEB.
    - fallback : si pas d'association, renvoie None (l'appelant garde la flottabilite pure,
      comportement actuel sans effet de liberation).

    floatabilities : dict {mineral: floatability} pour retrouver celle des associes.
    """
    assoc = (associations or {}).get(mineral)
    if not assoc:
        return None

    total = sum(assoc.values())
    if total <= 1e-12:
        return None
    fracs = {k: v / total for k, v in assoc.items()}

    f_locked = 0.0
    for assoc_mineral, frac in fracs.items():
        f_assoc = floatabilities.get(assoc_mineral, 0.05)   # flottabilite de l'associe (gangue par defaut)
        f_mix = mixed_floatability(f_pur, f_assoc, w_bias=w_bias)
        f_locked += frac * f_mix

    return lib * f_pur + (1.0 - lib) * f_locked