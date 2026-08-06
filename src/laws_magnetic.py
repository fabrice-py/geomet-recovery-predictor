"""
laws_magnetic.py
Loi de séparation magnétique, car certains minéraux se trient par leur réponse à un
champ et non par leur densité : ainsi on traduit la catégorie magnétique de chaque
minéral en une susceptibilité indicative, puis on capture ceux dont la susceptibilité
dépasse le seuil fixé par la machine.

Susceptibilités = valeurs INDICATIVES par catégorie (posture phénoménologique), car on
vise les bons sens de variation et non une précision calibrée.
"""

import math

from mineral_properties import MINERAL_PROPERTIES

# Traduction catégorie magnétique -> susceptibilité indicative (échelle 0-1), car la
# base stocke une catégorie texte alors que le calcul de seuil exige un nombre : ainsi
# on ordonne les catégories du plus au moins magnétique.
SUSCEPTIBILITY = {
    "ferromagnetique":        1.00,   # magnétite : capté même à faible champ (LIMS)
    "paramagnetique":         0.35,   # hématite, arsénopyrite : nécessite un fort champ
    "paramagnetique_faible":  0.12,   # sulfures faiblement paramagnétiques
    "diamagnetique":          0.00,   # quartz, gangue : non magnétiques
}


def magnetic_capture(susceptibility, threshold, sharpness):
    """
    Probabilité de capture d'un minéral au concentré magnétique, car la capture n'est
    jamais tout-ou-rien : ainsi on utilise une transition logistique autour du seuil,
    dont la raideur est fixée par la machine (un bon séparateur tranche net).
    """
    return 1.0 / (1.0 + math.exp(-sharpness * (susceptibility - threshold)))


def magnetic_recovery(stream, threshold, sharpness):
    """
    Récupération par minéral au concentré magnétique, car c'est le produit qu'attend
    separate() : ainsi on lit la catégorie magnétique de chaque minéral, on la traduit
    en susceptibilité, puis on applique la loi de capture.

    threshold, sharpness : fournis par la machine selon son mode et son champ.
    """
    recovery = {}
    for m in stream.modal:
        cat = MINERAL_PROPERTIES[m]["magnetic"]
        chi = SUSCEPTIBILITY[cat]
        recovery[m] = round(magnetic_capture(chi, threshold, sharpness), 4)
    return recovery


def magnetic_cutpoint(unit):
    """
    Traduction des réglages du séparateur magnétique en (seuil, raideur), car
    l'utilisateur règle un mode et un champ, pas un seuil de susceptibilité : ainsi le
    mode LIMS/WHIMS fixe la plage captée et le champ ajuste finement le seuil.
    """
    from separation import SEPARATION_SPECS
    if unit.unit_type != "magnetic":
        raise ValueError(f"{unit.unit_type} n'est pas un séparateur magnétique")
    s = unit.settings
    mode = s["mode"]

    # Le mode fixe le seuil de base, car LIMS ne capte que le ferromagnétique tandis que
    # WHIMS descend capter les paramagnétiques : ainsi WHIMS a un seuil bien plus bas.
    if mode.startswith("LIMS"):
        base_threshold = 0.65      # au-dessus de para (0.35), ne prend que le ferro (1.0)
    else:  # WHIMS
        base_threshold = 0.22      # descend capter les paramagnétiques (0.35)

    # Le champ ajuste le seuil autour de cette base, car un champ plus fort capte des
    # minéraux moins magnétiques : ainsi monter le champ ABAISSE le seuil.
    field = s["field_tesla"]
    field_frac = (field - 0.05) / (2.0 - 0.05)
    threshold = base_threshold - 0.10 * field_frac

    # La voie sèche trie moins finement les particules fines, car elles s'agglomèrent
    # faute d'eau pour les disperser : ainsi la voie sèche est un peu moins raide.
    sharpness = 25.0 if mode.endswith("wet") else 18.0

    return round(threshold, 3), round(sharpness, 1)


if __name__ == "__main__":
    # Test : le MÊME flux de fer séparé en LIMS puis en WHIMS, car on veut voir la
    # magnétite captée dans les deux, mais l'hématite seulement en WHIMS.
    from feed_generator import generate_feed
    from separation import separate, SeparationUnit

    flux = generate_feed("iron_flotation", n_samples=1, seed=1)[0]
    print(f"Alimentation : hematite={flux.modal['hematite']:.1f}% "
          f"magnetite={flux.modal['magnetite']:.1f}% quartz={flux.modal['quartz']:.1f}%\n")

    for mode in ["LIMS_wet", "WHIMS_wet"]:
        unit = SeparationUnit("magnetic", {"mode": mode, "field_tesla": 1.0})
        thr, sharp = magnetic_cutpoint(unit)
        reco = magnetic_recovery(flux, threshold=thr, sharpness=sharp)
        conc, rejet = separate(flux, reco)
        print(f"{mode:10s} seuil={thr:.2f} | "
              f"récup: mag={reco['magnetite']*100:.0f}% hem={reco['hematite']*100:.0f}% "
              f"qz={reco['quartz']*100:.0f}% | "
              f"concentré {conc.solids_tph:.1f}t/h à Fe={conc.assays['Fe']:.1f}%")