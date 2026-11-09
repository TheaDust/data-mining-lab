from fastapi.testclient import TestClient

from task7.api import app
from task7.graph_view import graph_payload, selection
from task7.tools import Knowledge


def test_graph_exports_original_ids_and_edges():
    k = Knowledge()
    payload = graph_payload(k)
    assert len(payload['nodes']) == 583
    assert len(payload['links']) == 1751
    original = {a['edge_id']: (s, t) for s, t, a in k.store.graph.edges(data=True)}
    assert all(original[e['id']] == (e['source'], e['target']) for e in payload['links'])
    assert TestClient(app).get('/api/graph').json() == payload


def test_query_projections_keep_only_real_selected_steps():
    k = Knowledge()
    g = k.store.graph
    route_node = next(n for n, a in g.nodes(data=True) if a['node_type'] == 'Route' and a['scenic_spot'] == '北京故宫')
    route_id = g.nodes[route_node]['route_id']
    steps = [t for _, t, a in g.out_edges(route_node, data=True) if a['edge_type'] == 'HAS_STEP']
    scenic = set(selection(k, '北京故宫'))
    candidates = set(selection(k, '北京故宫', [route_id]))
    final = {'route': {'route_id': route_id}, 'steps': [{'step_id': g.nodes[steps[0]]['step_id']}], 'advice': [], 'sources': []}
    chosen = set(selection(k, '北京故宫', final=final))
    assert chosen <= candidates <= scenic < set(g)
    assert route_node in chosen and steps[0] in chosen
    assert not (set(steps[1:]) & chosen)
    assert all(g.nodes[n]['scenic_spot'] == '北京故宫' for n in chosen)
