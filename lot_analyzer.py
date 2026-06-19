#!/usr/bin/env python3
"""
lot_analyzer.py — eBay Lot Buying / Bidding Evaluation Tool

Usage:
    python lot_analyzer.py <ebay_url_or_item_id>
    python lot_analyzer.py 123456789012
    python lot_analyzer.py "https://www.ebay.com/itm/123456789012"
    python lot_analyzer.py --manual          # enter card list by hand

What it does:
    1. Fetches lot listing details via eBay Browse API
       (title, price, description, images)
    2. Identifies cards using Claude Vision on lot photos (primary)
       Falls back to Firecrawl text scraping if vision unavailable
       Falls back to manual entry if neither finds cards
    3. Prices each card using active BIN listings (eBay Browse API)
       - Lowest BIN, 3 lowest, 3 highest, estimated value
    4. Calculates: total est. value vs asking price, suggested max bid,
       and a GO / CAUTION / NO-GO signal
    5. Saves a CSV alongside this script:  lot_XXXXXXXX_analysis.csv

Credentials (all in .env):
    ANTHROPIC_API_KEY   Claude Vision API key  (primary card ID)
    EBAY_APP_ID         eBay developer app ID
    EBAY_CLIENT_SECRET  eBay developer cert ID  (needed for Browse API)
    FIRECRAWL_API_KEY   Firecrawl key           (fallback text scrape)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── .env loader ────────────────────────────────────────────────────────────────
def _load_dotenv():
    """Load .env from the same directory as this script."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                k, v = k.strip(), v.strip()
                if v:
                    os.environ[k] = v
                else:
                    os.environ.setdefault(k, v)

_load_dotenv()

# ── Import pricing engine from existing app ────────────────────────────────────
# Must come AFTER _load_dotenv() so env vars are available.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from comps import search_active_listings, _get_browse_token  # noqa: E402
from card_vision import (                                    # noqa: E402
    vision_available,
    identify_cards_from_urls,
    card_to_lot_format,
)

# ── Constants ──────────────────────────────────────────────────────────────────
_BROWSE_ITEM_ENDPOINT = 'https://api.ebay.com/buy/browse/v1/item/v1|{item_id}|0'
_FIRECRAWL_SCRAPE     = 'https://api.firecrawl.dev/v1/scrape'
_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

# Buy-to-value thresholds (asking price as % of estimated value)
_THRESHOLD_GO      = 0.40   # ≤40%  → strong buy
_THRESHOLD_CAUTION = 0.55   # ≤55%  → proceed with caution
# > 55%  → no-go

# Suggested max bid = 40% of estimated total value
_MAX_BID_PCT = 0.40

# Active listing pricing params
_ACTIVE_MAX_RESULTS = 10   # fetch this many BIN listings per card

# ── eBay item-ID parser ────────────────────────────────────────────────────────
def parse_item_id(raw: str) -> str:
    """Extract the numeric eBay item ID from a URL or a bare number."""
    raw = raw.strip()
    # /itm/Title/123456789012  or  /itm/123456789012
    m = re.search(r'/itm/(?:[^/\s]+/)?(\d{8,13})', raw)
    if m:
        return m.group(1)
    # ?item=…  or  &id=…
    m = re.search(r'[?&](?:item|id)=(\d{8,13})', raw)
    if m:
        return m.group(1)
    # bare number
    if re.fullmatch(r'\d{8,13}', raw):
        return raw
    raise ValueError(f'Cannot parse an eBay item ID from: {raw!r}')

