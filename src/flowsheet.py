"""
Moteur de flowsheet a graphe, car un circuit reel n'est pas une simple serie : il peut
comporter des BOUCLES (charge circulante, ex. sousverse de cyclone -> broyeur -> retour
cyclone). On decrit donc le circuit en NOEUDS (unites) + CONNEXIONS (ou va chaque sortie),
ce qui permet n'importe quelle topologie. Ce palier pose la STRUCTURE et sa VALIDATION ;
le solveur (parcours, puis point fixe pour les boucles) viendra par-dessus.

Un noeud special "FEED" represente l'alimentation (sortie "out"). La destination "FINAL"
represente une sortie du circuit (produit ou rejet final).
"""

# Sorties nommees par type d'unite, car chaque appareil produit des flux differents : ainsi
# le moteur sait, pour un noeud donne, quelles sorties il faut connecter.
UNIT_OUTPUTS = {
    "shaking_table": ["concentre", "rejet"],
    "spiral": ["concentre", "rejet"],
    "falcon": ["concentre", "rejet"],
    "magnetic": ["concentre", "rejet"],
    "flotation": ["concentre", "rejet"],
    "ball_mill": ["out"],                    # transforme : une seule sortie
    "hydrocyclone": ["overflow", "underflow"],
}

FEED_NODE = "FEED"     # noeud d'alimentation (sortie "out")
FINAL_SINK = "FINAL"   # destination : sort du circuit


def outputs_of(unit_type):
    """Sorties nommees d'un type d'unite, car le moteur doit savoir quoi connecter : ainsi
    on lit le registre, en levant une erreur claire si le type est inconnu."""
    if unit_type == FEED_NODE:
        return ["out"]
    if unit_type not in UNIT_OUTPUTS:
        raise ValueError(f"Type d'unite inconnu pour le flowsheet : {unit_type}")
    return UNIT_OUTPUTS[unit_type]


def make_flowsheet(nodes, connections):
    """
    Construit un circuit-graphe, car un flowsheet = noeuds + connexions : ainsi on regroupe
    la description dans une structure unique, prete a valider puis a resoudre.
    nodes : dict {node_id: {"unit_type": ..., "settings": {...}}}.
    connections : liste de dicts {"from": (node_id, output_name), "to": node_id_or_FINAL}.
    """
    return {"nodes": dict(nodes), "connections": list(connections)}


def validate_flowsheet(flowsheet):
    """
    Verifie la coherence d'un circuit-graphe, car un graphe mal cable ne peut pas etre
    resolu : ainsi on detecte les erreurs AVANT tout calcul et on renvoie la liste des
    problemes (vide si tout va bien).
    Controles : noeuds references existants, chaque sortie de chaque noeud connectee une
    seule fois, sorties valides pour le type, presence d'une alimentation.
    """
    errors = []
    nodes = flowsheet["nodes"]
    conns = flowsheet["connections"]
    known = set(nodes.keys()) | {FEED_NODE}

    # 1) Chaque connexion reference des noeuds connus (source et destination).
    for c in conns:
        src_node, src_out = c["from"]
        dst = c["to"]
        if src_node not in known:
            errors.append(f"Connexion depuis un noeud inconnu : {src_node}")
            continue
        # La sortie doit exister pour le type du noeud source.
        if src_node == FEED_NODE:
            valid_outs = outputs_of(FEED_NODE)
        else:
            valid_outs = outputs_of(nodes[src_node]["unit_type"])
        if src_out not in valid_outs:
            errors.append(f"Sortie '{src_out}' invalide pour le noeud '{src_node}' "
                          f"(sorties valides : {valid_outs})")
        if dst != FINAL_SINK and dst not in nodes:
            errors.append(f"Connexion vers un noeud inconnu : {dst}")

    # 2) Chaque sortie de chaque noeud est connectee EXACTEMENT une fois, car un flux non
    # connecte serait perdu et une sortie doublement connectee serait ambigue.
    connected = {}
    for c in conns:
        key = c["from"]
        connected[key] = connected.get(key, 0) + 1
    # FEED : sa sortie "out" doit etre connectee.
    if (FEED_NODE, "out") not in connected:
        errors.append("L'alimentation (FEED) n'est connectee a aucun noeud.")
    for node_id, node in nodes.items():
        for out in outputs_of(node["unit_type"]):
            n = connected.get((node_id, out), 0)
            if n == 0:
                errors.append(f"Sortie '{out}' du noeud '{node_id}' non connectee "
                              f"(flux perdu).")
            elif n > 1:
                errors.append(f"Sortie '{out}' du noeud '{node_id}' connectee {n} fois "
                              f"(ambigu).")

    return errors


