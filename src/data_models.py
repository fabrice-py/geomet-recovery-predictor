"""
data_models.py
Structures de données centrales du projet géométallurgique.
Ces objets circulent dans toute la chaîne : générateur -> séparation -> bilan.

Conçu en Option A (libération scalaire par minéral) avec des hooks explicites
vers l'Option B (libération particulaire), pour évoluer sans casser l'interface.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class LiberationState:
    """
    État de libération d'un flux.

    Option A (utilisée) : `degree` = un degré de libération scalaire par minéral.
        Ex. {"chalcopyrite": 0.82, "quartz": 0.95}
    Option B (hook futur) : `classes` = distribution de particules / classes
        de libération par minéral. Laissé à None pour l'instant.
    """
    degree: dict                              # {mineral: float entre 0 et 1}
    classes: Optional[dict] = None            # hook Option B (non utilisé en A)

    def mean_liberation(self) -> float:
        """Libération moyenne (utile pour un résumé rapide)."""
        if not self.degree:
            return 0.0
        return float(np.mean(list(self.degree.values())))


@dataclass
class Stream:
    """
    Un flux de matière : solides + eau, décrit par sa minéralogie, sa libération,
    sa granulométrie et son état de pulpe. C'est l'unité qui circule dans le circuit.
    """
    # --- identité ---
    name: str                                 # ex. "alimentation", "concentre_1"

    # --- solides ---
    solids_tph: float                         # debit de solides (t/h)
    modal: dict                               # {mineral: % masse}, somme = 100
    liberation: LiberationState
    p80_um: float                             # maille P80 (resume granulo)
    psd_curve: Optional[np.ndarray] = None    # hook PSD complete (Option B)

    # --- pulpe / eau ---
    pct_solids_mass: float = 35.0             # % solides massique

    # --- champs derives (calcules plus tard, pas saisis) ---
    assays: dict = field(default_factory=dict)   # {element: %} reconstruit par stoechio
    water_tph: float = 0.0
    pulp_sg: float = 0.0
    solid_sg: float = 0.0

    def total_tph(self) -> float:
        """Debit total de pulpe (solides + eau)."""
        return self.solids_tph + self.water_tph

    def summary(self) -> str:
        """Petit resume lisible du flux (pour affichage/debug)."""
        top = sorted(self.modal.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_str = ", ".join(f"{m} {p:.1f}%" for m, p in top)
        return (f"[{self.name}] {self.solids_tph:.1f} t/h solides | "
                f"P80={self.p80_um:.0f} µm | pulpe {self.pct_solids_mass:.0f}% sol. | "
                f"top: {top_str}")
    
    def close_pulp(self, mineral_density: dict, rho_water: float = 1.0):
        """
        Fermeture de l'état pulpe du flux, car un flux réel est de la matière dans de
        l'eau : ainsi on calcule la densité du solide (loi de mélange), le débit d'eau
        (déduit du % solides) puis la densité de pulpe (masse totale / volume total).

        mineral_density : dict {mineral: densité g/cm3}, fourni par l'appelant, car la
        structure reste découplée de la base de propriétés.
        """
        # Densité du solide par loi de mélange, car les minéraux ont des densités
        # différentes : ainsi 1/rho_s = somme des (fraction massique / densité).
        w = {m: self.modal[m] / 100.0 for m in self.modal}
        inv_rho_s = sum(w[m] / mineral_density[m] for m in w)
        rho_s = 1.0 / inv_rho_s

        # Débit d'eau déduit du % solides massique, car % solides = solides/(solides+eau) :
        # ainsi eau = solides * (1/(pct/100) - 1).
        self.water_tph = self.solids_tph * (1.0 / (self.pct_solids_mass / 100.0) - 1.0)

        # Densité de pulpe = masse totale / volume total, car chaque volume vaut
        # masse/densité : ainsi une pulpe de minerai lourd sort plus dense.
        v_solids = self.solids_tph / rho_s
        v_water = self.water_tph / rho_water
        self.pulp_sg = (self.solids_tph + self.water_tph) / (v_solids + v_water)

        # On mémorise aussi la densité du solide, car elle resservira en gravimétrie.
        self.solid_sg = round(rho_s, 3)
        self.water_tph = round(self.water_tph, 2)
        self.pulp_sg = round(self.pulp_sg, 3)
        return self


if __name__ == "__main__":
    # Mini-test : on fabrique un flux À LA MAIN pour vérifier que les objets marchent.
    # (Le vrai générateur automatique viendra au Temps 3.)
    lib = LiberationState(degree={"chalcopyrite": 0.82, "quartz": 0.95})
    flux = Stream(
        name="test_alimentation",
        solids_tph=100.0,
        modal={"chalcopyrite": 4.0, "quartz": 96.0},
        liberation=lib,
        p80_um=120.0,
        pct_solids_mass=35.0,
    )
    print(flux.summary())
    print(f"Liberation moyenne : {lib.mean_liberation():.2f}")
    print(f"Debit total (avant calcul eau) : {flux.total_tph():.1f} t/h")