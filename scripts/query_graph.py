#!/usr/bin/env python3
"""
Graphify Knowledge Graph Query Tool
Query the project's knowledge graph (graphify-out/graph.json) for architectural insights.

Usage:
    python scripts/query_graph.py community KKCoin
    python scripts/query_graph.py callers update_user_kkcoin
    python scripts/query_graph.py impact cogs/shop/shop.py
    python scripts/query_graph.py hubs
    python scripts/query_graph.py node cogs_common_kcoin
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

GRAPH_PATH = Path(__file__).parent.parent / "graphify-out" / "graph.json"


def load_graph() -> Dict[str, Any]:
    """Load the graphify knowledge graph."""
    if not GRAPH_PATH.exists():
        print(f"Error: Graph not found at {GRAPH_PATH}")
        print("Run 'graphify build .' to generate it.")
        sys.exit(1)
    with open(GRAPH_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_indexes(graph: Dict[str, Any]) -> tuple:
    """Build lookup indexes for fast queries."""
    nodes = graph.get('nodes', [])
    links = graph.get('links', [])

    # Node lookup by id
    node_by_id: dict[str, dict] = {n['id']: n for n in nodes}

    # Node lookup by label (normalized)
    node_by_label: dict[str, list[dict]] = {}
    for n in nodes:
        key = n.get('norm_label', n.get('label', '')).lower()
        if key not in node_by_label:
            node_by_label[key] = []
        node_by_label[key].append(n)

    # Community lookup
    community_nodes: dict[str, list[dict]] = {}
    for n in nodes:
        comm = n.get('community_name', 'unknown')
        if comm not in community_nodes:
            community_nodes[comm] = []
        community_nodes[comm].append(n)

    # Source file lookup
    file_nodes: dict[str, list[dict]] = {}
    for n in nodes:
        src = n.get('source_file', '')
        if src:
            if src not in file_nodes:
                file_nodes[src] = []
            file_nodes[src].append(n)

    # Outgoing edges (source -> targets)
    outgoing: dict[str, list[dict]] = {}
    for link in links:
        src = link.get('source')
        tgt = link.get('target')
        rel = link.get('relation', 'relates_to')
        if src not in outgoing:
            outgoing[src] = []
        outgoing[src].append({'target': tgt, 'relation': rel, 'link': link})

    # Incoming edges (target -> sources)
    incoming: dict[str, list[dict]] = {}
    for link in links:
        src = link.get('source')
        tgt = link.get('target')
        rel = link.get('relation', 'relates_to')
        if tgt not in incoming:
            incoming[tgt] = []
        incoming[tgt].append({'source': src, 'relation': rel, 'link': link})

    return node_by_id, node_by_label, community_nodes, file_nodes, outgoing, incoming


def cmd_community(args, indexes):
    """Query nodes in a community."""
    _, _, community_nodes, _, _, _ = indexes
    comm_name = args.name

    # Fuzzy match community name
    matches = [k for k in community_nodes.keys() if comm_name.lower() in k.lower()]
    if not matches:
        print(f"Community '{comm_name}' not found. Available communities:")
        for c in sorted(community_nodes.keys())[:20]:
            print(f"  - {c} ({len(community_nodes[c])} nodes)")
        if len(community_nodes) > 20:
            print(f"  ... and {len(community_nodes) - 20} more")
        return

    for match in matches:
        nodes = community_nodes[match]
        print(f"\n=== Community: {match} ({len(nodes)} nodes) ===")
        for n in nodes[:30]:
            label = n.get('norm_label', n.get('label', '?'))
            src = n.get('source_file', '?')
            print(f"  {n['id']}: {label}  [{src}]")
        if len(nodes) > 30:
            print(f"  ... and {len(nodes) - 30} more")


def cmd_node(args, indexes):
    """Show details of a specific node."""
    node_by_id, _, _, _, outgoing, incoming = indexes
    node_id = args.node_id

    if node_id not in node_by_id:
        print(f"Node '{node_id}' not found")
        return

    node = node_by_id[node_id]
    print(f"=== Node: {node_id} ===")
    print(f"  Label: {node.get('label', '?')}")
    print(f"  Norm Label: {node.get('norm_label', '?')}")
    print(f"  File: {node.get('source_file', '?')}")
    print(f"  Location: {node.get('source_location', '?')}")
    print(f"  Community: {node.get('community_name', '?')} (id: {node.get('community', '?')})")
    print(f"  Type: {node.get('metadata', {}).get('kind', '?')}")
    print(f"  Language: {node.get('metadata', {}).get('language', '?')}")

    # Outgoing edges
    out_edges = outgoing.get(node_id, [])
    if out_edges:
        print(f"\n  Outgoing ({len(out_edges)}):")
        for e in out_edges[:10]:
            tgt = node_by_id.get(e['target'], {})
            print(f"    --{e['relation']}--> {e['target']} ({tgt.get('norm_label', tgt.get('label', '?'))})")
        if len(out_edges) > 10:
            print(f"    ... and {len(out_edges) - 10} more")

    # Incoming edges
    in_edges = incoming.get(node_id, [])
    if in_edges:
        print(f"\n  Incoming ({len(in_edges)}):")
        for e in in_edges[:10]:
            src = node_by_id.get(e['source'], {})
            print(f"    <--{e['relation']}-- {e['source']} ({src.get('norm_label', src.get('label', '?'))})")
        if len(in_edges) > 10:
            print(f"    ... and {len(in_edges) - 10} more")


def cmd_callers(args, indexes):
    """Find all nodes that call/reference a given node (incoming edges)."""
    node_by_id, node_by_label, _, _, _, incoming = indexes
    target = args.target

    # Try to find node by id or label
    node_id = None
    if target in node_by_id:
        node_id = target
    else:
        matches = node_by_label.get(target.lower(), [])
        if matches:
            node_id = matches[0]['id']
            print(f"Resolved '{target}' -> '{node_id}'")
        else:
            print(f"Node '{target}' not found")
            return

    in_edges = incoming.get(node_id, [])
    if not in_edges:
        print(f"No callers found for '{node_id}'")
        return

    print(f"=== Callers of {node_id} ({len(in_edges)}) ===")
    for e in in_edges:
        src = node_by_id.get(e['source'], {})
        label = src.get('norm_label', src.get('label', '?'))
        src_file = src.get('source_file', '?')
        print(f"  {e['source']}: {label}  [{src_file}]  (relation: {e['relation']})")


def cmd_callees(args, indexes):
    """Find all nodes called by a given node (outgoing edges)."""
    node_by_id, node_by_label, _, _, outgoing, _ = indexes
    target = args.target

    node_id = None
    if target in node_by_id:
        node_id = target
    else:
        matches = node_by_label.get(target.lower(), [])
        if matches:
            node_id = matches[0]['id']
            print(f"Resolved '{target}' -> '{node_id}'")
        else:
            print(f"Node '{target}' not found")
            return

    out_edges = outgoing.get(node_id, [])
    if not out_edges:
        print(f"No callees found for '{node_id}'")
        return

    print(f"=== Callees of {node_id} ({len(out_edges)}) ===")
    for e in out_edges:
        tgt = node_by_id.get(e['target'], {})
        label = tgt.get('norm_label', tgt.get('label', '?'))
        tgt_file = tgt.get('source_file', '?')
        print(f"  {e['target']}: {label}  [{tgt_file}]  (relation: {e['relation']})")


def cmd_impact(args, indexes):
    """Analyze impact of changing a file - find all related nodes."""
    node_by_id, _, _, file_nodes, outgoing, incoming = indexes
    file_path = args.file

    # Normalize path
    file_path = file_path.replace('\\', '/')

    # Find nodes in this file
    nodes = file_nodes.get(file_path, [])
    if not nodes:
        # Try partial match
        matches = [n for f, ns in file_nodes.items() if file_path in f for n in ns]
        nodes = matches

    if not nodes:
        print(f"No nodes found for file '{file_path}'")
        return

    print(f"=== Impact Analysis for {file_path} ({len(nodes)} nodes) ===")

    all_affected = set()
    for node in nodes:
        node_id = node['id']
        # Direct dependencies (outgoing)
        for e in outgoing.get(node_id, []):
            all_affected.add(e['target'])
        # Reverse dependencies (incoming)
        for e in incoming.get(node_id, []):
            all_affected.add(e['source'])

    # Group by community
    by_community = {}
    for aid in all_affected:
        n = node_by_id.get(aid, {})
        comm = n.get('community_name', 'unknown')
        if comm not in by_community:
            by_community[comm] = []
        by_community[comm].append(n)

    for comm, affected_nodes in sorted(by_community.items(), key=lambda x: -len(x[1])):
        print(f"\n  Community: {comm} ({len(affected_nodes)} affected)")
        for n in affected_nodes[:10]:
            label = n.get('norm_label', n.get('label', '?'))
            src = n.get('source_file', '?')
            print(f"    {n['id']}: {label}  [{src}]")
        if len(affected_nodes) > 10:
            print(f"    ... and {len(affected_nodes) - 10} more")


def cmd_hubs(args, indexes):
    """Show community hubs (largest/most connected communities)."""
    _, _, community_nodes, _, outgoing, incoming = indexes

    # Calculate hub score: nodes * connections
    hub_scores = []
    for comm_name, nodes in community_nodes.items():
        node_ids = {n['id'] for n in nodes}
        # Count internal edges
        internal_edges = 0
        external_edges = 0
        for n in nodes:
            for e in outgoing.get(n['id'], []):
                if e['target'] in node_ids:
                    internal_edges += 1
                else:
                    external_edges += 1
            for e in incoming.get(n['id'], []):
                if e['source'] not in node_ids:
                    external_edges += 1

        score = len(nodes) * 0.5 + internal_edges * 0.3 + external_edges * 0.2
        hub_scores.append((score, comm_name, len(nodes), internal_edges, external_edges))

    hub_scores.sort(reverse=True)

    print("=== Community Hubs (Top 30) ===")
    for i, (score, name, nodes, internal, external) in enumerate(hub_scores[:30], 1):
        print(f"  {i:2d}. {name}  (nodes: {nodes}, internal: {internal}, external: {external}, score: {score:.1f})")


def cmd_search(args, indexes):
    """Search nodes by label/keyword."""
    _, node_by_label, _, _, _, _ = indexes
    keyword = args.keyword.lower()

    matches = []
    for label, nodes in node_by_label.items():
        if keyword in label:
            matches.extend(nodes)

    if not matches:
        print(f"No nodes matching '{keyword}'")
        return

    print(f"=== Search: '{keyword}' ({len(matches)} matches) ===")
    for n in matches[:30]:
        label = n.get('norm_label', n.get('label', '?'))
        src = n.get('source_file', '?')
        comm = n.get('community_name', '?')
        print(f"  {n['id']}: {label}  [{src}]  (community: {comm})")
    if len(matches) > 30:
        print(f"  ... and {len(matches) - 30} more")


def cmd_stats(args, indexes):
    """Show graph statistics."""
    node_by_id, _, community_nodes, file_nodes, outgoing, incoming = indexes
    graph = load_graph()

    print("=== Graph Statistics ===")
    print(f"  Nodes: {len(node_by_id)}")
    print(f"  Edges: {len(graph.get('links', []))}")
    print(f"  Communities: {len(community_nodes)}")
    print(f"  Source Files: {len(file_nodes)}")
    print(f"  Built at commit: {graph.get('built_at_commit', 'unknown')}")

    # Top communities by size
    top_comms = sorted(community_nodes.items(), key=lambda x: -len(x[1]))[:10]
    print("\n  Top Communities by Size:")
    for name, nodes in top_comms:
        print(f"    {name}: {len(nodes)} nodes")


def main():
    parser = argparse.ArgumentParser(description='Query Graphify Knowledge Graph')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # community
    p = subparsers.add_parser('community', help='List nodes in a community')
    p.add_argument('name', help='Community name (fuzzy match)')

    # node
    p = subparsers.add_parser('node', help='Show node details')
    p.add_argument('node_id', help='Node ID')

    # callers (incoming)
    p = subparsers.add_parser('callers', help='Find callers of a node')
    p.add_argument('target', help='Node ID or label')

    # callees (outgoing)
    p = subparsers.add_parser('callees', help='Find callees of a node')
    p.add_argument('target', help='Node ID or label')

    # impact
    p = subparsers.add_parser('impact', help='Analyze impact of changing a file')
    p.add_argument('file', help='File path')

    # hubs
    subparsers.add_parser('hubs', help='Show community hubs')

    # search
    p = subparsers.add_parser('search', help='Search nodes by keyword')
    p.add_argument('keyword', help='Keyword to search')

    # stats
    subparsers.add_parser('stats', help='Show graph statistics')

    args = parser.parse_args()

    graph = load_graph()
    indexes = build_indexes(graph)

    commands = {
        'community': cmd_community,
        'node': cmd_node,
        'callers': cmd_callers,
        'callees': cmd_callees,
        'impact': cmd_impact,
        'hubs': cmd_hubs,
        'search': cmd_search,
        'stats': cmd_stats,
    }

    commands[args.command](args, indexes)


if __name__ == '__main__':
    main()
