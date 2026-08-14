"""
separation.py
Moteur de séparation : structure des unités et machinerie de partage d'un flux.

On sépare volontairement deux responsabilités, car elles reviennent dans les trois
voies : d'un côté la LOI (combien de chaque minéral part au concentré, propre à chaque
voie), de l'autre la MACHINERIE (comment on découpe le flux), identique partout. Ce
fichier pose la structure des unités et la machinerie ; les lois viendront ensuite.
"""

from dataclasses import dataclass, field

from data_models import Stream, LiberationState
from mineralogy import assays_from_modal


# --- Registre des paramètres de conduite par voie -----------------------------
# C'est de la DONNEE (bornes + défaut par paramètre), car elle sert à la fois à
# valider les entrées utilisateur et, plus tard, à générer une interface : ainsi
# ajouter une machine = ajouter une entrée, sans toucher au moteur.
SEPARATION_SPECS = {
    "shaking_table": {
        "deck_slope_deg": {"min": 1.5, "max": 6.0, "default": 3.0},
        "stroke_freq_hz": {"min": 4.0, "max": 7.0, "default": 5.5},
        "wash_water_lpm": {"min": 5.0, "max": 40.0, "default": 20.0},
        "_d50_range": (2.9, 8.0),   # plage de densité de coupure accessible
        "_ep_base": 0.35,           # netteté nominale (bonne)
    },
    "spiral": {
        "feed_rate_tph": {"min": 1.0, "max": 6.0, "default": 3.0},
        "splitter_pos": {"min": 0.2, "max": 0.8, "default": 0.5},
        "_d50_range": (3.2, 5.0),   # coupe plus haut, plus grossier
        "_ep_base": 0.55,           # tri moins net qu'une table
    },
    "falcon": {
        "rotation_g": {"min": 50.0, "max": 300.0, "default": 150.0},
        "fluid_water_lpm": {"min": 2.0, "max": 20.0, "default": 8.0},
        "_d50_range": (2.7, 4.0),   # la force G permet de couper plus bas (ultrafines)
        "_ep_base": 0.50,           # centrifuge : tri correct mais large
    },
    "magnetic": {
        "mode": {"choices": ["LIMS_wet", "LIMS_dry", "WHIMS_wet", "WHIMS_dry"],
                 "default": "WHIMS_wet"},
        "field_tesla": {"min": 0.05, "max": 2.0, "default": 1.0},
        "drum_speed_rpm": {"min": 10.0, "max": 120.0, "default": 60.0},
    },
    "flotation": {
        "collector_type": {"choices": ["xanthate_SIBX", "PAX", "amine_inverse"],
                           "default": "xanthate_SIBX"},
        "collector_gpt": {"min": 10.0, "max": 300.0, "default": 80.0},
        "frother_gpt": {"min": 5.0, "max": 60.0, "default": 25.0},
        "pulp_ph": {"min": 6.0, "max": 12.0, "default": 9.0},
        "residence_min": {"min": 2.0, "max": 20.0, "default": 8.0},
        "rotor_speed_rpm": {"min": 800.0, "max": 1800.0, "default": 1200.0},
        "depressed_minerals": {"default": []},
        "activated_minerals": {"default": []},
    },
}

@dataclass
class SeparationUnit:
    """
    Une unité de séparation = un type + ses réglages, car une machine ne se définit que
    par la voie qu'elle emploie et la façon dont on la conduit : ainsi on complète les
    réglages manquants par les défauts et on valide ceux fournis contre le registre.
    """
    unit_type: str
    settings: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.unit_type not in SEPARATION_SPECS:
            raise ValueError(f"Type de séparation inconnu : {self.unit_type}. "
                             f"Choix : {list(SEPARATION_SPECS)}")
        spec = SEPARATION_SPECS[self.unit_type]
        # Complétion et validation, car un réglage aberrant doit être refusé tôt : ainsi
        # on remplit les défauts absents et on contrôle les bornes / choix des présents.
        for param, rule in spec.items():
            if param.startswith("_"):
                continue   # clé interne au modèle, pas un réglage utilisateur
            if param not in self.settings:
                self.settings[param] = rule["default"]
            else:
                self._validate(param, rule, self.settings[param])

    def _validate(self, param, rule, value):
        if "choices" in rule and value not in rule["choices"]:
            raise ValueError(f"{param} = {value} hors des choix {rule['choices']}")
        if "min" in rule and not (rule["min"] <= value <= rule["max"]):
            raise ValueError(f"{param} = {value} hors bornes "
                             f"[{rule['min']}, {rule['max']}]")


