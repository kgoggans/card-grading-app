"""
Market Comparables — priority order:

  1. Card Hedge AI API (best quality, real sold comps) — requires CARD_HEDGE_API_KEY
     Sign up at ai.cardhedger.com/api-services → get key from dashboard
     Auth: X-API-Key header  |  Base: https://api.cardhedger.com

  2. SportsCardsPro API (aggregated prices, 1 call) — requires SPORTSCARDSPRO_API_KEY
     Sign up at sportscardspro.com → Legendary ($49/mo) → Subscription → API/Download

  3. eBay Finding API (findCompletedItems, 5K calls/day) — requires EBAY_APP_ID

  4. eBay Browse API (active listings, 5M calls/day) — requires EBAY_APP_ID + EBAY_CLIENT_SECRET

  export CARD_HEDGE_API_KEY=your_key
  export SPORTSCARDSPRO_API_KEY=your_40_char_token
  export EBAY_APP_ID=your_app_id
  export EBAY_CLIENT_SECRET=your_cert_id
"""

import base64
import os
import json
import re
import time
import urllib.parse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone


_FINDING_API  = 'https://svcs.ebay.com/services/search/FindingService/v1'
_BROWSE_API   = 'https://api.ebay.com/buy/browse/v1/item_summary/search'
_OAUTH_URL    = 'https://api.ebay.com/identity/v1/oauth2/token'
_SCP_BASE_URL = 'https://www.sportscardspro.com/api'
_CH_BASE_URL  = 'https://api.cardhedger.com'

# Card Hedge grade label map: our int/float grade → CH grade string
_CH_GRADE_LABELS: dict = {
    10:  'PSA 10',
    9.5: 'PSA 9.5',
    9:   'PSA 9',
    8.5: 'PSA 8.5',
    8:   'PSA 8',
    7.5: 'PSA 7.5',
    7:   'PSA 7',
    'raw': 'Raw',
}

# Candidate field names per grade — tried in order, first non-zero value wins.
# Confirmed against live API; defensive list handles any future field renames.
_SCP_GRADE_FIELDS: dict = {
    7:   ['grade-7-price',   'psa-7-price',   'grade7price'],
    8:   ['grade-8-price',   'psa-8-price',   'grade8price'],
    9:   ['grade-9-price',   'psa-9-price',   'grade9price'],
    9.5: ['grade-9.5-price', 'psa-9.5-price', 'grade95price'],
    10:  ['psa-10-price',    'grade-10-price', 'grade10price'],
}

# Cached OAuth token {access_token, expires_at}
_oauth_cache: dict = {}

# ---------------------------------------------------------------------------
# Sold-comps cache — avoids re-hitting the 5K/day Finding API for the same
# queries.  Keys are normalized query strings; TTL default = 6 hours.
# ---------------------------------------------------------------------------
_comps_cache: dict = {}
_CACHE_TTL_SECS: int = 6 * 3600  # 6 hours


def _cache_get(key: str):
    entry = _comps_cache.get(key)
    if entry and time.time() < entry['expires_at']:
        return entry['data']
    return None


def _cache_set(key: str, data, ttl: int = _CACHE_TTL_SECS):
    _comps_cache[key] = {'data': data, 'expires_at': time.time() + ttl}


def _parse_psa_grade_from_title(title: str) -> object:
    """
    Extract a PSA numeric grade from a listing title.
    Handles formats like: PSA 10, PSA GEM MINT 10, PSA 9.5, PSA MINT 9
    """
    m = re.search(
        r'\bPSA\b[\s\-]*(?:[A-Z][A-Z\s\-]*?)?\b(10|[1-9](?:\.5)?)\b',
        title,
        re.IGNORECASE,
    )
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _ch_price_to_stats(price, count=None, low=None, high=None) -> dict:
    """Convert a Card Hedge price (float or string) to a stats-compatible dict."""
    try:
        median = round(float(price), 2)
    except (TypeError, ValueError):
        return None
    if median <= 0:
        return None
    return {
        'count':  count,
        'median': median,
        'mean':   median,
        'low':    round(float(low), 2) if low is not None else None,
        'high':   round(float(high), 2) if high is not None else None,
    }


