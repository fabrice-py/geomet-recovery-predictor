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