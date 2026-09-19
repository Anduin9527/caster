"""Read-only display translations. Never alter stored templates or prompt tokens."""
import json
import sqlite3
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=2)
def vocabulary(path: str, mtime: int):
    with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True) as db:
        return {name: (category, cn.strip()) for name, category, cn in
                db.execute('SELECT name,category,cn_name FROM tags WHERE cn_name IS NOT NULL') if cn.strip()}


def dictionary(store):
    path = (store.root / 'translation/ffdkj/tag.sqlite').resolve()
    if not path.is_file(): return {}
    return vocabulary(str(path), path.stat().st_mtime_ns)


def lookup(words, text, category=None):
    entry = words.get(text.strip().replace(' ', '_'))
    return entry[1] if entry and (category is None or entry[0] == category) else ''


def display_for(template, words):
    character = template['kind'] == 'character'
    return {'name': lookup(words, template['name'], 4) if character else '',
            'categories': [lookup(words, c, 3) if character else '' for c in template.get('categories', [])],
            'tags': {tag: lookup(words, tag) for tag in template.get('tags', [])}}


def searchable(template, display, query):
    text = json.dumps(dict(template, display=display), ensure_ascii=False).replace('_', ' ').casefold()
    return all(token in text for token in query.replace('_', ' ').casefold().split())
