"""Projections of real task6 nodes; animation never fabricates relationships."""
def graph_payload(knowledge):
    g = knowledge.store.graph
    return {"nodes": [{"id": n, "label": a["label"], "group": a["node_type"],
                       "spot": a["scenic_spot"], "val": 5 if a["node_type"] == "ScenicSpot" else 2 if a["node_type"] in {"Route", "Document"} else 1}
                      for n, a in g.nodes(data=True)],
            "links": [{"source": s, "target": t, "id": a["edge_id"], "kind": a["edge_type"],
                       "value": 3 if a["edge_type"] == "NEXT" else 1}
                      for s, t, a in g.edges(data=True)]}


def selection(knowledge, spot, route_ids=None, final=None):
    g = knowledge.store.graph
    if route_ids is None and final is None:
        return sorted(n for n, a in g.nodes(data=True) if a["scenic_spot"] == spot)
    seeds = {f"spot:{spot}"}
    routes = [final["route"]["route_id"]] if final else list(route_ids or [])
    seeds.update(f"route:{r}" for r in routes)
    if final:
        seeds.update(f"step:{routes[0]}:{s['step_id']}" for s in final.get("steps", []))
        seeds.update(f"condition:{a['pair_id']}" for a in final.get("advice", []))
        seeds.update(f"doc:{s['doc_id']}" for s in final.get("sources", []))
    else:
        seeds.update(n for r in routes for _, n, a in g.out_edges(f"route:{r}", data=True) if a["edge_type"] == "HAS_STEP")
    # Only expand selected steps/conditions, never their unselected siblings.
    for n in list(seeds):
        if n in g and g.nodes[n]["node_type"] in {"Step", "Condition"}:
            seeds.update(t for _, t, a in g.out_edges(n, data=True) if a["edge_type"] != "NEXT")
    seeds.update(s for r in routes for s, _, a in g.in_edges(f"route:{r}", data=True) if a["edge_type"] == "DESCRIBES")
    return sorted(seeds & set(g))
