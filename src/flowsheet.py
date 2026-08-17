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
        ground = copy.deepcopy(feed_stream)
        grind_stream(ground, work_index=settings.get("work_index", 15.0),
                     energy_kwht=settings.get("energy_kwht", 10.0),
                     grid=grid, apply_p80_func=apply_p80_func)
        return {"out": ground}

    if unit_type == "hydrocyclone":
        over, under = classify_stream(
            feed_stream, diameter_cm=settings.get("diameter_cm", 15.0),
            pressure_kpa=settings.get("pressure_kpa", 100.0), grid=grid,
            apply_p80_func=apply_p80_func)
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
    finals = []

    while queue:
        node_id = queue.popleft()
        node = nodes[node_id]
        feed_in = merge_streams(incoming[node_id], grid=grid)
        if feed_in is None:
            # Noeud sans alimentation (flux nul) : on produit des sorties vides ignorables.
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

    return {"node_outputs": node_outputs, "finals": finals}

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
    tol : variation relative de debit du tear en dessous de laquelle on considere converge.
    Retour : dict avec node_outputs, finals, n_iter, converged, et le debit du/des tears.
    """
    tears = find_tear_edges(flowsheet)

    # Flowsheet "coupe" : on retire les connexions tears pour le calcul en une passe.
    cut_conns = [c for c in flowsheet["connections"] if c not in tears]
    cut_fs = {"nodes": flowsheet["nodes"], "connections": cut_conns}

    # Etat initial : chaque tear apporte un flux vide (None) a son noeud destinataire.
    tear_streams = {i: None for i in range(len(tears))}

    prev_debits = [0.0] * len(tears)
    converged = False
    n_iter = 0

    for it in range(max_iter):
        n_iter = it + 1
        # Construction des injections : pour chaque tear, son flux estime va vers sa destination.
        incoming_override = {}
        for i, tear in enumerate(tears):
            stream = tear_streams[i]
            if stream is not None:
                dst = tear["to"]
                incoming_override.setdefault(dst, []).append(stream)

        # Calcul en une passe avec les tears injectes.
        res = solve_once(cut_fs, feed, prop_lookup=prop_lookup, assay_func=assay_func,
                         grid=grid, apply_p80_func=apply_p80_func,
                         incoming_override=incoming_override)

        # Mise a jour des tears : on relit le flux reel produit a la source de chaque tear.
        new_debits = []
        for i, tear in enumerate(tears):
            src_node, src_out = tear["from"]
            outs = res["node_outputs"].get(src_node, {})
            stream = outs.get(src_out)
            tear_streams[i] = stream
            new_debits.append(stream.solids_tph if stream is not None else 0.0)

        # Convergence : variation relative du debit de chaque tear sous le seuil.
        max_rel = 0.0
        for i in range(len(tears)):
            d_new = new_debits[i]
            d_old = prev_debits[i]
            if d_new > 1e-9:
                rel = abs(d_new - d_old) / d_new
                max_rel = max(max_rel, rel)
            elif d_old > 1e-9:
                max_rel = max(max_rel, 1.0)
        prev_debits = new_debits

        if len(tears) == 0 or max_rel < tol:
            converged = True
            break

    return {"node_outputs": res["node_outputs"], "finals": res["finals"],
            "n_iter": n_iter, "converged": converged,
            "tear_debits": prev_debits, "n_tears": len(tears)}