def separate(stream, recovery_by_mineral, gold_recovery=None,
             conc_name="concentre", tail_name="rejet", assay_func=None):
    """
    Partage d'un flux en concentré + rejet à partir d'une récupération par minéral, car
    c'est l'opération commune à toutes les voies : ainsi chaque minéral voit sa masse
    répartie selon son taux de récupération, puis on reconstruit entièrement les deux
    flux de sortie (minéralogie, teneurs, libération).

    gold_recovery : fraction 0-1 de l'or partant au concentré, car l'or n'est pas un
    minéral de modal mais un traceur en g/t : ainsi on transporte le métal CONTENU
    (g/t x masse) plutôt que la teneur, puis on recalcule la teneur de chaque produit.
    """
    minerals = list(stream.modal.keys())

    # Masse de chaque minéral à l'alimentation, car tout le partage part de là.
    feed_mass = {m: stream.solids_tph * stream.modal[m] / 100.0 for m in minerals}
    conc_mass = {m: feed_mass[m] * recovery_by_mineral.get(m, 0.0) for m in minerals}
    tail_mass = {m: feed_mass[m] - conc_mass[m] for m in minerals}

    # Or contenu à l'alimentation en grammes, car on conserve le métal et non la teneur :
    # ainsi masse d'or = teneur (g/t) x masse solides (t).
    au_feed_gt = stream.assays.get("Au_gt", 0.0)
    au_total_g = au_feed_gt * stream.solids_tph
    if gold_recovery is not None:
        au_conc_g = au_total_g * gold_recovery
        au_tail_g = au_total_g - au_conc_g
    else:
        au_conc_g = au_tail_g = 0.0

    def build(mass_dict, name, au_grams):
        total = sum(mass_dict.values())
        # Reconstruction de la minéralogie du flux de sortie, car les proportions changent
        # après tri : ainsi on renormalise, en gérant le cas d'un flux vide.
        if total <= 1e-9:
            modal = {m: 0.0 for m in minerals}
            assays = {}
        else:
            modal = {m: round(mass_dict[m] / total * 100.0, 4) for m in minerals}
            # Reconstruction des teneurs : fonction custom si fournie (mineraux hors base),
            # sinon la stoechiometrie de la base, car un minerai custom a sa propre chimie.
            assays = assay_func(modal) if assay_func is not None else assays_from_modal(modal)
            # Teneur en or du produit = or contenu / masse du produit, car l'or se
            # reconcentre dans le flux qui capte les sulfures : ainsi un petit concentré
            # riche en sulfures aura une teneur en or bien plus élevée que l'alimentation.
            if au_grams > 0:
                assays["Au_gt"] = round(au_grams / total, 3)
        # La libération est portée telle quelle vers les deux produits (simplification
        # Option A), car son EFFET sur le tri est déjà pris en compte dans la loi de
        # récupération : ainsi la machinerie ne fait que déplacer la masse.
        lib = LiberationState(degree=dict(stream.liberation.degree))
        return Stream(
            name=f"{stream.name}_{name}",
            solids_tph=round(total, 4),
            modal=modal,
            liberation=lib,
            p80_um=stream.p80_um,
            pct_solids_mass=stream.pct_solids_mass,
            assays=assays,
        )

    return (build(conc_mass, conc_name, au_conc_g),
            build(tail_mass, tail_name, au_tail_g))


if __name__ == "__main__":
    # Test de la machinerie avec une récupération FIXÉE À LA MAIN, car on veut valider
    # le partage AVANT d'avoir la moindre physique : ainsi on isole la machinerie.
    from feed_generator import generate_feed

    flux = generate_feed("iron_flotation", n_samples=1, seed=1)[0]
    print("ALIMENTATION")
    print(" ", flux.summary())
    print(f"  Fe alim. = {flux.assays['Fe']} %\n")

    # On envoie les oxydes de fer au concentré, le quartz au rejet, car c'est le
    # comportement attendu d'une séparation qui concentre le fer.
    reco = {"hematite": 0.92, "magnetite": 0.95, "quartz": 0.05}
    conc, rejet = separate(flux, reco)

    print("CONCENTRE"); print(" ", conc.summary()); print(f"  Fe conc. = {conc.assays['Fe']} %")
    print("REJET");     print(" ", rejet.summary()); print(f"  Fe rejet = {rejet.assays['Fe']} %")

    # Contrôle de conservation de la masse, car un bilan doit TOUJOURS boucler : ainsi
    # concentré + rejet doit égaler l'alimentation, à l'arrondi près.
    total = conc.solids_tph + rejet.solids_tph
    print(f"\nConservation masse : {conc.solids_tph} + {rejet.solids_tph} = {total} t/h "
          f"(alim. {flux.solids_tph})")