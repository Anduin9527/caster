"""Resume upstream thumbnail downloads into ignored backend data; no inference or approvals."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import sys
import time
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aigc.store import Store
from aigc.template_previews import fetch_preview, source_url, atomic_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--workers', type=int, default=4, choices=range(1,9))
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    store = Store(args.data_dir)
    root = store.root / 'template-previews'
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = [t for t in store.list('prompt_template') if source_url(t)]
        # Seed both visible first pages before the rest of the catalog.
        initial = [t for k in ('character','outfit') for t in [r for r in rows if r['kind']==k][:12]]
        ids = {t['id'] for t in initial}
        rows = initial + [t for t in rows if t['id'] not in ids]
        if args.limit: rows = rows[:args.limit]
        report = {'started_at': time.time(), 'total': len(rows), 'completed': 0, 'downloaded': 0, 'cached': 0, 'failed': [], 'bytes': 0, 'state': 'running'}
        def save():
            atomic_write(root / 'download-status.json', json.dumps(report, ensure_ascii=False, indent=2).encode())
        save()
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=False, trust_env=False) as client:
            def work(t):
                try:
                    return fetch_preview(store, t, client)
                except Exception as e:
                    return {'id':t['id'], 'status':'failed', 'error':str(e)[:350]}
                finally:
                    time.sleep(.15)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(work, t) for t in rows]
                for future in as_completed(futures):
                    item = future.result()
                    report['completed'] += 1
                    if item['status'] == 'failed': report['failed'].append(item)
                    else:
                        report[item['status']] += 1
                        report['bytes'] += item.get('bytes',0)
                    if report['completed'] % 50 == 0 or report['completed'] == len(rows):
                        save()
                        print(json.dumps({k:v for k,v in report.items() if k!='failed'}), 'failed=',len(report['failed']), flush=True)
        report['state'] = 'complete'
        report['finished_at'] = time.time()
        save()

if __name__ == '__main__': main()
