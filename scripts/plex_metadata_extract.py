#!/usr/bin/env python3
"""
Scan a directory of FLAC/MP3 files, group by Album and Artist,
and export a JSON file with album, artist, unique genres, and track counts.

Usage:
  python3 scripts/plex_metadata_extract.py --root /path/to/music --output albums.json

Requires: mutagen (pip install mutagen)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Iterable, List, Optional, Tuple

from mutagen import File


def first_tag(val: Optional[Iterable[str]]) -> Optional[str]:
    if not val:
        return None
    if isinstance(val, (list, tuple)):
        return val[0]
    return str(val)


def split_genre_string(s: Optional[str]) -> List[str]:
    if not s:
        return []
    s = s.strip()
    # Common separators used in genre tags
    for sep in [';', '/', ',', '|']:
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s]


def extract_tags(path: str) -> Dict[str, Optional[object]]:
    try:
        audio = File(path, easy=True)
        if audio is None:
            return {}
        album = first_tag(audio.get('album'))
        artist = first_tag(audio.get('artist'))
        raw_genres = audio.get('genre') or []
        genres: List[str] = []
        for g in raw_genres:
            genres.extend(split_genre_string(g))
        return {'album': album, 'artist': artist, 'genres': genres}
    except Exception:
        return {}


def scan_directory(root: str, exts: Tuple[str, ...] = ('.flac', '.mp3')) -> Dict[Tuple[str, str], Dict]:
    groups: Dict[Tuple[str, str], Dict] = {}
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if not fname.lower().endswith(exts):
                continue
            path = os.path.join(dirpath, fname)
            tags = extract_tags(path)
            album = (tags.get('album') or 'Unknown Album').strip()
            artist = (tags.get('artist') or 'Unknown Artist').strip()
            key = (album, artist)
            entry = groups.setdefault(key, {'album': album, 'artist': artist, 'genres': set(), 'tracks': 0})
            for g in tags.get('genres', []):
                gs = g.strip()
                if gs:
                    entry['genres'].add(gs)
            entry['tracks'] += 1
    return groups


def build_output_list(groups: Dict[Tuple[str, str], Dict]) -> List[Dict]:
    out: List[Dict] = []
    # Sort by artist then album for stable output
    for (album, artist), v in sorted(groups.items(), key=lambda x: (x[0][1].lower(), x[0][0].lower())):
        out.append({
            'album': album,
            'artist': artist,
            'current_genres': sorted(list(v['genres'])),
            'tracks': v['tracks'],
            'suggested_group': None,
            'suggested_subgenre': None,
        })
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Scan music files and export album-genre JSON')
    p.add_argument('--root', '-r', required=True, help='Root directory to scan')
    p.add_argument('--output', '-o', required=True, help='Output JSON file path')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.isdir(args.root):
        print(f'Root path not found: {args.root}', file=sys.stderr)
        return 2
    groups = scan_directory(args.root)
    out_list = build_output_list(groups)
    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump(out_list, fh, indent=2, ensure_ascii=False)
    print(f'Wrote {len(out_list)} albums to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
