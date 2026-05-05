#!/usr/bin/env python3
"""
Segment Merger — Chain connected cycling segments into continuous polylines.

Two modes:
  --same-class   Merge only segments with identical canbics_class (default)
  --cross-class  Merge segments across class boundaries to form real routes

Usage:
  python3 segment_merger.py --db /path/to/cycling.db \
    --municipality Surrey --cross-class \
    --output merged.geojson
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict


def load_segments(db_path, municipality=None, cls=None, province='bc'):
    """Load segments from cycling.db, optionally filtered."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    where = ["province = ?"]
    params = [province]

    if municipality:
        where.append("municipality = ?")
        params.append(municipality)
    if cls:
        where.append("canbics_class = ?")
        params.append(cls)

    query = f"""
        SELECT id, municipality, canbics_class, source_class,
               surface_type, length_km, geometry_json, n_points
        FROM cycling_segments
        WHERE {' AND '.join(where)}
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()

    segments = []
    for r in rows:
        geo = json.loads(r['geometry_json'])
        segments.append({
            'id': r['id'],
            'municipality': r['municipality'],
            'canbics_class': r['canbics_class'],
            'source_class': r['source_class'],
            'surface_type': r['surface_type'],
            'length_km': r['length_km'],
            'n_points': r['n_points'],
            'coords': geo,
        })
    return segments


def endpoint_key(lon, lat, precision=6):
    return (round(lon, precision), round(lat, precision))


def build_endpoint_index(segments, cross_class=False):
    """
    Build endpoint index.

    cross_class=False: key is (lon, lat, canbics_class) — match only same-class
    cross_class=True:  key is (lon, lat) — match any class
    """
    index = defaultdict(list)

    for i, seg in enumerate(segments):
        coords = seg['coords']

        if coords and coords[0]:
            start = coords[0][0]
            base_key = endpoint_key(start[0], start[1])
            key = base_key if cross_class else (*base_key, seg['canbics_class'])
            index[key].append((i, 'start'))

        if coords and coords[-1]:
            end = coords[-1][-1]
            base_key = endpoint_key(end[0], end[1])
            key = base_key if cross_class else (*base_key, seg['canbics_class'])
            index[key].append((i, 'end'))

    return index


def merge_chains(segments, endpoint_index, cross_class=False):
    """Walk endpoint graph, merging connected segments into chains."""
    n = len(segments)
    visited = set()
    chains = []

    for i in range(n):
        if i in visited:
            continue
        visited.add(i)

        chain = [(i, False)]
        extend_direction(chain, segments, endpoint_index, visited, True, cross_class)
        extend_direction(chain, segments, endpoint_index, visited, False, cross_class)

        if len(chain) > 1:
            chains.append(chain)

    all_chained = {ci for c in chains for ci, _ in c}
    orphans = set(range(n)) - all_chained

    return chains, orphans


def extend_direction(chain, segments, endpoint_index, visited, forward, cross_class):
    """Extend chain from its end (forward=True) or start (forward=False)."""
    while True:
        if forward:
            seg_idx, is_rev = chain[-1]
            seg = segments[seg_idx]
            if is_rev:
                pt = seg['coords'][0][0]
            else:
                pt = seg['coords'][-1][-1]
        else:
            seg_idx, is_rev = chain[0]
            seg = segments[seg_idx]
            if is_rev:
                pt = seg['coords'][-1][-1]
            else:
                pt = seg['coords'][0][0]

        base_key = endpoint_key(pt[0], pt[1])
        key = base_key if cross_class else (*base_key, seg['canbics_class'])
        candidates = endpoint_index.get(key, [])

        found = None
        for candidate_idx, candidate_end in candidates:
            if candidate_idx == seg_idx:
                continue
            if candidate_idx in visited:
                continue

            if forward:
                reverse_candidate = (candidate_end == 'end')
            else:
                reverse_candidate = (candidate_end == 'start')

            found = (candidate_idx, reverse_candidate)
            break

        if found is None:
            break

        candidate_idx, reverse_candidate = found
        visited.add(candidate_idx)

        if forward:
            chain.append((candidate_idx, reverse_candidate))
        else:
            chain.insert(0, (candidate_idx, reverse_candidate))


def build_chain_geometry(chain, segments):
    """Concatenate segment geometries into one MultiLineString."""
    all_coords = []
    total_length = 0
    total_points = 0
    seg_ids = []
    class_sequence = []

    for seg_idx, is_rev in chain:
        seg = segments[seg_idx]
        coords = seg['coords']
        total_length += seg['length_km'] or 0
        total_points += seg['n_points'] or 0
        seg_ids.append(seg['id'])
        class_sequence.append(seg['canbics_class'])

        for line in coords:
            if is_rev:
                line = list(reversed(line))
            all_coords.append(line)

    return {
        'type': 'MultiLineString',
        'coordinates': all_coords
    }, total_length, total_points, seg_ids, class_sequence


def build_geojson(segments, chains, orphans, cross_class=False):
    """Build GeoJSON FeatureCollection."""
    features = []

    for chain in chains:
        geom, total_len, total_pts, seg_ids, class_seq = build_chain_geometry(chain, segments)
        first = segments[chain[0][0]]

        # Compute class composition
        if cross_class:
            class_counts = defaultdict(int)
            class_lengths = defaultdict(float)
            for seg_idx, is_rev in chain:
                s = segments[seg_idx]
                class_counts[s['canbics_class']] += 1
                class_lengths[s['canbics_class']] += s['length_km'] or 0

            # Dominant class by length
            dominant = max(class_lengths, key=class_lengths.get)
            props = {
                'type': 'merged_route',
                'mode': 'cross_class',
                'segment_count': len(chain),
                'original_ids': seg_ids,
                'total_length_km': round(total_len, 3),
                'total_points': total_pts,
                'dominant_class': dominant,
                'class_composition': dict(class_counts),
                'class_sequence': class_seq,
                'municipality': first['municipality'],
            }
        else:
            props = {
                'type': 'merged_path',
                'mode': 'same_class',
                'segment_count': len(chain),
                'original_ids': seg_ids,
                'total_length_km': round(total_len, 3),
                'total_points': total_pts,
                'canbics_class': first['canbics_class'],
                'municipality': first['municipality'],
                'source_class': first['source_class'],
                'surface_type': first['surface_type'],
            }

        features.append({
            'type': 'Feature',
            'geometry': geom,
            'properties': props,
        })

    for idx in orphans:
        seg = segments[idx]
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'MultiLineString',
                'coordinates': seg['coords']
            },
            'properties': {
                'type': 'segment',
                'mode': 'orphan',
                'segment_count': 1,
                'original_ids': [seg['id']],
                'total_length_km': seg['length_km'],
                'total_points': seg['n_points'],
                'canbics_class': seg['canbics_class'],
                'municipality': seg['municipality'],
                'source_class': seg['source_class'],
                'surface_type': seg['surface_type'],
            }
        })

    return {
        'type': 'FeatureCollection',
        'features': features
    }


def main():
    parser = argparse.ArgumentParser(description='Merge connected cycling segments')
    parser.add_argument('--db', required=True)
    parser.add_argument('--municipality')
    parser.add_argument('--class', dest='cls')
    parser.add_argument('--province', default='bc')
    parser.add_argument('--cross-class', action='store_true',
                        help='Merge across Can-BICS classes (default: same-class only)')
    parser.add_argument('--output', '-o')
    args = parser.parse_args()

    segments = load_segments(args.db, args.municipality, args.cls, args.province)
    if not segments:
        print(json.dumps({'type': 'FeatureCollection', 'features': []}))
        return

    endpoint_index = build_endpoint_index(segments, cross_class=args.cross_class)
    chains, orphans = merge_chains(segments, endpoint_index, cross_class=args.cross_class)
    geojson = build_geojson(segments, chains, orphans, cross_class=args.cross_class)

    mode = 'cross-class' if args.cross_class else 'same-class'
    stats = {
        'mode': mode,
        'input_segments': len(segments),
        'chains': len(chains),
        'orphans': len(orphans),
        'merged_into_chains': sum(len(c) for c in chains),
        'total_output_features': len(chains) + len(orphans),
    }
    geojson['metadata'] = stats

    output = json.dumps(geojson, indent=2) if args.output else json.dumps(geojson)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        reduction = (1 - stats['total_output_features'] / stats['input_segments']) * 100
        print(f"Written {stats['total_output_features']} features to {args.output}")
        print(f"  Mode: {mode}")
        print(f"  Chains: {stats['chains']} (from {stats['merged_into_chains']} segments)")
        print(f"  Orphans: {stats['orphans']}")
        print(f"  Reduction: {reduction:.0f}% ({stats['input_segments']} -> {stats['total_output_features']})")
    else:
        print(output)


if __name__ == '__main__':
    main()