def has_cycle(flowsheet):
    """
    Detecte si le graphe contient une boucle (charge circulante), car le solveur devra
    iterer si oui, ou calculer en une passe si non : ainsi on parcourt le graphe en DFS et
    l'on signale tout retour vers un noeud deja dans la pile courante.
    Retour : True si au moins une boucle existe, sinon False.
    """
    nodes = flowsheet["nodes"]
    # Graphe d'adjacence : node -> liste des noeuds destinations (hors FINAL).
    adj = {n: [] for n in nodes}
    adj[FEED_NODE] = []
    for c in flowsheet["connections"]:
        src = c["from"][0]
        dst = c["to"]
        if dst != FINAL_SINK:
            adj.setdefault(src, []).append(dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}

    def dfs(u):
        color[u] = GRAY
        for v in adj.get(u, []):
            if color.get(v, WHITE) == GRAY:
                return True                 # retour vers un noeud de la pile -> boucle
            if color.get(v, WHITE) == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    for n in adj:
        if color[n] == WHITE and dfs(n):
            return True
    return False

import copy

def apply_node(unit_type, settings, feed_stream, prop_lookup=None, assay_func=None,
               grid=None, apply_p80_func=None):
    """
    Applique la physique d'un noeud a son flux d'entree et renvoie ses sorties NOMMEES, car
    le solveur graphe raisonne en sorties (concentre/rejet, overflow/underflow, out) : ainsi
    on aiguille vers la bonne loi (les MEMES que run_series) et l'on renvoie un dict
    {nom_sortie: flux}. Aucune physique n'est reecrite ici, seulement routee.
    """
    # Imports locaux, car flowsheet ne doit pas dependre de circuit au chargement.
    from separation import SeparationUnit
    from circuit import apply_unit
    from comminution import grind_stream
    from classification import classify_stream

    if unit_type == "ball_mill":
        import population_grinding as pg
        # Application du preset materiau AVANT le broyage (voir circuit.py pour le detail),
        # car le moteur graphe est la voie utilisee par l'interface multi-voies : ainsi le
        # materiau choisi agit aussi dans l'app. "personnalise" restaure les valeurs par defaut.
        materiau = settings.get("materiau", "personnalise")
        if materiau != "personnalise":
            pg.apply_material_preset(materiau)
        else:
            pg.reset_material_defaults()
        # Le Wi du preset ecrase le curseur (voir circuit.py), car le materiau fixe sa durete.
        wi_effectif = pg.material_work_index(materiau)
        if wi_effectif is None:
            wi_effectif = settings.get("work_index", 15.0)
        ground = copy.deepcopy(feed_stream)
        grind_stream(ground, work_index=wi_effectif,
                     energy_kwht=settings.get("energy_kwht", 10.0),
                     grid=grid, apply_p80_func=apply_p80_func,
                                          pct_solids=settings.get("pct_solids", 75.0),
                     mode=settings.get("mode", "humide"),
                     filling_pct=settings.get("filling_pct", 37.0),
                     comblement_u=settings.get("comblement_u", 1.0),
                     modele=settings.get("modele_broyage", "bond"),
                     ball_distribution=settings.get("ball_distribution"))
        return {"out": ground}
    
    if unit_type == "hydrocyclone":
        over, under = classify_stream(
            feed_stream, diameter_cm=settings.get("diameter_cm", 15.0),
            pressure_kpa=settings.get("pressure_kpa", 100.0), grid=grid,
            apply_p80_func=apply_p80_func, pct_solids=settings.get("pct_solids", 50.0))
        return {"overflow": over, "underflow": under}

    # Separateurs classiques (gravite, magnetique, flottation).
    unit = SeparationUnit(unit_type, settings)
    conc, tail = apply_unit(feed_stream, unit, prop_lookup=prop_lookup, assay_func=assay_func)
    return {"concentre": conc, "rejet": tail}