# ── Browse API: fetch single item ──────────────────────────────────────────────
def fetch_lot_item(item_id: str) -> dict:
    """
    Fetch lot listing details from the eBay Browse API.

    Returns a dict with keys:
        item_id, title, price, currency, description, image_urls,
        item_url, condition, seller, error
    """
    try:
        token = _get_browse_token()
    except Exception as exc:
        return {'error': f'OAuth failed: {exc}', 'item_id': item_id}

    url = _BROWSE_ITEM_ENDPOINT.format(item_id=item_id)
    headers = {
        'Authorization':            f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID':  'EBAY_US',
        'Accept':                   'application/json',
        'User-Agent':               _UA,
    }
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return {'error': f'HTTP {exc.code}: {body[:300]}', 'item_id': item_id}
    except Exception as exc:
        return {'error': str(exc), 'item_id': item_id}

    # --- price ---
    price_info = data.get('price', {})
    try:
        price = float(price_info.get('value', 0))
    except (TypeError, ValueError):
        price = 0.0

    # --- images ---
    images = []
    if data.get('image', {}).get('imageUrl'):
        images.append(data['image']['imageUrl'])
    for img in data.get('additionalImages', []):
        if img.get('imageUrl'):
            images.append(img['imageUrl'])

    return {
        'item_id':     item_id,
        'title':       data.get('title', ''),
        'price':       price,
        'currency':    price_info.get('currency', 'USD'),
        'description': data.get('shortDescription', '') or '',
        'image_urls':  images,
        'item_url':    data.get('itemWebUrl', f'https://www.ebay.com/itm/{item_id}'),
        'condition':   data.get('condition', ''),
        'seller':      data.get('seller', {}).get('username', ''),
        'error':       None,
    }

# ── Firecrawl: full listing page text ─────────────────────────────────────────
def fetch_lot_page_text(item_url: str) -> str:
    """
    Scrape the full eBay listing page via Firecrawl to get the complete
    item description (Browse API truncates it).

    Returns markdown text, or '' if unavailable.
    """
    key = os.environ.get('FIRECRAWL_API_KEY', '').strip()
    if not key:
        return ''

    payload = {
        'url':             item_url,
        'formats':         ['markdown'],
        'onlyMainContent': True,
        'timeout':         45_000,
    }
    hdr = {
        'Content-Type':  'application/json',
        'Authorization': f'Bearer {key}',
        'User-Agent':    _UA,
    }
    try:
        body = json.dumps(payload).encode()
        req = Request(_FIRECRAWL_SCRAPE, data=body, headers=hdr, method='POST')
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result.get('data', {}).get('markdown', '') or ''
    except Exception:
        return ''


def _extract_ebay_image_urls(html: str) -> list:
    """
    Extract only the LISTING GALLERY image URLs from raw eBay page HTML.

    eBay embeds listing images as i.ebayimg.com URLs in the HTML, but the
    full page also contains images from "Similar items", sponsored listings,
    "You might also like", and other recommendations — none of which belong
    to the lot being analyzed.

    We truncate the HTML at the first sidebar/recommendation section header
    before running the URL regex, so only photos the seller uploaded are returned.
    We normalize all URLs to s-l1600 (largest available size).
    """
    # Cut HTML at the first "similar items" / sponsored section to avoid
    # pulling in images from other sellers' listings or eBay ads.
    _CUTOFF_MARKERS = [
        'Similar sponsored items',
        'You might also like',
        'People who viewed this item also viewed',
        'Explore related items',
        'More to explore',
        'Related sponsored items',
        'Sponsored items based on your recent',
        '"sectionType":"RECOMMENDED"',
        '"sectionType":"SIMILAR"',
    ]
    content = html
    for marker in _CUTOFF_MARKERS:
        idx = html.find(marker)
        if 0 < idx < len(html):
            content = html[:idx]
            break

    # Match eBay image CDN URLs within the truncated (listing-only) content
    pattern = re.compile(
        r'https?://i\.ebayimg\.com/images/g/[A-Za-z0-9\-_]+/s-l\d+\.(?:jpg|jpeg|png|webp)',
        re.IGNORECASE,
    )
    raw_urls = pattern.findall(content)

    # Also catch URLs in JSON-encoded strings (backslash-escaped slashes)
    raw_urls += re.findall(
        r'https?:\\/\\/i\\.ebayimg\\.com\\/images\\/g\\/[A-Za-z0-9\\-_]+\\/s-l\d+\\.(?:jpg|jpeg|png|webp)',
        content, re.IGNORECASE,
    )

    normalized, seen = [], set()
    for url in raw_urls:
        # Unescape backslash encoding
        url = url.replace('\\/', '/').replace('\\.', '.')
        # Upgrade to largest size
        url = re.sub(r'/s-l\d+\.', '/s-l1600.', url)
        if url not in seen:
            seen.add(url)
            normalized.append(url)

    return normalized


