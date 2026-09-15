#!/usr/bin/env python3
"""
Tier the Wikidata candidate pool (phase 2).

Stages, each runnable on its own:

  join      2.1  attach wd_item / wd_class to channels already in the frame
  classify  2.2  class filter over the `outlet` stratum          (no quota)
  persons   2.3  occupation filter over the `commentator` stratum (no quota,
                 SPARQL against Wikidata)
  confirm   2.2/2.3  YouTube-side confirmation of the survivors   (SPENDS QUOTA)
  write     emit data/frame_tiers.csv and update `channels`

Tiers:
  0  the validated NewsGuard frame, unchanged
  1  Wikidata outlets that pass the class filter and the YouTube checks
  2  Wikidata individuals that pass the occupation filter and the checks
  3  recorded, never collected

Sitelink count is a fame proxy. It is used only as a tie-breaker between
channels of the same Wikidata item, never as an inclusion criterion.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database  # noqa: E402

CANDIDATES = 'seeds/wikidata/frame_candidates.csv'

# ---------------------------------------------------------------------------
# 2.2 class filter
# ---------------------------------------------------------------------------

# At least one of these must be present for an outlet to be a news outlet.
NEWS_CLASSES = {
    'news media', 'news agency', 'newspaper', 'online newspaper',
    'news website', 'news magazine', 'news program', 'public broadcaster',
}

# A row whose classes are *only* these is a carrier, not a newsroom: a TV
# station or a media company may broadcast anything.
CARRIER_ONLY_CLASSES = {
    'mass media', 'media company', 'television channel', 'television station',
    'radio station', 'magazine',
}

# ---------------------------------------------------------------------------
# 2.3 occupation filter
# ---------------------------------------------------------------------------

NEWS_OCCUPATIONS = {
    'journalist', 'news presenter', 'columnist', 'political analyst',
    'pundit', 'commentator', 'political commentator', 'war correspondent',
    'editor', 'news anchor', 'reporter', 'newspaper editor',
    'editor-in-chief', 'opinion journalist', 'investigative journalist',
    'political journalist', 'sports journalist', 'television journalist',
    'radio journalist', 'photojournalist', 'correspondent',
    # Found by auditing the labels actually present in the P106 results
    # rather than guessed at. Domain journalists (science, technology, music)
    # are included: they are journalists, and the YouTube-side topic check
    # removes the ones whose channel is not news.
    'political pundit', 'economic pundit', 'freelance journalist',
    'political reporter', 'broadcast journalist', 'video journalist',
    'editorial columnist', 'media critic', 'news editor',
    'science journalist', 'technology journalist', 'music journalist',
    'video game journalist', 'foreign correspondent', 'war reporter',
    'opinion columnist', 'newspaper journalist', 'online journalist',
}

# Deliberately NOT news occupations, though they look adjacent:
#   sports/baseball/esports/color commentator -- sports commentary, not news
#   film/video/television/literary editor     -- cutting rooms, not newsrooms
#   media manager / media scholar / media personality -- about media, not in it

# 'television presenter' counts only alongside a news occupation: on its own it
# is a game-show host as often as a news anchor.
CONDITIONAL_OCCUPATIONS = {'television presenter', 'presenter',
                           'radio personality', 'broadcaster', 'writer',
                           'author', 'blogger', 'podcaster', 'youtuber'}

DISQUALIFYING_OCCUPATIONS = {
    'politician', 'head of government', 'head of state', 'singer', 'actor',
    'actress', 'musician', 'athlete', 'model', 'comedian', 'novelist',
    'businessperson', 'entrepreneur', 'rapper', 'composer', 'film director',
    'football player', 'association football player', 'basketball player',
    'tennis player', 'baseball player', 'ice hockey player', 'cricketer',
    'racing driver', 'boxer', 'wrestler', 'swimmer', 'athletics competitor',
    'chess player', 'golfer', 'cyclist', 'martial artist',
    'member of parliament', 'diplomat', 'military officer', 'religious leader',
}

TOPIC_SUFFIXES = ('News', 'Politics', 'Society', 'Business')

STOPWORDS = {
    'the', 'a', 'an', 'of', 'and', 'or', 'de', 'la', 'le', 'les', 'el', 'il',
    'lo', 'der', 'die', 'das', 'und', 'et', 'y', 'e', 'news', 'tv', 'radio',
    'official', 'channel', 'media', 'online', 'daily', 'times', 'post',
    'journal', 'magazine', 'group', 'com', 'net', 'org',
}


def fold(text: str) -> str:
    """Case-fold and strip diacritics for token comparison."""
    if not text:
        return ''
    decomposed = unicodedata.normalize('NFKD', text)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()


def tokens(text: str) -> set:
    return {t for t in re.split(r'[^0-9a-z]+', fold(text)) if t and t not in STOPWORDS}


QID_RE = re.compile(r'Q[1-9][0-9]*')


def qids_of(row: dict) -> list:
    """All Wikidata items for a row; 13 rows carry a pipe-joined pair."""
    return QID_RE.findall(row.get('wd_item') or '')


def occupations_for(row: dict, occupations: dict) -> set:
    """Union of P106 across the row's item(s)."""
    out = set()
    for qid in qids_of(row):
        out.update(occupations.get(qid, []))
    return out


