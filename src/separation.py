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
        "pct_solids": {"min": 10.0, "max": 45.0, "default": 22.0},
        "_d50_range": (2.9, 6.5),   # plage de densité de coupure accessible
        "_ep_base": 0.8,           # netteté nominale (bonne)
    },
    "spiral": {
        "feed_rate_tph": {"min": 1.0, "max": 6.0, "default": 3.0},
        "splitter_pos": {"min": 0.2, "max": 0.8, "default": 0.5},
        "pct_solids": {"min": 10.0, "max": 45.0, "default": 22.0},
        "_d50_range": (3.2, 5.0),   # coupe plus haut, plus grossier
        "_ep_base": 0.55,           # tri moins net qu'une table
    },
    "falcon": {
        "rotation_g": {"min": 50.0, "max": 300.0, "default": 150.0},
        "fluid_water_lpm": {"min": 2.0, "max": 20.0, "default": 8.0},
        "pct_solids": {"min": 10.0, "max": 45.0, "default": 22.0},
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
        "pct_solids": {"min": 10.0, "max": 50.0, "default": 32.0},
        "depressed_minerals": {"default": []},
        "activated_minerals": {"default": []},
    },
    "ball_mill": {
        "work_index": {"min": 5.0, "max": 25.0, "default": 15.0},
        "energy_kwht": {"min": 5.0, "max": 30.0, "default": 10.0},
    },
    "hydrocyclone": {
        "diameter_cm": {"min": 5.0, "max": 50.0, "default": 15.0},
        "pressure_kpa": {"min": 20.0, "max": 300.0, "default": 100.0},
        "continue_flux": {"choices": ["overflow", "underflow"], "default": "overflow"},
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
    Partage d'un flux en concentre + rejet a partir d'une recuperation par mineral, car
    c'est l'operation commune a toutes les voies : ainsi chaque mineral voit sa masse
    repartie selon son taux, puis on reconstruit entierement les deux flux de sortie.
    gold_recovery : soit un float (fraction de l'or TOTAL au concentre), soit un dict par
    MODE {"sulfide":.., "native":.., "gangue":..}, car chaque mode d'or a sa propre
    recuperation (l'or des sulfures suit ses hotes, l'or natif a sa flottabilite, etc.) :
    ainsi on repartit chaque mode separement et l'on reconstruit les sous-cles dans chaque
    produit, ce qui permet a l'or de voyager correctement a travers un circuit.
    """
    minerals = list(stream.modal.keys())
    feed_mass = {m: stream.solids_tph * stream.modal[m] / 100.0 for m in minerals}
    conc_mass = {m: feed_mass[m] * recovery_by_mineral.get(m, 0.0) for m in minerals}
    tail_mass = {m: feed_mass[m] - conc_mass[m] for m in minerals}

    # Modes d'or transportes (en grammes contenus), car on conserve le metal et non la
    # teneur : ainsi chaque mode est reparti selon son propre taux de recuperation.
    au_modes = {
        "sulfide": "Au_sulfide_gt",
        "native": "Au_native_gt",
        "gangue": "Au_gangue_recoverable_gt",
    }
    # Grammes de chaque mode a l'alimentation.
    mode_feed_g = {mode: stream.assays.get(key, 0.0) * stream.solids_tph
                   for mode, key in au_modes.items()}

    # Taux de recuperation par mode, car gold_recovery peut etre un float (meme taux pour
    # tout) ou un dict (un taux par mode) : ainsi on normalise vers un dict.
    if gold_recovery is None:
        mode_rec = {mode: 0.0 for mode in au_modes}
    elif isinstance(gold_recovery, dict):
        mode_rec = {mode: float(gold_recovery.get(mode, 0.0)) for mode in au_modes}
    else:
        # Float : meme taux applique a tous les modes (compatibilite).
        mode_rec = {mode: float(gold_recovery) for mode in au_modes}

    # Grammes de chaque mode au concentre et au rejet.
    mode_conc_g = {mode: mode_feed_g[mode] * mode_rec[mode] for mode in au_modes}
    mode_tail_g = {mode: mode_feed_g[mode] - mode_conc_g[mode] for mode in au_modes}

    def build(mass_dict, name, mode_grams):
        total = sum(mass_dict.values())
        if total <= 1e-9:
            modal = {m: 0.0 for m in minerals}
            assays = {}
        else:
            modal = {m: round(mass_dict[m] / total * 100.0, 4) for m in minerals}
            assays = assay_func(modal) if assay_func is not None else assays_from_modal(modal)
            # Reconstruction des sous-cles d'or (teneur = grammes du mode / masse produit),
            # car chaque mode se reconcentre differemment : ainsi les modes voyagent intacts.
            au_total_g = sum(mode_grams.values())
            if au_total_g > 0:
                assays["Au_gt"] = round(au_total_g / total, 3)
                assays["Au_sulfide_gt"] = round(mode_grams["sulfide"] / total, 3)
                assays["Au_native_gt"] = round(mode_grams["native"] / total, 3)
                assays["Au_gangue_recoverable_gt"] = round(mode_grams["gangue"] / total, 3)
        lib = LiberationState(degree=dict(stream.liberation.degree),
                              classes=stream.liberation.classes,
                              associations=stream.liberation.associations)
        return Stream(
            name=f"{stream.name}_{name}",
            solids_tph=round(total, 4),
            modal=modal,
            liberation=lib,
            p80_um=stream.p80_um,
            psd_curve=stream.psd_curve,
            pct_solids_mass=stream.pct_solids_mass,
            assays=assays,
        )

    conc_modes = {mode: mode_conc_g[mode] for mode in au_modes}
    tail_modes = {mode: mode_tail_g[mode] for mode in au_modes}
    return (build(conc_mass, conc_name, conc_modes),
            build(tail_mass, tail_name, tail_modes))


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