def fetch_all_lot_images(item_url: str, browse_images: list) -> list:
    """
    Return the COMPLETE gallery image list for an eBay lot listing.

    eBay Browse API only returns ~24 images even for large lots.
    This fetches the full listing page HTML via Firecrawl and extracts
    ALL gallery image URLs — essential for lots with 50-200+ photos.

    Args:
        item_url      : eBay listing URL
        browse_images : Images already found via Browse API (kept as fallback)

    Returns:
        Deduplicated list of image URLs (Browse API + page HTML)
    """
    key = os.environ.get('FIRECRAWL_API_KEY', '').strip()
    all_images = list(browse_images)
    existing   = set(browse_images)

    if not key:
        return all_images  # no Firecrawl key — use Browse API images only

    payload = {
        'url':             item_url,
        'formats':         ['html'],   # raw HTML gives us all embedded image URLs
        'onlyMainContent': False,      # include the full page, not just article content
        'timeout':         45_000,
    }
    hdr = {
        'Content-Type':  'application/json',
        'Authorization': f'Bearer {key}',
        'User-Agent':    _UA,
    }
    try:
        body = json.dumps(payload).encode()
        req  = Request(_FIRECRAWL_SCRAPE, data=body, headers=hdr, method='POST')
        with urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        html = result.get('data', {}).get('html', '') or ''
        if html:
            page_images = _extract_ebay_image_urls(html)
            added = 0
            for img in page_images:
                if img not in existing:
                    all_images.append(img)
                    existing.add(img)
                    added += 1
    except Exception:
        pass  # Fall back to Browse API images

    return all_images

# ── Card extraction from lot text ──────────────────────────────────────────────
_YEAR_RE     = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')
_GRADE_RE    = re.compile(r'\b(PSA|BGS|SGC|CSG|HGA)\s*(\d+(?:\.\d)?)\b', re.IGNORECASE)
_CARDNUM_RE  = re.compile(r'#\s*(\d+)\b')

_SKIP_WORDS = {
    'shipping', 'feedback', 'seller', 'payment', 'return', 'condition',
    'click here', 'see photo', 'buy it now', 'make offer', 'watch list',
    'item number', 'category', 'brand new', 'pre-owned', 'price:',
    'postage', 'handling', 'estimated delivery', 'read more', 'show more',
    'sold by', 'ships from', 'top rated',
}

def _clean_markdown(text: str) -> str:
    """
    Strip Firecrawl markdown artifacts so card text is clean for parsing.

    Handles:
      - Markdown links: [Card Name](https://...) → Card Name
      - Markdown headers: ### Some Header → Some Header
      - Inline code/bold/italic: `text`, **text**, *text*, ~~text~~
      - Bare URLs: https://... or http://...
      - HTML entities: &amp; &lt; &gt; &nbsp; etc.
    """
    # 1. Strip markdown links: [text](url) → text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # 2. Strip markdown headers (###, ##, #)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # 3. Strip inline markdown formatting (*bold*, _italic_, ~~strike~~, `code`)
    text = re.sub(r'[*_`~]+', '', text)
    # 4. Strip bare URLs
    text = re.sub(r'https?://\S+', '', text)
    # 5. Strip HTML entities
    text = re.sub(r'&\w+;', ' ', text)
    # 6. Strip table separators (|---|---|)
    text = re.sub(r'^\|[\s\-|]+\|?\s*$', '', text, flags=re.MULTILINE)
    # 7. Collapse extra whitespace
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text


