"""
app.py
Interface web du simulateur geometallurgique (Streamlit). Trois modes de minerai :
profil predefini, mineralogie composee depuis la base, et mineraux ENTIEREMENT
personnalises (l'utilisateur definit nom, proportion, proprietes physiques et chimie).
L'interface ne fait qu'habiller la logique de src/ (principe logique/presentation separe).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pandas as pd
import streamlit as st

from feed_generator import generate_feed
from mineralogy import ORE_PROFILES, MINERALS, assays_from_modal
from data_models import Stream, LiberationState
from separation import SeparationUnit, SEPARATION_SPECS, separate
from laws_gravity import gravity_recovery, gravity_cutpoint
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery


# Perimetre d'elements type XRF, car l'utilisateur veut saisir une composition large :
# ainsi on couvre metaux de valeur, gangue et elements penalisants.
XRF_ELEMENTS = [
    "Fe", "Cu", "Zn", "Pb", "Au", "Ag", "Ni", "Co", "Sn", "W", "Mn", "Ti", "Cr", "V",
    "U", "Mo", "SiO2", "Al2O3", "CaO", "MgO", "K", "Na", "P", "S", "As", "Sb", "Bi", "F",
]

MAGNETIC_CATEGORIES = ["ferromagnetique", "paramagnetique",
                       "paramagnetique_faible", "diamagnetique"]


st.set_page_config(page_title="Simulateur geometallurgique", layout="wide")
st.title("Simulateur geometallurgique de separation")
st.caption("Choisissez un minerai, une voie de separation et ses reglages : "
           "l'outil predit le concentre, le rejet et les teneurs.")


# ============================ BARRE LATERALE ============================
st.sidebar.header("1. Minerai")

feed_tph = st.sidebar.number_input("Debit d'alimentation (t/h)",
                                   min_value=1.0, max_value=10000.0, value=100.0, step=10.0)

mode_minerai = st.sidebar.radio(
    "Mode", ["Profil predefini", "Mineralogie (base)", "Mineraux personnalises"])

profile_name = None
custom_modal = None
use_custom_minerals = False

if mode_minerai == "Profil predefini":
    profile_name = st.sidebar.selectbox("Profil", options=list(ORE_PROFILES.keys()))

elif mode_minerai == "Mineralogie (base)":
    st.sidebar.markdown("**Composez depuis la base** (% de chaque phase)")
    custom_modal = {}
    for mineral in MINERALS.keys():
        pct = st.sidebar.slider(mineral, 0.0, 100.0, 0.0, step=0.5)
        if pct > 0:
            custom_modal[mineral] = pct
    total_saisi = sum(custom_modal.values())
    if total_saisi == 0:
        st.sidebar.warning("Ajoutez au moins une phase (proportion > 0).")
    elif abs(total_saisi - 100.0) < 0.01:
        st.sidebar.success(f"Total : {total_saisi:.1f} %")
    else:
        st.sidebar.info(f"Total : {total_saisi:.1f} % -> renormalise a 100 %")

else:  # Mineraux personnalises
    use_custom_minerals = True
    st.sidebar.markdown("**Mineraux personnalises**")
    st.sidebar.caption("Definissez vos phases dans la zone principale (tableaux a droite), "
                       "puis reglez ici la voie et lancez.")

p80 = st.sidebar.slider("P80 (um) - finesse de broyage", 45.0, 300.0, 150.0, step=5.0)
liberation_deg = st.sidebar.slider("Degre de liberation moyen", 0.0, 1.0, 0.85, step=0.05)

st.sidebar.header("2. Voie de separation")
voies = ["shaking_table", "spiral", "falcon", "magnetic", "flotation"]
unit_type = st.sidebar.selectbox("Type d'unite", options=voies)

st.sidebar.header("3. Reglages machine")
settings = {}
for param, rule in SEPARATION_SPECS[unit_type].items():
    if param.startswith("_"):
        continue
    if "choices" in rule:
        settings[param] = st.sidebar.selectbox(param, options=rule["choices"],
                                               index=rule["choices"].index(rule["default"]))
    elif "min" in rule:
        settings[param] = st.sidebar.slider(
            param, float(rule["min"]), float(rule["max"]), float(rule["default"]))

lancer = st.sidebar.button("Lancer la separation", type="primary")

# ============================ ZONE PRINCIPALE : SAISIE CUSTOM ============================
# Les tableaux editables vivent dans la zone principale (plus de place que la sidebar),
# car saisir des mineraux custom demande de la largeur : ainsi on les affiche a droite.
custom_props = None
custom_chem = None
if use_custom_minerals:
    st.header("Definition des mineraux personnalises")
    st.markdown("**Tableau 1 - Proprietes physiques.** Une ligne par mineral. "
                "La proportion sera renormalisee a 100 %.")

    default_props = pd.DataFrame([
        {"mineral": "mon_mineral_1", "proportion_%": 5.0, "densite_g_cm3": 4.2,
         "magnetique": "paramagnetique_faible", "flottabilite_0_1": 0.9},
        {"mineral": "gangue", "proportion_%": 95.0, "densite_g_cm3": 2.65,
         "magnetique": "diamagnetique", "flottabilite_0_1": 0.1},
    ])
    custom_props = st.data_editor(
        default_props, num_rows="dynamic", use_container_width=True,
        column_config={
            "magnetique": st.column_config.SelectboxColumn(options=MAGNETIC_CATEGORIES),
            "flottabilite_0_1": st.column_config.NumberColumn(min_value=0.0, max_value=1.0),
        },
        key="props_editor")

    st.markdown("**Tableau 2 - Composition chimique (% massique, type XRF).** "
                "Pour chaque mineral, renseignez les elements presents. Le reste a 0.")

    minerals_list = [m for m in custom_props["mineral"].tolist() if str(m).strip()]
    chem_init = pd.DataFrame({"mineral": minerals_list})
    for el in XRF_ELEMENTS:
        chem_init[el] = 0.0
    custom_chem = st.data_editor(chem_init, use_container_width=True, key="chem_editor")

    # Avertissement doux si un mineral ne boucle pas a ~100 %, car un mineral est fait a
    # 100 % d'elements : ainsi on previent sans bloquer.
    for _, row in custom_chem.iterrows():
        total_el = sum(row[el] for el in XRF_ELEMENTS)
        if row["mineral"] and abs(total_el - 100.0) > 5.0:
            st.warning(f"Le mineral '{row['mineral']}' totalise {total_el:.1f} % "
                       f"d'elements (attendu ~100 %). Verifiez la composition.")


# ============================ AIGUILLAGE ============================
def apply_unit_ui(stream, unit, prop_lookup=None, assay_func=None):
    """Aiguillage vers la bonne loi selon la voie, avec proprietes et chimie custom."""
    if unit.unit_type in ("shaking_table", "spiral", "falcon"):
        d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(stream, d50, ep, densities=prop_lookup)
        return separate(stream, reco, assay_func=assay_func)
    elif unit.unit_type == "magnetic":
        thr, sharp = magnetic_cutpoint(unit)
        reco = magnetic_recovery(stream, thr, sharp, mineral_props=prop_lookup)
        return separate(stream, reco, assay_func=assay_func)
    else:
        reco = flotation_recovery(stream, unit, mineral_props=prop_lookup)
        au = gold_flotation_recovery(stream, reco, unit)
        return separate(stream, reco, gold_recovery=au, assay_func=assay_func)


# ============================ LANCEMENT ============================
if lancer:
    prop_lookup = None
    assay_func = None

    if profile_name is not None:
        feed = generate_feed(profile_name, n_samples=1, seed=42, feed_tph=feed_tph)[0]
        feed.p80_um = p80
        feed.liberation = LiberationState(degree={m: liberation_deg for m in feed.modal})

    elif custom_modal is not None:
        total = sum(custom_modal.values())
        if total == 0:
            st.error("Ajoutez au moins une phase minerale (proportion > 0).")
            st.stop()
        modal = {m: round(v / total * 100, 3) for m, v in custom_modal.items()}
        assays = assays_from_modal(modal)
        lib = LiberationState(degree={m: liberation_deg for m in modal})
        feed = Stream(name="minerai_base", solids_tph=feed_tph, modal=modal,
                      liberation=lib, p80_um=p80, assays=assays)

    else:  # mineraux personnalises
        props = custom_props.copy()
        # Nettoyage : on retire les lignes sans nom, et on remplace les proportions vides
        # par 0, car une cellule laissee vide dans le tableau vaut None : ainsi le calcul
        # ne plante pas sur un None.
        props = props[props["mineral"].astype(str).str.strip() != ""]
        props["proportion_%"] = pd.to_numeric(props["proportion_%"], errors="coerce").fillna(0.0)
        props["densite_g_cm3"] = pd.to_numeric(props["densite_g_cm3"], errors="coerce").fillna(2.65)
        props["flottabilite_0_1"] = pd.to_numeric(props["flottabilite_0_1"], errors="coerce").fillna(0.1)
        props = props[props["proportion_%"] > 0]

        if len(props) == 0:
            st.error("Definissez au moins un mineral avec une proportion > 0.")
            st.stop()

        total = props["proportion_%"].sum()
        modal = {r["mineral"]: round(r["proportion_%"] / total * 100, 3)
                 for _, r in props.iterrows()}
        # Table de proprietes physiques par mineral, car le moteur en a besoin pour trier.
        prop_lookup = {}
        for _, r in props.iterrows():
            prop_lookup[r["mineral"]] = {
                "density": float(r["densite_g_cm3"]),
                "magnetic": r["magnetique"],
                "floatability": float(r["flottabilite_0_1"]),
            }
        # Teneurs elementaires = somme (proportion x fraction massique) sur les mineraux.
        # Fonction de conversion mineralogie -> teneurs basee sur la chimie custom, car
        # separate() en aura besoin pour recalculer les teneurs des produits : ainsi on
        # la definit une fois et on l'utilise pour l'alimentation ET les sorties.
        chem_indexed = custom_chem.set_index("mineral")

        def custom_assay_func(modal_dict):
            out = {}
            for mineral, pct in modal_dict.items():
                if mineral in chem_indexed.index:
                    for el in XRF_ELEMENTS:
                        val = chem_indexed.loc[mineral, el]
                        frac = (float(val) if pd.notna(val) else 0.0) / 100.0
                        if frac > 0:
                            out[el] = out.get(el, 0.0) + pct * frac
            return {el: round(v, 3) for el, v in out.items()}

        assays = custom_assay_func(modal)
        assay_func = custom_assay_func
        lib = LiberationState(degree={m: liberation_deg for m in modal})
        feed = Stream(name="minerai_custom", solids_tph=feed_tph, modal=modal,
                      liberation=lib, p80_um=p80, assays=assays)

    unit = SeparationUnit(unit_type, settings)
    conc, rejet = apply_unit_ui(feed, unit, prop_lookup=prop_lookup, assay_func=assay_func)
    st.header("Resultats")
    st.subheader("Mineralogie de l'alimentation (%)")
    st.dataframe([{"Mineral": m, "%": round(v, 2)} for m, v in feed.modal.items()],
                 use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Alimentation", f"{feed.solids_tph:.0f} t/h")
    col2.metric("Concentre", f"{conc.solids_tph:.1f} t/h")
    col3.metric("Rejet", f"{rejet.solids_tph:.1f} t/h")

    st.subheader("Teneurs (%) - calculees depuis la mineralogie")
    elements = sorted(set(feed.assays) | set(conc.assays) | set(rejet.assays))
    rows = [{"Element": el,
             "Alimentation": round(feed.assays.get(el, 0), 3),
             "Concentre": round(conc.assays.get(el, 0), 3),
             "Rejet": round(rejet.assays.get(el, 0), 3)} for el in elements]
    st.dataframe(rows, use_container_width=True)

    minerai_label = (profile_name if profile_name else
                     ("minerai personnalise" if use_custom_minerals else "minerai (base)"))
    st.caption(f"Minerai : {minerai_label} | Voie : {unit_type} | "
               f"P80 : {feed.p80_um:.0f} um | Liberation : {liberation_deg:.2f}")
else:
    if not use_custom_minerals:
        st.info("Configurez les parametres dans la barre laterale, puis cliquez "
                "sur **Lancer la separation**.")
