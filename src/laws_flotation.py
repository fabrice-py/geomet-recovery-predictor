"""
laws_flotation.py
Loi de flottation par cinétique de premier ordre, car la flottation dépend du temps
contrairement aux autres voies : ainsi chaque minéral récupère selon
R = Rmax * (1 - exp(-k * t)), où sa flottabilité native fixe Rmax et k de référence,
que les réglages (collecteur, moussant, rotor) viennent ensuite moduler.

Modèle cinétique (macroscopique), car il accueille tous les réglages de conduite sans
exiger les données microscopiques de collision bulle-particule (extension Option B).
Ce fichier traite la flottation DIRECTE au xanthate (5a) ; pH et flottation inverse
viendront au 5b.
"""

import math

from mineral_properties import MINERAL_PROPERTIES
from liberation_physics import effective_floatability_assoc

def kinetic_recovery(rmax, k, t):
    """
    Récupération cinétique de premier ordre, car la flottation progresse dans le temps
    vers un plateau : ainsi la récupération croît puis sature à Rmax.
    """
    return rmax * (1.0 - math.exp(-k * t))


def rotor_bell_factor(rpm, rpm_opt=1200.0, width=350.0):
    """
    Facteur cloche de l'agitation du rotor sur k, car il existe un optimum d'agitation :
    ainsi trop peu de rotation limite les collisions bulle-particule et trop de rotation
    détache les particules et fait coalescer les bulles, k chutant des deux côtés.
    """
    return math.exp(-((rpm - rpm_opt) ** 2) / (2 * width ** 2))

def effective_floatability(mineral, unit_settings, mineral_props=None):
    """
    Flottabilité effective d'un minéral selon le collecteur et les modificateurs, car la
    sélectivité d'un circuit différentiel se pilote minéral par minéral : ainsi tout
    minéral listé comme déprimé est écrasé et tout minéral listé comme activé est rendu
    fortement flottable, quel qu'il soit (sphalérite, galène, pyrite...).
    """
    collector = unit_settings["collector_type"]

    # Flottation inverse : seule la gangue silicatée flotte.
    if collector == "amine_inverse":
        return 0.85 if mineral in ("quartz", "gangue_silicate") else 0.05

    # Dépression / activation génériques, car elles priment sur la flottabilité native :
    # ainsi on interroge les listes fournies par l'étage plutôt qu'un minéral en dur.
    if mineral in unit_settings.get("depressed_minerals", []):
        return 0.05                          # déprimé : reste au fond
    if mineral in unit_settings.get("activated_minerals", []):
        return 0.90                          # activé : flotte comme un bon sulfure

    # Flottabilite custom si fournie, sinon la base, car l'utilisateur peut definir des
    # mineraux hors base : ainsi on lit sa valeur en priorite.
    if mineral_props is not None and mineral in mineral_props:
        return mineral_props[mineral]["floatability"]
    return MINERAL_PROPERTIES[mineral]["floatability"]


def ph_pyrite_factor(ph):
    """
    Facteur de dépression de la pyrite selon le pH, car la pyrite est déprimée en milieu
    alcalin : ainsi son Rmax reste plein à pH neutre et chute fortement vers pH 12.
    """
    return max(0.1, min(1.0, 1.0 - (ph - 8.0) / 4.0))


def flotation_recovery(stream, unit, mineral_props=None):
    """
    Récupération par minéral en flottation, car c'est le produit qu'attend separate() :
    ainsi on part de la flottabilité effective (selon le collecteur), on module k par la
    dose et l'agitation, Rmax par le moussant, on déprime la pyrite selon le pH, puis on
    convertit la fraction montée dans la mousse en récupération au concentré selon le
    sens (directe : mousse = concentré ; inverse : mousse = rejet).
    """
    s = unit.settings
    t = s["residence_min"]
    collector = s["collector_type"]
    reverse = (collector == "amine_inverse")

    dose_factor = 1.0 - math.exp(-s["collector_gpt"] / 80.0)
    bell = rotor_bell_factor(s["rotor_speed_rpm"])
    rmax_bonus = 0.10 * (1.0 - math.exp(-s["frother_gpt"] / 25.0))
    ph = s["pulp_ph"]

    # Table des flottabilites de tous les mineraux du flux, car les associations ont besoin de
    # la flottabilite des mineraux associes (pas seulement celle du mineral courant).
    floatab_table = {mm: effective_floatability(mm, s, mineral_props=mineral_props)
                     for mm in stream.modal}
    associations = getattr(stream.liberation, "associations", None)
    depressed = s.get("depressed_minerals", [])
    activated = s.get("activated_minerals", [])

    recovery = {}
    for m in stream.modal:
        floatab = floatab_table[m]
        # Associations (chemin 2) : la flottabilite depend de la liberation. On enrichit
        # SEULEMENT la flottabilite native, car depression/activation sont des choix chimiques
        # de l'operateur qui priment : ainsi un mineral deprime reste deprime quelle que soit
        # sa liberation. Fallback si pas d'association (comportement actuel).
        if m not in depressed and m not in activated:
            lib = stream.liberation.degree.get(m, 1.0)
            f_assoc = effective_floatability_assoc(m, floatab, lib, associations, floatab_table)
            if f_assoc is not None:
                floatab = f_assoc
        rmax = min(0.98, 0.02 + 0.95 * (floatab ** 2) + rmax_bonus)
        k = (0.15 + 1.60 * floatab) * dose_factor * bell

        # Dépression de la pyrite en milieu alcalin (uniquement flottation directe).
        if m == "pyrite_co" and not reverse:
            rmax *= ph_pyrite_factor(ph)

        float_frac = kinetic_recovery(rmax, k, t)   # fraction montant dans la mousse

        # Conversion mousse -> concentré, car en flottation inverse la mousse est le
        # rejet : ainsi le concentré récupère ce qui NE monte PAS.
        recovery[m] = round(1.0 - float_frac if reverse else float_frac, 4)
    return recovery