def merge_streams(streams, grid=None):
    """
    Additionne plusieurs flux en un seul, car un noeud peut recevoir plusieurs alimentations
    (ex. alimentation fraiche + charge circulante de retour) : ainsi on somme les masses par
    mineral, on recombine les PSD ponderees par la masse, et l'on reconstruit un flux unique.
    """
    from data_models import Stream, LiberationState
    from mineralogy import assays_from_modal
    from size_classes import p80_from_psd, DEFAULT_GRID_UM
    if grid is None:
        grid = DEFAULT_GRID_UM
    streams = [s for s in streams if s is not None and s.solids_tph > 1e-12]
    if not streams:
        return None
    if len(streams) == 1:
        return copy.deepcopy(streams[0])

    total_mass = sum(s.solids_tph for s in streams)
    # Masse par mineral = somme des (fraction modale x masse) de chaque flux.
    minerals = set()
    for s in streams:
        minerals.update(s.modal.keys())
    mineral_mass = {m: 0.0 for m in minerals}
    for s in streams:
        for m, pct in s.modal.items():
            mineral_mass[m] += pct / 100.0 * s.solids_tph
    modal = {m: round(mineral_mass[m] / total_mass * 100.0, 4) for m in minerals}

    # PSD ponderee par la masse, car chaque flux apporte sa distribution : ainsi la PSD
    # resultante est la moyenne massique classe par classe.
    psd = None
    if all(s.psd_curve is not None for s in streams):
        n_classes = len(streams[0].psd_curve)
        psd = [0.0] * n_classes
        for s in streams:
            for i in range(n_classes):
                psd[i] += s.psd_curve[i] * s.solids_tph
        psd = [round(p / total_mass, 6) for p in psd]

    # Liberation ponderee par la masse (approximation raisonnable).
    lib_deg = {}
    for m in minerals:
        num = sum(s.liberation.degree.get(m, 0.0) * s.solids_tph for s in streams)
        lib_deg[m] = round(num / total_mass, 3)

    assays = assays_from_modal(modal)
    merged = Stream(
        name="merge",
        solids_tph=round(total_mass, 4),
        modal=modal,
        liberation=LiberationState(degree=lib_deg),
        p80_um=round(p80_from_psd(grid, psd), 1) if psd else streams[0].p80_um,
        psd_curve=psd,
        pct_solids_mass=streams[0].pct_solids_mass,
        assays=assays,
    )
    return merged