def classes_of(row: dict) -> set:
    return {c.strip().casefold() for c in (row.get('wd_class') or '').split('|') if c.strip()}


def load_candidates(path: str) -> list:
    csv.field_size_limit(sys.maxsize)
    with open(path) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 2.1
# ---------------------------------------------------------------------------

def stage_join(con, rows: list, dry_run: bool = False) -> dict:
    """Attach Wikidata provenance to channels already in the validated frame."""
    existing = {r[0] for r in con.execute("SELECT channel_id FROM channels")}
    by_channel = {}
    for r in rows:
        if r['channel_id'] in existing:
            by_channel.setdefault(r['channel_id'], r)

    if not dry_run:
        con.executemany("""
            UPDATE channels
               SET wd_item = COALESCE(wd_item, ?),
                   wd_class = COALESCE(wd_class, ?)
             WHERE channel_id = ?
        """, [(r['wd_item'], r['wd_class'], cid) for cid, r in by_channel.items()])
        con.commit()

    tiers = {} if dry_run else {
        row[0]: row[1] for row in con.execute(
            "SELECT COALESCE(tier, 0), COUNT(*) FROM channels "
            "WHERE wd_item IS NOT NULL GROUP BY COALESCE(tier, 0)")}
    return {'matched': len(by_channel), 'tiers': tiers}


# ---------------------------------------------------------------------------
# 2.2 class filter (free)
# ---------------------------------------------------------------------------

def stage_classify(rows: list) -> dict:
    """
    Class filter over the `outlet` stratum. Costs nothing.

    Returns the survivors plus the count at each step, which is what the
    LOGBOOK records.
    """
    steps = {}
    outlets = [r for r in rows if r['stratum'] == 'outlet']
    steps['stratum_outlet'] = len(outlets)

    has_news_class, no_news_class = [], []
    for r in outlets:
        (has_news_class if classes_of(r) & NEWS_CLASSES else no_news_class).append(r)
    steps['has_news_class'] = len(has_news_class)
    steps['rejected_no_news_class'] = len(no_news_class)

    survivors, carrier_only = [], []
    for r in has_news_class:
        cls = classes_of(r)
        # Excluded when the row's classes are *only* carrier classes. A row
        # with a news class keeps it, which is why this can only bite rows
        # that reached here with an empty news intersection -- kept as an
        # explicit guard for pools where wd_class is noisier.
        if cls and cls <= CARRIER_ONLY_CLASSES:
            carrier_only.append(r)
        else:
            survivors.append(r)
    steps['rejected_carrier_only'] = len(carrier_only)

    seen, deduped = set(), []
    for r in survivors:
        if r['channel_id'] not in seen:
            seen.add(r['channel_id'])
            deduped.append(r)
    steps['distinct_channels'] = len(deduped)

    return {'steps': steps, 'survivors': deduped,
            'rejected': no_news_class + carrier_only}


# ---------------------------------------------------------------------------
# 2.3 occupation filter (free, needs the SPARQL result)
# ---------------------------------------------------------------------------

