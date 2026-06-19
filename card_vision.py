#!/usr/bin/env python3
"""
card_vision.py — Claude Vision card identification

Uses the Anthropic Messages API (claude-3-5-haiku) to identify sports cards
from images. Works for:
  • Single card photos (front or back)
  • Grid / binder shots (multiple cards at once)
  • Graded PSA / BGS / SGC slab photos
  • eBay lot listing images

Requires:  ANTHROPIC_API_KEY in .env

Output schema is a superset of card_identifier.identify_card():
    player_name, year, manufacturer, set_name, card_number,
    search_query, raw_text, confidence,
    + parallel, grader, grade, cert_number, sport, team, rookie

Standalone usage:
    python card_vision.py path/to/card.jpg
    python card_vision.py --grid path/to/binder_page.jpg
    python card_vision.py --url https://i.ebayimg.com/images/...
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── Constants ──────────────────────────────────────────────────────────────────
_ANTHROPIC_API  = 'https://api.anthropic.com/v1/messages'
_API_VERSION    = '2023-06-01'
# Use haiku for speed/cost; swap to 'claude-sonnet-4-6' for trickier images
_DEFAULT_MODEL  = 'claude-3-5-haiku-20241022'
_MAX_TOKENS     = 2048
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB — Anthropic limit per image
_UA = 'Mozilla/5.0 CardVision/1.0'

# Empty card skeleton — same schema as card_identifier.identify_card()
# (with extra grading / parallel fields added)
EMPTY_CARD: dict = {
    'player_name': None,
    'year':        None,
    'manufacturer': None,
    'set_name':    None,
    'card_number': None,
    'parallel':    None,   # extra
    'grader':      None,   # extra
    'grade':       None,   # extra
    'cert_number': None,   # extra
    'sport':       None,   # extra
    'team':        None,   # extra
    'rookie':      False,  # extra
    'search_query': '',
    'raw_text':    [],
    'confidence':  'low',
}

# ── Single-card prompt ─────────────────────────────────────────────────────────
_SINGLE_PROMPT = """You are an expert sports card analyst. Examine the card image carefully.

Return ONLY a JSON object (no explanation text, no markdown, just the raw JSON):

{
  "player_name": "Full name as printed on the card",
  "year": "4-digit release year",
  "manufacturer": "Brand — e.g. Panini, Topps, Upper Deck, Bowman, Donruss",
  "set_name": "Product name — e.g. Prizm, Chrome, Heritage, Select, Mosaic",
  "card_number": "Number only — e.g. 302 (omit # symbol)",
  "parallel": "Color/parallel variant — e.g. Silver Prizm, Gold, Lazer, Hyper (null if base)",
  "grader": "Grading company if in a slab — PSA, BGS, SGC, CSG (null if raw)",
  "grade": "Numeric grade — e.g. 10, 9.5 (null if raw or ungraded)",
  "cert_number": "Grading cert number or serial number if visible (null if not visible)",
  "sport": "Football, Basketball, Baseball, Hockey, Soccer, etc.",
  "team": "Team name",
  "rookie": true or false,
  "search_query": "eBay search string to find this exact card — include year, name, set, grade if graded",
  "confidence": "high if all key fields certain, medium if 1-2 fields uncertain, low if image unclear"
}

Use null for any field you cannot determine. Be precise and concise."""

# ── Grid-shot prompt ───────────────────────────────────────────────────────────
_GRID_PROMPT = """You are an expert sports card analyst. This image shows one or more sports cards \
(a binder page, lot photo, or graded slab collection).

Return ONLY a JSON array (no explanation, no markdown) — one object per visible card, \
ordered left-to-right, top-to-bottom. If only one card is visible, return a 1-element array.

Each object must have exactly these fields:
{
  "player_name": "Full name as printed",
  "year": "4-digit year",
  "manufacturer": "Brand — e.g. Panini, Topps, Upper Deck, Bowman, Donruss",
  "set_name": "Product — e.g. Prizm, Chrome, Heritage, Select, Mosaic",
  "card_number": "Number only (omit # symbol)",
  "parallel": "Parallel/color variant (null if base)",
  "grader": "PSA, BGS, SGC, CSG, etc. (null if raw)",
  "grade": "Numeric grade e.g. 10 (null if raw)",
  "cert_number": "Cert/serial number if visible (null otherwise)",
  "sport": "Football, Basketball, Baseball, etc.",
  "team": "Team name",
  "rookie": true or false,
  "search_query": "eBay search string for finding this exact card",
  "confidence": "high / medium / low"
}

