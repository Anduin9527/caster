"""Map exported character/work names using category-aware exact Danbooru tags."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3


def map_names(bundle, db):
    output = copy.deepcopy(bundle)
    stats = {}
    unmatched = {}
    for group, category in [('characters', 4), ('works', 3)]:
        matched = 0
        missing = []
        for item in output[group]:
            # Only normalize the source convention: spaces vs underscores.
            tag = item['original_name'].strip().replace(' ', '_')
            row = db.execute('SELECT cn_name FROM tags WHERE name=? AND category=?', (tag, category)).fetchone()
            if row and row[0] and row[0].strip():
                item['translated_name'] = row[0].strip()
                matched += 1
            else:
                item['translated_name'] = ''
                missing.append(copy.deepcopy(item))
        stats[group] = {'total': len(output[group]), 'matched': matched, 'unmatched': len(missing)}
        unmatched[group] = missing
    return output, unmatched, stats


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    bundle = json.loads(args.input.read_text())
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        translated, missing, stats = map_names(bundle, db)
    source = {'repository': 'https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table',
              'revision': args.revision, 'database_sha256': hashlib.sha256(args.database.read_bytes()).hexdigest(),
              'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
              'method': 'Exact name with spaces replaced by underscores; characters category=4, works category=3; no fuzzy matching',
              'review_status': 'upstream translations, not manually reviewed', 'coverage': stats}
    translated['translation_source'] = source
    translated['instructions'] = '已按固定版本词表填写精确匹配项。只补齐空白 translated_name；保留 ID、原名、作品关联和已有译名。不含生成提示词。'
    # Include work context without asking the translator to retranslate matched works.
    missing = {'schema_version': 1, 'instructions': translated['instructions'], **missing,
               'work_context': translated['works'], 'translation_source': source}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [('caster-names-mapped.json', translated), ('caster-names-unmatched.json', missing), ('mapping-report.json', source)]:
        (args.output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(stats, ensure_ascii=False))

if __name__ == '__main__': main()
