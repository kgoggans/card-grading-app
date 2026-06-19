#!/usr/bin/env python3
"""
lot_cataloger.py — Two-phase lot card cataloger

Phase 1: Identify all cards in an eBay lot via Claude Vision (streams results,
         caches by item ID so re-running costs zero tokens)
Phase 2: Price a confirmed/edited card list via eBay BIN search

Used by Flask routes /lot-cataloger/identify-stream and /lot-cataloger/price
"""

import json
import os
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR  = os.path.join(_SCRIPT_DIR, 'cache')
os.makedirs(_CACHE_DIR, exist_ok=True)

if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from lot_analyzer import (
    parse_item_id,
    fetch_lot_item,
    fetch_all_lot_images,
    price_card,
    _THRESHOLD_GO,
    _THRESHOLD_CAUTION,
    _MAX_BID_PCT,
)
from card_vision import (
    identify_cards_from_url,
    card_to_lot_format,
    vision_available,
)

_MAX_IMAGES = 200


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_path(item_id: str) -> str:
    return os.path.join(_CACHE_DIR, f'lot_{item_id}_vision.json')


def load_cached(item_id: str):
    """Return cached Vision identification result dict, or None."""
    path = _cache_path(item_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_cached(item_id: str, data: dict):
    path = _cache_path(item_id)
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def clear_cache(item_id: str):
    path = _cache_path(item_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


# ── SSE event helpers ──────────────────────────────────────────────────────────

def _evt(data: dict) -> str:
    """Format a dict as an SSE 'data:' line."""
    return f"data: {json.dumps(data)}\n\n"


# ── Phase 1: Identification stream ─────────────────────────────────────────────

def identify_lot_stream(item_id_or_url: str):
    """
    Generator that yields SSE-formatted strings while identifying cards.

    Event types (all JSON in the 'data:' field):
      {'type': 'lot',      'lot': {...}}
      {'type': 'images',   'count': N, 'cached': bool}
      {'type': 'progress', 'current': N, 'total': N, 'msg': '...'}
      {'type': 'card',     'image_url': '...', 'card': {...}}
      {'type': 'done',     'total_cards': N, 'item_id': '...', 'cached': bool}
      {'type': 'error',    'message': '...'}
    """

    # ── Parse item ID ──────────────────────────────────────────────────────────
    try:
        item_id = parse_item_id(item_id_or_url)
    except ValueError as exc:
        yield _evt({'type': 'error', 'message': str(exc)})
        return

    # ── Serve from cache ───────────────────────────────────────────────────────
    cached = load_cached(item_id)
    if cached:
        lot_meta = cached.get('lot', {})
        cards    = cached.get('cards', [])
        yield _evt({'type': 'lot',    'lot': _safe_lot(lot_meta)})
        yield _evt({'type': 'images', 'count': len(cached.get('images', [])), 'cached': True})
        for card in cards:
            yield _evt({'type': 'card', 'image_url': card.get('_image_url', ''), 'card': card})
        yield _evt({
            'type': 'done',
            'total_cards': len(cards),
            'item_id': item_id,
            'cached': True,
        })
        return

    # ── Fetch lot from eBay Browse API ─────────────────────────────────────────
    yield _evt({'type': 'progress', 'current': 0, 'total': 0,
                'msg': 'Fetching listing from eBay...'})
    lot = fetch_lot_item(item_id)
    if lot.get('error'):
        yield _evt({'type': 'error', 'message': f"eBay API error: {lot['error']}"})
        return

    yield _evt({'type': 'lot', 'lot': _safe_lot(lot)})

    # ── Get ALL gallery images (Browse API + Firecrawl full-page HTML) ─────────
    yield _evt({'type': 'progress', 'current': 0, 'total': 0,
                'msg': 'Scanning listing page for all card photos...'})
    images = fetch_all_lot_images(lot['item_url'], lot.get('image_urls', []))

    if not images:
        yield _evt({'type': 'error',
                    'message': 'No images found in this listing. '
                               'The seller may not have uploaded photos yet.'})
        return

    capped = images[:_MAX_IMAGES]
    yield _evt({'type': 'images', 'count': len(capped), 'cached': False})

    if not vision_available():
        yield _evt({'type': 'error',
                    'message': 'ANTHROPIC_API_KEY not configured. '
                               'Claude Vision is unavailable.'})
        return

    # ── Identify cards image by image ──────────────────────────────────────────
    all_cards  = []
    seen_keys  = set()
    total_imgs = len(capped)

    for i, img_url in enumerate(capped, 1):
        yield _evt({
            'type': 'progress',
            'current': i,
            'total':   total_imgs,
            'msg':     f'Analyzing photo {i} of {total_imgs}...',
        })

        try:
            raw_cards = identify_cards_from_url(img_url)
        except Exception as exc:
            # Skip bad images — don't abort the whole run
            yield _evt({'type': 'progress', 'current': i, 'total': total_imgs,
                        'msg': f'Skipped photo {i} ({str(exc)[:60]})'})
            time.sleep(0.2)
            continue

        for rc in raw_cards:
            if rc.get('error'):
                continue
            player = (rc.get('player_name') or '').strip()
            if not player:
                continue   # no readable name → skip (not hallucinate)

            card = card_to_lot_format(rc)
            card['_image_url'] = img_url

            # Deduplicate on (player, year, card_num, serial)
            key = (
                player.lower(),
                card.get('year') or '',
                card.get('card_num') or '',
                card.get('serial_number') or '',
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_cards.append(card)

            yield _evt({'type': 'card', 'image_url': img_url, 'card': card})

        time.sleep(0.3)

    # ── Cache and signal completion ────────────────────────────────────────────
    save_cached(item_id, {
        'lot':       lot,
        'images':    images,
        'cards':     all_cards,
        'timestamp': time.time(),
    })

    yield _evt({
        'type':        'done',
        'total_cards': len(all_cards),
        'item_id':     item_id,
        'cached':      False,
    })


def _safe_lot(lot: dict) -> dict:
    """Return a JSON-safe subset of the lot dict."""
    return {
        'item_id':  lot.get('item_id', ''),
        'title':    lot.get('title', ''),
        'price':    lot.get('price', 0),
        'seller':   lot.get('seller', ''),
        'item_url': lot.get('item_url', ''),
    }


# ── Phase 2: Price confirmed cards ─────────────────────────────────────────────

def price_confirmed_cards(cards: list, asking_price: float = 0.0) -> dict:
    """
    Run eBay BIN pricing on a list of confirmed/edited card dicts.

    Args:
        cards:         List of card dicts (description, year, card_num,
                       grader, grade, auto, patch, serial_number, …)
        asking_price:  Lot asking price — used for GO/CAUTION/NO-GO

    Returns dict:
        priced_cards  — list of card dicts with 'pricing' key added
        totals        — summary (total_est_value, signal, etc.)
    """
    priced_cards = []
    for card in cards:
        try:
            pricing = price_card(card)
        except Exception:
            pricing = {
                'query': '', 'lowest': None, 'three_lowest': [],
                'three_highest': [], 'est_value': None,
                'count': 0, 'items': [], 'unreliable': False,
                'graded_comp': None,
            }
        priced_cards.append({**card, 'pricing': pricing})
        time.sleep(0.25)

    valued    = [c for c in priced_cards if c['pricing'].get('est_value') is not None]
    total_est = sum(c['pricing']['est_value'] for c in valued)
    priced_n  = len(valued)

    if priced_n > 0 and priced_n < len(priced_cards):
        avg          = total_est / priced_n
        extrapolated = total_est + avg * (len(priced_cards) - priced_n)
    else:
        extrapolated = total_est

    ratio             = (asking_price / extrapolated) if extrapolated > 0 and asking_price > 0 else None
    suggested_max_bid = round(extrapolated * _MAX_BID_PCT, 2) if extrapolated > 0 else None

    if ratio is None:
        signal_code = 'unknown'
        signal      = '⚠️ UNKNOWN — Enter asking price for a GO / NO-GO signal'
    elif ratio <= _THRESHOLD_GO:
        signal_code = 'go'
        signal      = f'✅ GO — Strong value ({ratio:.0%} of est. market)'
    elif ratio <= _THRESHOLD_CAUTION:
        signal_code = 'caution'
        signal      = f'⚠️ CAUTION — Moderate value ({ratio:.0%} of est. market)'
    else:
        signal_code = 'no-go'
        signal      = f'🛑 NO-GO — Overpriced ({ratio:.0%} of est. market)'

    return {
        'priced_cards': priced_cards,
        'totals': {
            'total_cards':        len(priced_cards),
            'priced_count':       priced_n,
            'total_est_value':    round(total_est, 2),
            'extrapolated_value': round(extrapolated, 2),
            'asking_price':       asking_price,
            'ratio':              round(ratio, 4) if ratio is not None else None,
            'suggested_max_bid':  suggested_max_bid,
            'signal_code':        signal_code,
            'signal':             signal,
        },
    }
