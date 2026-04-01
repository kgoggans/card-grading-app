"""
Auction House Fetcher — Fanatics Collect (PWCC), Goldin, Heritage Auctions

All three sites use DataDome + Cloudflare, so Firecrawl is required.
Firecrawl spins up a real headless Chrome that bypasses bot protection.

How it works (2-step):
  1. Scrape the search results page  → collect listing page URLs + titles
  2. Scrape each individual listing  → extract front + back image URLs

Credit cost: ~1 credit/page.  Free tier = 500 credits/month.
Typical run (3 grades × 10 listings each) ≈ 33 credits.

Setup:
    Add to .env:  FIRECRAWL_API_KEY=fc-xxxxxxxx
    (Sign up free at https://firecrawl.dev)
"""

import os
import re
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)
_BASE_HEADERS = {
    'User-Agent': _UA,
    'Accept': 'application/json, text/html, */*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

_FIRECRAWL_SCRAPE = 'https://api.firecrawl.dev/v1/scrape'
_FIRECRAWL_BATCH  = 'https://api.firecrawl.dev/v1/batch/scrape'


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _grade_str(grade):
    return str(int(grade)) if grade == int(grade) else str(grade)


def _get_firecrawl_key():
    return os.environ.get('FIRECRAWL_API_KEY', '').strip()


def firecrawl_available():
    return bool(_get_firecrawl_key())


def _http(url, method='GET', payload=None, extra_headers=None, timeout=45):
    headers = dict(_BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if payload:
        headers['Content-Type'] = 'application/json'
    try:
        body = json.dumps(payload).encode() if payload else None
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='replace'), None
    except HTTPError as e:
        return None, f'HTTP {e.code}: {e.reason}'
    except URLError as e:
        return None, f'URL error: {e.reason}'
    except Exception as e:
        return None, str(e)


def _firecrawl_scrape_with_actions(url):
    """Scrape with scroll actions to trigger lazy-loaded images (e.g. Goldin)."""
    key = _get_firecrawl_key()
    if not key:
        return None, 'No FIRECRAWL_API_KEY'
    payload = {
        'url': url,
        'formats': ['markdown'],
        'onlyMainContent': False,
        'timeout': 60000,
        'actions': [
            {'type': 'wait', 'milliseconds': 5000},
            {'type': 'scroll', 'direction': 'down', 'amount': 600},
            {'type': 'wait', 'milliseconds': 3000},
            {'type': 'scroll', 'direction': 'down', 'amount': 600},
            {'type': 'wait', 'milliseconds': 2000},
        ]
    }
    text, err = _http(_FIRECRAWL_SCRAPE, 'POST', payload,
                      {'Authorization': f'Bearer {key}'}, timeout=90)
    if not text:
        return None, err
    try:
        data = json.loads(text)
        md = (data.get('data') or {}).get('markdown') or ''
        return md or None, None if md else 'Empty response'
    except Exception as e:
        return None, str(e)


def _firecrawl_scrape(url, wait_ms=4000):
    """Single-page scrape via Firecrawl. Returns (markdown, error)."""
    key = _get_firecrawl_key()
    if not key:
        return None, 'No FIRECRAWL_API_KEY'
    payload = {
        'url': url,
        'formats': ['markdown'],
        'onlyMainContent': False,
        'timeout': 50000,
        'waitFor': wait_ms,
    }
    text, err = _http(_FIRECRAWL_SCRAPE, 'POST', payload,
                      {'Authorization': f'Bearer {key}'}, timeout=70)
    if not text:
        return None, err
    try:
        data = json.loads(text)
        md = (data.get('data') or {}).get('markdown') or data.get('markdown') or ''
        return md or None, None if md else 'Empty response from Firecrawl'
    except Exception as e:
        return None, str(e)


def _firecrawl_batch(urls, wait_ms=4000):
    """
    Batch-scrape multiple URLs via Firecrawl.
    Returns list of markdown strings (same order as input, '' on failure).
    """
    key = _get_firecrawl_key()
    if not key or not urls:
        return [''] * len(urls)

    payload = {
        'urls': urls,
        'formats': ['markdown'],
        'onlyMainContent': False,
        'waitFor': wait_ms,
    }
    # Start the batch job
    text, err = _http(_FIRECRAWL_BATCH, 'POST', payload,
                      {'Authorization': f'Bearer {key}'}, timeout=30)
    if not text:
        return [''] * len(urls)
    try:
        data = json.loads(text)
        job_id = data.get('id') or data.get('jobId')
        if not job_id:
            return [''] * len(urls)
    except Exception:
        return [''] * len(urls)

    # Poll until done
    status_url = f'https://api.firecrawl.dev/v1/batch/scrape/{job_id}'
    for _ in range(60):          # up to 60 × 3s = 3 min
        time.sleep(3)
        t, e = _http(status_url, extra_headers={'Authorization': f'Bearer {key}'}, timeout=15)
        if not t:
            continue
        try:
            s = json.loads(t)
            if s.get('status') in ('completed', 'failed', 'partial'):
                results = s.get('data') or []
                out = []
                for item in results:
                    md = (item or {}).get('markdown') or ''
                    out.append(md)
                # Pad in case fewer results than URLs
                while len(out) < len(urls):
                    out.append('')
                return out
        except Exception:
            continue

    return [''] * len(urls)


def _extract_md_images(md):
    """Return list of image URLs from markdown `![...](url)` syntax."""
    return re.findall(r'!\[[^\]]*\]\((https://[^\)]+)\)', md)


def _upgrade_res(url):
    if not url:
        return url
    url = re.sub(r'/upload/[^/]*w_\d+[^/]*/', '/upload/w_1600,q_auto/', url)
    for s in ('s-l140', 's-l225', 's-l300', 's-l400', 's-l500', 's-l640'):
        url = url.replace(s, 's-l1600')
    return url


def _psa_grade_in_title(title, grade):
    """Return True if title mentions PSA {grade} (not BGS/CGC/etc.)."""
    grade_s = _grade_str(grade)
    title_up = title.upper()
    # Must have PSA and the grade, not just another grader
    return bool(re.search(rf'PSA\s+{re.escape(grade_s)}\b', title_up))


# ---------------------------------------------------------------------------
# Fanatics Collect (fanaticscollect.com)  — formerly PWCC
# ---------------------------------------------------------------------------

def fetch_fanatics_candidates(query, grade, max_results=30):
    """
    Two-step fetch:
      1. Scrape search results page → collect listing URLs that are PSA {grade}
      2. Batch-scrape each listing page → extract front + back thumbnails
    """
    if not firecrawl_available():
        return [], 'No FIRECRAWL_API_KEY — sign up free at firecrawl.dev'

    grade_s = _grade_str(grade)
    search_q = f'PSA {grade_s} {query}'
    params = urlencode({'query': search_q})
    search_url = f'https://www.fanaticscollect.com/marketplace?{params}'

    # Step 1: search page
    md, err = _firecrawl_scrape(search_url, wait_ms=6000)
    if not md:
        return [], f'Fanatics Collect search failed: {err}'

    # Extract listing URLs and titles from markdown
    # Pattern: [Title](https://www.fanaticscollect.com/weekly/... or /fixed/...)
    link_pattern = re.findall(
        r'\[([^\]]+)\]\((https://www\.fanaticscollect\.com/(?:weekly|fixed|item)/[^\)]+)\)',
        md
    )
    # Filter to PSA {grade} listings
    matching = [(title, url) for title, url in link_pattern
                if _psa_grade_in_title(title, grade)]

    if not matching:
        # Fallback: take all listing URLs and filter later
        matching = [(title, url) for title, url in link_pattern
                    if 'fanaticscollect.com' in url]

    if not matching:
        return [], f'No PSA {grade_s} listings found on Fanatics Collect'

    matching = matching[:max_results]

    # Step 2: batch scrape listing pages
    listing_urls = [url for _, url in matching]
    mds = _firecrawl_batch(listing_urls, wait_ms=4000)

    candidates = []
    for (title, _url), listing_md in zip(matching, mds):
        if not listing_md:
            continue
        imgs = _extract_md_images(listing_md)
        # Filter out logos (small, named 'logo', or from known logo CDNs)
        imgs = [u for u in imgs if 'logo' not in u.lower() and
                's3-us-west-2.amazonaws.com/pwccauctions/website' not in u]
        if not imgs:
            continue
        front_url = _upgrade_res(imgs[0])
        back_url  = _upgrade_res(imgs[1]) if len(imgs) > 1 else ''
        candidates.append({
            'front_url': front_url,
            'back_url':  back_url,
            'title':     title[:120],
            'grade':     grade,
            'source':    'FanaticsCollect',
        })

    if candidates:
        return candidates, None
    return [], 'No card images extracted from Fanatics Collect listings'


# ---------------------------------------------------------------------------
# Goldin Auctions  (goldin.co)
# ---------------------------------------------------------------------------

def fetch_goldin_candidates(query, grade, max_results=30):
    if not firecrawl_available():
        return [], 'No FIRECRAWL_API_KEY'

    grade_s = _grade_str(grade)
    search_q = f'PSA {grade_s} {query}'
    params = urlencode({'search': search_q})
    search_url = f'https://goldin.co/buy?{params}'

    md, err = _firecrawl_scrape(search_url, wait_ms=8000)
    if not md:
        return [], f'Goldin search failed: {err}'

    all_links = re.findall(
        r'\[([^\]]{8,120})\]\((https://goldin\.co/item/[^\)#?]+)\)',
        md
    )
    seen_urls = set()
    unique_links = []
    for title, url in all_links:
        clean_title = re.sub(r'\*+|\\+', ' ', title).strip()
        clean_title = re.sub(r'\s+', ' ', clean_title)
        if url not in seen_urls and clean_title not in ('Bid Now', 'View', ''):
            seen_urls.add(url)
            unique_links.append((clean_title, url))

    matching = [(t, u) for t, u in unique_links if _psa_grade_in_title(t, grade)]
    if not matching:
        matching = unique_links
    if not matching:
        return [], f'No listings found on Goldin for "{search_q}"'

    matching = matching[:max_results]
    candidates = []
    for title, listing_url in matching:
        # Goldin lazy-loads images — use longer wait + scroll actions
        listing_md, _ = _firecrawl_scrape_with_actions(listing_url)
        if not listing_md:
            continue
        imgs = _extract_md_images(listing_md)
        real_imgs = [u for u in imgs if
                     'no_logo' not in u and
                     not any(x in u.lower() for x in ('logo', 'icon', 'footer', 'banner', 'consign'))]
        if not real_imgs:
            continue
        candidates.append({
            'front_url': _upgrade_res(real_imgs[0]),
            'back_url':  _upgrade_res(real_imgs[1]) if len(real_imgs) > 1 else '',
            'title':     title[:120],
            'grade':     grade,
            'source':    'Goldin',
        })

    if candidates:
        return candidates, None
    return [], 'No card images extracted from Goldin listings (lazy-load may still be blocking)'


# ---------------------------------------------------------------------------
# Heritage Auctions  (ha.com)
# ---------------------------------------------------------------------------

def fetch_heritage_candidates(query, grade, max_results=30):
    if not firecrawl_available():
        return [], 'No FIRECRAWL_API_KEY'

    grade_s = _grade_str(grade)
    search_q = f'PSA {grade_s} {query}'
    # Sports cards live on sports.ha.com, not www.ha.com
    params = urlencode({'searchTerm': search_q, 'Nrpp': min(max_results * 3, 48)})
    search_url = f'https://sports.ha.com/c/search-results.zx?{params}'

    md, err = _firecrawl_scrape(search_url, wait_ms=6000)
    if not md:
        return [], f'Heritage search failed: {err}'

    # Heritage item links: sports.ha.com/itm/category/subcategory/title/a/SALE-LOT.s
    all_links = re.findall(
        r'\[([^\]]{8,120})\]\((https://sports\.ha\.com/itm/[^\)#]+)\)',
        md
    )
    # Deduplicate by URL, skip "Bid Now" / nav labels; clean markdown bold
    seen_urls = set()
    unique_links = []
    for title, url in all_links:
        clean_title = re.sub(r'\*+', '', title).replace('\\', ' ').strip()
        clean_title = re.sub(r'\s+', ' ', clean_title)
        if url not in seen_urls and clean_title not in ('Bid Now', 'View', 'Details', ''):
            seen_urls.add(url)
            unique_links.append((clean_title, url))

    matching = [(t, u) for t, u in unique_links if _psa_grade_in_title(t, grade)]
    if not matching:
        matching = unique_links  # fall back to all items if grade not in titles
    if not matching:
        return [], f'No listings found on Heritage for "{search_q}"'

    matching = matching[:max_results]

    candidates = []
    for title, listing_url in matching:
        # Scrape each Heritage listing individually — batch scrape returns
        # duplicate cached responses across Heritage pages
        listing_md, _ = _firecrawl_scrape(listing_url, wait_ms=4000)
        if not listing_md:
            continue
        # Heritage images: dyn1.heritagestatic.com/ha?p=...&it=product
        # Extract all image URLs from markdown then filter to product images
        all_imgs = _extract_md_images(listing_md)
        product_imgs = [u for u in all_imgs
                        if 'heritagestatic.com' in u and 'it=product' in u]
        if not product_imgs:
            # fall back to any non-logo image
            product_imgs = [u for u in all_imgs
                            if not any(x in u.lower() for x in
                                       ('logo', 'icon', 'employee', 'sprite', 'nav'))]
        if not product_imgs:
            continue

        # Upgrade to high-res: replace w=120&h=300 with w=1200&h=1600
        def _heritage_hires(url):
            url = re.sub(r'&w=\d+', '&w=1200', url)
            url = re.sub(r'&h=\d+', '&h=1600', url)
            return url

        # Deduplicate images within this listing
        seen_imgs = set()
        unique_imgs = []
        for u in product_imgs:
            key = re.search(r'p=([^&]+)', u)
            key = key.group(1) if key else u
            if key not in seen_imgs:
                seen_imgs.add(key)
                unique_imgs.append(u)

        front_url = _heritage_hires(unique_imgs[0])
        back_url  = _heritage_hires(unique_imgs[1]) if len(unique_imgs) > 1 else ''
        candidates.append({
            'front_url': front_url,
            'back_url':  back_url,
            'title':     title[:120],
            'grade':     grade,
            'source':    'Heritage',
        })

    if candidates:
        return candidates, None
    return [], 'No card images extracted from Heritage listings'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_FETCHERS = {
    'pwcc':     fetch_fanatics_candidates,
    'fanatics': fetch_fanatics_candidates,
    'goldin':   fetch_goldin_candidates,
    'heritage': fetch_heritage_candidates,
}


def fetch_auction_candidates(query, grade, max_results=30, sources=None):
    """
    Fetch from auction houses via Firecrawl.

    Args:
        query:       Card description, e.g. 'Michael Jordan Fleer 1986'
        grade:       PSA grade float
        max_results: Max total candidates
        sources:     ['pwcc', 'goldin', 'heritage'] (default: all)

    Returns:
        (candidates_list, errors_list)
    """
    if sources is None:
        sources = ['pwcc', 'goldin', 'heritage']

    if not firecrawl_available():
        return [], [
            'Firecrawl API key required. '
            'Sign up at https://firecrawl.dev (free: 500 scrapes/month) '
            'then add FIRECRAWL_API_KEY=fc-... to your .env file and restart.'
        ]

    unique = list(dict.fromkeys(s.lower() for s in sources if s.lower() in _FETCHERS))
    if not unique:
        return [], ['No valid sources specified']

    all_candidates, errors = [], []
    per_source = max(1, max_results // len(unique))

    for source in unique:
        remaining = max_results - len(all_candidates)
        if remaining <= 0:
            break
        cands, err = _FETCHERS[source](query, grade, min(per_source, remaining))
        all_candidates.extend(cands)
        if err and not cands:
            errors.append(f'{source.capitalize()}: {err}')

    return all_candidates[:max_results], errors
