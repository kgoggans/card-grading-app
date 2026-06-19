"""
Card Identification

Primary:  Claude Vision (card_vision.py) — reads player, year, set, parallel,
          grader, grade, cert# in one API call. Handles foil, holo, slabs,
          grid shots. Requires ANTHROPIC_API_KEY in .env.

Fallback: EasyOCR + regex — local/free, lower accuracy, single cards only.

identify_card(image_path) always tries Vision first; falls back to OCR if
ANTHROPIC_API_KEY is not set or the Vision call errors.
"""

import re
import os
import cv2
import numpy as np
import difflib

# ── Vision import (optional — falls back gracefully if not available) ──────────
try:
    from card_vision import identify_card_vision as _vision_identify, vision_available
    _VISION_IMPORTED = True
except ImportError:
    _VISION_IMPORTED = False
    def vision_available(): return False

try:
    import easyocr as _easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False

_reader = None

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

_YEAR_RE   = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')
_CARDNUM_RE = re.compile(r'(?:#\s*|No\.?\s*)(\d{1,4}[A-Za-z]?)|^\s*(\d{1,4}[A-Za-z]?)\s*$')

_MANUFACTURERS = [
    'TOPPS', 'PANINI', 'UPPER DECK', 'BOWMAN', 'FLEER', 'DONRUSS', 'SCORE',
    'LEAF', 'PACIFIC', 'SP', 'SPX', 'SKYBOX', 'HOOPS', 'ULTRA', 'FINEST',
    'STADIUM CLUB', 'HERITAGE', 'ARCHIVES', 'GALLERY',
]

_SET_KEYWORDS = [
    'PRIZM', 'OPTIC', 'MOSAIC', 'CHROME', 'REFRACTOR', 'SELECT', 'ABSOLUTE',
    'ILLUSIONS', 'CERTIFIED', 'CHRONICLES', 'CONTENDERS', 'SPECTRA', 'NOIR',
    'NATIONAL TREASURES', 'IMMACULATE', 'FLAWLESS', 'TOPPS FINEST',
    'BOWMAN CHROME', 'HERITAGE', 'GALLERY', 'TRIBUTE', 'TRIBUTE',
    'ROOKIE', 'RC', 'AUTO', 'AUTOGRAPH', 'PATCH', 'RPA', 'GOLD', 'SILVER',
    'HOLO', 'CRACKED ICE', 'WAVE', 'TIGER STRIPE', 'RED', 'BLUE',
]

# Words that are NOT player names
_IGNORE_WORDS = {
    'THE', 'OF', 'AND', 'FOR', 'IN', 'OUT', 'IS', 'IT', 'TO',
    'CARD', 'CARDS', 'MINT', 'NEAR', 'POOR', 'FAIR', 'GOOD',
    'PSA', 'BGS', 'SGC', 'CGC', 'GEM', 'GRADE', 'GRADED',
    'NBA', 'NFL', 'MLB', 'NHL', 'MLS', 'NFC', 'AFC',
    'ROOKIE', 'SEASON', 'SERIES', 'BASE', 'SET', 'RC',
} | set(_MANUFACTURERS) | set(_SET_KEYWORDS)


def _get_reader():
    global _reader
    if _reader is None and _EASYOCR_AVAILABLE:
        _reader = _easyocr.Reader(['en'], gpu=False, verbose=False)
    return _reader