def solve_once(flowsheet, feed, prop_lookup=None, assay_func=None,
               grid=None, apply_p80_func=None, incoming_override=None):
    """
    Resout un flowsheet SANS boucle en une passe, car sans charge circulante l'ordre de
    calcul existe toujours (tri topologique) : ainsi chaque noeud est calcule quand ses
    alimentations sont pretes, et ses sorties sont routees vers les destinataires.
    incoming_override : pour le futur solveur iteratif, flux de retour a injecter au depart.
    Retour : dict {node_id: {nom_sortie: flux}} + les flux FINAL collectes.
    """
    nodes = flowsheet["nodes"]
    conns = flowsheet["connections"]

    # Adjacence : pour router les sorties. dest_of[(node, out)] = liste de noeuds destinataires.
    dest_of = {}
    for c in conns:
        dest_of.setdefault(c["from"], []).append(c["to"])

    # Alimentations en attente par noeud : liste de flux recus.
    incoming = {n: [] for n in nodes}
    if incoming_override:
        for n, streams in incoming_override.items():
            incoming[n].extend(streams)
    # Le FEED alimente ses destinataires.
    for dst in dest_of.get((FEED_NODE, "out"), []):
        if dst != FINAL_SINK:
            incoming[dst].append(feed)

    # Ordre topologique (Kahn), car un noeud n'est calculable que quand toutes ses entrees
    # sont connues : ainsi on traite les noeuds sans dependance en attente d'abord.
    # On compte, par noeud, combien de connexions entrantes viennent d'autres NOEUDS (pas FEED).
    from collections import deque
    in_deg = {n: 0 for n in nodes}
    for c in conns:
        src = c["from"][0]
        dst = c["to"]
        if dst != FINAL_SINK and src != FEED_NODE:
            in_deg[dst] += 1
    # Les noeuds alimentes uniquement par FEED (ou override) demarrent.
    queue = deque([n for n in nodes if in_deg[n] == 0])

    node_outputs = {}
    node_feeds = {}
    finals = []

    while queue:
        node_id = queue.popleft()
        node = nodes[node_id]
        feed_in = merge_streams(incoming[node_id], grid=grid)
        node_feeds[node_id] = feed_in
        if feed_in is None:
            node_outputs[node_id] = {}
        else:
            outs = apply_node(node["unit_type"], node["settings"], feed_in,
                              prop_lookup=prop_lookup, assay_func=assay_func,
                              grid=grid, apply_p80_func=apply_p80_func)
            node_outputs[node_id] = outs
            # Router chaque sortie vers ses destinataires.
            for out_name, stream in outs.items():
                for dst in dest_of.get((node_id, out_name), []):
                    if dst == FINAL_SINK:
                        finals.append((f"{node_id}_{out_name}", stream))
                    else:
                        incoming[dst].append(stream)
        # Decrementer les dependances des destinataires.
        for c in conns:
            if c["from"][0] == node_id and c["to"] != FINAL_SINK:
                in_deg[c["to"]] -= 1
                if in_deg[c["to"]] == 0:
                    queue.append(c["to"])

    return {"node_outputs": node_outputs, "finals": finals, "node_feeds": node_feeds}

def find_tear_edges(flowsheet):
    """
    Identifie les connexions de RETOUR (tear streams) qui ferment les boucles, car pour
    resoudre un circuit ferme on coupe ces flux, on les suppose vides au depart, puis on
    itere : ainsi le circuit devient calculable en une passe a chaque tour. On repere les
    aretes qui pointent vers un noeud deja dans la pile DFS courante (arete arriere).
    Retour : liste de connexions (dicts) considerees comme tears.
    """
    nodes = flowsheet["nodes"]
    conns = flowsheet["connections"]
    # Adjacence noeud -> liste de (noeud_destination, connexion).
    adj = {n: [] for n in nodes}
    adj[FEED_NODE] = []
    for c in conns:
        src = c["from"][0]
        dst = c["to"]
        if dst != FINAL_SINK:
            adj.setdefault(src, []).append((dst, c))

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    tears = []

    def dfs(u):
        color[u] = GRAY
        for v, conn in adj.get(u, []):
            if color.get(v, WHITE) == GRAY:
                tears.append(conn)          # arete arriere -> ferme une boucle -> tear
            elif color.get(v, WHITE) == WHITE:
                dfs(v)
        color[u] = BLACK

    for n in adj:
        if color[n] == WHITE:
            dfs(n)
    return tears