def extract_cards_from_text(text: str) -> list:
    """
    Parse lot listing text and return a list of card dicts.

    Each dict has: raw_line, description, year, card_num, grader, grade
    """
    # Pre-process: strip all Firecrawl markdown artifacts first
    text = _clean_markdown(text)

    cards = []
    # Split on newlines
    lines = re.split(r'[\n\r]+', text)

    for line in lines:
        clean = line.strip()
        if len(clean) < 8:
            continue

        # Skip boilerplate
        cl = clean.lower()
        if any(w in cl for w in _SKIP_WORDS):
            continue

        # Must contain a plausible year to be treated as a card line
        year_m = _YEAR_RE.search(clean)
        if not year_m:
            continue

        year    = year_m.group(1)
        grade_m = _GRADE_RE.search(clean)
        num_m   = _CARDNUM_RE.search(clean)

        grader   = grade_m.group(1).upper() if grade_m else None
        grade    = grade_m.group(2)         if grade_m else None
        card_num = num_m.group(1)           if num_m   else None

        # Strip out the parsed fields to isolate player/set description.
        # Use regex substitution on remainder (not index slicing) so that
        # earlier removals do not shift the positions of later matches.
        remainder = clean
        remainder = _YEAR_RE.sub('', remainder)
        remainder = _GRADE_RE.sub('', remainder)
        remainder = _CARDNUM_RE.sub('', remainder)
        remainder = re.sub(r'[\-–:,|]+', ' ', remainder)
        remainder = re.sub(r'\s+', ' ', remainder).strip()
        # Remove leading list numbers like "1." or "1)"
        remainder = re.sub(r'^[\d]+[.)]\s*', '', remainder).strip('- •→•').strip()

        if len(remainder) < 4:
            continue

        cards.append({
            'raw_line':    clean,
            'description': remainder,
            'year':        year,
            'card_num':    card_num,
            'grader':      grader,
            'grade':       grade,
        })

    # Deduplicate (same raw line within first 80 chars)
    seen, deduped = set(), []
    for c in cards:
        key = re.sub(r'\s+', ' ', c['raw_line'].lower())[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped

# ── eBay search query builders ─────────────────────────────────────────────────
_GRADE_EXCLUSIONS = '-PSA -BGS -SGC -CSG -HGA -graded -slab'

def _clean_desc(desc: str) -> str:
    """Strip markdown/URL artifacts from a card description."""
    desc = re.sub(r'https?://\S+', '', desc)
    desc = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', desc)
    desc = re.sub(r'[\[\]()]+', '', desc)
    desc = re.sub(r'\s+', ' ', desc).strip()
    return desc


def build_search_query(card: dict) -> str:
    """
    Build an eBay search string for a card.

    For RAW cards (no grader/grade): appends exclusion keywords so eBay
    only returns ungraded copies (-PSA -BGS -SGC -CSG -HGA -graded -slab).

    For GRADED cards: includes the grading company + grade.
    """
    parts = []
    if card.get('year'):
        parts.append(card['year'])
    desc = _clean_desc((card.get('description') or '').strip())
    if desc:
        parts.append(desc[:55].strip())
    if card.get('grader') and card.get('grade'):
        # Graded card — include the grade in the query
        parts.append(f"{card['grader']} {card['grade']}")
    else:
        # Raw card — exclude slabs so comps are apples-to-apples
        parts.append(_GRADE_EXCLUSIONS)
    if card.get('card_num'):
        parts.append(f"#{card['card_num']}")
    return ' '.join(parts)


def build_graded_query(card: dict) -> str:
    """
    Build a query for PSA-graded comps of a raw card.
    Used to show the 'if graded' column.
    """
    parts = []
    if card.get('year'):
        parts.append(card['year'])
    desc = _clean_desc((card.get('description') or '').strip())
    if desc:
        parts.append(desc[:55].strip())
    # Any slab — PSA, BGS, SGC
    parts.append('PSA OR BGS OR SGC')
    if card.get('card_num'):
        parts.append(f"#{card['card_num']}")
    return ' '.join(parts)

# ── Per-card pricing ───────────────────────────────────────────────────────────
def _pricing_stats(items: list, query: str) -> dict:
    """Compute pricing stats from a list of eBay items."""
    prices = sorted(i['total_cost'] for i in items if i.get('total_cost', 0) > 0)

    if not prices:
        return {
            'query':         query,
            'lowest':        None,
            'three_lowest':  [],
            'three_highest': [],
            'est_value':     None,
            'count':         0,
            'items':         [],
            'unreliable':    False,
        }

    three_low  = prices[:3]
    three_high = prices[-3:]

    # Outlier guard: if spread within the 3 lowest is > 5x, the query
    # matched mixed condition cards — use single lowest as conservative floor.
    spread_ratio = (three_low[-1] / three_low[0]) if three_low[0] > 0 else 1
    if spread_ratio > 5:
        est_value  = three_low[0]
        unreliable = True
    else:
        # Conservative estimated value = median of 3 lowest BIN prices
        est_value  = three_low[len(three_low) // 2]
        unreliable = False

    return {
        'query':         query,
        'lowest':        prices[0],
        'three_lowest':  three_low,
        'three_highest': three_high,
        'est_value':     est_value,
        'count':         len(prices),
        'items':         items[:5],
        'unreliable':    unreliable,
    }


def price_card(card: dict) -> dict:
    """
    Fetch active BIN listings for a card and compute pricing stats.

    For raw cards (no grader/grade):
      - Main pricing uses raw-only query (-PSA -BGS etc.)
      - Also fetches a 'graded_comp' dict showing graded market prices
        (useful for deciding if the card is worth submitting to grading)

    Returns a dict with:
        query, lowest, three_lowest, three_highest, est_value, count, items,
        unreliable, graded_comp (dict or None)
    """
    is_raw = not (card.get('grader') and card.get('grade'))

    # ── Raw / graded main pricing ──────────────────────────────────────────
    query  = build_search_query(card)
    result = search_active_listings(query, max_results=_ACTIVE_MAX_RESULTS, listing_type='FIXED_PRICE')
    stats  = _pricing_stats(result.get('items', []), query)

    # ── Graded comp (raw cards only) ───────────────────────────────────────
    graded_comp = None
    if is_raw:
        time.sleep(0.15)   # brief pause between back-to-back API calls
        gq      = build_graded_query(card)
        gresult = search_active_listings(gq, max_results=_ACTIVE_MAX_RESULTS, listing_type='FIXED_PRICE')
        gstats  = _pricing_stats(gresult.get('items', []), gq)
        graded_comp = gstats

    stats['graded_comp'] = graded_comp
    return stats

# ── Manual card entry ──────────────────────────────────────────────────────────
def manual_entry_mode() -> list:
    """Prompt the user to enter cards line by line."""
    print()
    print('─' * 55)
    print('MANUAL CARD ENTRY')
    print('Enter one card per line, then a blank line to finish.')
    print()
    print('Format:  YEAR  PLAYER / SET  [GRADER GRADE]  [#CARDNUM]')
    print('Example: 2019 Daniel Jones Panini Prizm PSA 10 #302')
    print('─' * 55)

    lines = []
    while True:
        try:
            line = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            if lines:
                break
        else:
            lines.append(line)

    cards = []
    for line in lines:
        year_m  = _YEAR_RE.search(line)
        grade_m = _GRADE_RE.search(line)
        num_m   = _CARDNUM_RE.search(line)

        remainder = line
        remainder = _YEAR_RE.sub('', remainder)
        remainder = _GRADE_RE.sub('', remainder)
        remainder = _CARDNUM_RE.sub('', remainder)
        remainder = re.sub(r'[\-–:,/|]+', ' ', remainder)
        remainder = re.sub(r'\s+', ' ', remainder).strip()

        cards.append({
            'raw_line':    line,
            'description': remainder,
            'year':        year_m.group(1)  if year_m  else None,
            'card_num':    num_m.group(1)   if num_m   else None,
            'grader':      grade_m.group(1).upper() if grade_m else None,
            'grade':       grade_m.group(2) if grade_m else None,
        })
    return cards

# ── Main lot analysis pipeline ─────────────────────────────────────────────────
def analyze_lot(item_id_or_url: str,
                manual_cards: list = None,
                verbose: bool = True) -> dict:
    """
    Full lot evaluation pipeline.

    Args:
        item_id_or_url : eBay URL or numeric item ID
        manual_cards   : Optional pre-built card list (skips auto-detection)
        verbose        : Print progress to stdout

    Returns:
        dict with keys: lot, cards, totals
    """
    item_id = parse_item_id(item_id_or_url)

    sep = '=' * 62
    if verbose:
        print(f'\n{sep}')
        print(f'  LOT ANALYZER  —  eBay #{item_id}')
        print(sep)
        print('Fetching lot details from eBay...')

    # ── Step 1: Browse API item fetch ──────────────────────────────────────
    lot = fetch_lot_item(item_id)
    if lot.get('error'):
        print(f'ERROR: {lot["error"]}')
        return {'error': lot['error']}

    if verbose:
        print(f'  Title:   {lot["title"]}')
        print(f'  Price:   ${lot["price"]:.2f} {lot["currency"]}')
        print(f'  Images:  {len(lot["image_urls"])} found')
        print(f'  Seller:  {lot["seller"] or "N/A"}')

    # ── Step 2: Card identification ────────────────────────────────────────
    if manual_cards is not None:
        cards = manual_cards
        if verbose:
            print(f'\nUsing {len(cards)} manually supplied cards.')

    elif vision_available() and lot.get('image_urls'):
        # PRIMARY: Claude Vision reads the lot photos directly.
        # IMPORTANT: eBay Browse API only returns ~24 images.
        # We fetch the full listing HTML to get ALL gallery images first.
        _MAX_VISION_IMAGES = 200
        if verbose:
            print(f'\nFetching full image gallery from listing page...')
        lot['image_urls'] = fetch_all_lot_images(lot['item_url'], lot['image_urls'])
        if verbose:
            n_imgs = min(len(lot['image_urls']), _MAX_VISION_IMAGES)
            print(f'  → {len(lot["image_urls"])} image(s) found in gallery')
            print(f'\nIdentifying cards via Claude Vision ({n_imgs} image(s))...')
        vision_cards = identify_cards_from_urls(
            lot['image_urls'],
            max_images=_MAX_VISION_IMAGES,
            verbose=verbose,
        )
        cards = [card_to_lot_format(c) for c in vision_cards if not c.get('error')]

        if verbose:
            print(f'  → {len(cards)} card(s) identified by vision.')

        # If vision found nothing, fall through to text extraction
        if not cards:
            if verbose:
                print('  Vision found no cards; trying Firecrawl text...')
            page_text = fetch_lot_page_text(lot['item_url'])
            if page_text:
                cards = extract_cards_from_text(page_text)
                if verbose:
                    print(f'  → {len(cards)} cards extracted from page text.')

    else:
        # FALLBACK: Firecrawl text scrape (no vision key, or no images)
        if verbose:
            reason = 'no ANTHROPIC_API_KEY' if not vision_available() else 'no lot images'
            print(f'\nScraping listing text via Firecrawl ({reason})...')
        page_text = fetch_lot_page_text(lot['item_url'])

        if page_text:
            cards = extract_cards_from_text(page_text)
            if verbose:
                print(f'  → {len(cards)} cards extracted from page text.')
        else:
            # Last resort: Browse API short description + title
            combo_text = (lot.get('description') or '') + '\n' + (lot.get('title') or '')
            cards = extract_cards_from_text(combo_text)
            if verbose:
                print(f'  → {len(cards)} cards from listing title/description.')

    if not cards:
        if verbose:
            print()
            print('No cards detected automatically. Switching to manual entry.')
        cards = manual_entry_mode()

    if not cards:
        print('No cards to price. Exiting.')
        return {'error': 'No cards identified'}

    # ── Step 3: Price each card ────────────────────────────────────────────
    if verbose:
        print(f'\nPricing {len(cards)} card(s) via active eBay BIN listings...')

    priced_cards = []
    for i, card in enumerate(cards, 1):
        label = (card.get('description') or card.get('raw_line') or f'Card {i}')[:50]
        if verbose:
            print(f'  [{i:>2}/{len(cards)}] {label}...', end=' ', flush=True)

        pricing = price_card(card)
        priced_cards.append({**card, 'pricing': pricing})

        if verbose:
            if pricing['est_value'] is not None:
                low = pricing['lowest']
                ev  = pricing['est_value']
                n   = pricing['count']
                print(f'  low BIN ${low:.2f}  |  est. ${ev:.2f}  ({n} listings)')
            else:
                print('  no comps found')

        time.sleep(0.25)   # gentle on the API

    # ── Step 4: Totals & signal ────────────────────────────────────────────
    valued = [c for c in priced_cards if c['pricing'].get('est_value') is not None]
    total_est  = sum(c['pricing']['est_value'] for c in valued)
    priced_n   = len(valued)
    asking     = lot['price']

    # If some cards are unpriced, extrapolate using the average of priced cards
    if priced_n > 0 and priced_n < len(priced_cards):
        avg_val      = total_est / priced_n
        extrapolated = total_est + avg_val * (len(priced_cards) - priced_n)
    else:
        extrapolated = total_est

    ratio             = (asking / extrapolated) if extrapolated > 0 else None
    suggested_max_bid = round(extrapolated * _MAX_BID_PCT, 2) if extrapolated > 0 else None

    if ratio is None:
        signal_code = 'unknown'
        signal      = '⚠️  UNKNOWN — No pricing data found; cannot evaluate'
    elif ratio <= _THRESHOLD_GO:
        signal_code = 'go'
        signal      = f'✅ GO — Strong value ({ratio:.0%} of est. market)'
    elif ratio <= _THRESHOLD_CAUTION:
        signal_code = 'caution'
        signal      = f'⚠️  CAUTION — Moderate value ({ratio:.0%} of est. market)'
    else:
        signal_code = 'no-go'
        signal      = f'🛑 NO-GO — Overpriced ({ratio:.0%} of est. market)'

    return {
        'lot':   lot,
        'cards': priced_cards,
        'totals': {
            'total_cards':        len(priced_cards),
            'priced_count':       priced_n,
            'total_est_value':    round(total_est, 2),
            'extrapolated_value': round(extrapolated, 2),
            'asking_price':       asking,
            'ratio':              round(ratio, 4) if ratio is not None else None,
            'suggested_max_bid':  suggested_max_bid,
            'signal_code':        signal_code,
            'signal':             signal,
        },
    }

# ── Console output ─────────────────────────────────────────────────────────────
def print_results(result: dict):
    """Print a formatted analysis table and summary to stdout."""
    if result.get('error'):
        print(f'\nERROR: {result["error"]}')
        return

    lot    = result['lot']
    cards  = result['cards']
    totals = result['totals']

    W = 78   # total line width
    print()
    print('=' * W)
    print(f'  LOT ANALYSIS  —  eBay #{lot["item_id"]}')
    print('=' * W)
    print(f'  Title:        {lot["title"]}')
    print(f'  Asking price: ${lot["price"]:,.2f}')
    print(f'  Seller:       {lot.get("seller") or "N/A"}')
    print(f'  URL:          {lot["item_url"]}')

    # ── Per-card table ──
    print()
    hdr = f'{"#":>3}  {"Card (Year + Description)":<42}  {"Low BIN":>8}  {"Est.Val":>8}  {"Listed":>6}'
    print(hdr)
    print('-' * W)

    for i, card in enumerate(cards, 1):
        p    = card['pricing']
        year = card.get('year', '')
        desc = (card.get('description') or card.get('raw_line') or '')[:40]
        label = f'{year} {desc}'.strip()[:42]
        flag  = '' if p.get('est_value') is not None else '?'
        low   = f'${p["lowest"]:>7.2f}' if p.get('lowest') is not None else '    N/A'
        ev    = f'${p["est_value"]:>7.2f}' if p.get('est_value') is not None else '    N/A'
        cnt   = str(p.get('count', 0))

        print(f'{i:>3}{flag} {label:<42}  {low}  {ev}  {cnt:>6}')

        # Show 3-lowest / 3-highest on a sub-line if available
        three_l = p.get('three_lowest', [])
        three_h = p.get('three_highest', [])
        if len(three_l) > 1:
            lows_str  = '  '.join(f'${v:.2f}' for v in three_l)
            highs_str = '  '.join(f'${v:.2f}' for v in three_h)
            print(f'{"":>5}  3 lowest: {lows_str:<30}  3 highest: {highs_str}')

    print('-' * W)
    print(f'{"":>3}  {"TOTAL ESTIMATED VALUE":<42}  {"":>8}  ${totals["total_est_value"]:>7.2f}')
    if totals['total_cards'] > totals['priced_count']:
        print(
            f'{"":>3}  {"EXTRAPOLATED (avg applied to unpriced)":<42}  '
            f'{"":>8}  ${totals["extrapolated_value"]:>7.2f}  *'
        )

    # ── Summary ──
    print()
    print('=' * W)
    print('  SUMMARY')
    print(f'  Cards identified:       {totals["total_cards"]}')
    print(f'  Cards with pricing:     {totals["priced_count"]}')
    print(f'  Total est. value:       ${totals["total_est_value"]:,.2f}')
    if totals['total_cards'] > totals['priced_count']:
        print(f'  Extrapolated value:     ${totals["extrapolated_value"]:,.2f}  (* avg of priced cards)')
    print(f'  Lot asking price:       ${totals["asking_price"]:,.2f}')
    if totals.get('ratio') is not None:
        print(f'  Price / est. value:     {totals["ratio"]:.0%}  (lower = better deal)')
    if totals.get('suggested_max_bid') is not None:
        print(f'  Suggested max bid:      ${totals["suggested_max_bid"]:,.2f}  (40% of est. value)')
    print()
    print(f'  {totals["signal"]}')
    print('=' * W)
    print()

# ── CSV export ─────────────────────────────────────────────────────────────────
def save_csv(result: dict, output_dir: str = None) -> str:
    """
    Write a CSV with per-card pricing and a summary footer.

    Returns the file path, or None on error.
    """
    if result.get('error'):
        return None

    lot   = result['lot']
    cards = result['cards']
    tots  = result['totals']

    fname = f'lot_{lot["item_id"]}_analysis.csv'
    fpath = os.path.join(output_dir or _SCRIPT_DIR, fname)

    with open(fpath, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)

        # Lot header
        w.writerow(['LOT ANALYSIS', f'eBay #{lot["item_id"]}'])
        w.writerow(['Title',        lot['title']])
        w.writerow(['Asking Price', f'${lot["price"]:.2f}'])
        w.writerow(['Seller',       lot.get('seller', '')])
        w.writerow(['URL',          lot['item_url']])
        w.writerow(['Analyzed',     datetime.now().strftime('%Y-%m-%d %H:%M')])
        w.writerow([])

        # Column headers
        w.writerow([
            '#', 'Year', 'Description', 'Grader', 'Grade', 'Card #',
            'Lowest BIN', 'Est. Value',
            '3 Lowest BINs', '3 Highest BINs',
            '# Active Listings', 'Search Query',
        ])

        # Card rows
        for i, card in enumerate(cards, 1):
            p = card['pricing']
            w.writerow([
                i,
                card.get('year', ''),
                (card.get('description') or '')[:80],
                card.get('grader', ''),
                card.get('grade', ''),
                card.get('card_num', ''),
                f'${p["lowest"]:.2f}'     if p.get('lowest')     is not None else 'N/A',
                f'${p["est_value"]:.2f}'  if p.get('est_value')  is not None else 'N/A',
                ' | '.join(f'${v:.2f}' for v in p.get('three_lowest',  [])),
                ' | '.join(f'${v:.2f}' for v in p.get('three_highest', [])),
                p.get('count', 0),
                p.get('query', ''),
            ])

        # Summary footer
        w.writerow([])
        w.writerow(['SUMMARY'])
        w.writerow(['Total Cards',        tots['total_cards']])
        w.writerow(['Cards Priced',        tots['priced_count']])
        w.writerow(['Total Est. Value',    f'${tots["total_est_value"]:.2f}'])
        w.writerow(['Extrapolated Value',  f'${tots["extrapolated_value"]:.2f}'])
        w.writerow(['Asking Price',        f'${tots["asking_price"]:.2f}'])
        w.writerow(['Price / Est. Value',  f'{tots["ratio"]:.1%}' if tots.get('ratio') is not None else 'N/A'])
        w.writerow(['Suggested Max Bid',   f'${tots["suggested_max_bid"]:.2f}' if tots.get('suggested_max_bid') is not None else 'N/A'])
        w.writerow(['Signal',              tots['signal']])

    return fpath

# ── CLI entry point ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog='lot_analyzer',
        description='Evaluate an eBay card lot for buy/bid decisions.',
        epilog='Example:  python lot_analyzer.py 123456789012',
    )
    parser.add_argument(
        'lot', nargs='?',
        help='eBay listing URL or item number',
    )
    parser.add_argument(
        '--manual', '-m', action='store_true',
        help='Skip auto card-detection; enter cards manually',
    )
    parser.add_argument(
        '--no-csv', action='store_true',
        help='Do not save a CSV output file',
    )
    parser.add_argument(
        '--output-dir', '-o', default=None,
        help='Directory for CSV output (default: same folder as this script)',
    )
    args = parser.parse_args()

    # Prompt if no lot provided
    if not args.lot:
        print('eBay Lot Analyzer')
        print('─' * 40)
        lot_input = input('Enter eBay URL or item number: ').strip()
    else:
        lot_input = args.lot

    if not lot_input:
        parser.print_help()
        sys.exit(1)

    try:
        parse_item_id(lot_input)   # validate early
    except ValueError as exc:
        print(f'Error: {exc}')
        sys.exit(1)

    manual_cards = manual_entry_mode() if args.manual else None

    result = analyze_lot(lot_input, manual_cards=manual_cards, verbose=True)
    print_results(result)

    if not args.no_csv and not result.get('error'):
        csv_path = save_csv(result, output_dir=args.output_dir)
        if csv_path:
            print(f'Results saved to: {csv_path}')

    return result


if __name__ == '__main__':
    main()
