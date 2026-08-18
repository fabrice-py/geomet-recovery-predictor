"""
i18n.py
Internationalisation de l'interface (francais / anglais), car un portfolio gagne a etre
lisible au-dela du francophone : ainsi chaque texte de l'app recoit une cle, et la fonction
t(cle, langue) renvoie la version voulue. Le francais reste la langue par defaut.

Usage dans app.py :
    from i18n import t, LANGUAGES
    lang = st.sidebar.selectbox(...)          # renvoie "fr" ou "en"
    st.header(t("ore_header", lang))
"""

# Langues proposees dans le selecteur (libelle affiche -> code interne).
LANGUAGES = {"Francais": "fr", "English": "en"}

# Dictionnaire des traductions : cle -> {"fr": ..., "en": ...}.
TRANSLATIONS = {
    # ----- Titre general -----
    "app_title": {
        "fr": "Simulateur geometallurgique de separation",
        "en": "Geometallurgical Separation Simulator"},
    "app_caption": {
        "fr": "Choisissez un minerai, un traitement (separation simple ou circuit compose) "
              "et ses reglages : l'outil predit les concentres, le rejet et les teneurs.",
        "en": "Pick an ore, a process (single separation or composed circuit) and its "
              "settings: the tool predicts concentrates, tailings and grades."},
    "language": {"fr": "Langue", "en": "Language"},

    # ----- Sidebar : minerai -----
    "ore_header": {"fr": "1. Minerai", "en": "1. Ore"},
    "feed_rate": {"fr": "Debit d'alimentation (t/h)", "en": "Feed rate (t/h)"},
    "mode": {"fr": "Mode", "en": "Mode"},
    "mode_profile": {"fr": "Profil predefini", "en": "Preset profile"},
    "mode_base": {"fr": "Mineralogie (base)", "en": "Mineralogy (base)"},
    "mode_custom": {"fr": "Mineraux personnalises", "en": "Custom minerals"},
    "profile": {"fr": "Profil", "en": "Profile"},
    "compose_base": {"fr": "Composez depuis la base (% de chaque phase)",
                     "en": "Compose from the base (% of each phase)"},
    "add_phase_warn": {"fr": "Ajoutez au moins une phase (proportion > 0).",
                       "en": "Add at least one phase (proportion > 0)."},
    "total_ok": {"fr": "Total : {v:.1f} %", "en": "Total: {v:.1f} %"},
    "total_renorm": {"fr": "Total : {v:.1f} % -> renormalise a 100 %",
                     "en": "Total: {v:.1f} % -> renormalised to 100 %"},
    "custom_minerals_label": {"fr": "Mineraux personnalises", "en": "Custom minerals"},
    "custom_minerals_caption": {
        "fr": "Definissez vos phases dans la zone principale.",
        "en": "Define your phases in the main area."},
    "p80": {"fr": "P80 (um)", "en": "P80 (um)"},
    "liberation": {"fr": "Degre de liberation moyen", "en": "Average liberation degree"},
"psd_section": {"fr": "Granulometrie de l'alimentation", "en": "Feed size distribution"},
    "psd_view": {"fr": "Type de courbe", "en": "Curve type"},
    "psd_view_freq": {"fr": "Histogramme frequentiel", "en": "Frequency histogram"},
    "psd_view_cum": {"fr": "Passant cumule", "en": "Cumulative passing"},
    "psd_size_axis": {"fr": "Taille (um)", "en": "Size (um)"},
    "psd_passing_axis": {"fr": "Passant cumule (%)", "en": "Cumulative passing (%)"},
    "psd_class_axis": {"fr": "Classe granulometrique", "en": "Size class"},
    "psd_massfrac_axis": {"fr": "Fraction massique (%)", "en": "Mass fraction (%)"},
    "psd_cum_title": {"fr": "Passant cumule (P80 = {p80} um)", "en": "Cumulative passing (P80 = {p80} um)"},
    "psd_freq_title": {"fr": "Distribution massique (P80 = {p80} um)", "en": "Mass distribution (P80 = {p80} um)"},
    "grid_section": {"fr": "Grille granulometrique", "en": "Size grid"},
    "grid_caption": {"fr": "Bornes de tamis (um), decroissantes. S'applique a tout le flowsheet.",
                     "en": "Sieve boundaries (um), decreasing. Applies to the whole flowsheet."},
    "grid_min_warning": {"fr": "Il faut au moins 2 bornes valides.",
                         "en": "At least 2 valid boundaries are required."},
    "grid_invalid_warning": {"fr": "Grille invalide : entrez des nombres positifs.", "en": "Invalid grid: enter positive numbers."},
    # ----- Sidebar : metal d'interet -----
    "metal_header": {"fr": "2. Metal d'interet", "en": "2. Metal of interest"},
    "metal_followed": {"fr": "Metal suivi (recuperations et courbe)",
                       "en": "Tracked metal (recoveries and curve)"},
"process_multi": {"fr": "Circuit multi-voies", "en": "Multi-route circuit"},
    "n_stages": {"fr": "Nombre d'etages", "en": "Number of stages"},
    "stage_n": {"fr": "Etage", "en": "Stage"},
    "stage_name": {"fr": "Nom de l'etage", "en": "Stage name"},
    "stage_route": {"fr": "Voie de separation", "en": "Separation route"},
    # ----- Sidebar : traitement -----
    "process_header": {"fr": "3. Traitement", "en": "3. Process"},
    "process_type": {"fr": "Type", "en": "Type"},
    "process_simple": {"fr": "Separation simple", "en": "Single separation"},
    "process_circuit": {"fr": "Circuit", "en": "Circuit"},
    "sep_route": {"fr": "Voie de separation", "en": "Separation route"},
    "unit_type": {"fr": "Type d'unite", "en": "Unit type"},
    "machine_settings": {"fr": "Reglages machine", "en": "Machine settings"},
    "circuit_composed": {"fr": "Circuit compose", "en": "Composed circuit"},
    "start_from_template": {"fr": "Partir d'un modele", "en": "Start from a template"},
    "circuit_edit_hint": {"fr": "Le tableau des etages s'edite dans la zone principale.",
                          "en": "The stage table is edited in the main area."},
    "run": {"fr": "Lancer", "en": "Run"},
"xrf_section": {"fr": "XRF (composition chimique mesuree)", "en": "XRF (measured chemical composition)"},
    "xrf_caption": {"fr": "Optionnel : chargez la chimie globale mesuree du minerai pour la comparer a celle reconstruite depuis la mineralogie.",
                    "en": "Optional: load the measured bulk chemistry of the ore to compare it with the one reconstructed from mineralogy."},
    "xrf_mode_label": {"fr": "Source XRF", "en": "XRF source"},
    "xrf_none": {"fr": "Aucune", "en": "None"},
    "xrf_manual": {"fr": "Saisie manuelle", "en": "Manual entry"},
    "xrf_csv": {"fr": "Fichier CSV", "en": "CSV file"},
    "xrf_loaded_info": {"fr": "XRF saisie : {n} elements (total {tot}%).", "en": "XRF entered: {n} elements (total {tot}%)."},
    "xrf_csv_caption": {"fr": "Deux colonnes : element et teneur (%). Une ligne par element.",
                        "en": "Two columns: element and grade (%). One row per element."},
    "xrf_template": {"fr": "Modele XRF (CSV)", "en": "XRF template (CSV)"},
    "xrf_upload": {"fr": "Charger une XRF (CSV)", "en": "Load XRF (CSV)"},
    "xrf_cols_err": {"fr": "Colonnes introuvables (attendu : Element, Teneur %).", "en": "Columns not found (expected: Element, Grade %)."},
    "xrf_ok": {"fr": "XRF chargee : {n} elements.", "en": "XRF loaded: {n} elements."},
    "xrf_unknown_ok": {"fr": "Elements hors modele acceptes : {u}.", "en": "Elements outside model accepted: {u}."},
    "xrf_empty_err": {"fr": "Aucun element valide.", "en": "No valid element."},
    "xrf_parse_err": {"fr": "Erreur de lecture : {err}", "en": "Read error: {err}"},
    "xrf_compare_title": {"fr": "Comparaison XRF : mesure vs modele", "en": "XRF comparison: measured vs model"},
    "xrf_compare_caption": {"fr": "Chimie mesuree (XRF) comparee a celle reconstruite depuis la mineralogie. Un ecart faible valide la mineralogie.",
                            "en": "Measured chemistry (XRF) compared to the one reconstructed from mineralogy. A small gap validates the mineralogy."},
    "xrf_element": {"fr": "Element", "en": "Element"},
    "xrf_measured": {"fr": "Mesuree (XRF)", "en": "Measured (XRF)"},
    "xrf_reconstructed": {"fr": "Reconstruite (modele)", "en": "Reconstructed (model)"},
    "xrf_gap": {"fr": "Ecart", "en": "Gap"},
    "xrf_out_of_model": {"fr": "Elements mesures hors modele (non reconstruits) : {u}.",
                         "en": "Measured elements outside model (not reconstructed): {u}."},
    # ----- Zone principale : mineraux custom -----
    "custom_def_header": {"fr": "Definition des mineraux personnalises",
                          "en": "Custom minerals definition"},
    "table1_props": {"fr": "Tableau 1 - Proprietes physiques.",
                     "en": "Table 1 - Physical properties."},
    "table2_chem": {"fr": "Tableau 2 - Composition chimique par phase (stoechiometrie, % massique).", "en": "Table 2 - Chemical composition per phase (stoichiometry, mass %)."},

    # ----- Zone principale : circuit -----
    "circuit_compo_header": {"fr": "Composition du circuit", "en": "Circuit composition"},
    "circuit_compo_hint": {
        "fr": "Chaque ligne est un etage applique en serie. Deprimer/activer : noms de "
              "mineraux separes par des virgules.",
        "en": "Each row is a stage applied in series. Depress/activate: mineral names "
              "separated by commas."},
    "base_minerals": {"fr": "Mineraux de la base : ", "en": "Base minerals: "},

    # ----- Resultats -----
    "results": {"fr": "Resultats", "en": "Results"},
    "feed_mineralogy": {"fr": "Mineralogie de l'alimentation (%)",
                        "en": "Feed mineralogy (%)"},
    "mineral": {"fr": "Mineral", "en": "Mineral"},
    "performance": {"fr": "Performance (metal suivi : {el})",
                    "en": "Performance (tracked metal: {el})"},
    "product": {"fr": "Produit", "en": "Product"},
    "concentrate": {"fr": "Concentre", "en": "Concentrate"},
    "tailings": {"fr": "Rejet", "en": "Tailings"},
    "final_tail": {"fr": "Rejet final", "en": "Final tailings"},
    "define_stage_err": {"fr": "Definissez au moins un etage (avec un nom).",
                         "en": "Define at least one stage (with a name)."},
"mill_result": {
        "fr": "Broyage : P80 {p_in} um -> {p_out} um (energie {e} kWh/t, indice Wi {wi}). "
              "Masse et mineralogie inchangees ; liberation amelioree.",
        "en": "Grinding: P80 {p_in} um -> {p_out} um (energy {e} kWh/t, work index {wi}). "
              "Mass and mineralogy unchanged; liberation improved."},
    "cyclone_result": {
        "fr": "Classification : surverse {m_over} t/h (P80 {p_over} um), sousverse {m_under} t/h "
              "(P80 {p_under} um). Flux continue : {cont}.",
        "en": "Classification: overflow {m_over} t/h (P80 {p_over} um), underflow {m_under} t/h "
              "(P80 {p_under} um). Continuing flow: {cont}."},
              "partition_title": {"fr": "Courbe de partage (Tromp)", "en": "Partition curve (Tromp)"},
    "partition_size_axis": {"fr": "Taille des particules (um)", "en": "Particle size (um)"},
    "partition_yaxis": {"fr": "Probabilite vers la sousverse (%)", "en": "Probability to underflow (%)"},

"cc_converged": {"fr": "Charge circulante convergee en {n} iterations (debit boucle : {load} t/h).",
                     "en": "Circulating load converged in {n} iterations (loop flow: {load} t/h)."},
    "cc_diverged": {"fr": "Le circuit ne converge pas (charge circulante qui s'emballe). Revoyez les reglages.",
                    "en": "Circuit does not converge (circulating load diverging). Review settings."},
    "cc_too_high": {"fr": "Charge circulante excessive (>10x l'alimentation). Circuit ingerable, revoyez les reglages.",
                    "en": "Excessive circulating load (>10x feed). Unmanageable circuit, review settings."},
    "cc_max_iter": {"fr": "Convergence non atteinte apres {n} iterations. Resultat approximatif.",
                    "en": "Convergence not reached after {n} iterations. Approximate result."},

"returns_section": {"fr": "Retours (charge circulante)", "en": "Recycles (circulating load)"},
    "returns_caption": {"fr": "Renvoyez une sortie d'etage vers un etage anterieur pour creer une boucle (ex. sousverse -> broyeur).",
                        "en": "Send a stage output back to an earlier stage to form a loop (e.g. underflow -> mill)."},
    "n_returns": {"fr": "Nombre de retours", "en": "Number of recycles"},
    "return_n": {"fr": "Retour", "en": "Recycle"},
    "return_from_stage": {"fr": "Etage source", "en": "From stage"},
    "return_output": {"fr": "Sortie", "en": "Output"},
    "return_to_stage": {"fr": "Retourne vers", "en": "Returns to"},
    "returns_need_two": {"fr": "Ajoutez au moins 2 etages pour definir un retour.",
                        "en": "Add at least 2 stages to define a recycle."},
"psd_mode_label": {"fr": "Distribution granulometrique", "en": "Size distribution"},
    "psd_mode_auto": {"fr": "Generee (P80)", "en": "Generated (P80)"},
    "psd_mode_manual": {"fr": "Manuelle (saisie)", "en": "Manual (entry)"},
    "psd_class_col": {"fr": "Classe", "en": "Class"},
    "psd_pct_col": {"fr": "% masse", "en": "% mass"},
    "psd_manual_info": {"fr": "PSD saisie : P80 derive = {p80} um (total saisi {tot}%, normalise a 100%).",
                        "en": "Entered PSD: derived P80 = {p80} um (entered total {tot}%, normalized to 100%)."},
    "psd_manual_empty": {"fr": "Entrez au moins une proportion non nulle.", "en": "Enter at least one non-zero proportion."},
    "psd_manual_invalid": {"fr": "Valeurs invalides : entrez des nombres.", "en": "Invalid values: enter numbers."},

"psd_csv_label": {"fr": "Charger une PSD (CSV)", "en": "Load a PSD (CSV)"},
    "psd_csv_caption": {"fr": "Une ligne par classe : borne inferieure (um) et % masse. Derniere ligne = fines (borne 0).",
                        "en": "One row per class: lower bound (um) and % mass. Last row = fines (bound 0)."},
    "psd_csv_template": {"fr": "Telecharger un modele CSV", "en": "Download a CSV template"},
    "psd_csv_upload": {"fr": "Fichier CSV de granulometrie", "en": "Size distribution CSV file"},
    "psd_csv_cols_err": {"fr": "Colonnes introuvables. Attendu : borne_inf_um et pct_masse.",
                         "en": "Columns not found. Expected: borne_inf_um and pct_masse."},
    "psd_csv_few_err": {"fr": "Au moins 2 classes sont necessaires.", "en": "At least 2 classes are required."},
    "psd_csv_empty_err": {"fr": "Les proportions sont toutes nulles.", "en": "All proportions are zero."},
    "psd_csv_ok": {"fr": "PSD chargee : {n} classes, P80 derive = {p80} um.",
                   "en": "PSD loaded: {n} classes, derived P80 = {p80} um."},
    "psd_csv_parse_err": {"fr": "Erreur de lecture du CSV : {err}", "en": "CSV read error: {err}"},

"drx_import_title": {"fr": "Import DRX (mineralogie mesuree)", "en": "XRD import (measured mineralogy)"},
    "drx_import_caption": {"fr": "Chargez vos phases et proportions. Vous devrez ensuite completer leurs proprietes ci-dessous.",
                           "en": "Load your phases and proportions. You must then complete their properties below."},
    "drx_template": {"fr": "Modele DRX (CSV)", "en": "XRD template (CSV)"},
    "drx_upload": {"fr": "Charger une DRX (CSV)", "en": "Load XRD (CSV)"},
    "drx_cols_err": {"fr": "Colonnes introuvables (attendu : Mineral, Proportion %).",
                     "en": "Columns not found (expected: Mineral, Proportion %)."},
    "drx_ok": {"fr": "DRX chargee : {n} phases.", "en": "XRD loaded: {n} phases."},
    "drx_complete_props": {"fr": "OBLIGATOIRE : completez densite, magnetisme et flottabilite de chaque phase dans le tableau ci-dessous.",
                           "en": "REQUIRED: complete density, magnetism and floatability of each phase in the table below."},
    "drx_none_known": {"fr": "Aucune phase valide dans le fichier.", "en": "No valid phase in the file."},
    "drx_parse_err": {"fr": "Erreur de lecture : {err}", "en": "Read error: {err}"},

    # ----- Courbe teneur-recuperation -----
    "gr_curve_title": {"fr": "Courbe teneur-recuperation", "en": "Grade-recovery curve"},
    "gr_curve_simple_caption": {
        "fr": "Coherente avec la separation ci-dessus : on balaye un parametre autour du "
              "point simule, tout le reste etant fixe.",
        "en": "Consistent with the separation above: one parameter is swept around the "
              "simulated point, everything else fixed."},
    "gr_curve_circuit_caption": {
        "fr": "Choisissez le concentre a suivre et le parametre d'un etage a balayer. Le "
              "circuit entier est re-simule a chaque point.",
        "en": "Pick the concentrate to track and a stage parameter to sweep. The whole "
              "circuit is re-simulated at each point."},
    "sweep_param": {"fr": "Parametre a balayer", "en": "Parameter to sweep"},
    "no_sweep_param": {"fr": "Aucun parametre continu a balayer pour cette voie.",
                       "en": "No continuous parameter to sweep for this route."},
    "min_val": {"fr": "Min", "en": "Min"},
    "max_val": {"fr": "Max", "en": "Max"},
    "trace_curve": {"fr": "Tracer la courbe", "en": "Plot the curve"},
    "tracked_conc": {"fr": "Concentre suivi", "en": "Tracked concentrate"},
    "stage_to_set": {"fr": "Etage a regler", "en": "Stage to set"},
    "parameter": {"fr": "Parametre", "en": "Parameter"},
    "curve_points": {"fr": "Points de la courbe", "en": "Curve points"},
    "recovery_axis": {"fr": "Recuperation metallurgique {el} (%)",
                      "en": "Metallurgical recovery {el} (%)"},
    "grade_axis": {"fr": "Teneur {el} concentre (%)", "en": "Concentrate {el} grade (%)"},
    "gr_title_simple": {"fr": "Teneur-recuperation ({el}) - balayage {p}",
                        "en": "Grade-recovery ({el}) - sweep {p}"},
    "gr_title_circuit": {
        "fr": "Teneur-recuperation ({el}) dans conc. {c} - balayage {p} etage {s}",
        "en": "Grade-recovery ({el}) in conc. {c} - sweep {p} stage {s}"},
    "col_recov": {"fr": "Recup metal %", "en": "Metal recovery %"},
    "col_grade": {"fr": "Teneur %", "en": "Grade %"},
    "col_mass": {"fr": "Recup massique %", "en": "Mass recovery %"},

    # ----- Avertissement variation negligeable -----
    "flat_warning": {
        "fr": "Le metal suivi ({el}) ne reagit quasiment pas au parametre '{p}' : "
              "recuperation varie de {ar:.2f} pt, teneur de {ag:.2f} pt. Ce n'est "
              "probablement pas le bon levier pour ce metal. Essayez un autre metal "
              "d'interet, ou un parametre qui mobilise ce metal. La courbe ci-dessous "
              "reste affichee a titre indicatif.",
        "en": "The tracked metal ({el}) barely responds to parameter '{p}': recovery "
              "varies by {ar:.2f} pt, grade by {ag:.2f} pt. This is probably not the right "
              "lever for this metal. Try another metal of interest, or a parameter that "
              "mobilises it. The curve below is shown for reference only."},

    # ----- Cinetique -----
    "kinetics_title": {"fr": "Cinetique de flottation", "en": "Flotation kinetics"},
    "kinetics_caption": {
        "fr": "Recuperation de chaque mineral en fonction du temps de residence, a reglages "
              "fixes. On voit la selectivite s'installer dans le temps : les mineraux "
              "flottables montent vite vers leur plateau.",
        "en": "Recovery of each mineral versus residence time, at fixed settings. "
              "Selectivity builds up over time: floatable minerals rise quickly to their "
              "plateau."},
    "trace_kinetics": {"fr": "Tracer la cinetique", "en": "Plot kinetics"},
    "kinetics_plot_title": {"fr": "Cinetique de flottation par mineral",
                            "en": "Flotation kinetics per mineral"},
    "time_axis": {"fr": "Temps de residence (min)", "en": "Residence time (min)"},
    "recovery_pct": {"fr": "Recuperation (%)", "en": "Recovery (%)"},
    "kinetics_foot": {
        "fr": "Le temps de residence actuel du reglage est {t:.1f} min. Au-dela du plateau "
              "d'un mineral, prolonger ne fait qu'entrainer de la gangue.",
        "en": "The current residence-time setting is {t:.1f} min. Beyond a mineral's "
              "plateau, extending time only entrains gangue."},

    # ----- Messages d'info/erreur generaux -----
    "info_configure": {
        "fr": "Configurez le minerai et le traitement dans la barre laterale, puis cliquez "
              "sur Lancer.",
        "en": "Configure the ore and process in the sidebar, then click Run."},
    "err_add_phase": {"fr": "Ajoutez au moins une phase minerale (proportion > 0).",
                      "en": "Add at least one mineral phase (proportion > 0)."},
    "err_define_mineral": {"fr": "Definissez au moins un mineral avec une proportion > 0.",
                           "en": "Define at least one mineral with a proportion > 0."},
                           "cut_mode": {"fr": "Mode de reglage", "en": "Setting mode"},
    "cut_mode_machine": {"fr": "Reglages machine", "en": "Machine settings"},
    "cut_mode_direct": {"fr": "Coupure directe (d50/Ep)", "en": "Direct cut (d50/Ep)"},
    "d50_label": {"fr": "d50 - densite de coupure", "en": "d50 - cut density"},
    "ep_label": {"fr": "Ep - nettete de coupure", "en": "Ep - cut sharpness"},
    
}
# ============================================================================
# Libelles des parametres machine, car les cles techniques
# ============================================================================
PARAM_LABELS = {
    # Shaking table
    "deck_slope_deg": {"fr": "Pente de la table (deg)", "en": "Deck slope (deg)"},
    "stroke_freq_hz": {"fr": "Frequence de rotation (Hz)", "en": "Rotation frequency (Hz)"},
    "wash_water_lpm": {"fr": "Eau de lavage (lpm)", "en": "Washing water (lpm)"},
    # Spiral
    "feed_rate_tph": {"fr": "Debit d'alimentation (t/h)", "en": "Feed rate (t/h)"},
    "splitter_pos": {"fr": "Position du separateur", "en": "Splitter position"},
    # Falcon
    "rotation_g": {"fr": "Force centrifuge (G)", "en": "Centrifugal force (G)"},
    "fluid_water_lpm": {"fr": "Eau de lavage (lpm)", "en": "Washing water (lpm)"},
    # Magnetic
    "mode": {"fr": "Mode", "en": "Mode"},
    "field_tesla": {"fr": "Intensite du champ (T)", "en": "Field strength (T)"},
    "drum_speed_rpm": {"fr": "Vitesse du tambour (rpm)", "en": "Drum speed (rpm)"},
    # Flotation
    "collector_type": {"fr": "Type de collecteur", "en": "Collector type"},
    "collector_gpt": {"fr": "Dose de collecteur (g/t)", "en": "Collector dose (g/t)"},
    "frother_gpt": {"fr": "Dose de moussant (g/t)", "en": "Frother dose (g/t)"},
    "pulp_ph": {"fr": "pH de la pulpe", "en": "Pulp pH"},
    "residence_min": {"fr": "Temps de residence (min)", "en": "Residence time (min)"},
    "rotor_speed_rpm": {"fr": "Vitesse du rotor (rpm)", "en": "Rotor speed (rpm)"},
    "depressed_minerals": {"fr": "Mineraux deprimes", "en": "Depressed minerals"},
    "activated_minerals": {"fr": "Mineraux actives", "en": "Activated minerals"},
    "work_index": {"fr": "Indice de travail Wi (kWh/t)", "en": "Work index Wi (kWh/t)"},
    "energy_kwht": {"fr": "Energie specifique (kWh/t)", "en": "Specific energy (kWh/t)"},
    "diameter_cm": {"fr": "Diametre du cyclone (cm)", "en": "Cyclone diameter (cm)"},
    "pressure_kpa": {"fr": "Pression d'alimentation (kPa)", "en": "Feed pressure (kPa)"},
    "continue_flux": {"fr": "Flux qui continue", "en": "Continuing flow"},
}