def solve_iterative(flowsheet, feed, prop_lookup=None, assay_func=None,
                    grid=None, apply_p80_func=None, tol=0.001, max_iter=100):
    """
    Resout un flowsheet AVEC boucles par iteration de point fixe (methode du tear stream),
    car un circuit ferme est circulaire : ainsi on coupe les flux de retour, on les suppose
    vides, puis on recalcule en injectant a chaque tour le tear estime au tour precedent,
    jusqu'a stabilisation du debit (charge circulante convergee).

    Gestion robuste, car un circuit mal regle peut ne pas converger : ainsi on detecte la
    divergence (charge circulante croissant sans fin), un plafond absolu (10x l'alimentation),
    et le depassement du nombre d'iterations. Dans tous ces cas on renvoie le DERNIER etat
    calcule avec un statut explicite, plutot qu'un echec muet.

    Statuts possibles : 'converged', 'max_iter_reached', 'diverged', 'circulating_load_too_high'.
    """
    tears = find_tear_edges(flowsheet)
    cut_conns = [c for c in flowsheet["connections"] if c not in tears]
    cut_fs = {"nodes": flowsheet["nodes"], "connections": cut_conns}

    tear_streams = {i: None for i in range(len(tears))}
    prev_debits = [0.0] * len(tears)
    history = []                     # debit total du/des tears a chaque iteration
    feed_mass = feed.solids_tph
    load_ceiling = 10.0 * feed_mass  # plafond absolu de charge circulante
    rising_count = 0                 # nb d'iterations consecutives de croissance monotone

    status = "max_iter_reached"
    n_iter = 0
    res = None

    for it in range(max_iter):
        n_iter = it + 1
        incoming_override = {}
        for i, tear in enumerate(tears):
            stream = tear_streams[i]
            if stream is not None:
                dst = tear["to"]
                incoming_override.setdefault(dst, []).append(stream)

        res = solve_once(cut_fs, feed, prop_lookup=prop_lookup, assay_func=assay_func,
                         grid=grid, apply_p80_func=apply_p80_func,
                         incoming_override=incoming_override)

        new_debits = []
        for i, tear in enumerate(tears):
            src_node, src_out = tear["from"]
            outs = res["node_outputs"].get(src_node, {})
            stream = outs.get(src_out)
            tear_streams[i] = stream
            new_debits.append(stream.solids_tph if stream is not None else 0.0)

        total_tear = sum(new_debits)
        history.append(round(total_tear, 2))

        # Plafond absolu : charge circulante ingerable -> on arrete.
        if total_tear > load_ceiling:
            status = "circulating_load_too_high"
            break

        # Convergence : variation relative de chaque tear sous le seuil.
        max_rel = 0.0
        for i in range(len(tears)):
            d_new, d_old = new_debits[i], prev_debits[i]
            if d_new > 1e-9:
                max_rel = max(max_rel, abs(d_new - d_old) / d_new)
            elif d_old > 1e-9:
                max_rel = max(max_rel, 1.0)

        # Detection de divergence, car une hausse n'est PAS une divergence si elle ralentit
        # (convergence lente) : ainsi on regarde l'ecart entre iterations. Si l'ecart
        # AUGMENTE sur plusieurs tours (au lieu de diminuer), la charge circulante s'emballe.
        if len(history) >= 3:
            ecart_actuel = abs(history[-1] - history[-2])
            ecart_precedent = abs(history[-2] - history[-3])
            if ecart_actuel > ecart_precedent * 1.001:   # l'ecart grandit -> emballement
                rising_count += 1
            else:                                          # l'ecart retrecit -> ca converge
                rising_count = 0
        if rising_count >= 5:
            status = "diverged"
            break

        prev_debits = new_debits

        if len(tears) == 0 or max_rel < tol:
            status = "converged"
            break

    converged = (status == "converged")
    return {"node_outputs": res["node_outputs"], "finals": res["finals"],
            "node_feeds": res.get("node_feeds", {}),
            "n_iter": n_iter, "converged": converged, "status": status,
            "tear_debits": prev_debits if converged else [round(d, 2) for d in new_debits],
            "n_tears": len(tears), "history": history}
