"""
feed_generator.py
Génération de flux d'alimentation synthétiques, car sans données nous devons
fabriquer nous-mêmes la matière première du modèle : ainsi le générateur part de la
minéralogie (tirée par une loi de Dirichlet qui garantit la fermeture à 100 %), puis
en déduit les teneurs par stœchiométrie, la libération et l'état de pulpe, avant
d'assembler le tout en objets Stream.

La logique reste séparée de la présentation, car c'est ce qui rend le cœur branchable
sur n'importe quelle interface : ainsi generate_feed renvoie des Stream, tandis que
streams_to_dataframe ne sert qu'à explorer.
"""

import numpy as np
import pandas as pd

from data_models import Stream, LiberationState
from mineralogy import ORE_PROFILES, assays_from_modal


def generate_feed(profile_name="polymetallic_refractory_au", n_samples=500,
                  seed=42, feed_tph=100.0, assay_noise_pct=0.0):
    """
    Génération de n flux d'alimentation pour un profil donné, car chaque flux doit
    être un échantillon cohérent : ainsi on tire d'abord la minéralogie, puis on en
    dérive les teneurs, la libération et la pulpe.
    """
    if profile_name not in ORE_PROFILES:
        raise ValueError(f"Profil inconnu : {profile_name}. "
                         f"Choix possibles : {list(ORE_PROFILES)}")

    profile = ORE_PROFILES[profile_name]
    minerals = profile["minerals"]
    rng = np.random.default_rng(seed)

    # Tirage de la finesse de broyage P80, car elle conditionne la libération : ainsi
    # un P80 faible (broyage fin) se traduira plus bas par une meilleure libération.
    p80 = np.clip(rng.normal(150, 45, n_samples), 45, 300)
    fineness = 1 - (p80 - 45) / (300 - 45)   # normalisation de 0 (grossier) à 1 (fin)

    # Tirage de la minéralogie modale par une loi de Dirichlet, car elle garantit
    # d'office que les proportions somment à 100 % (contrainte de fermeture).
    modal_matrix = rng.dirichlet(profile["modal_alpha"], size=n_samples) * 100.0

    # Variation réaliste du % solides de la pulpe autour d'une valeur d'alimentation.
    pct_solids = np.clip(rng.normal(35, 3, n_samples), 20, 50)

    # Préparation de l'or si le profil en contient, car sa part réfractaire dépendra
    # des sulfures hôtes : ainsi on repère leurs indices une fois pour toutes.
    gold = profile.get("gold_bearing", False)
    if gold:
        au_lo, au_hi = profile["au_gt_range"]
        au_gt = rng.uniform(au_lo, au_hi, n_samples)
        host_idx = [minerals.index(h) for h in profile["au_hosts"]]

    streams = []
    for i in range(n_samples):
        # Assemblage de la minéralogie modale de l'échantillon i sous forme de dict.
        modal = {m: round(float(modal_matrix[i, j]), 3)
                 for j, m in enumerate(minerals)}

        # Reconstruction des teneurs élémentaires par stœchiométrie (minéral -> élément).
        assays = assays_from_modal(modal)

        # Ajout d'un bruit analytique sur les teneurs, car aucune mesure XRF n'est
        # parfaite : ainsi on simule l'incertitude de l'instrument (bruit relatif,
        # gaussien) sans jamais toucher à la minéralogie, qui reste la vérité physique.
        if assay_noise_pct > 0:
            assays = {el: round(max(0.0, v * (1 + rng.normal(0, assay_noise_pct / 100))), 3)
                      for el, v in assays.items()}
            
        # Attribution d'un degré de libération par minéral, car la libération pilotera
        # la récupération : ainsi on la fait croître avec la finesse, avec un léger
        # bruit propre à chaque minéral pour rester réaliste.
        degree = {m: float(np.clip(0.55 + 0.35 * fineness[i] + rng.normal(0, 0.05), 0, 1))
                  for m in minerals}
        liberation = LiberationState(degree={m: round(v, 3) for m, v in degree.items()})

        # Construction du flux, car c'est l'objet qui circulera dans tout le circuit.
        stream = Stream(
            name=f"{profile_name}_feed_{i + 1}",
            solids_tph=feed_tph,
            modal=modal,
            liberation=liberation,
            p80_um=round(float(p80[i]), 1),
            pct_solids_mass=round(float(pct_solids[i]), 1),
            assays=assays,
        )