def _ch_post(endpoint: str, body: dict, timeout: int = 12) -> dict:
    """Make an authenticated POST request to the Card Hedge API."""
    key = _get_ch_key()
    url = f'{_CH_BASE_URL}{endpoint}'
    data = json.dumps(body).encode('utf-8')
    req = Request(url, data=data, headers={
        'X-API-Key':    key,
        'Content-Type': 'application/json',
        'User-Agent':   'CardGradingApp/2.0',
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        body_text = ''
        try:
            body_text = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        raise HTTPError(exc.url, exc.code, f'{exc.reason} | {body_text[:200]}', exc.headers, None) from None


def _search_card_hedge(query: str) -> dict:
    """
    Look up a card on Card Hedge and return per-grade price stats + sold comp items.

    Step 1: POST /v1/cards/card-search  → finds card_id + current grade prices
    Step 2: POST /v1/cards/comps        → per-grade comp price with actual sold records
                                          (only called once per grade, results cached)

    Returns:
        {
            success:      bool,
            card_id:      str | None,
            card_name:    str | None,
            loose_stats:  stats_dict | None,   # Raw/ungraded
            grade_stats:  {7: stats|None, 8: ..., 9: ..., 9.5: ..., 10: ...},
            raw_items:    list[sold_item],      # individual sold records for comps panel
            error:        str | None,
        }
    Never raises.
    """
    if not _get_ch_key():
        return {'success': False, 'card_id': None, 'card_name': None,
                'loose_stats': None, 'grade_stats': {}, 'raw_items': [], 'error': 'CARD_HEDGE_API_KEY not set'}

    # --- Step 1: card search ---
    try:
        search_resp = _ch_post('/v1/cards/card-search', {'search': query.strip(), 'page_size': 5})
    except Exception as exc:
        return {'success': False, 'card_id': None, 'card_name': None,
                'loose_stats': None, 'grade_stats': {}, 'raw_items': [], 'error': f'CH search error: {exc}'}

    cards = search_resp.get('cards', [])
    if not cards:
        return {'success': False, 'card_id': None, 'card_name': None,
                'loose_stats': None, 'grade_stats': {}, 'raw_items': [], 'error': f'No Card Hedge results for "{query}"'}

    best     = cards[0]
    card_id  = best.get('card_id', '')
    card_name = best.get('description', best.get('player', ''))

    # Parse grade prices from card-search response (strings like "850")
    grade_stats  = {}
    loose_stats  = None
    for gp in best.get('prices', []):
        label = (gp.get('grade') or '').strip()
        price = gp.get('price')
        stats = _ch_price_to_stats(price)
        if label in ('Raw', 'Ungraded', ''):
            loose_stats = stats
        else:
            # Map "PSA 9" → 9, "PSA 9.5" → 9.5, "PSA 10" → 10, etc.
            m = re.search(r'(\d+(?:\.\d+)?)\s*$', label)
            if m:
                g = float(m.group(1))
                if g == int(g):
                    g = int(g)
                grade_stats[g] = stats

    # --- Step 2: comps for the predicted/default grades to get real sold records ---
    raw_items = []
    if card_id:
        # Fetch comps for PSA 9 as the representative grade for sold items list
        try:
            comps_resp = _ch_post('/v1/cards/comps', {
                'card_id':           card_id,
                'count':             15,
                'grade':             'PSA 9',
                'include_raw_prices': True,
            })
            comp_price = comps_resp.get('comp_price')
            comp_high  = comps_resp.get('high')
            comp_low   = comps_resp.get('low')
            count_used = comps_resp.get('count_used')

            # Upgrade PSA 9 stats with real comp data (better than card-search price string)
            if comp_price:
                grade_stats[9] = _ch_price_to_stats(comp_price, count=count_used,
                                                     low=comp_low, high=comp_high)

            for sale in (comps_resp.get('raw_prices') or []):
                try:
                    raw_items.append({
                        'title':     sale.get('title', ''),
                        'price':     float(sale.get('price', 0)),
                        'currency':  'USD',
                        'sold_date': (sale.get('sale_date') or '')[:10],
                        'url':       sale.get('sale_url', ''),
                        'condition': sale.get('grade', 'PSA 9'),
                    })
                except Exception:
                    continue
        except Exception:
            pass  # comps call is best-effort; card-search prices are the fallback

    return {
        'success':     True,
        'card_id':     card_id,
        'card_name':   card_name,
        'loose_stats': loose_stats,
        'grade_stats': grade_stats,
        'raw_items':   raw_items,
        'error':       None,
    }


def _scp_price_to_stats(pennies) -> dict:
    """Convert a SportsCardsPro penny-integer price to a stats-compatible dict.
    Only median is populated — that's all downstream callers read."""
    if not pennies:
        return None
    try:
        dollars = int(pennies) / 100.0
    except (TypeError, ValueError):
        return None
    if dollars <= 0:
        return None
    return {'count': None, 'median': round(dollars, 2), 'mean': None, 'low': None, 'high': None}


def _scp_error_result(error_msg: str) -> dict:
    return {
        'success': False, 'product_id': None, 'product_name': None,
        'loose_stats': None,
        'grade_stats': {g: None for g in _SCP_GRADE_FIELDS},
        'raw_product': {}, 'error': error_msg,
    }


def _search_sportscardspro(query: str, timeout: int = 10) -> dict:
    """
    Look up a card on SportsCardsPro and return per-grade price stats.

    Makes two HTTP calls (both count toward no known rate limit):
      1. GET /api/products?q={query}  — find the best-matching product ID
      2. GET /api/product?id={id}     — fetch grade prices for that product

    Returns:
        {
            success:      bool,
            product_id:   str | None,
            product_name: str | None,
            loose_stats:  stats_dict | None,   # ungraded/raw price
            grade_stats:  {7: stats|None, 8: ..., 9: ..., 9.5: ..., 10: ...},
            raw_product:  dict,                # full product JSON for debugging
            error:        str | None,
        }
    Never raises — all errors captured in 'error' key.
    """
    key = _get_scp_key()
    if not key:
        return _scp_error_result('SPORTSCARDSPRO_API_KEY not set')

    # --- Call 1: search ---
    search_url = f'{_SCP_BASE_URL}/products?' + urllib.parse.urlencode({'q': query.strip(), 'api_key': key})
    try:
        req = Request(search_url, headers={'User-Agent': 'CardGradingApp/2.0'})
        with urlopen(req, timeout=timeout) as resp:
            search_data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        return _scp_error_result(f'SCP search HTTP {exc.code}: {body[:200]}')
    except Exception as exc:
        return _scp_error_result(f'SCP search error: {exc}')

    products = search_data if isinstance(search_data, list) else search_data.get('products', [])
    if not products:
        return _scp_error_result(f'No SportsCardsPro results for "{query}"')

    best       = products[0]
    product_id = str(best.get('id', '')).strip()
    if not product_id:
        return _scp_error_result('SCP: first product has no id field')

    # --- Call 2: fetch product details ---
    product_url = f'{_SCP_BASE_URL}/product?' + urllib.parse.urlencode({'id': product_id, 'api_key': key})
    try:
        req = Request(product_url, headers={'User-Agent': 'CardGradingApp/2.0'})
        with urlopen(req, timeout=timeout) as resp:
            product_data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        return _scp_error_result(f'SCP product HTTP {exc.code}: {body[:200]}')
    except Exception as exc:
        return _scp_error_result(f'SCP product error: {exc}')

    if isinstance(product_data, dict) and 'product' in product_data:
        product_data = product_data['product']

    # --- Parse grade prices defensively ---
    grade_stats = {}
    for grade, field_candidates in _SCP_GRADE_FIELDS.items():
        pennies = None
        for field in field_candidates:
            val = product_data.get(field)
            if val is not None and val != '' and val != 0:
                pennies = val
                break
        grade_stats[grade] = _scp_price_to_stats(pennies)

    # --- Parse loose (ungraded) price ---
    loose_pennies = None
    for field in ('loose-price', 'loose_price', 'ungraded-price'):
        val = product_data.get(field)
        if val is not None and val != '' and val != 0:
            loose_pennies = val
            break

    return {
        'success':      True,
        'product_id':   product_id,
        'product_name': product_data.get('name') or best.get('name', ''),
        'loose_stats':  _scp_price_to_stats(loose_pennies),
        'grade_stats':  grade_stats,
        'raw_product':  product_data,
        'error':        None,
    }


def _compute_stats(prices: list) -> object:
    if not prices:
        return None
    s = sorted(prices)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {
        'count':  n,
        'median': round(median, 2),
        'mean':   round(sum(s) / n, 2),
        'low':    round(min(s), 2),
        'high':   round(max(s), 2),
    }


def _get_ch_key() -> str:
    return os.environ.get('CARD_HEDGE_API_KEY', '').strip()


def _get_scp_key() -> str:
    return os.environ.get('SPORTSCARDSPRO_API_KEY', '').strip()


def _get_app_id() -> str:
    return os.environ.get('EBAY_APP_ID', '').strip()


def _get_client_secret() -> str:
    return os.environ.get('EBAY_CLIENT_SECRET', '').strip()


def _get_browse_token() -> str:
    """
    Return a valid Browse API OAuth token, fetching a new one if expired.
    Uses Client Credentials flow (no user login required).
    """
    global _oauth_cache
    now = time.time()
    if _oauth_cache.get('access_token') and now < _oauth_cache.get('expires_at', 0) - 60:
        return _oauth_cache['access_token']

    app_id = _get_app_id()
    secret = _get_client_secret()
    if not app_id or not secret:
        raise ValueError(
            'Browse API requires both EBAY_APP_ID and EBAY_CLIENT_SECRET. '
            'Get your Cert ID at https://developer.ebay.com/'
        )

    credentials = base64.b64encode(f'{app_id}:{secret}'.encode()).decode()
    body = urllib.parse.urlencode({
        'grant_type': 'client_credentials',
        'scope':      'https://api.ebay.com/oauth/api_scope',
    }).encode()

    req = Request(
        _OAUTH_URL,
        data=body,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type':  'application/x-www-form-urlencoded',
        }
    )
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    token      = data['access_token']
    expires_in = int(data.get('expires_in', 7200))
    _oauth_cache = {'access_token': token, 'expires_at': now + expires_in}
    return token


def _call_finding_api(operation: str, params: dict, timeout: int = 10) -> dict:
    """Make a JSON request to the eBay Finding API. Returns parsed JSON or raises."""
    app_id = _get_app_id()
    if not app_id:
        raise ValueError(
            'EBAY_APP_ID environment variable is not set. '
            'Get a free key at https://developer.ebay.com/'
        )

    base_params = {
        'OPERATION-NAME': operation,
        'SERVICE-VERSION': '1.0.0',
        'SECURITY-APPNAME': app_id,
        'RESPONSE-DATA-FORMAT': 'JSON',
        'REST-PAYLOAD': '',
    }
    base_params.update(params)

    url = _FINDING_API + '?' + urllib.parse.urlencode(base_params)
    req = Request(url, headers={'User-Agent': 'CardGradingApp/2.0'})

    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        raise HTTPError(exc.url, exc.code, f'{exc.reason} | {body[:300]}', exc.headers, None) from None


def _check_finding_error(data: dict, operation: str) -> None:
    """Raise ValueError if the eBay Finding API JSON body contains an error."""
    key = f"{operation}Response"
    resp = data.get(key, [{}])[0]
    ack = resp.get("ack", ["Success"])[0]
    if ack in ("Failure", "PartialFailure"):
        msgs = []
        for err in resp.get("errorMessage", [{}])[0].get("error", []):
            msg = err.get("message", ["Unknown eBay error"])[0]
            eid = err.get("errorId", [""])[0]
            msgs.append(f"{msg} (code {eid})" if eid else msg)
        raise ValueError("; ".join(msgs) or "eBay Finding API returned failure")


def _parse_finding_response(data: dict, operation: str) -> list:
    """Extract item list from a findCompletedItems / findItemsAdvanced response."""
    key = f'{operation}Response'
    search_result = data.get(key, [{}])[0].get('searchResult', [{}])[0]
    count = int(search_result.get('@count', 0))
    if count == 0:
        return []

    items = []
    for raw in search_result.get('item', []):
        try:
            price  = float(raw['sellingStatus'][0]['convertedCurrentPrice'][0]['__value__'])
            curr   = raw['sellingStatus'][0]['convertedCurrentPrice'][0].get('@currencyId', 'USD')
            title  = raw['title'][0]
            end_ts = raw['listingInfo'][0]['endTime'][0]
            url    = raw['viewItemURL'][0]
            cond   = raw.get('condition', [{}])[0].get('conditionDisplayName', ['Unknown'])[0]
            items.append({
                'title':     title,
                'price':     price,
                'currency':  curr,
                'sold_date': end_ts[:10] if end_ts else None,
                'url':       url,
                'condition': cond,
            })
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return items


def search_sold_listings(query: str, psa_grade=None, max_results: int = 12) -> dict:
    """
    Search eBay completed/sold listings for a card.

    Args:
        query:      Base search string (e.g. "2021 Topps Mike Trout")
        psa_grade:  If provided, appends "PSA {grade}" to the query
        max_results: How many results to return (max 50)

    Returns dict:
        {
            success: bool,
            query: str,
            items: list[{title, price, currency, sold_date, url, condition}],
            stats: {median, mean, low, high, count} | None,
            error: str | None
        }
    """
    if not query.strip():
        return {'success': False, 'query': query, 'items': [], 'stats': None,
                'error': 'Empty search query'}

    full_query = query.strip()
    if psa_grade is not None:
        full_query = f'{full_query} PSA {psa_grade}'

    cache_key = f'ebay:sold:{full_query.lower()}:{max_results}'
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {
        'keywords': full_query,
        'itemFilter(0).name':  'SoldItemsOnly',
        'itemFilter(0).value': 'true',
        'itemFilter(1).name':  'ListingType',
        'itemFilter(1).value': 'AuctionWithBIN',
        'itemFilter(2).name':  'ListingType',
        'itemFilter(2).value': 'FixedPrice',
        'itemFilter(3).name':  'ListingType',
        'itemFilter(3).value': 'Auction',
        'sortOrder':           'EndTimeSoonest',
        'paginationInput.entriesPerPage': str(min(max_results, 50)),
    }

    try:
        data = _call_finding_api('findCompletedItems', params)
    except ValueError as exc:
        return {'success': False, 'query': full_query, 'items': [], 'stats': None,
                'error': str(exc)}
    except (URLError, HTTPError, TimeoutError) as exc:
        return {'success': False, 'query': full_query, 'items': [], 'stats': None,
                'error': f'eBay API request failed: {exc}'}
    except Exception as exc:
        return {'success': False, 'query': full_query, 'items': [], 'stats': None,
                'error': f'Unexpected error: {exc}'}

    try:
        _check_finding_error(data, 'findCompletedItems')
    except ValueError as exc:
        return {'success': False, 'query': full_query, 'items': [], 'stats': None,
                'error': str(exc)}
    items = _parse_finding_response(data, 'findCompletedItems')
    stats = _compute_stats([i['price'] for i in items])
    result = {'success': True, 'query': full_query, 'items': items, 'stats': stats, 'error': None}
    _cache_set(cache_key, result)
    return result


def fetch_training_candidates(query: str, grade: float, max_results: int = 15) -> tuple:
    """
    Search eBay for PSA-graded card listings and return image URLs for training.
    Uses Browse API (5M calls/day) when EBAY_CLIENT_SECRET is set,
    falls back to Finding API otherwise.

    Returns (candidates, error_message).
    candidates: list of {title, image_url, grade, listing_url}
    """
    if _get_client_secret():
        return _fetch_via_browse_api(query, grade, max_results)
    return _fetch_via_finding_api(query, grade, max_results)


def _fetch_via_browse_api(query: str, grade: float, max_results: int) -> tuple:
    """Fetch training candidates using the Browse API (high rate limits)."""
    grade_str  = str(int(grade)) if grade == int(grade) else str(grade)
    full_query = f"{query.strip()} PSA {grade_str}"
    try:
        token = _get_browse_token()
    except Exception as exc:
        return [], f'Could not get Browse API token: {exc}'

    params = urllib.parse.urlencode({
        'q':     full_query,
        'limit': str(min(max_results, 50)),
        'sort':  'newlyListed',
    })
    url = f'{_BROWSE_API}?{params}'
    req = Request(url, headers={
        'Authorization':            f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    })

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        err_body = ''
        try:
            err_body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        return [], f'Browse API error {exc.code}: {err_body[:200]}'
    except Exception as exc:
        return [], f'Browse API request failed: {exc}'

    items = data.get('itemSummaries', [])
    if not items:
        return [], None

    candidates = []
    for item in items:
        try:
            title       = item.get('title', '')
            listing_url = item.get('itemWebUrl', '')
            image_url   = item.get('image', {}).get('imageUrl', '')
            # Upgrade thumbnail to full size (s-l225 or s-l140 → s-l1600)
            for thumb_size in ('s-l140', 's-l225', 's-l300', 's-l500'):
                if thumb_size in image_url:
                    image_url = image_url.replace(thumb_size, 's-l1600')
                    break
            if not image_url:
                continue
            candidates.append({
                'title':       title,
                'image_url':   image_url,
                'grade':       grade,
                'listing_url': listing_url,
            })
        except Exception:
            continue
    return candidates, None


def _fetch_via_finding_api(query: str, grade: float, max_results: int) -> tuple:
    """Fetch training candidates using the Finding API (5K calls/day fallback)."""
    grade_str  = str(int(grade)) if grade == int(grade) else str(grade)
    full_query = f"{query.strip()} PSA {grade_str}"
    params = {
        'keywords':                       full_query,
        'itemFilter(0).name':             'SoldItemsOnly',
        'itemFilter(0).value':            'true',
        'outputSelector(0)':              'PictureURLSuperSize',
        'outputSelector(1)':              'PictureURLLarge',
        'sortOrder':                      'EndTimeSoonest',
        'paginationInput.entriesPerPage': str(min(max_results, 50)),
    }
    try:
        data = _call_finding_api('findCompletedItems', params)
    except (URLError, HTTPError) as exc:
        err_body = ''
        if hasattr(exc, 'read'):
            try:
                err_body = exc.read().decode('utf-8', errors='ignore')
            except Exception:
                pass
        if 'RateLimiter' in err_body or '10001' in err_body:
            return [], ('eBay Finding API rate limit reached (5K calls/day). '
                        'Add EBAY_CLIENT_SECRET to use the Browse API (5M calls/day) instead.')
        return [], f'eBay API request failed: {exc}'
    except Exception as exc:
        return [], f'Unexpected error: {exc}'

    search_result = data.get('findCompletedItemsResponse', [{}])[0].get('searchResult', [{}])[0]
    if int(search_result.get('@count', 0)) == 0:
        return [], None

    candidates = []
    for raw in search_result.get('item', []):
        try:
            title       = raw['title'][0]
            listing_url = raw['viewItemURL'][0]
            gallery_url = raw.get('galleryURL', [''])[0]
            if gallery_url and 's-l140' in gallery_url:
                gallery_url = gallery_url.replace('s-l140', 's-l1600')
            image_url = (
                raw.get('pictureURLSuperSize', [''])[0] or
                raw.get('pictureURLLarge',     [''])[0] or
                gallery_url
            )
            if not image_url:
                continue
            candidates.append({
                'title':       title,
                'image_url':   image_url,
                'grade':       grade,
                'listing_url': listing_url,
            })
        except (KeyError, IndexError):
            continue
    return candidates, None


def search_active_listings(query: str, max_results: int = 20) -> dict:
    """
    Search eBay ACTIVE listings for a card.
    Uses Browse API (5M calls/day) when EBAY_CLIENT_SECRET is set,
    falls back to Finding API (5K calls/day) otherwise.
    """
    if not query.strip():
        return {'success': False, 'query': query, 'items': [], 'error': 'Empty search query'}

    if _get_client_secret():
        return _active_via_browse_api(query, max_results)
    return _active_via_finding_api(query, max_results)


def _active_via_browse_api(query: str, max_results: int) -> dict:
    """Fetch active listings via Browse API (5M calls/day)."""
    try:
        token = _get_browse_token()
    except Exception as exc:
        return {'success': False, 'query': query, 'items': [], 'error': f'Browse API token error: {exc}'}

    params = urllib.parse.urlencode({
        'q':     query.strip(),
        'limit': str(min(max_results, 50)),
        'sort':  'price',
    })
    url = f'{_BROWSE_API}?{params}'
    req = Request(url, headers={
        'Authorization':            f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    })

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        return {'success': False, 'query': query, 'items': [], 'error': f'Browse API error {exc.code}: {body[:200]}'}
    except Exception as exc:
        return {'success': False, 'query': query, 'items': [], 'error': f'Browse API request failed: {exc}'}

    items = []
    for item in data.get('itemSummaries', []):
        try:
            price_info   = item.get('price', {})
            price        = float(price_info.get('value', 0))
            ship_options = item.get('shippingOptions', [])
            shipping     = 0.0
            if ship_options:
                s = ship_options[0].get('shippingCost', {})
                try:
                    shipping = float(s.get('value', 0))
                except (ValueError, TypeError):
                    pass
            items.append({
                'title':        item.get('title', ''),
                'price':        price,
                'shipping':     shipping,
                'total_cost':   round(price + shipping, 2),
                'currency':     price_info.get('currency', 'USD'),
                'url':          item.get('itemWebUrl', ''),
                'condition':    item.get('condition', 'Unknown'),
                'listing_type': item.get('buyingOptions', ['Unknown'])[0] if item.get('buyingOptions') else 'Unknown',
            })
        except Exception:
            continue
    return {'success': True, 'query': query, 'items': items, 'error': None}


def _active_via_finding_api(query: str, max_results: int) -> dict:
    """Fetch active listings via Finding API (5K calls/day fallback)."""
    params = {
        'keywords':                       query.strip(),
        'itemFilter(0).name':             'ListingType',
        'itemFilter(0).value(0)':         'AuctionWithBIN',
        'itemFilter(0).value(1)':         'FixedPrice',
        'itemFilter(0).value(2)':         'Auction',
        'sortOrder':                      'PricePlusShippingLowest',
        'paginationInput.entriesPerPage': str(min(max_results, 50)),
    }

    try:
        data = _call_finding_api('findItemsByKeywords', params)
    except ValueError as exc:
        return {'success': False, 'query': query, 'items': [], 'error': str(exc)}
    except (URLError, HTTPError, TimeoutError) as exc:
        return {'success': False, 'query': query, 'items': [], 'error': f'eBay API request failed: {exc}'}
    except Exception as exc:
        return {'success': False, 'query': query, 'items': [], 'error': f'Unexpected error: {exc}'}

    search_result = data.get('findItemsByKeywordsResponse', [{}])[0].get('searchResult', [{}])[0]
    if int(search_result.get('@count', 0)) == 0:
        return {'success': True, 'query': query, 'items': [], 'error': None}

    items = []
    for raw in search_result.get('item', []):
        try:
            price  = float(raw['sellingStatus'][0]['convertedCurrentPrice'][0]['__value__'])
            curr   = raw['sellingStatus'][0]['convertedCurrentPrice'][0].get('@currencyId', 'USD')
            title  = raw['title'][0]
            url    = raw['viewItemURL'][0]
            cond   = raw.get('condition', [{}])[0].get('conditionDisplayName', ['Unknown'])[0]
            ltype  = raw.get('listingInfo', [{}])[0].get('listingType', ['Unknown'])[0]
            shipping_cost = 0.0
            ship_cost_list = raw.get('shippingInfo', [{}])[0].get('shippingServiceCost', [])
            if ship_cost_list:
                try:
                    shipping_cost = float(ship_cost_list[0].get('__value__', 0))
                except (ValueError, TypeError):
                    pass
            items.append({
                'title':        title,
                'price':        price,
                'shipping':     shipping_cost,
                'total_cost':   round(price + shipping_cost, 2),
                'currency':     curr,
                'url':          url,
                'condition':    cond,
                'listing_type': ltype,
            })
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return {'success': True, 'query': query, 'items': items, 'error': None}


def _fetch_graded_comps_bulk(query: str, grades: list) -> dict:
    """
    Fetch graded sold comps for multiple PSA grades with a SINGLE API call.
    Searches "PSA {query}" with max results, parses grade from each title,
    and buckets into per-grade stats.

    Returns {grade_int: stats_dict | None, ...}  e.g. {7: {...}, 8: {...}, 9: {...}, 10: {...}}
    """
    cache_key = f'ebay:bulk_graded:{query.lower().strip()}'
    cached = _cache_get(cache_key)
    if cached:
        return cached

    full_query = f'PSA {query.strip()}'
    params = {
        'keywords':                       full_query,
        'itemFilter(0).name':             'SoldItemsOnly',
        'itemFilter(0).value':            'true',
        'sortOrder':                      'EndTimeSoonest',
        'paginationInput.entriesPerPage': '50',
    }

    try:
        data = _call_finding_api('findCompletedItems', params)
        _check_finding_error(data, 'findCompletedItems')
    except Exception as exc:
        empty = {int(g): None for g in grades}
        empty['_error'] = str(exc)
        return empty

    items = _parse_finding_response(data, 'findCompletedItems')

    # Bucket prices by grade
    buckets = {int(g): [] for g in grades}
    for item in items:
        grade = _parse_psa_grade_from_title(item['title'])
        if grade is not None:
            key = int(grade) if grade == int(grade) else grade
            if key in buckets:
                buckets[key].append(item['price'])

    result = {g: _compute_stats(prices) for g, prices in buckets.items()}
    _cache_set(cache_key, result)
    return result


def find_deals(
    query: str,
    psa_grade_estimate: float = None,
    max_listings: int = 20,
    grading_cost: float = 25.0,
    ebay_fee_pct: float = 0.1325,
) -> dict:
    """
    Find good buy opportunities on eBay by comparing active listings to sold comps.

    For each active listing, calculates:
      - Raw flip profit: sell it as-is minus eBay fees
      - Graded profit: sell after PSA grading at various grade levels
      - ROI % and a deal verdict (BUY / WATCH / PASS)

    Args:
        query:              Search term (e.g. "2021 Topps Mike Trout #27")
        psa_grade_estimate: If you have a grade prediction, focus that grade; otherwise checks PSA 7-10
        max_listings:       How many active listings to analyze (max 50)
        grading_cost:       PSA grading cost per card in USD (default $25 = economy tier)
        ebay_fee_pct:       eBay final value fee + payment processing (default 13.25%)

    Returns:
        {
            success: bool,
            query: str,
            deals: list[deal_dict],
            sold_comps: { raw, psa7, psa8, psa9, psa10 },
            grading_cost: float,
            ebay_fee_pct: float,
            error: str | None
        }
    """
    if not query.strip():
        return {'success': False, 'query': query, 'deals': [], 'sold_comps': {}, 'error': 'Empty search query'}

    # ---- Fetch active listings ----
    active = search_active_listings(query, max_results=max_listings)
    if not active['success']:
        return {'success': False, 'query': query, 'deals': [], 'sold_comps': {}, 'error': active['error']}
    if not active['items']:
        return {'success': True, 'query': query, 'deals': [], 'sold_comps': {}, 'error': 'No active listings found'}

    grade_levels = [7, 8, 9, 10] if psa_grade_estimate is None else [int(psa_grade_estimate)]
    sold_comps = {}
    sold_comps_error = None

    if _get_ch_key():
        # ---- Card Hedge path: 2 calls, all grades, best quality ----
        ch_cache_key = f'ch:bulk_graded:{query.lower().strip()}'
        cached = _cache_get(ch_cache_key)
        if cached:
            sold_comps = cached
        else:
            ch = _search_card_hedge(query)
            if ch['success']:
                sold_comps['raw'] = ch['loose_stats']
                for g in grade_levels:
                    gk = int(g) if float(g) == int(g) else float(g)
                    sold_comps[f'psa{int(g)}'] = ch['grade_stats'].get(gk)
            else:
                sold_comps_error = ch.get('error')
                sold_comps['raw'] = None
                for g in grade_levels:
                    sold_comps[f'psa{int(g)}'] = None
            _cache_set(ch_cache_key, sold_comps)
    elif _get_scp_key():
        # ---- SCP path: 1 call returns all grades at once ----
        scp_cache_key = f'scp:bulk_graded:{query.lower().strip()}'
        cached = _cache_get(scp_cache_key)
        if cached:
            sold_comps = cached
        else:
            scp = _search_sportscardspro(query)
            if scp['success']:
                sold_comps['raw'] = scp['loose_stats']
                for g in grade_levels:
                    gk = int(g) if float(g) == int(g) else float(g)
                    sold_comps[f'psa{int(g)}'] = scp['grade_stats'].get(gk)
            else:
                sold_comps_error = scp.get('error')
                sold_comps['raw'] = None
                for g in grade_levels:
                    sold_comps[f'psa{int(g)}'] = None
            _cache_set(scp_cache_key, sold_comps)
    else:
        # ---- eBay fallback: 2 Finding API calls, both cached 6 hrs ----
        raw_result = search_sold_listings(query, max_results=20)
        sold_comps['raw'] = raw_result.get('stats')
        sold_comps_error = raw_result.get('error')

        graded_bulk = _fetch_graded_comps_bulk(query, grade_levels)
        if graded_bulk.get('_error') and not sold_comps_error:
            sold_comps_error = graded_bulk['_error']
        for g in grade_levels:
            sold_comps[f'psa{int(g)}'] = graded_bulk.get(int(g))

    raw_median = sold_comps['raw']['median'] if sold_comps.get('raw') else None

    # Build a map of grade → median sold price
    grade_medians = {}
    for g in grade_levels:
        key = f'psa{int(g)}'
        if sold_comps.get(key) and sold_comps[key].get('median'):
            grade_medians[int(g)] = sold_comps[key]['median']

    # ---- Score each active listing ----
    deals = []
    for item in active['items']:
        cost = item['total_cost']  # price + shipping

        # Raw flip profit
        raw_profit = None
        raw_roi = None
        if raw_median:
            raw_sell = raw_median * (1 - ebay_fee_pct)
            raw_profit = round(raw_sell - cost, 2)
            raw_roi = round((raw_profit / cost) * 100, 1) if cost > 0 else 0

        # Graded profit — find best grade scenario
        best_grade_profit = None
        best_grade = None
        best_grade_sell_price = None
        grade_breakdown = {}
        for g, median in grade_medians.items():
            sell_net = median * (1 - ebay_fee_pct)
            profit = round(sell_net - cost - grading_cost, 2)
            roi = round((profit / (cost + grading_cost)) * 100, 1) if (cost + grading_cost) > 0 else 0
            grade_breakdown[f'psa{int(g)}'] = {
                'sold_median': median,
                'profit': profit,
                'roi_pct': roi,
            }
            if best_grade_profit is None or profit > best_grade_profit:
                best_grade_profit = profit
                best_grade = g
                best_grade_sell_price = median

        # Determine verdict
        best_profit = max(
            raw_profit if raw_profit is not None else float('-inf'),
            best_grade_profit if best_grade_profit is not None else float('-inf'),
        )
        if best_profit == float('-inf'):
            verdict = 'UNKNOWN'
        elif best_profit >= 15 and (raw_roi or 0) >= 20:
            verdict = 'BUY'
        elif best_profit >= 5:
            verdict = 'WATCH'
        else:
            verdict = 'PASS'

        deals.append({
            'title':             item['title'],
            'listing_price':     item['price'],
            'shipping':          item['shipping'],
            'total_cost':        cost,
            'url':               item['url'],
            'condition':         item['condition'],
            'listing_type':      item['listing_type'],
            'raw_median_sold':   raw_median,
            'raw_profit':        raw_profit,
            'raw_roi_pct':       raw_roi,
            'best_grade':        best_grade,
            'best_grade_profit': best_grade_profit,
            'best_grade_sell':   best_grade_sell_price,
            'grade_breakdown':   grade_breakdown,
            'verdict':           verdict,
        })

    # Sort: BUY first, then by raw_profit descending
    verdict_order = {'BUY': 0, 'WATCH': 1, 'UNKNOWN': 2, 'PASS': 3}
    deals.sort(key=lambda d: (verdict_order.get(d['verdict'], 4), -(d['raw_profit'] or float('-inf'))))

    return {
        'success':           True,
        'query':             query,
        'deals':             deals,
        'sold_comps':        sold_comps,
        'sold_comps_error':  sold_comps_error,
        'grading_cost':      grading_cost,
        'ebay_fee_pct':      ebay_fee_pct,
        'error':             None,
    }


def get_comps(search_query: str, predicted_grade=None) -> dict:
    """
    Fetch both graded and raw (ungraded) comps for a card.
    Priority: Card Hedge AI → SportsCardsPro → eBay Finding API.

    Returns:
        {
            graded_comps:    search result dict (stats + items),
            raw_comps:       search result dict (stats + items),
            ebay_configured: bool,
            scp_configured:  bool,
            ch_configured:   bool,
        }
    """
    ch_configured   = bool(_get_ch_key())
    scp_configured  = bool(_get_scp_key())
    ebay_configured = bool(_get_app_id())

    if ch_configured and search_query:
        grade_str = str(int(predicted_grade)) if predicted_grade is not None else 'none'
        cache_key = f'ch:comps:{search_query.lower().strip()}:{grade_str}'
        cached = _cache_get(cache_key)
        if cached:
            return cached

        ch = _search_card_hedge(search_query)
        if ch['success']:
            graded_stats = None
            if predicted_grade is not None:
                gk = int(predicted_grade) if float(predicted_grade) == int(predicted_grade) else float(predicted_grade)
                graded_stats = ch['grade_stats'].get(gk)
            graded_comps = {
                'success': True,
                'query':   f'{search_query} PSA {predicted_grade}' if predicted_grade else search_query,
                'items':   ch['raw_items'],
                'stats':   graded_stats,
                'error':   None,
                'source':  'cardhedge',
            }
            raw_comps = {
                'success': True,
                'query':   search_query,
                'items':   [],
                'stats':   ch['loose_stats'],
                'error':   None,
                'source':  'cardhedge',
            }
        else:
            err = ch.get('error', 'Card Hedge lookup failed')
            graded_comps = {'success': False, 'query': search_query, 'items': [], 'stats': None, 'error': err}
            raw_comps    = {'success': False, 'query': search_query, 'items': [], 'stats': None, 'error': err}

        result = {
            'graded_comps':    graded_comps,
            'raw_comps':       raw_comps,
            'ebay_configured': ebay_configured,
            'scp_configured':  scp_configured,
            'ch_configured':   True,
        }
        _cache_set(cache_key, result)
        return result

    if scp_configured and search_query:
        grade_str = str(int(predicted_grade)) if predicted_grade is not None else 'none'
        cache_key = f'scp:comps:{search_query.lower().strip()}:{grade_str}'
        cached = _cache_get(cache_key)
        if cached:
            return cached

        scp = _search_sportscardspro(search_query)
        if scp['success']:
            graded_stats = None
            if predicted_grade is not None:
                gk = int(predicted_grade) if float(predicted_grade) == int(predicted_grade) else float(predicted_grade)
                graded_stats = scp['grade_stats'].get(gk)
            graded_comps = {
                'success': True,
                'query':   f'{search_query} PSA {predicted_grade}' if predicted_grade else search_query,
                'items':   [],
                'stats':   graded_stats,
                'error':   None,
                'source':  'sportscardspro',
            }
            raw_comps = {
                'success': True,
                'query':   search_query,
                'items':   [],
                'stats':   scp['loose_stats'],
                'error':   None,
                'source':  'sportscardspro',
            }
        else:
            err = scp.get('error', 'SportsCardsPro lookup failed')
            graded_comps = {'success': False, 'query': search_query, 'items': [], 'stats': None, 'error': err}
            raw_comps    = {'success': False, 'query': search_query, 'items': [], 'stats': None, 'error': err}

        result = {
            'graded_comps':    graded_comps,
            'raw_comps':       raw_comps,
            'ebay_configured': ebay_configured,
            'scp_configured':  True,
            'ch_configured':   ch_configured,
        }
        _cache_set(cache_key, result)
        return result

    # ---- eBay fallback ----
    graded = None
    if predicted_grade is not None and search_query:
        graded = search_sold_listings(search_query, psa_grade=predicted_grade)

    raw = search_sold_listings(search_query) if search_query else {
        'success': False, 'query': search_query,
        'items': [], 'stats': None, 'error': 'No search query',
    }

    return {
        'graded_comps':    graded,
        'raw_comps':       raw,
        'ebay_configured': ebay_configured,
        'scp_configured':  False,
        'ch_configured':   False,
    }