def run_series_as_graph(feed, stages, prop_lookup=None, assay_func=None,
                        grid=None, apply_p80_func=None, returns=None):
    """
    Execute une liste d'etages (multi-voies) via le moteur GRAPHE, car on veut un moteur
    unique qui gere aussi bien la serie que les boucles : ainsi on construit un flowsheet
    ou chaque etage alimente le suivant (serie), plus d'eventuels RETOURS (charge circulante),
    puis on resout par point fixe. Le resultat est remis au format de run_series pour ne pas
    bouleverser l'affichage.

    stages : liste de dicts {name, unit_type, settings, ...} (ordre = serie).
    returns : liste optionnelle de retours {"from_stage": nom, "from_output": nom_sortie,
              "to_stage": nom} decrivant une sortie qui reboucle vers un etage anterieur.

    Retour : dict facon run_series (concentrates, final_tail, stage_feeds) + infos graphe
    (mill_outputs, cyclone_outputs, circulating : statut/iterations/debit).
    """
    # 1) Construire les noeuds.
    nodes = {}
    for s in stages:
        nodes[s["name"]] = {"unit_type": s["unit_type"], "settings": s["settings"]}

    # 2) Determiner les sorties qui sont "detournees" par un retour (pour ne pas les router
    # aussi en serie), car une sortie rebouclee ne continue pas vers l'etage suivant.
    returns = returns or []
    diverted = set()   # (stage_name, output_name) detournes vers un retour
    for r in returns:
        diverted.add((r["from_stage"], r["from_output"]))

    # 3) Construire les connexions.
    conns = []
    names = [s["name"] for s in stages]
    # Alimentation : le FEED alimente le premier etage.
    if names:
        conns.append({"from": (FEED_NODE, "out"), "to": names[0]})

    for idx, s in enumerate(stages):
        name = s["name"]
        outs = outputs_of(s["unit_type"])
        # La sortie "principale" qui continue en serie depend du type d'unite.
        if s["unit_type"] == "ball_mill":
            main_out = "out"
        elif s["unit_type"] == "hydrocyclone":
            main_out = s["settings"].get("continue_flux", "overflow")
        else:
            main_out = "concentre"   # separateurs : le concentre continue ? Non -> voir note
        # NOTE serie multi-voies actuelle : le flux qui CONTINUE est le REJET pour les
        # separateurs (le concentre sort), et la sortie choisie pour cyclone/broyeur.
        if s["unit_type"] in ("shaking_table", "spiral", "falcon", "magnetic", "flotation"):
            continue_out = "rejet"       # le rejet alimente l'etage suivant (le concentre sort)
        else:
            continue_out = main_out

        for out in outs:
            key = (name, out)
            if key in diverted:
                continue   # cette sortie part dans un retour, gere plus bas
            if out == continue_out and idx < len(stages) - 1:
                # continue vers l'etage suivant
                conns.append({"from": key, "to": names[idx + 1]})
            else:
                # sort du circuit
                conns.append({"from": key, "to": FINAL_SINK})

    # 4) Ajouter les retours (boucles).
    for r in returns:
        conns.append({"from": (r["from_stage"], r["from_output"]), "to": r["to_stage"]})

    fs = make_flowsheet(nodes, conns)

    # 5) Resoudre (iteratif : gere serie ET boucles).
    res = solve_iterative(fs, feed, prop_lookup=prop_lookup, assay_func=assay_func,
                          grid=grid, apply_p80_func=apply_p80_func)

    # 6) Remettre au format run_series : concentrates, final_tail, stage_feeds.
    node_outputs = res["node_outputs"]
    concentrates = {}
    mill_outputs = {}
    cyclone_outputs = {}
    for s in stages:
        name = s["name"]
        outs = node_outputs.get(name, {})
        if s["unit_type"] == "ball_mill":
            if "out" in outs:
                mill_outputs[name] = outs["out"]
        elif s["unit_type"] == "hydrocyclone":
            cyclone_outputs[name] = {"overflow": outs.get("overflow"),
                                     "underflow": outs.get("underflow")}
            # produit sortant = le flux NON continue
            cont = s["settings"].get("continue_flux", "overflow")
            other = "underflow" if cont == "overflow" else "overflow"
            if outs.get(other) is not None:
                concentrates[f"{name}_{other}"] = outs[other]
        else:
            if outs.get("concentre") is not None:
                concentrates[name] = outs["concentre"]

    # final_tail = le rejet du dernier separateur, ou le dernier flux serie. Approximation :
    # on prend le flux FINAL de plus grande masse qui n'est pas un concentre nomme.
    final_tail = None
    for fname, stream in res["finals"]:
        if fname.endswith("_rejet"):
            final_tail = stream
    if final_tail is None and res["finals"]:
        final_tail = max((s for _, s in res["finals"]), key=lambda x: x.solids_tph)

    # stage_feeds : flux d'entree reel de chaque etage (expose par le moteur graphe), car
    # les courbes par etage et l'affichage broyeur en ont besoin.
    stage_feeds = res.get("node_feeds", {})

    return {"concentrates": concentrates, "final_tail": final_tail,
            "stage_feeds": stage_feeds, "mill_outputs": mill_outputs,
            "cyclone_outputs": cyclone_outputs, "circulating": res,
            "flowsheet": fs}