def _preprocess(img):
    """Return a list of image variants for OCR (original + enhanced)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return [img, cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)]


def _bbox_area(bbox):
    """Approximate area of an EasyOCR bounding box [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _is_name_candidate(text: str) -> bool:
    """Heuristic: text looks like a person's name."""
    words = text.upper().split()
    if len(words) < 2 or len(words) > 5:
        return False
    if any(re.search(r'\d', w) for w in words):
        return False
    if any(w in _IGNORE_WORDS for w in words):
        return False
    if all(re.match(r"^[A-Z][A-Z'\-\.]*$", w) for w in words):
        return True
    return False


def identify_card(image_path: str) -> dict:
    """
    Identify a sports card from its front image.

    Tries Claude Vision first (if ANTHROPIC_API_KEY is set); falls back
    to EasyOCR + regex if Vision is unavailable or returns an error.

    Returns:
        {
            player_name: str | None,
            year: str | None,
            manufacturer: str | None,
            set_name: str | None,
            card_number: str | None,
            search_query: str,         # ready-to-use eBay query
            raw_text: list[str],
            confidence: 'high'|'medium'|'low',
            # (Vision only) parallel, grader, grade, cert_number, sport, team, rookie
        }
    """
    # ── Claude Vision (primary) ────────────────────────────────────────────────
    if _VISION_IMPORTED and vision_available():
        result = _vision_identify(image_path)
        if not result.get('error') and result.get('confidence') != 'low':
            return result
        # If vision returned low confidence, try OCR as well and pick the better one
        ocr_result = _identify_card_ocr(image_path)
        if ocr_result.get('confidence') in ('high', 'medium'):
            return ocr_result
        # Vision low-confidence beats OCR low-confidence (Vision still parsed more fields)
        return result

    # ── EasyOCR fallback ───────────────────────────────────────────────────────
    return _identify_card_ocr(image_path)


def _identify_card_ocr(image_path: str) -> dict:
    """EasyOCR-based card identification (original implementation)."""
    reader = _get_reader()
    if reader is None:
        return {
            'player_name': None, 'year': None, 'manufacturer': None,
            'set_name': None, 'card_number': None,
            'search_query': '', 'raw_text': [], 'confidence': 'low',
            'error': 'EasyOCR not available'
        }

    img = cv2.imread(image_path)
    if img is None:
        return {
            'player_name': None, 'year': None, 'manufacturer': None,
            'set_name': None, 'card_number': None,
            'search_query': '', 'raw_text': [], 'confidence': 'low',
            'error': 'Could not load image'
        }

    h, w = img.shape[:2]
    scale = max(1.0, 800.0 / min(h, w))
    if scale > 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Collect OCR results from all variants
    all_results = []
    for variant in _preprocess(img):
        try:
            results = reader.readtext(variant, detail=1, paragraph=False)
            for bbox, text, conf in results:
                if conf >= 0.3 and text.strip():
                    all_results.append((bbox, text.strip(), conf))
        except Exception:
            continue

    if not all_results:
        return {
            'player_name': None, 'year': None, 'manufacturer': None,
            'set_name': None, 'card_number': None,
            'search_query': '', 'raw_text': [], 'confidence': 'low',
        }

    # Deduplicate (same text, overlapping bbox)
    seen_texts = set()
    unique_results = []
    for bbox, text, conf in sorted(all_results, key=lambda x: -x[2]):
        key = text.upper().strip()
        if key not in seen_texts:
            seen_texts.add(key)
            unique_results.append((bbox, text, conf))

    raw_text = [t for _, t, _ in unique_results]
    combined = ' '.join(raw_text).upper()

    # --- Extract fields ---

    # Year
    year_match = _YEAR_RE.search(combined)
    year = year_match.group(1) if year_match else None

    # Manufacturer
    manufacturer = None
    for mfr in _MANUFACTURERS:
        if mfr in combined:
            manufacturer = mfr.title()
            break

    # Set name (fuzzy match)
    set_name = None
    for kw in _SET_KEYWORDS:
        if kw in combined:
            set_name = kw.title()
            break

    # Card number
    card_number = None
    for _, text, _ in unique_results:
        m = _CARDNUM_RE.search(text.upper())
        if m:
            card_number = next(g for g in m.groups() if g is not None)
            break

    # Player name: highest-confidence large-font text that looks like a name
    player_name = None
    name_candidates = []
    for bbox, text, conf in unique_results:
        if conf < 0.5:
            continue
        area = _bbox_area(bbox)
        if _is_name_candidate(text):
            name_candidates.append((text, conf, area))

    if name_candidates:
        # Prefer larger text (bigger bounding box = bigger font = more likely the name)
        name_candidates.sort(key=lambda x: (-x[2], -x[1]))
        player_name = name_candidates[0][0]

    # Confidence scoring
    found = sum(1 for x in [player_name, year, manufacturer] if x is not None)
    confidence = 'high' if found >= 3 else ('medium' if found >= 1 else 'low')

    # Build search query
    parts = [p for p in [year, manufacturer, set_name, player_name] if p]
    if card_number:
        parts.append(f'#{card_number}')
    search_query = ' '.join(parts)

    return {
        'player_name': player_name,
        'year': year,
        'manufacturer': manufacturer,
        'set_name': set_name,
        'card_number': card_number,
        'search_query': search_query,
        'raw_text': raw_text[:20],
        'confidence': confidence,
    }