def gold_flotation_recovery(stream, mineral_recovery, unit):
    """
    Recuperation de l'or au concentre en flottation, selon ses trois modes, car chacun a un
    comportement propre : ainsi l'or des sulfures suit ses hotes (pyrite/arseno), l'or natif
    a sa flottabilite propre passee dans la cinetique (donc sensible aux reglages), et l'or
    de gangue ne flotte quasiment pas. En flottation inverse (fer), pas d'or a traiter.

    Renvoie une fraction 0-1 de l'or TOTAL partant au concentre (ce qu'attend separate()).
    """
    if unit.settings["collector_type"] == "amine_inverse":
        return 0.0

    total_au = stream.assays.get("Au_gt", None)
    if total_au is None or total_au <= 1e-9:
        return 0.0

    au_sulfide = stream.assays.get("Au_sulfide_gt", 0.0)
    au_native = stream.assays.get("Au_native_gt", 0.0)
    au_gangue_recov = stream.assays.get("Au_gangue_recoverable_gt", 0.0)

    # 1) Or des sulfures : suit ses hotes (moyenne ponderee par leur masse), car il est pige
    # dans pyrite/arseno : ainsi il flotte quand elles flottent -> sensible aux reglages via
    # mineral_recovery des sulfures.
    hosts = ["arsenopyrite", "pyrite_co"]
    host_mass = {h: stream.modal.get(h, 0.0) for h in hosts}
    total_host = sum(host_mass.values())
    host_recovery = (sum(mineral_recovery.get(h, 0.0) * host_mass[h] for h in hosts)
                     / total_host) if total_host > 1e-9 else 0.0

    # 2) Or natif : flottabilite propre moderee, passee dans la MEME cinetique que les
    # mineraux, car l'or natif flotte mais moins bien qu'attache a un sulfure : ainsi
    # collecteur, dose, temps et moussant l'affectent (reglages actifs).
    s = unit.settings
    t = s["residence_min"]
    dose_factor = 1.0 - math.exp(-s["collector_gpt"] / 80.0)
    bell = rotor_bell_factor(s["rotor_speed_rpm"])
    rmax_bonus = 0.10 * (1.0 - math.exp(-s["frother_gpt"] / 25.0))
    native_floatab = 0.85   # or natif libere : bonne flottabilite (hydrophobe, xanthate), a calibrer
    rmax_nat = min(0.98, 0.02 + 0.95 * (native_floatab ** 2) + rmax_bonus)
    k_nat = (0.15 + 1.60 * native_floatab) * dose_factor * bell
    native_recovery = kinetic_recovery(rmax_nat, k_nat, t)

    # 3) Or de gangue RECUPERABLE : c'est de l'or LIBERE par le broyage, donc detache de la
    # silice -> il se comporte comme de l'or natif nouvellement libere, et flotte comme lui
    # (et non comme la gangue). Ainsi broyer fin ameliore la recuperation au lieu de la
    # degrader : l'or libere devient flottable.
    gangue_recovery = native_recovery

    # On renvoie un taux PAR MODE (dict), car separate() repartit chaque mode d'or
    # separement : ainsi l'or des sulfures suit ses hotes, l'or natif sa cinetique, etc.,
    # et chaque mode voyage correctement a travers un circuit.
    return {
        "sulfide": round(host_recovery, 4),
        "native": round(native_recovery, 4),
        "gangue": round(gangue_recovery, 4),
    }

if __name__ == "__main__":
    # Test : flottation directe d'un minerai polymétallique, car on veut voir les
    # sulfures (chalcopyrite en tête) monter dans la mousse et la gangue rester au rejet.
    from feed_generator import generate_feed
    from separation import separate, SeparationUnit

    flux = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]
    print("Alimentation (minéralogie) :")
    for m, p in sorted(flux.modal.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {m:16s} {p:5.1f} %   (flottabilité {MINERAL_PROPERTIES[m]['floatability']})")

    unit = SeparationUnit("flotation", {"collector_gpt": 100, "residence_min": 8,
                                        "rotor_speed_rpm": 1200})
    reco = flotation_recovery(flux, unit)
    print("\nRécupération par minéral (flottation directe) :")
    for m, r in sorted(reco.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {m:16s} {r*100:5.1f} %")

    conc, rejet = separate(flux, reco)
    print(f"\nCu alimentation : {flux.assays.get('Cu', 0):.2f} %")
    print(f"Cu concentré    : {conc.assays.get('Cu', 0):.2f} %   (masse {conc.solids_tph:.1f} t/h)")
    print(f"Cu rejet        : {rejet.assays.get('Cu', 0):.2f} %")