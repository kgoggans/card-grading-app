"""
Market Comparables via eBay APIs

- Price comps: eBay Finding API (findCompletedItems) — requires EBAY_APP_ID
- Training image fetch: eBay Browse API — requires EBAY_APP_ID + EBAY_CLIENT_SECRET
  Browse API has 5M calls/day vs 5K for Finding API.

Get credentials at: https://developer.ebay.com/
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


_FINDING_API = 'https://svcs.ebay.com/services/search/FindingService/v1'
_BROWSE_API   = 'https://api.ebay.com/buy/browse/v1/item_summary/search'
_OAUTH_URL    = 'https://api.ebay.com/identity/v1/oauth2/token'

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

    cache_key = f'sold:{full_query.lower()}:{max_results}'
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
    cache_key = f'bulk_graded:{query.lower().strip()}'
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

    # ---- Fetch sold comps: 2 API calls total (was 5), both cached 6 hrs ----
    # Call 1: raw (ungraded) sold comps
    # Call 2: one broad "PSA {card}" query, bucket results by grade from title
    grade_levels = [7, 8, 9, 10] if psa_grade_estimate is None else [int(psa_grade_estimate)]
    sold_comps = {}

    raw_result = search_sold_listings(query, max_results=20)
    sold_comps['raw'] = raw_result.get('stats')
    sold_comps_error = raw_result.get('error')  # captures rate limit / API errors

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

    Returns:
        {
            graded_comps: search result dict (with PSA grade appended),
            raw_comps:    search result dict (without grade),
            ebay_configured: bool
        }
    """
    configured = bool(_get_app_id())

    graded = None
    if predicted_grade is not None and search_query:
        graded = search_sold_listings(search_query, psa_grade=predicted_grade)

    raw = search_sold_listings(search_query) if search_query else {
        'success': False, 'query': search_query,
        'items': [], 'stats': None, 'error': 'No search query'
    }

    return {
        'graded_comps':    graded,
        'raw_comps':       raw,
        'ebay_configured': configured,
    }
