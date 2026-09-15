#!/usr/bin/env python3
"""
Calibrate the tier-1 / tier-2 decision rule against labelled positives.

Reads the archived channels.list responses under data/raw/wikidata_confirm/.
Spends no quota; rules can be changed and this re-run for free.

The labelled positives are Wikidata candidates that are *already* in tier 0,
having reached the validated frame independently through NewsGuard. They are
known-good news channels, so the fraction of them a rule keeps is a retention
rate: a rule that discards labelled positives is discarding real news channels,
and its pass rate on the candidates should be read in that light.

Five labelled individuals is far too few to bind any decision. It is reported
because it is what exists, not because it means anything.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tier_frame import topic_ok, title_ok, TOPIC_SUFFIXES  # noqa: E402


def load_raw(raw_dir: Path, label: str) -> dict:
    items, requested = {}, []
    for path in sorted(raw_dir.glob(f"{label}_*.json")):
        page = json.loads(path.read_text())
        requested.extend(page.get('_requested', []))
        for item in page.get('items', []):
            items[item['id']] = item
    return items, requested


def evaluate(items: dict, requested: list, meta: dict) -> list:
    """One record per requested channel, with each check's outcome."""
    out = []
    for cid in requested:
        item = items.get(cid)
        seed = meta.get(cid, {})
        if item is None:
            out.append({'channel_id': cid, 'resolved': False, 'has_videos': False,
                        'topic': False, 'title': False,
                        'label': seed.get('label', ''), 'topics': []})
            continue
        stats = item.get('statistics', {})
        topics = item.get('topicDetails', {}).get('topicCategories', []) or []
        out.append({
            'channel_id': cid,
            'resolved': True,
            'has_videos': int(stats.get('videoCount') or 0) > 0,
            'topic': topic_ok(topics),
            'title': title_ok(seed.get('label', ''),
                              item.get('snippet', {}).get('title', '')),
            'label': seed.get('label', ''),
            'channel_title': item.get('snippet', {}).get('title', ''),
            'topics': topics,
            'country': item.get('snippet', {}).get('country'),
            'video_count': int(stats.get('videoCount') or 0),
        })
    return out


# Topics that make a channel not-news regardless of its seed label. Gaming and
# music only: Sport is deliberately absent, because genuine local newspapers
# are routinely tagged Sport (their YouTube output is high-school games).
NON_NEWS_TOPICS = {
    'Video_game_culture', 'Action_game', 'Role-playing_video_game',
    'Action-adventure_game', 'Strategy_video_game', 'Sports_game',
    'Racing_video_game', 'Simulation_video_game', 'Puzzle_video_game',
    'Music', 'Pop_music', 'Hip_hop_music', 'Rock_music', 'Electronic_music',
    'Independent_music', 'Soul_music', 'Country_music', 'Christian_music',
    'Reggae', 'Jazz', 'Classical_music', 'Music_of_Asia', 'Music_of_Africa',
    'Music_of_Latin_America',
}


def topic_names(record) -> set:
    return {u.rstrip('/').rsplit('/', 1)[-1] for u in record['topics']}


def non_news(record) -> bool:
    """Tagged as gaming or music: not a news channel whatever its label says."""
    return bool(topic_names(record) & NON_NEWS_TOPICS)


RULES = {
    'resolved + has videos': lambda r: r['resolved'] and r['has_videos'],
    'topic only':            lambda r: r['resolved'] and r['has_videos'] and r['topic'],
    'title only':            lambda r: r['resolved'] and r['has_videos'] and r['title'],
    'topic OR title':        lambda r: r['resolved'] and r['has_videos'] and (r['topic'] or r['title']),
    'topic AND title':       lambda r: r['resolved'] and r['has_videos'] and r['topic'] and r['title'],
    'topic OR (title & !ent)': lambda r: (r['resolved'] and r['has_videos']
                                          and (r['topic'] or (r['title'] and not non_news(r)))),
    'topic, or title if no topics at all':
        lambda r: (r['resolved'] and r['has_videos']
                   and (r['topic'] or (r['title'] and not r['topics']))),
}


def table(name: str, labelled: list, candidates: list) -> None:
    print(f"\n{name}")
    print("-" * 74)
    print(f"{'rule':<24} {'labelled kept':>20} {'candidates passed':>24}")
    print(f"{'':<24} {f'(n={len(labelled)})':>20} {f'(n={len(candidates)})':>24}")
    print("-" * 74)
    for rule, fn in RULES.items():
        lk = sum(1 for r in labelled if fn(r))
        ck = sum(1 for r in candidates if fn(r))
        lpct = 100 * lk / len(labelled) if labelled else 0
        cpct = 100 * ck / len(candidates) if candidates else 0
        print(f"{rule:<24} {lk:>7,} ({lpct:>5.1f}%) {ck:>12,} ({cpct:>5.1f}%)")


def topic_distribution(name: str, records: list, top: int = 12) -> None:
    print(f"\ntopicCategories distribution -- {name}")
    print("-" * 74)
    counter = Counter()
    none_count = 0
    for r in records:
        if not r['topics']:
            none_count += 1
        for url in r['topics']:
            counter[url.rstrip('/').rsplit('/', 1)[-1]] += 1
    total = len(records)
    print(f"  {'(no topicCategories)':<34} {none_count:>7,}  {100*none_count/total:>5.1f}%")
    for topic, n in counter.most_common(top):
        marker = ' *' if topic in TOPIC_SUFFIXES else '  '
        print(f"{marker}{topic:<34} {n:>7,}  {100*n/total:>5.1f}%")
    print("  * counts as a topic match")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--meta', required=True)
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    meta = json.loads(Path(args.meta).read_text())

    groups = {}
    for label in ('outlet_labelled', 'outlet_candidate',
                  'person_labelled', 'person_candidate'):
        items, requested = load_raw(raw_dir, label)
        groups[label] = evaluate(items, requested, meta)
        unresolved = sum(1 for r in groups[label] if not r['resolved'])
        no_videos = sum(1 for r in groups[label] if r['resolved'] and not r['has_videos'])
        print(f"{label:<20} requested {len(requested):>6,}  "
              f"unresolved {unresolved:>5,}  zero-video {no_videos:>5,}")

    table("OUTLETS (2.2)", groups['outlet_labelled'], groups['outlet_candidate'])
    table("INDIVIDUALS (2.3) -- 5 labelled is far too few to bind",
          groups['person_labelled'], groups['person_candidate'])

    topic_distribution("outlet labelled positives (n=240)", groups['outlet_labelled'])
    topic_distribution("outlet candidates (n=1,916)", groups['outlet_candidate'])
    topic_distribution("person candidates (n=1,262)", groups['person_candidate'])

    # What the default rule would do, for reference.
    print("\n" + "=" * 74)
    print("Default rule: topic required for tier 1; title-only -> tier 2")
    print("=" * 74)
    for name, key in (("outlets", 'outlet_candidate'), ("individuals", 'person_candidate')):
        recs = groups[key]
        base = [r for r in recs if r['resolved'] and r['has_videos']]
        tier_a = [r for r in base if r['topic']]
        title_only = [r for r in base if not r['topic'] and r['title']]
        neither = [r for r in base if not r['topic'] and not r['title']]
        print(f"  {name:<14} topic {len(tier_a):>6,}   "
              f"title-only {len(title_only):>6,}   neither {len(neither):>6,}")
        print(f"  {'':<14} recency calls needed if both kept: "
              f"{len(tier_a) + len(title_only):,}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