# Libelles des OPTIONS de type de collecteur (les valeurs, pas le parametre).
OPTION_LABELS = {
    # Type de collecteur (flottation)
    "xanthate_SIBX": {"fr": "Xanthate (direct)", "en": "Xanthate (direct)"},
    "amine_inverse": {"fr": "Amine (inverse)", "en": "Amine (inverse)"},
    # Mode de separation magnetique
    "LIMS_wet": {"fr": "Basse intensite, voie humide", "en": "Low intensity, wet"},
    "LIMS_dry": {"fr": "Basse intensite, voie seche", "en": "Low intensity, dry"},
    "WHIMS_wet": {"fr": "Haute intensite, voie humide", "en": "High intensity, wet"},
    "WHIMS_dry": {"fr": "Haute intensite, voie seche", "en": "High intensity, dry"},
    "overflow": {"fr": "Surverse (fins)", "en": "Overflow (fines)"},
    "underflow": {"fr": "Sousverse (grossiers)", "en": "Underflow (coarse)"},
}

ROUTE_LABELS = {
    "shaking_table": {"fr": "Table à secousses", "en": "Shaking table"},
    "spiral": {"fr": "Spirale", "en": "Spiral"},
    "falcon": {"fr": "Concentrateur Falcon", "en": "Falcon concentrator"},
    "magnetic": {"fr": "Séparation magnétique", "en": "Magnetic separation"},
    "flotation": {"fr": "Flottation", "en": "Flotation"},
    'ball_mill': {'fr': 'Broyeur à boulets', 'en': 'Ball mill'},
    'hydrocyclone': {'fr': 'Hydrocyclone', 'en': 'Hydrocyclone'},
}


def route_label(route, lang="fr"):
    """Libelle lisible d'une voie de separation, meme principe que param_label."""
    entry = ROUTE_LABELS.get(route)
    if entry is None:
        return route
    return entry.get(lang) or entry.get("fr") or route

def param_label(param, lang="fr"):
    """Libelle lisible d'un parametre machine, car l'UI ne doit pas montrer la cle brute :
    ainsi on cherche dans PARAM_LABELS, avec repli sur la cle si absente."""
    entry = PARAM_LABELS.get(param)
    if entry is None:
        return param
    return entry.get(lang) or entry.get("fr") or param


def option_label(value, lang="fr"):
    """Libelle lisible d'une option (ex. type de collecteur), meme principe."""
    entry = OPTION_LABELS.get(value)
    if entry is None:
        return value
    return entry.get(lang) or entry.get("fr") or value

def t(key, lang="fr", **kwargs):
    """
    Renvoie le texte de la cle dans la langue demandee, car l'app bascule FR/EN : ainsi on
    lit TRANSLATIONS[cle][lang], on formate les variables ({v}, {el}...), et l'on retombe
    sur le francais puis sur la cle si un texte manque (robustesse).
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get("fr") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