def classify_person(occupations: set) -> tuple:
    """
    Decide a person from their full P106 occupation list.

    Tier 2 when every occupation is a news occupation, or when news
    occupations are the majority and nothing disqualifying is present.
    Everything else is tier 3.
    """
    occ = {o.strip().casefold() for o in occupations if o and o.strip()}
    if not occ:
        return 3, 'no_occupations'

    news = occ & NEWS_OCCUPATIONS
    disqualifying = occ & DISQUALIFYING_OCCUPATIONS
    conditional = occ & CONDITIONAL_OCCUPATIONS

    # 'television presenter' counts as news only next to a real news occupation.
    effective_news = news | (conditional if news else set())
    other = occ - effective_news - disqualifying

    if not effective_news:
        return 3, 'no_news_occupation'
    if disqualifying:
        return 3, f"disqualifying:{'|'.join(sorted(disqualifying))}"
    if len(effective_news) == len(occ):
        return 2, 'all_news_occupations'
    if len(effective_news) > (len(occ) - len(effective_news)):
        return 2, 'news_majority'
    return 3, f"news_minority:{'|'.join(sorted(other))}"


def stage_persons(rows: list, occupations: dict) -> dict:
    """Apply the occupation filter to the `commentator` stratum."""
    steps = {}
    commentators = [r for r in rows if r['stratum'] == 'commentator']
    steps['stratum_commentator'] = len(commentators)

    seen, deduped = set(), []
    for r in commentators:
        if r['channel_id'] not in seen:
            seen.add(r['channel_id'])
            deduped.append(r)
    steps['distinct_channels'] = len(deduped)

    steps['qids_queried'] = len({r['wd_item'] for r in deduped})
    steps['qids_with_occupations'] = len(occupations)

    survivors, rejected, reasons = [], [], Counter()
    for r in deduped:
        tier, reason = classify_person(occupations_for(r, occupations))
        r = dict(r, _reason=reason)
        reasons[reason.split(':')[0]] += 1
        (survivors if tier == 2 else rejected).append(r)

    steps['passed_occupation_filter'] = len(survivors)
    steps['rejected'] = len(rejected)
    return {'steps': steps, 'survivors': survivors, 'rejected': rejected,
            'reasons': dict(reasons)}


# ---------------------------------------------------------------------------
# YouTube-side confirmation (2.2 / 2.3) -- SPENDS QUOTA
# ---------------------------------------------------------------------------

def topic_ok(topic_categories) -> bool:
    """A Wikipedia topic URL ending in News, Politics, Society or Business."""
    for url in topic_categories or []:
        tail = url.rstrip('/').rsplit('/', 1)[-1]
        if tail in TOPIC_SUFFIXES:
            return True
    return False


def title_ok(seed_label: str, channel_title: str) -> bool:
    """At least one shared non-stopword token, case-folded, diacritics stripped."""
    return bool(tokens(seed_label) & tokens(channel_title))


def confirm_check(item: dict, seed_label: str) -> tuple:
    """
    Apply the cheap half of the confirmation to one channels.list item.

    Returns (passed, reason). The recency check needs a second call and is
    applied separately, only to rows that get this far.
    """
    stats = item.get('statistics', {})
    video_count = int(stats.get('videoCount') or 0)
    if video_count == 0:
        return False, 'no_videos'

    topics = item.get('topicDetails', {}).get('topicCategories', [])
    if topic_ok(topics):
        return True, 'topic_match'
    if title_ok(seed_label, item.get('snippet', {}).get('title', '')):
        return True, 'title_match'
    return False, 'no_topic_or_title_match'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('stage', choices=['join', 'classify', 'persons',
                                          'confirm', 'write', 'report'])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--candidates', default=CANDIDATES)
    parser.add_argument('--occupations', default='data/wikidata_occupations.json',
                        help='SPARQL result: {QID: [occupation labels]}')
    parser.add_argument('--out', default='data/frame_tiers.csv')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    rows = load_candidates(args.candidates)

    if args.stage == 'join':
        db = Database(db_path=args.db)
        result = stage_join(db.conn, rows, dry_run=args.dry_run)
        print(f"Wikidata rows matching channels already in the frame: "
              f"{result['matched']:,}")
        print(f"tier distribution of joined rows: {result['tiers']}")
        db.close()
        return 0

    if args.stage == 'classify':
        result = stage_classify(rows)
        print("2.2 class filter (no quota)")
        for step, n in result['steps'].items():
            print(f"  {step:<28} {n:>8,}")
        return 0

    if args.stage == 'persons':
        occ = {}
        if Path(args.occupations).exists():
            occ = json.load(open(args.occupations))
        result = stage_persons(rows, occ)
        print("2.3 occupation filter (no quota)")
        for step, n in result['steps'].items():
            print(f"  {step:<28} {n:>8,}")
        print(f"  reasons: {result['reasons']}")
        return 0

    print(f"stage {args.stage!r} not yet wired")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