# On memorise le profil dans le flux, car recalculer la liberation/l'or selon un
        # nouveau P80 (via apply_p80) exige de connaitre les hotes de l'or et les fractions :
        # ainsi le flux devient autonome.
        stream.profile_name = profile_name
        # Ajout de l'or réfractaire à part, car il ne provient pas de la stœchiométrie
        # des minéraux : ainsi sa part piégée croît avec les sulfures hôtes et avec un
        # broyage grossier, et le reste constitue l'or libre récupérable.
        
        if gold:
            host_modal = sum(modal_matrix[i, j] for j in host_idx)
            host_norm = np.clip(host_modal / 5.0, 0, 1)
            refractory = float(np.clip(
                0.25 + 0.50 * host_norm + 0.20 * (1 - fineness[i])
                + rng.normal(0, 0.05), 0, 0.95))
            total_au = float(au_gt[i])
            # Or dans les sulfures (part refractaire), car pige dans pyrite/arseno : ainsi
            # il suivra la flottation de ses hotes.
            au_sulfide = total_au * refractory
            # La part non-sulfures se scinde en natif (gravimetrie) et gangue (recuperable
            # seulement si le broyage libere), selon les fractions du profil.
            nf = profile.get("au_native_frac", 1.0)
            gf = profile.get("au_gangue_frac", 0.0)
            denom = nf + gf if (nf + gf) > 1e-9 else 1.0
            non_sulfide = total_au * (1 - refractory)
            au_native = non_sulfide * nf / denom
            au_gangue = non_sulfide * gf / denom
            # L'or de la gangue n'est effectivement recuperable qu'a hauteur de la finesse
            # de broyage, car il faut liberer le grain : ainsi broyage grossier -> ~0.
            au_gangue_recoverable = au_gangue * fineness[i]

            stream.assays["Au_gt"] = round(total_au, 2)
            stream.assays["Au_refractory_frac"] = round(refractory, 3)
            stream.assays["Au_sulfide_gt"] = round(au_sulfide, 3)
            stream.assays["Au_native_gt"] = round(au_native, 3)
            stream.assays["Au_gangue_gt"] = round(au_gangue, 3)
            stream.assays["Au_gangue_recoverable_gt"] = round(au_gangue_recoverable, 3)
            # Distribution de LIBERATION de l'or natif, car un grain d'or mal degage se
            # recupere mal en gravite : ainsi on scinde le natif en trois classes selon la
            # finesse, ce qui etale la courbe teneur-recuperation (au lieu d'un "tout ou rien").
            L = fineness[i]
            f_lib = L
            f_lock = (1 - L) ** 2
            f_med = max(0.0, 1 - f_lib - f_lock)
            stream.assays["Au_native_liberated_gt"] = round(au_native * f_lib, 3)
            stream.assays["Au_native_medium_gt"] = round(au_native * f_med, 3)
            stream.assays["Au_native_locked_gt"] = round(au_native * f_lock, 3)
            # Conserve l'ancienne cle pour compatibilite (or "libre" = natif + gangue libere).
            stream.assays["Au_free_gt"] = round(au_native + au_gangue_recoverable, 2)

        streams.append(stream)

    return streams


def streams_to_dataframe(streams):
    """
    Mise à plat d'une liste de Stream en DataFrame, car les objets circulent bien mais
    s'explorent mal : ainsi ce tableau ne sert qu'aux statistiques et aux figures, et
    jamais au calcul lui-même.
    """
    rows = []
    for s in streams:
        row = {"name": s.name, "p80_um": s.p80_um, "pct_solids": s.pct_solids_mass,
               "liberation_moy": round(s.liberation.mean_liberation(), 3)}
        row.update(s.assays)
        rows.append(row)
    return pd.DataFrame(rows)