Use null for fields you cannot determine. Identify every card you can see, even partially."""


# ── Core API call ──────────────────────────────────────────────────────────────
def _get_api_key() -> str:
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not key:
        raise EnvironmentError(
            'ANTHROPIC_API_KEY not set. Add it to your .env file.\n'
            'Get one at: https://console.anthropic.com/settings/keys'
        )
    return key


def _image_to_b64(image_path: str) -> tuple[str, str]:
    """Return (base64_data, media_type) for a local image file."""
    mime, _ = mimetypes.guess_type(image_path)
    if not mime or not mime.startswith('image/'):
        mime = 'image/jpeg'
    with open(image_path, 'rb') as fh:
        data = fh.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f'Image too large ({len(data) // 1024}KB). Max 5MB.')
    return base64.b64encode(data).decode('ascii'), mime


def _url_to_b64(image_url: str) -> tuple[str, str]:
    """Download an image URL and return (base64_data, media_type)."""
    headers = {'User-Agent': _UA, 'Accept': 'image/*'}
    try:
        req = Request(image_url, headers=headers)
        with urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            data = resp.read()
    except Exception as exc:
        raise RuntimeError(f'Could not download image: {exc}') from exc

    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f'Image too large ({len(data) // 1024}KB). Max 5MB.')
    return base64.b64encode(data).decode('ascii'), content_type


def _call_vision_api(
    b64_data: str,
    media_type: str,
    prompt: str,
    model: str = _DEFAULT_MODEL,
    retries: int = 2,
) -> str:
    """Call the Anthropic Messages API with one image. Returns the text response."""
    key = _get_api_key()
    payload = {
        'model':      model,
        'max_tokens': _MAX_TOKENS,
        'messages': [{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type':       'base64',
                        'media_type': media_type,
                        'data':       b64_data,
                    },
                },
                {'type': 'text', 'text': prompt},
            ],
        }],
    }
    headers = {
        'x-api-key':         key,
        'anthropic-version': _API_VERSION,
        'content-type':      'application/json',
        'User-Agent':        _UA,
    }

    for attempt in range(retries + 1):
        try:
            body = json.dumps(payload).encode('utf-8')
            req  = Request(_ANTHROPIC_API, data=body, headers=headers, method='POST')
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            return result['content'][0]['text'].strip()
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            body_text = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'Anthropic API HTTP {exc.code}: {body_text[:300]}') from exc
        except (URLError, TimeoutError) as exc:
            if attempt < retries:
                time.sleep(3)
                continue
            raise RuntimeError(f'Anthropic API request failed: {exc}') from exc


def _parse_json_response(text: str) -> object:
    """Extract JSON from the Claude response (strips markdown fences if present)."""
    # Strip ```json ... ``` fences
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Find the first [ or { and try from there
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            if start == -1:
                continue
            end = text.rfind(end_char)
            if end == -1:
                continue
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f'Could not parse JSON from API response: {text[:200]}')


def _normalise_card(raw: dict) -> dict:
    """Merge a raw Claude JSON response into a clean EMPTY_CARD skeleton."""
    card = dict(EMPTY_CARD)
    for key in card:
        if key in raw and raw[key] is not None:
            card[key] = raw[key]
    # Normalise types
    card['rookie']     = bool(card.get('rookie', False))
    card['grade']      = str(card['grade']) if card.get('grade') is not None else None
    card['year']       = str(card['year'])  if card.get('year')  is not None else None
    card['card_number'] = str(card['card_number']) if card.get('card_number') is not None else None
    # raw_text: store the original JSON for traceability
    card['raw_text']   = [json.dumps(raw)]
    return card


# ── Public API ─────────────────────────────────────────────────────────────────
def vision_available() -> bool:
    """Return True if ANTHROPIC_API_KEY is configured."""
    return bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())


def identify_card_vision(image_path: str, model: str = _DEFAULT_MODEL) -> dict:
    """
    Identify a single sports card from a local image file.

    Returns a dict matching the card_identifier.identify_card() schema
    (plus parallel, grader, grade, cert_number, sport, team, rookie).
    Never raises — returns an error dict on failure.
    """
    try:
        b64, mime = _image_to_b64(image_path)
        text = _call_vision_api(b64, mime, _SINGLE_PROMPT, model=model)
        raw  = _parse_json_response(text)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        return _normalise_card(raw)
    except Exception as exc:
        card = dict(EMPTY_CARD)
        card['error'] = str(exc)
        return card


def identify_cards_grid(image_path: str, model: str = _DEFAULT_MODEL) -> list:
    """
    Identify all cards visible in a grid / binder / lot photo (local file).

    Returns a list of card dicts (one per visible card).
    Never raises — returns [error_dict] on failure.
    """
    try:
        b64, mime = _image_to_b64(image_path)
        text = _call_vision_api(b64, mime, _GRID_PROMPT, model=model)
        raw  = _parse_json_response(text)
        if isinstance(raw, dict):
            raw = [raw]
        return [_normalise_card(r) for r in raw if isinstance(r, dict)]
    except Exception as exc:
        card = dict(EMPTY_CARD)
        card['error'] = str(exc)
        return [card]


def identify_cards_from_url(image_url: str, model: str = _DEFAULT_MODEL) -> list:
    """
    Identify all cards visible in an image at a URL.

    Downloads the image, then calls identify_cards_grid.
    Returns a list of card dicts.
    """
    try:
        b64, mime = _url_to_b64(image_url)
        text = _call_vision_api(b64, mime, _GRID_PROMPT, model=model)
        raw  = _parse_json_response(text)
        if isinstance(raw, dict):
            raw = [raw]
        return [_normalise_card(r) for r in raw if isinstance(r, dict)]
    except Exception as exc:
        card = dict(EMPTY_CARD)
        card['error'] = str(exc)
        return [card]


def identify_cards_from_urls(
    image_urls: list,
    max_images: int = 6,
    model: str = _DEFAULT_MODEL,
    verbose: bool = False,
) -> list:
    """
    Identify cards from a list of image URLs (e.g. all lot photos from eBay).

    Processes up to `max_images` images, deduplicates by player+year, and
    returns a merged list of unique card dicts.

    Args:
        image_urls  : list of image URL strings
        max_images  : cap to limit API calls / cost
        model       : Claude model to use
        verbose     : print progress to stdout

    Returns:
        list of card dicts
    """
    all_cards: list = []
    seen_keys: set  = set()

    for i, url in enumerate(image_urls[:max_images], 1):
        if verbose:
            print(f'  [image {i}/{min(len(image_urls), max_images)}] {url[:60]}...',
                  end=' ', flush=True)
        try:
            cards = identify_cards_from_url(url, model=model)
            new_count = 0
            for card in cards:
                if card.get('error'):
                    continue
                # Deduplicate by (player, year, card_number)
                key = (
                    (card.get('player_name') or '').lower(),
                    card.get('year') or '',
                    card.get('card_number') or '',
                )
                if key == ('', '', ''):
                    continue  # skip blank results
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_cards.append(card)
                    new_count += 1
            if verbose:
                print(f'{new_count} card(s) found')
        except Exception as exc:
            if verbose:
                print(f'ERROR: {exc}')
        time.sleep(0.5)  # gentle pacing

    return all_cards


# ── Lot-analyzer-compatible card dict ─────────────────────────────────────────
def card_to_lot_format(card: dict) -> dict:
    """
    Convert a card_vision card dict to the format expected by lot_analyzer.py.

    lot_analyzer uses: description, year, card_num, grader, grade, raw_line
    card_vision uses:  player_name, year, card_number, grader, grade, set_name, etc.
    """
    parts = []
    if card.get('manufacturer'):
        parts.append(card['manufacturer'])
    if card.get('set_name'):
        parts.append(card['set_name'])
    if card.get('parallel'):
        parts.append(card['parallel'])
    if card.get('player_name'):
        parts.append(card['player_name'])
    if card.get('rookie'):
        parts.append('RC')

    description = ' '.join(p for p in parts if p)

    return {
        'raw_line':    card.get('search_query', description),
        'description': description,
        'year':        card.get('year'),
        'card_num':    card.get('card_number'),
        'grader':      card.get('grader'),
        'grade':       card.get('grade'),
        # Keep extra fields for reference
        'player_name': card.get('player_name'),
        'set_name':    card.get('set_name'),
        'parallel':    card.get('parallel'),
        'confidence':  card.get('confidence', 'low'),
        '_source':     'vision',
    }


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Identify sports cards in images using Claude Vision.',
        epilog='Example: python card_vision.py front.jpg'
    )
    parser.add_argument('image', nargs='?', help='Path to image file')
    parser.add_argument('--grid',   action='store_true',
                        help='Use grid prompt (multiple cards per image)')
    parser.add_argument('--url',    metavar='URL',
                        help='Identify cards in an image URL instead of a file')
    parser.add_argument('--model',  default=_DEFAULT_MODEL,
                        help=f'Claude model (default: {_DEFAULT_MODEL})')
    parser.add_argument('--json',   action='store_true',
                        help='Output raw JSON')
    args = parser.parse_args()

    if not vision_available():
        print('ERROR: ANTHROPIC_API_KEY not set in .env')
        sys.exit(1)

    if args.url:
        cards = identify_cards_from_url(args.url, model=args.model)
    elif args.image:
        if args.grid:
            cards = identify_cards_grid(args.image, model=args.model)
        else:
            cards = [identify_card_vision(args.image, model=args.model)]
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(cards, indent=2))
        return

    for i, card in enumerate(cards, 1):
        print(f'\n─── Card {i} ───')
        if card.get('error'):
            print(f'  ERROR: {card["error"]}')
            continue
        fields = [
            ('Player',      card.get('player_name')),
            ('Year',        card.get('year')),
            ('Brand/Set',   f'{card.get("manufacturer") or ""} {card.get("set_name") or ""}'.strip()),
            ('Parallel',    card.get('parallel')),
            ('Card #',      card.get('card_number')),
            ('Grader',      card.get('grader')),
            ('Grade',       card.get('grade')),
            ('Cert #',      card.get('cert_number')),
            ('Sport',       card.get('sport')),
            ('Team',        card.get('team')),
            ('Rookie',      'Yes' if card.get('rookie') else 'No'),
            ('Confidence',  card.get('confidence')),
            ('Search query', card.get('search_query')),
        ]
        for label, value in fields:
            if value:
                print(f'  {label:<14} {value}')


if __name__ == '__main__':
    # Auto-load .env when running standalone
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(_env_path):
        with open(_env_path) as _fh:
            for _line in _fh:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _, _v = _line.partition('=')
                    _k, _v = _k.strip(), _v.strip()
                    if _v:
                        os.environ[_k] = _v

    main()
