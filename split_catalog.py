#!/usr/bin/env python3
"""Split catalog.json into chunks for lazy loading."""
import json, os, sys

CHUNK_SIZE = 2000
CATALOG = os.path.join(os.path.dirname(__file__), 'catalog.json')
OUT_DIR = os.path.dirname(__file__)

def main():
    with open(CATALOG, 'r', encoding='utf-8') as f:
        films = json.load(f)

    total = len(films)
    chunks = []
    for i in range(0, total, CHUNK_SIZE):
        chunk = films[i:i + CHUNK_SIZE]
        name = f'catalog_{i // CHUNK_SIZE}.json'
        path = os.path.join(OUT_DIR, name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(',', ':'))
        chunks.append(name)
        print(f'  {name}: {len(chunk)} films')

    index = {'total': total, 'chunkSize': CHUNK_SIZE, 'chunks': chunks}
    idx_path = os.path.join(OUT_DIR, 'catalog_index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(index, f)
    print(f'\nTotal: {total} films, {len(chunks)} chunks')
    print(f'Index: {idx_path}')

if __name__ == '__main__':
    main()