def apply_p80(stream, p80):
    """
    Recalcule la liberation et la distribution de l'or d'un flux pour un P80 donne, car le
    P80 regle par l'utilisateur doit reellement piloter la liberation (et donc les
    recuperations) : ainsi on refait, de façon deterministe, ce que generate_feed calcule,
    mais avec le P80 effectif. Modifie le flux en place.
    """
    p80 = float(np.clip(p80, 10, 300))
    fineness = 1 - (p80 - 45) / (300 - 45)
    fineness = float(np.clip(fineness, 0.0, 1.0))
    stream.p80_um = round(p80, 1)

    # Liberation par mineral, deterministe (sans bruit), car un reglage utilisateur doit
    # etre reproductible : ainsi la liberation est une fonction lisse du P80.
    degree = {m: float(np.clip(0.55 + 0.35 * fineness, 0, 1)) for m in stream.modal}
    stream.liberation = LiberationState(degree={m: round(v, 3) for m, v in degree.items()})

    # Cascade de l'or, si present, recalculee avec le P80 effectif.
    profile_name = getattr(stream, "profile_name", None)
    if profile_name is None or profile_name not in ORE_PROFILES:
        return stream
    profile = ORE_PROFILES[profile_name]
    if not profile.get("gold_bearing", False):
        return stream

    total_au = stream.assays.get("Au_gt", 0.0)
    if total_au <= 1e-9:
        return stream

    # Part refractaire recalculee, car broyer plus fin libere une partie de l'or des
    # sulfures : ainsi refractory baisse quand la finesse monte.
    hosts = profile["au_hosts"]
    host_modal = sum(stream.modal.get(h, 0.0) for h in hosts)
    host_norm = float(np.clip(host_modal / 5.0, 0, 1))
    refractory = float(np.clip(0.25 + 0.50 * host_norm + 0.20 * (1 - fineness), 0, 0.95))

    au_sulfide = total_au * refractory
    nf = profile.get("au_native_frac", 1.0)
    gf = profile.get("au_gangue_frac", 0.0)
    denom = nf + gf if (nf + gf) > 1e-9 else 1.0
    non_sulfide = total_au * (1 - refractory)
    au_native = non_sulfide * nf / denom
    au_gangue = non_sulfide * gf / denom
    au_gangue_recoverable = au_gangue * fineness

    L = fineness
    f_lib = L
    f_lock = (1 - L) ** 2
    f_med = max(0.0, 1 - f_lib - f_lock)

    stream.assays["Au_refractory_frac"] = round(refractory, 3)
    stream.assays["Au_sulfide_gt"] = round(au_sulfide, 3)
    stream.assays["Au_native_gt"] = round(au_native, 3)
    stream.assays["Au_gangue_gt"] = round(au_gangue, 3)
    stream.assays["Au_gangue_recoverable_gt"] = round(au_gangue_recoverable, 3)
    stream.assays["Au_native_liberated_gt"] = round(au_native * f_lib, 3)
    stream.assays["Au_native_medium_gt"] = round(au_native * f_med, 3)
    stream.assays["Au_native_locked_gt"] = round(au_native * f_lock, 3)
    stream.assays["Au_free_gt"] = round(au_native + au_gangue_recoverable, 2)
    return stream

def liberation_from_p80(p80):
    """Degre de liberation moyen deduit du P80, car la finesse de broyage pilote la
    liberation : ainsi base et custom utilisent la meme loi que les profils (coherence)."""
    p80 = float(np.clip(p80, 10, 300))
    fineness = 1 - (p80 - 45) / (300 - 45)
    fineness = float(np.clip(fineness, 0.0, 1.0))
    return round(float(np.clip(0.55 + 0.35 * fineness, 0, 1)), 3)

if __name__ == "__main__":
    # Génération des deux profils, car on veut vérifier que l'architecture tient sur
    # le cas simple (fer) comme sur le cas complexe (polymétallique).
    for name in ORE_PROFILES:
        print(f"\n===== Profil : {name} =====")
        streams = generate_feed(profile_name=name, n_samples=500, assay_noise_pct=2.0)

        # Affichage de deux flux, car un contrôle à l'oeil complète les statistiques.
        for s in streams[:2]:
            print(s.summary())

        # Statistiques des teneurs, car c'est là qu'on juge le réalisme des ordres
        # de grandeur (Cu autour de 1 %, SiO2 dominant, etc.).
        df = streams_to_dataframe(streams)
        assay_cols = [c for c in df.columns
                      if c not in ("name", "p80_um", "pct_solids", "liberation_moy")]
        print("\nStatistiques des teneurs :")
        print(df[assay_cols].describe().round(2).to_string())