"""
Flask Web Application for Card Grading

This app allows users to upload front and back images of sports cards
and receive AI-powered PSA grade estimates.
"""

import functools
import ipaddress
import socket
import time
import os

# Load credentials from .env file so no manual exports are needed
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                k, v = key.strip(), val.strip()
                if v:  # always apply non-empty values from .env
                    os.environ[k] = v
                else:
                    os.environ.setdefault(k, v)

_load_dotenv()

from flask import Flask, render_template, request, jsonify, url_for
from werkzeug.utils import secure_filename
import json
import secrets
import csv
import numpy as np
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import re
import cv2
import easyocr

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _LIMITER_AVAILABLE = True
except ImportError:
    _LIMITER_AVAILABLE = False

from grading_system import CardGrader
from image_analysis import analyze_card_images
from ml_model import get_model, reload_model
from card_identifier import identify_card
from comps import get_comps, find_deals

# ---------------------------------------------------------------------------
# Lazy OCR reader (initialized on first use to avoid startup delay)
# ---------------------------------------------------------------------------
_ocr_reader = None

def get_ocr_reader():
    """Return a cached EasyOCR reader (English, CPU-only)."""
    global _ocr_reader
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _ocr_reader


# PSA grade descriptor → numeric grade mapping
_PSA_DESCRIPTORS = {
    'GEM-MT': 10, 'GEM MT': 10, 'GEMMT': 10,
    'MINT': 9,
    'NM-MT': 8,  'NM MT': 8,  'NMMT': 8,
    'NM':    7,
    'EX-MT': 6,  'EX MT': 6,  'EXMT': 6,
    'EX':    5,
    'VG-EX': 4,  'VG EX': 4,  'VGEX': 4,
    'VG':    3,
    'GOOD':  2,
    'POOR':  1,
}

_VALID_PSA_GRADES = {1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5,
                    6, 6.5, 7, 7.5, 8, 8.5, 9, 10}


def _preprocess_variants(region):
    """
    Return a list of preprocessed numpy arrays for a given BGR region.
    Multiple variants help OCR succeed under different lighting/contrast conditions.
    """
    import numpy as np
    variants = [region]  # always try original colour

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    variants.append(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))

    # CLAHE – boosts local contrast (great for low-contrast labels)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    clahe_gray = clahe.apply(gray)
    variants.append(cv2.cvtColor(clahe_gray, cv2.COLOR_GRAY2BGR))

    # Otsu threshold – works when text is dark on white/light background
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR))

    # Inverted Otsu – works when text is light on dark background (some PSA labels)
    variants.append(cv2.cvtColor(cv2.bitwise_not(otsu), cv2.COLOR_GRAY2BGR))

    # Sharpened
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(region, -1, kernel)
    variants.append(sharpened)

    return variants


def detect_psa_grade_from_image(image_path):
    """
    Use EasyOCR to detect the PSA numeric grade from a slab photo.
    Returns (grade_float_or_None, message_str).
    """
    img = cv2.imread(image_path)
    if img is None:
        return None, 'Could not load image'

    h, w = img.shape[:2]

    # PSA grade label is printed on the label at the TOP of the slab.
    # Try top-focused crops first, then progressively wider, then full image.
    crop_regions = [
        img[:h // 4, :],                 # top quarter  (PSA label area)
        img[:h // 3, :],                 # top third
        img[:h // 2, :],                 # top half
        img[h // 4: 3 * h // 4, :],     # middle half
        img[h // 2:, :],                 # bottom half  (upright holder photos)
        img,                             # full image   (last resort)
    ]

    reader = get_ocr_reader()
    best_grade = None
    best_conf = 0.0
    all_detections = []  # (text, conf)

    for region in crop_regions:
        rh, rw = region.shape[:2]
        if rh == 0 or rw == 0:
            continue

        # Upscale small regions so OCR is more accurate (target ≥600px on short side)
        scale = max(1.0, 600.0 / min(rh, rw))
        if scale > 1.0:
            region = cv2.resize(region, None, fx=scale, fy=scale,
                                interpolation=cv2.INTER_CUBIC)

        for variant in _preprocess_variants(region):
            try:
                results = reader.readtext(
                    variant,
                    detail=1,
                    paragraph=False,
                    min_size=5,
                    text_threshold=0.4,   # lower than default 0.7 → catch faint text
                    low_text=0.3,
                    link_threshold=0.3,
                )
            except Exception:
                continue

            for _bbox, text, conf in results:
                t = text.strip()
                if not t:
                    continue
                all_detections.append((t, conf))
                tu = t.upper()

                # 1. Descriptor match (e.g. "GEM-MT 10", "MINT", "NM-MT")
                for desc, grade in _PSA_DESCRIPTORS.items():
                    if desc in tu:
                        if conf > best_conf:
                            best_conf = conf
                            best_grade = float(grade)

                # 2. "PSA 9", "PSA10", "PSA-9" patterns
                m = re.search(r'PSA[\s\-]*(10|[1-9](?:\.5)?)', tu)
                if m:
                    try:
                        num = float(m.group(1))
                        if num in _VALID_PSA_GRADES and conf > best_conf:
                            best_conf = conf
                            best_grade = num
                    except ValueError:
                        pass

                # 3. Standalone number matching a valid grade (with or without surrounding noise)
                for m in re.finditer(r'(?<!\d)(10|[1-9](?:\.5)?)(?!\d)', tu):
                    try:
                        num = float(m.group(1))
                        if num in _VALID_PSA_GRADES and conf > best_conf:
                            best_conf = conf
                            best_grade = num
                    except ValueError:
                        pass

        # Early exit: clear high-confidence hit found in this crop region
        if best_grade is not None and best_conf >= 0.6:
            break

    if best_grade is not None:
        return best_grade, f'Detected PSA {best_grade} (confidence {best_conf:.0%})'

    # Last-resort: scan all detections sorted by confidence, look for any valid number
    for text, conf in sorted(all_detections, key=lambda x: -x[1]):
        tu = text.upper()
        for m in re.finditer(r'(?<!\d)(10|[1-9](?:\.5)?)(?!\d)', tu):
            try:
                num = float(m.group(1))
                if num in _VALID_PSA_GRADES:
                    return num, f'Extracted "{text}" → PSA {num} (confidence {conf:.0%})'
            except ValueError:
                pass

    # Include what was actually read to help the user understand why it failed
    seen = [t for t, _ in sorted(all_detections, key=lambda x: -x[1])[:8]]
    hint = f'OCR read: {seen}' if seen else 'No text detected'
    return None, f'Could not detect grade. {hint}. Try uploading just the label portion of the slab.'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['TRAINING_FOLDER'] = 'training_data'
app.config['TRAINING_IMAGES_FOLDER'] = os.path.join(app.config['TRAINING_FOLDER'], 'images')
app.config['TRAINING_METADATA_CSV'] = os.path.join(app.config['TRAINING_FOLDER'], 'labels.csv')

# ---------------------------------------------------------------------------
# Rate limiting (requires flask-limiter; degrades gracefully if not installed)
# ---------------------------------------------------------------------------
if _LIMITER_AVAILABLE:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["120 per minute"],
        storage_uri="memory://",
    )
else:
    limiter = None


def _rate_limit(limit_string):
    """Decorator that applies a rate limit only when flask-limiter is available."""
    def decorator(f):
        if limiter is not None:
            return limiter.limit(limit_string)(f)
        return f
    return decorator


# ---------------------------------------------------------------------------
# Admin-token auth for training / calibration routes
# ---------------------------------------------------------------------------
def require_admin(f):
    """
    Require X-Admin-Token header or admin_token form field to match ADMIN_TOKEN env var.
    If ADMIN_TOKEN is not set, all requests are allowed (development mode).
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        expected = os.environ.get('ADMIN_TOKEN', '').strip()
        if expected:
            provided = (
                request.headers.get('X-Admin-Token', '') or
                request.form.get('admin_token', '')
            ).strip()
            if not secrets.compare_digest(provided, expected):
                return jsonify({'error': 'Unauthorized. Provide a valid X-Admin-Token header.'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------
def _is_safe_host(hostname: str) -> bool:
    """Return True only if the resolved IP is a public, routable address."""
    try:
        addr = ipaddress.ip_address(socket.gethostbyname(hostname))
        return not (
            addr.is_private or
            addr.is_loopback or
            addr.is_link_local or
            addr.is_multicast or
            addr.is_reserved or
            addr.is_unspecified
        )
    except Exception:
        return False  # block anything we can't resolve


def round_float(value, digits=2):
    """Safely round numeric values for JSON debug output."""
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TRAINING_IMAGES_FOLDER'], exist_ok=True)


def ensure_training_csv():
    """Create training metadata CSV with headers if missing."""
    if os.path.exists(app.config['TRAINING_METADATA_CSV']):
        return
    with open(app.config['TRAINING_METADATA_CSV'], 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            'sample_id',
            'created_at',
            'psa_grade',
            'card_title',
            'notes',
            'front_image',
            'back_image'
        ])


def parse_grade(grade_text):
    """Validate and parse PSA grade input — must be an exact valid PSA grade."""
    try:
        grade_value = float(grade_text)
    except (TypeError, ValueError):
        return None
    if grade_value not in _VALID_PSA_GRADES:
        return None
    return grade_value


def read_training_rows():
    """Read all training rows from CSV."""
    ensure_training_csv()
    with open(app.config['TRAINING_METADATA_CSV'], 'r', newline='') as csv_file:
        return list(csv.DictReader(csv_file))


def summarize_training_dataset(rows):
    """Build basic dataset counts by grade."""
    by_grade = {}
    for row in rows:
        grade = row.get('psa_grade', 'unknown')
        by_grade[grade] = by_grade.get(grade, 0) + 1
    return {
        'total_samples': len(rows),
        'by_grade': by_grade
    }


# ---------------------------------------------------------------------------
# PSA grade number → ideal target score on the 100-1000 scale
# (midpoint of each grade band per PSAGradingCriteria.GRADE_RANGES)
# ---------------------------------------------------------------------------
_PSA_GRADE_TO_TARGET = {
    10.0: 970, 9.0: 925, 8.5: 875, 8.0: 825,
    7.5: 775, 7.0: 725, 6.5: 675, 6.0: 625, 5.5: 575,
    5.0: 525, 4.5: 475, 4.0: 425, 3.5: 375, 3.0: 325,
    2.5: 275, 2.0: 225, 1.5: 175, 1.0: 125
}


def run_calibration():
    """
    Re-grade every sample in the training dataset, then use scipy to find the
    category weights + global bias that minimise prediction error.

    Saves result to training_data/calibration.json.
    Returns (calibration_dict, error_string_or_None).
    """
    from scipy.optimize import minimize

    rows = read_training_rows()
    if not rows:
        return None, 'No training samples found. Add PSA-labeled cards first.'

    categories = ['corners', 'edges', 'surface', 'centering']
    grader = CardGrader()  # loads existing calibration for _analyze_side; weights replaced below

    features = []   # list of [corners, edges, surface, centering] after worst-side blend
    targets  = []   # list of target scores from known PSA grades
    processed = []
    skipped   = []

    for row in rows:
        sample_id = row.get('sample_id', '?')
        try:
            psa_grade = float(row.get('psa_grade') or 0)
        except (TypeError, ValueError):
            skipped.append(f"{sample_id}: invalid grade")
            continue

        if psa_grade not in _PSA_GRADE_TO_TARGET:
            skipped.append(f"{sample_id}: unsupported grade {psa_grade}")
            continue

        front_img = os.path.join(
            app.config['TRAINING_IMAGES_FOLDER'], row.get('front_image', '')
        )
        back_img = os.path.join(
            app.config['TRAINING_IMAGES_FOLDER'], row.get('back_image', '')
        )
        if not os.path.exists(front_img) or not os.path.exists(back_img):
            skipped.append(f"{sample_id}: image files missing")
            continue

        try:
            front_analysis, back_analysis = analyze_card_images(front_img, back_img)

            # Get raw per-category scores for both sides without using current weights
            front_scores = grader._analyze_side(front_analysis, 'front')
            back_scores  = grader._analyze_side(back_analysis, 'back')

            combined = {}
            for cat in categories:
                fs = front_scores.get(cat, 100)
                bs = back_scores.get(cat, 100)
                worse  = min(fs, bs)
                better = max(fs, bs)
                combined[cat] = (worse * 0.7) + (better * 0.3)

            feat = [combined[cat] for cat in categories]
            features.append(feat)
            targets.append(_PSA_GRADE_TO_TARGET[psa_grade])
            processed.append(sample_id)
        except Exception as exc:
            skipped.append(f"{sample_id}: {exc}")

    if len(features) < 2:
        return None, (
            f'Need at least 2 gradable samples (got {len(features)}, '
            f'skipped {len(skipped)}).'
        )

    X = np.array(features, dtype=float)   # (N, 4)
    y = np.array(targets,  dtype=float)   # (N,)

    orig_weights = np.array([0.25, 0.25, 0.25, 0.25])

    def objective(params):
        w    = params[:4]
        bias = params[4]
        pred = X @ w + bias
        mse  = float(np.mean((pred - y) ** 2))
        # L2 regularisation toward equal weights — prevents wild swings on small datasets
        reg_strength = max(0.1, 3.0 / len(features))
        reg = reg_strength * float(np.sum((w - orig_weights) ** 2)) * 100_000
        return mse + reg

    constraints = [{'type': 'eq', 'fun': lambda p: np.sum(p[:4]) - 1.0}]
    bounds = [(0.05, 0.70)] * 4 + [(-200.0, 200.0)]
    x0    = np.array([0.25, 0.25, 0.25, 0.25, 0.0])

    result = minimize(
        objective, x0, method='SLSQP',
        bounds=bounds, constraints=constraints,
        options={'ftol': 1e-10, 'maxiter': 1000}
    )

    best_w    = result.x[:4]
    best_bias = float(result.x[4])

    # Normalise weights to sum exactly to 1.0
    best_w = best_w / best_w.sum()

    # Accuracy metrics before and after
    pred_before = X @ orig_weights
    pred_after  = X @ best_w + best_bias

    mae_before = float(np.mean(np.abs(pred_before - y)))
    mae_after  = float(np.mean(np.abs(pred_after  - y)))

    # Grade-level accuracy (within 0.5 PSA grade = ±~50 pts)
    def grade_accuracy(pred_arr):
        from grading_system import PSAGradingCriteria
        correct = 0
        for p, t in zip(pred_arr, y):
            p_grade, _, _ = PSAGradingCriteria.get_grade_from_score(int(round(max(100, min(1000, p)))))
            t_grade, _, _ = PSAGradingCriteria.get_grade_from_score(int(round(t)))
            if abs(p_grade - t_grade) <= 0.5:
                correct += 1
        return round(100 * correct / len(pred_arr), 1)

    acc_before = grade_accuracy(pred_before)
    acc_after  = grade_accuracy(pred_after)

    calibration = {
        'category_weights': {cat: round(float(w), 6) for cat, w in zip(categories, best_w)},
        'score_bias':        round(best_bias, 4),
        'training_samples':  len(features),
        'skipped_samples':   len(skipped),
        'mae_before':        round(mae_before, 1),
        'mae_after':         round(mae_after,  1),
        'grade_accuracy_before': acc_before,
        'grade_accuracy_after':  acc_after,
        'calibrated_at':     datetime.utcnow().isoformat(),
    }

    calib_path = os.path.join(app.config['TRAINING_FOLDER'], 'calibration.json')
    with open(calib_path, 'w') as f:
        json.dump(calibration, f, indent=2)

    return calibration, None


def append_training_record(sample_id, grade_value, card_title, notes, front_filename, back_filename):
    """Append one training metadata row to CSV."""
    ensure_training_csv()
    with open(app.config['TRAINING_METADATA_CSV'], 'a', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            sample_id,
            datetime.utcnow().isoformat(),
            grade_value,
            card_title,
            notes,
            front_filename,
            back_filename
        ])


def save_labeled_pair(front_file, back_file, grade_value, card_title='', notes=''):
    """Persist one labeled front/back pair into training dataset."""
    ensure_training_csv()

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    sample_id = f"sample_{timestamp}"

    front_original = secure_filename(front_file.filename)
    back_original = secure_filename(back_file.filename)
    front_filename = f"{sample_id}_front_{front_original}"
    back_filename = f"{sample_id}_back_{back_original}"
    front_path = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], front_filename)
    back_path = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], back_filename)

    front_file.save(front_path)
    back_file.save(back_path)

    append_training_record(
        sample_id=sample_id,
        grade_value=grade_value,
        card_title=card_title,
        notes=notes,
        front_filename=front_filename,
        back_filename=back_filename
    )

    return sample_id

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extension_from_content_type(content_type):
    """Map common image content types to file extensions."""
    mapping = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp'
    }
    return mapping.get((content_type or '').split(';')[0].strip().lower())


def is_valid_http_url(value):
    """Validate http/https URL (scheme + netloc only — SSRF check done at download time)."""
    try:
        parsed = urlparse(value or '')
        return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
    except Exception:
        return False


def download_image_from_url(image_url, output_dir, output_prefix):
    """Download remote image URL to disk and return saved filename/path."""
    if not is_valid_http_url(image_url):
        raise ValueError('Invalid image URL. Must be http(s).')

    # SSRF protection: block private/internal IP ranges
    parsed_url = urlparse(image_url)
    hostname = parsed_url.hostname or ''
    if not _is_safe_host(hostname):
        raise ValueError('Image URL resolves to a disallowed (private/internal) address.')

    req = Request(
        image_url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'image/*,*/*;q=0.8'
        }
    )

    with urlopen(req, timeout=20) as response:
        content_type = response.headers.get('Content-Type', '')
        ext = extension_from_content_type(content_type)
        if not ext:
            path_ext = urlparse(image_url).path.rsplit('.', 1)[-1].lower() if '.' in urlparse(image_url).path else ''
            if path_ext in app.config['ALLOWED_EXTENSIONS']:
                ext = path_ext

        if not ext:
            raise ValueError('Unsupported remote image format. Allowed: png, jpg, jpeg, gif, webp')

        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > app.config['MAX_CONTENT_LENGTH']:
            raise ValueError('Remote image is too large')

        image_bytes = response.read(app.config['MAX_CONTENT_LENGTH'] + 1)
        if len(image_bytes) > app.config['MAX_CONTENT_LENGTH']:
            raise ValueError('Remote image is too large')

    filename = f"{output_prefix}.{ext}"
    saved_path = os.path.join(output_dir, filename)
    with open(saved_path, 'wb') as output_file:
        output_file.write(image_bytes)

    return filename, saved_path


def resolve_image_input(uploaded_file, image_url, output_dir, output_prefix):
    """Resolve an image from either uploaded file or remote URL."""
    has_file = uploaded_file is not None and uploaded_file.filename != ''
    has_url = bool((image_url or '').strip())

    if has_file:
        if not allowed_file(uploaded_file.filename):
            raise ValueError('Invalid file type. Please upload PNG, JPG, JPEG, GIF, or WEBP files')
        safe_name = secure_filename(uploaded_file.filename)
        filename = f"{output_prefix}_{safe_name}"
        saved_path = os.path.join(output_dir, filename)
        uploaded_file.save(saved_path)
        return filename, saved_path

    if has_url:
        return download_image_from_url(image_url.strip(), output_dir=output_dir, output_prefix=output_prefix)

    raise ValueError('Image is required (upload a file or provide an image URL)')


def parse_optional_positive_int(value):
    """Parse optional positive integer input."""
    if value is None:
        return None
    text = str(value).strip()
    if text == '':
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def split_image_grid(image, rows, cols):
    """Split image into a fixed rows x cols grid of crops."""
    height, width = image.shape[:2]
    crops = []
    for row in range(rows):
        for col in range(cols):
            y1 = int(row * height / rows)
            y2 = int((row + 1) * height / rows)
            x1 = int(col * width / cols)
            x2 = int((col + 1) * width / cols)
            crop = image[y1:y2, x1:x2]
            if crop.size > 0:
                crops.append(crop)
    return crops


def detect_card_boxes_auto(image):
    """Auto-detect likely card bounding boxes in a lot image."""
    height, width = image.shape[:2]

    # Downscale to max 2000px for speed; scale boxes back up afterward
    MAX_DIM = 2000
    scale = 1.0
    if max(height, width) > MAX_DIM:
        scale = MAX_DIM / max(height, width)
        new_w = int(width * scale)
        new_h = int(height * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        height, width = new_h, new_w

    image_area = float(height * width)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.012:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            continue

        aspect_ratio = w / float(h)
        if not (0.5 <= aspect_ratio <= 0.85):
            continue

        if w < 80 or h < 120:
            continue

        boxes.append((x, y, w, h, area))

    if not boxes:
        return []

    # Remove near-duplicate overlapping boxes by keeping larger area box.
    boxes = sorted(boxes, key=lambda item: item[4], reverse=True)
    filtered = []

    def iou(box_a, box_b):
        ax, ay, aw, ah, _ = box_a
        bx, by, bw, bh, _ = box_b
        a_x2, a_y2 = ax + aw, ay + ah
        b_x2, b_y2 = bx + bw, by + bh

        inter_x1 = max(ax, bx)
        inter_y1 = max(ay, by)
        inter_x2 = min(a_x2, b_x2)
        inter_y2 = min(a_y2, b_y2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        a_area = aw * ah
        b_area = bw * bh
        union = a_area + b_area - inter_area
        if union <= 0:
            return 0.0
        return inter_area / float(union)

    for candidate in boxes:
        if all(iou(candidate, kept) < 0.55 for kept in filtered):
            filtered.append(candidate)

    if not filtered:
        return []

    median_h = sorted([box[3] for box in filtered])[len(filtered) // 2]
    row_threshold = max(20, int(median_h * 0.6))

    filtered = sorted(filtered, key=lambda item: item[1])
    rows = []
    for box in filtered:
        x, y, w, h, area = box
        placed = False
        for row in rows:
            if abs(y - row['y']) <= row_threshold:
                row['boxes'].append(box)
                row['y'] = int((row['y'] + y) / 2)
                placed = True
                break
        if not placed:
            rows.append({'y': y, 'boxes': [box]})

    ordered = []
    rows = sorted(rows, key=lambda row: row['y'])
    for row in rows:
        for box in sorted(row['boxes'], key=lambda item: item[0]):
            ordered.append(box)

    # Scale boxes back to original image coordinates
    if scale != 1.0:
        ordered = [
            (int(x / scale), int(y / scale), int(w / scale), int(h / scale), area)
            for x, y, w, h, area in ordered
        ]

    return ordered


def extract_card_crops_from_lot(image_path, rows=None, cols=None):
    """Extract card crops from lot image via optional grid or auto detection."""
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError('Could not load lot image')

    if rows and cols:
        return split_image_grid(image, rows, cols)

    boxes = detect_card_boxes_auto(image)
    if not boxes:
        raise ValueError('Could not auto-detect cards in lot image. Try setting rows/cols.')

    crops = []
    height, width = image.shape[:2]
    for x, y, w, h, _ in boxes:
        pad_x = int(w * 0.02)
        pad_y = int(h * 0.02)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(width, x + w + pad_x)
        y2 = min(height, y + h + pad_y)
        crop = image[y1:y2, x1:x2]
        if crop.size > 0:
            crops.append(crop)

    return crops


def save_lot_crop_pair(front_crop, back_crop, grade_value, card_title='', notes=''):
    """Save one front/back crop pair into training dataset."""
    ensure_training_csv()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    sample_id = f"sample_{timestamp}"

    front_filename = f"{sample_id}_front.jpg"
    back_filename = f"{sample_id}_back.jpg"
    front_path = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], front_filename)
    back_path = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], back_filename)

    cv2.imwrite(front_path, front_crop)
    cv2.imwrite(back_path, back_crop)

    append_training_record(
        sample_id=sample_id,
        grade_value=grade_value,
        card_title=card_title,
        notes=notes,
        front_filename=front_filename,
        back_filename=back_filename
    )

    return sample_id


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/grade', methods=['POST'])
@_rate_limit("15 per minute")
def grade_card():
    """Grade a card from uploaded front and back images."""
    front_file = request.files.get('front_image')
    back_file   = request.files.get('back_image')
    front_image_url = request.form.get('front_image_url', '')
    back_image_url  = request.form.get('back_image_url', '')

    front_path = None
    back_path  = None
    try:
        timestamp = str(int(time.time()))

        _front_filename, front_path = resolve_image_input(
            uploaded_file=front_file,
            image_url=front_image_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"{timestamp}_front"
        )
        _back_filename, back_path = resolve_image_input(
            uploaded_file=back_file,
            image_url=back_image_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"{timestamp}_back"
        )

        # --- Computer-vision analysis ---
        front_analysis, back_analysis = analyze_card_images(front_path, back_path)

        # --- Rule-based grading ---
        grader = CardGrader()
        grading_result = grader.grade_card(front_analysis, back_analysis)

        # --- ML model blending (if trained) ---
        ml_info = {}
        try:
            ml_model = get_model()
            if ml_model.is_trained:
                front_scores = grading_result.get('front_scores', {})
                back_scores  = grading_result.get('back_scores',  {})
                ml_grade, ml_raw = ml_model.predict(front_scores, back_scores)
                status = ml_model.status()
                n = status.get('n_samples', 0)

                # Blend: ML weight ramps from 0→80% as samples grow from 10→100
                ml_weight = min(0.80, max(0.0, (n - 10) / 90))
                rule_score = grading_result['score']

                _grade_to_score = {
                    10.0: 970, 9.0: 925, 8.5: 875, 8.0: 825,
                    7.5: 775, 7.0: 725, 6.5: 675, 6.0: 625, 5.5: 575,
                    5.0: 525, 4.5: 475, 4.0: 425, 3.5: 375, 3.0: 325,
                    2.5: 275, 2.0: 225, 1.5: 175, 1.0: 125
                }
                ml_score = _grade_to_score.get(ml_grade, rule_score)
                blended  = int(round(rule_score * (1 - ml_weight) + ml_score * ml_weight))
                blended  = max(100, min(1000, blended))

                if blended != rule_score:
                    from grading_system import PSAGradingCriteria
                    new_grade, new_name, new_desc = PSAGradingCriteria.get_grade_from_score(blended)
                    grading_result['score']      = blended
                    grading_result['grade']      = new_grade
                    grading_result['grade_name'] = new_name
                    grading_result['description'] = new_desc

                ml_info = {
                    'active':        True,
                    'ml_grade':      ml_grade,
                    'ml_raw':        ml_raw,
                    'ml_weight':     round(ml_weight, 2),
                    'n_samples':     n,
                    'grade_accuracy': status.get('grade_accuracy_pct'),
                    'cv_mae':        status.get('cv_mae'),
                }
        except Exception:
            ml_info = {'active': False}

        # --- Card identification (best-effort, non-blocking) ---
        card_id = {}
        try:
            card_id = identify_card(front_path)
        except Exception:
            pass

        # --- Format response ---
        from grading_system import PSAGradingCriteria
        description       = grading_result['description']
        formatted_desc    = PSAGradingCriteria.format_description(description)
        detailed_criteria = PSAGradingCriteria.get_detailed_criteria(description)

        front_centering = front_analysis.get('centering', {})
        back_centering  = back_analysis.get('centering', {})
        front_corners   = front_analysis.get('corners', {})
        back_corners    = back_analysis.get('corners', {})
        front_surface   = front_analysis.get('surface', {})
        back_surface    = back_analysis.get('surface', {})

        def pick_fields(data, fields):
            return {f: data.get(f) for f in fields if f in data}

        response = {
            'success':        True,
            'score':          grading_result['score'],
            'grade':          grading_result['grade'],
            'grade_name':     grading_result['grade_name'],
            'description':    formatted_desc,
            'details':        grading_result['details'],
            'category_scores': grading_result['category_scores'],
            'ml':             ml_info,
            'card_id':        card_id,
            'debug': {
                'front_centering_ratios': {
                    'left_right_ratio': round_float(front_centering.get('left_right_ratio', 60.0)),
                    'top_bottom_ratio': round_float(front_centering.get('top_bottom_ratio', 60.0)),
                    'method':   front_centering.get('centering_method', 'unknown'),
                    'reliable': bool(front_centering.get('centering_reliable', False)),
                    'note':     front_centering.get('centering_note', ''),
                },
                'back_centering_ratios': {
                    'left_right_ratio': round_float(back_centering.get('left_right_ratio', 60.0)),
                    'top_bottom_ratio': round_float(back_centering.get('top_bottom_ratio', 60.0)),
                    'method':   back_centering.get('centering_method', 'unknown'),
                    'reliable': bool(back_centering.get('centering_reliable', False)),
                    'note':     back_centering.get('centering_note', ''),
                },
                'centering_scores': {
                    'front':    grading_result.get('front_scores', {}).get('centering'),
                    'back':     grading_result.get('back_scores',  {}).get('centering'),
                    'combined': grading_result.get('category_scores', {}).get('centering'),
                },
                'front_corners': pick_fields(front_corners,
                    ['sharpness', 'worn_corners', 'rounding_level', 'fraying', 'missing_stock']),
                'back_corners':  pick_fields(back_corners,
                    ['sharpness', 'worn_corners', 'rounding_level', 'fraying', 'missing_stock']),
                'corner_scores': {
                    'front':    grading_result.get('front_scores', {}).get('corners'),
                    'back':     grading_result.get('back_scores',  {}).get('corners'),
                    'combined': grading_result.get('category_scores', {}).get('corners'),
                },
                'front_surface': pick_fields(front_surface,
                    ['scratch_count', 'crease_count', 'wrinkle_count', 'wrinkle_length',
                     'stain_count', 'print_defects', 'dent_count', 'scuffing', 'gloss_loss']),
                'back_surface':  pick_fields(back_surface,
                    ['scratch_count', 'crease_count', 'wrinkle_count', 'wrinkle_length',
                     'stain_count', 'print_defects', 'dent_count', 'scuffing', 'gloss_loss']),
                'surface_scores': {
                    'front':    grading_result.get('front_scores', {}).get('surface'),
                    'back':     grading_result.get('back_scores',  {}).get('surface'),
                    'combined': grading_result.get('category_scores', {}).get('surface'),
                },
                'framing_warning': (
                    not bool(front_centering.get('centering_reliable', False)) or
                    not bool(back_centering.get('centering_reliable', False))
                ),
            }
        }

        if detailed_criteria:
            response['detailed_criteria'] = detailed_criteria

        return jsonify(response)

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error processing images: {exc}'}), 500
    finally:
        # Always clean up uploaded temp files
        for path in [front_path, back_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


@app.route('/about')
def about():
    """About page explaining the grading system"""
    return render_template('about.html')


@app.route('/label-sample', methods=['POST'])
@require_admin
def label_sample():
    """Save a labeled front/back sample for future model training."""
    front_file = request.files.get('front_image')
    back_file = request.files.get('back_image')
    front_image_url = request.form.get('front_image_url', '')
    back_image_url = request.form.get('back_image_url', '')
    grade_value = parse_grade(request.form.get('psa_grade'))
    card_title = (request.form.get('card_title') or '').strip()
    notes = (request.form.get('notes') or '').strip()

    if grade_value is None:
        return jsonify({'error': 'PSA grade must be a number between 1 and 10'}), 400

    has_front = (front_file is not None and front_file.filename != '') or bool(front_image_url.strip())
    has_back = (back_file is not None and back_file.filename != '') or bool(back_image_url.strip())
    if not (has_front and has_back):
        return jsonify({'error': 'Both front and back images are required (file upload or image URL)'}), 400

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    sample_id = f"sample_{timestamp}"

    try:
        front_filename, _ = resolve_image_input(
            uploaded_file=front_file,
            image_url=front_image_url,
            output_dir=app.config['TRAINING_IMAGES_FOLDER'],
            output_prefix=f"{sample_id}_front"
        )
        back_filename, _ = resolve_image_input(
            uploaded_file=back_file,
            image_url=back_image_url,
            output_dir=app.config['TRAINING_IMAGES_FOLDER'],
            output_prefix=f"{sample_id}_back"
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    append_training_record(
        sample_id=sample_id,
        grade_value=grade_value,
        card_title=card_title,
        notes=notes,
        front_filename=front_filename,
        back_filename=back_filename
    )

    rows = read_training_rows()
    summary = summarize_training_dataset(rows)

    return jsonify({
        'success': True,
        'sample_id': sample_id,
        'dataset': summary
    })


@app.route('/bulk-label-samples', methods=['POST'])
@require_admin
def bulk_label_samples():
    """Save many labeled front/back pairs (training only, no grading)."""
    front_files = request.files.getlist('front_images')
    back_files = request.files.getlist('back_images')
    grade_value = parse_grade(request.form.get('psa_grade'))
    title_prefix = (request.form.get('card_title_prefix') or '').strip()
    notes = (request.form.get('notes') or '').strip()

    if grade_value is None:
        return jsonify({'error': 'PSA grade must be a number between 1 and 10'}), 400
    if not front_files or not back_files:
        return jsonify({'error': 'Upload both front and back image batches'}), 400
    if len(front_files) != len(back_files):
        return jsonify({'error': 'Front and back image counts must match'}), 400

    max_batch = 200
    if len(front_files) > max_batch:
        return jsonify({'error': f'Batch too large. Max {max_batch} pairs per upload'}), 400

    saved_sample_ids = []
    for index, (front_file, back_file) in enumerate(zip(front_files, back_files), start=1):
        if front_file.filename == '' or back_file.filename == '':
            return jsonify({'error': f'Missing filename in pair #{index}'}), 400
        if not (allowed_file(front_file.filename) and allowed_file(back_file.filename)):
            return jsonify({'error': f'Invalid file type in pair #{index}'}), 400

        pair_title = title_prefix
        if title_prefix:
            pair_title = f"{title_prefix} #{index}"

        sample_id = save_labeled_pair(
            front_file=front_file,
            back_file=back_file,
            grade_value=grade_value,
            card_title=pair_title,
            notes=notes
        )
        saved_sample_ids.append(sample_id)

    rows = read_training_rows()
    summary = summarize_training_dataset(rows)

    return jsonify({
        'success': True,
        'saved_pairs': len(saved_sample_ids),
        'sample_ids': saved_sample_ids,
        'dataset': summary
    })


@app.route('/bulk-label-from-csv', methods=['POST'])
@require_admin
def bulk_label_from_csv():
    """Bulk import training rows from CSV containing front/back image URLs."""
    csv_file = request.files.get('csv_file')
    default_grade = parse_grade(request.form.get('default_psa_grade'))

    if csv_file is None or csv_file.filename == '':
        return jsonify({'error': 'CSV file is required'}), 400

    if not csv_file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files are supported'}), 400

    try:
        csv_text = csv_file.stream.read().decode('utf-8-sig')
    except Exception:
        return jsonify({'error': 'Could not read CSV file'}), 400

    reader = csv.DictReader(csv_text.splitlines())
    if reader.fieldnames is None:
        return jsonify({'error': 'CSV must include a header row'}), 400

    normalized_headers = {header.strip().lower(): header for header in reader.fieldnames if header}
    if 'front_image_url' not in normalized_headers or 'back_image_url' not in normalized_headers:
        return jsonify({'error': 'CSV requires front_image_url and back_image_url columns'}), 400

    max_rows = 300
    saved = 0
    skipped = []
    row_index = 1

    for row in reader:
        row_index += 1
        if saved >= max_rows:
            skipped.append({'row': row_index, 'reason': f'max {max_rows} rows per import'})
            continue

        front_url = (row.get(normalized_headers['front_image_url']) or '').strip()
        back_url = (row.get(normalized_headers['back_image_url']) or '').strip()
        row_grade_text = (row.get(normalized_headers.get('psa_grade', '')) or '').strip()
        row_title = (row.get(normalized_headers.get('card_title', '')) or '').strip()
        row_notes = (row.get(normalized_headers.get('notes', '')) or '').strip()

        grade_value = parse_grade(row_grade_text) if row_grade_text else default_grade
        if not front_url or not back_url:
            skipped.append({'row': row_index, 'reason': 'missing front/back URL'})
            continue
        if grade_value is None:
            skipped.append({'row': row_index, 'reason': 'missing/invalid psa_grade and no valid default provided'})
            continue

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        sample_id = f"sample_{timestamp}"

        try:
            front_filename, _ = resolve_image_input(
                uploaded_file=None,
                image_url=front_url,
                output_dir=app.config['TRAINING_IMAGES_FOLDER'],
                output_prefix=f"{sample_id}_front"
            )
            back_filename, _ = resolve_image_input(
                uploaded_file=None,
                image_url=back_url,
                output_dir=app.config['TRAINING_IMAGES_FOLDER'],
                output_prefix=f"{sample_id}_back"
            )
        except Exception as error:
            skipped.append({'row': row_index, 'reason': str(error)})
            continue

        append_training_record(
            sample_id=sample_id,
            grade_value=grade_value,
            card_title=row_title,
            notes=row_notes,
            front_filename=front_filename,
            back_filename=back_filename
        )
        saved += 1

    rows = read_training_rows()
    summary = summarize_training_dataset(rows)

    return jsonify({
        'success': True,
        'saved_pairs': saved,
        'skipped': skipped,
        'dataset': summary
    })


@app.route('/bulk-label-from-lot-image', methods=['POST'])
@require_admin
def bulk_label_from_lot_image():
    """Split front/back lot images into card pairs and save as training samples."""
    front_lot_file = request.files.get('front_lot_image')
    back_lot_file  = request.files.get('back_lot_image')
    front_lot_url  = request.form.get('front_lot_image_url', '').strip()
    back_lot_url   = request.form.get('back_lot_image_url',  '').strip()
    grade_value = parse_grade(request.form.get('psa_grade'))
    title_prefix = (request.form.get('card_title_prefix') or '').strip()
    notes = (request.form.get('notes') or '').strip()
    rows = parse_optional_positive_int(request.form.get('rows'))
    cols = parse_optional_positive_int(request.form.get('cols'))

    has_front = (front_lot_file and front_lot_file.filename) or front_lot_url
    has_back  = (back_lot_file  and back_lot_file.filename)  or back_lot_url

    if not has_front:
        return jsonify({'error': 'Front lot image is required'}), 400
    if not has_back:
        return jsonify({'error': 'Back lot image is required'}), 400
    if grade_value is None:
        return jsonify({'error': 'PSA grade must be a number between 1 and 10'}), 400
    if (rows is None) ^ (cols is None):
        return jsonify({'error': 'Provide both rows and cols, or leave both empty for auto-detect'}), 400

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    try:
        front_lot_name, front_lot_path = resolve_image_input(
            uploaded_file=front_lot_file,
            image_url=front_lot_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"lot_{timestamp}_front"
        )
        back_lot_name, back_lot_path = resolve_image_input(
            uploaded_file=back_lot_file,
            image_url=back_lot_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"lot_{timestamp}_back"
        )

        front_crops = extract_card_crops_from_lot(front_lot_path, rows=rows, cols=cols)
        back_crops = extract_card_crops_from_lot(back_lot_path, rows=rows, cols=cols)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception as error:
        return jsonify({'error': f'Failed to process lot images: {str(error)}'}), 400

    if len(front_crops) == 0 or len(back_crops) == 0:
        return jsonify({'error': 'No card crops found in lot images'}), 400
    if len(front_crops) != len(back_crops):
        return jsonify({'error': f'Front/back lot crop count mismatch ({len(front_crops)} vs {len(back_crops)}). Try rows/cols mode.'}), 400

    max_pairs = 200
    if len(front_crops) > max_pairs:
        return jsonify({'error': f'Too many detected cards ({len(front_crops)}). Max {max_pairs} per lot import'}), 400

    saved_sample_ids = []
    for index, (front_crop, back_crop) in enumerate(zip(front_crops, back_crops), start=1):
        pair_title = title_prefix
        if title_prefix:
            pair_title = f"{title_prefix} #{index}"
        sample_id = save_lot_crop_pair(
            front_crop=front_crop,
            back_crop=back_crop,
            grade_value=grade_value,
            card_title=pair_title,
            notes=notes
        )
        saved_sample_ids.append(sample_id)

    rows_data = read_training_rows()
    summary = summarize_training_dataset(rows_data)

    return jsonify({
        'success': True,
        'saved_pairs': len(saved_sample_ids),
        'sample_ids': saved_sample_ids,
        'detected_front_cards': len(front_crops),
        'detected_back_cards': len(back_crops),
        'dataset': summary
    })


@app.route('/detect-grade', methods=['POST'])
def detect_grade_route():
    """
    OCR the PSA grade from a slab image.
    Accepts either a file upload (field: slab_image) or a URL (field: slab_image_url).
    Returns: { success, grade, message }
    """
    uploaded_file = request.files.get('slab_image')
    image_url = request.form.get('slab_image_url', '').strip()

    try:
        _filename, tmp_path = resolve_image_input(
            uploaded_file, image_url,
            app.config['UPLOAD_FOLDER'], 'slab_ocr'
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    try:
        grade, message = detect_psa_grade_from_image(tmp_path)
        if grade is not None:
            return jsonify({'success': True, 'grade': grade, 'message': message})
        return jsonify({'success': False, 'grade': None, 'message': message})
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


@app.route('/calibrate', methods=['POST'])
@require_admin
def calibrate_route():
    """
    Re-grade all PSA-labeled training samples and optimise category weights.
    Saves calibration.json; CardGrader reloads it on next grade request.
    """
    calibration, error = run_calibration()
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'training_samples':       calibration['training_samples'],
        'skipped_samples':        calibration['skipped_samples'],
        'mae_before':             calibration['mae_before'],
        'mae_after':              calibration['mae_after'],
        'grade_accuracy_before':  calibration['grade_accuracy_before'],
        'grade_accuracy_after':   calibration['grade_accuracy_after'],
        'category_weights':       calibration['category_weights'],
        'score_bias':             calibration['score_bias'],
        'calibrated_at':          calibration['calibrated_at'],
    })


@app.route('/calibration-status', methods=['GET'])
def calibration_status_route():
    """Return current calibration.json if it exists."""
    calib_path = os.path.join(app.config['TRAINING_FOLDER'], 'calibration.json')
    if not os.path.exists(calib_path):
        return jsonify({'calibrated': False})
    try:
        with open(calib_path, 'r') as f:
            data = json.load(f)
        return jsonify({'calibrated': True, **data})
    except Exception as exc:
        return jsonify({'calibrated': False, 'error': str(exc)})


@app.route('/dataset-stats', methods=['GET'])
def dataset_stats():
    """Return training dataset summary for UI display."""
    rows = read_training_rows()
    return jsonify({
        'success': True,
        'dataset': summarize_training_dataset(rows)
    })


# ---------------------------------------------------------------------------
# Feature cache — avoids re-running CV analysis on unchanged images
# ---------------------------------------------------------------------------

def _feature_cache_path():
    return os.path.join(app.config['TRAINING_FOLDER'], 'feature_cache.json')


def _load_feature_cache():
    path = _feature_cache_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_feature_cache(cache):
    try:
        with open(_feature_cache_path(), 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass


def _image_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def build_training_samples(rows, training_images_folder):
    """
    Build (front_scores, back_scores, psa_grade) tuples for all valid rows.
    Uses a disk cache keyed by sample_id + image mtimes so unchanged images
    are never re-analyzed.
    """
    grader = CardGrader()
    cache  = _load_feature_cache()
    samples, skipped = [], []
    cache_dirty = False

    for row in rows:
        sample_id = row.get('sample_id', '?')
        try:
            psa_grade = float(row.get('psa_grade') or 0)
        except (TypeError, ValueError):
            skipped.append(f"{sample_id}: invalid grade")
            continue

        front_img = os.path.join(training_images_folder, row.get('front_image', ''))
        back_img  = os.path.join(training_images_folder, row.get('back_image', ''))
        if not os.path.exists(front_img) or not os.path.exists(back_img):
            skipped.append(f"{sample_id}: image files missing")
            continue

        # Cache key includes file mtimes so any image change triggers re-analysis
        cache_key = f"{sample_id}|{_image_mtime(front_img):.0f}|{_image_mtime(back_img):.0f}"
        if cache_key in cache:
            entry  = cache[cache_key]
            weight = 1.0 if 'ebay' in (row.get('notes') or '').lower() else 5.0
            samples.append((entry['front_scores'], entry['back_scores'], psa_grade, weight))
            continue

        try:
            front_analysis, back_analysis = analyze_card_images(front_img, back_img)
            front_scores = grader._analyze_side(front_analysis, 'front')
            back_scores  = grader._analyze_side(back_analysis,  'back')
            cache[cache_key] = {'front_scores': front_scores, 'back_scores': back_scores}
            cache_dirty = True
            weight = 1.0 if 'ebay' in (row.get('notes') or '').lower() else 5.0
            samples.append((front_scores, back_scores, psa_grade, weight))
        except Exception as exc:
            skipped.append(f"{sample_id}: {exc}")

    if cache_dirty:
        _save_feature_cache(cache)

    return samples, skipped


# ---------------------------------------------------------------------------
# ML model training route
# ---------------------------------------------------------------------------

@app.route('/train-model', methods=['POST'])
@require_admin
@_rate_limit("2 per minute")
def train_model_route():
    """
    Re-grade all labeled training samples and train the GradientBoosting ML model.
    Uses cached CV features so only new/changed images are re-analyzed.
    """
    rows = read_training_rows()
    if not rows:
        return jsonify({'success': False, 'error': 'No training samples found.'}), 400

    samples, skipped = build_training_samples(rows, app.config['TRAINING_IMAGES_FOLDER'])

    ml_model = reload_model()
    try:
        meta = ml_model.train(samples)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc), 'skipped': skipped}), 400

    # Also run legacy scipy calibration so CardGrader weights stay updated
    try:
        run_calibration()
    except Exception:
        pass

    return jsonify({
        'success':        True,
        'n_samples':      meta['n_samples'],
        'skipped':        skipped,
        'train_mae':      meta.get('train_mae'),
        'cv_mae':         meta.get('cv_mae'),
        'grade_accuracy': meta.get('grade_accuracy_pct'),
        'trained_at':     meta.get('trained_at'),
    })


@app.route('/model-status', methods=['GET'])
def model_status_route():
    """Return ML model status for UI display."""
    return jsonify(get_model().status())


# ---------------------------------------------------------------------------
# eBay bulk training — background job with progress polling
# ---------------------------------------------------------------------------

import threading
_ebay_jobs: dict = {}  # job_id -> progress dict


def _run_ebay_bulk_job(job_id, search_query, grades, max_per_grade, upload_folder, training_folder):
    """Background thread: fetch eBay images, save samples, retrain model."""
    from image_analysis import CardImageAnalyzer
    from comps import fetch_training_candidates

    job = _ebay_jobs[job_id]
    analyzer = CardImageAnalyzer()
    saved, skipped, api_errors = [], [], []

    # Step 1: fetch all candidates first (fast API calls)
    all_candidates = []
    for grade in grades:
        if job.get('cancelled'):
            break
        candidates, api_err = fetch_training_candidates(search_query, grade, max_per_grade)
        if api_err:
            api_errors.append(f'PSA {grade}: {api_err}')
        else:
            all_candidates.extend(candidates)

    if api_errors and not all_candidates:
        job.update({'status': 'error', 'error': api_errors[0], 'done': True})
        return

    job['total'] = len(all_candidates)
    job['status'] = 'downloading'

    # Step 2: download and save each image
    for i, candidate in enumerate(all_candidates):
        if job.get('cancelled'):
            break
        job['current'] = i + 1
        front_url = candidate['image_url']
        back_url  = candidate.get('back_url', '')
        title     = candidate['title']
        grade     = candidate['grade']
        tmp_front = tmp_back = None
        try:
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')

            _fn, tmp_front = resolve_image_input(
                uploaded_file=None, image_url=front_url,
                output_dir=upload_folder, output_prefix=f"ebay_{ts}_f"
            )
            front_img = cv2.imread(tmp_front)
            if front_img is None:
                skipped.append({'title': title, 'grade': grade, 'reason': 'Could not load front image'})
                continue

            # Download back image if available, otherwise duplicate front
            if back_url:
                try:
                    _fn2, tmp_back = resolve_image_input(
                        uploaded_file=None, image_url=back_url,
                        output_dir=upload_folder, output_prefix=f"ebay_{ts}_b"
                    )
                    back_img = cv2.imread(tmp_back) or front_img
                except Exception:
                    back_img = front_img
            else:
                back_img = front_img

            # Extract card from slab for both sides
            try:
                front_card = analyzer.extract_card_from_slab(front_img)['card_image']
            except Exception:
                front_card = front_img
            try:
                back_card = analyzer.extract_card_from_slab(back_img)['card_image']
            except Exception:
                back_card = back_img

            # Minimum resolution filter — skip tiny images
            MIN_DIM = 200
            fh, fw = front_card.shape[:2]
            bh, bw = back_card.shape[:2]
            if min(fh, fw) < MIN_DIM or min(bh, bw) < MIN_DIM:
                skipped.append({'title': title, 'grade': grade,
                                'reason': f'Too small (front {fw}x{fh}, back {bw}x{bh})'})
                continue

            sample_id = f"sample_{ts}_ebay"
            front_fn  = f"{sample_id}_front.jpg"
            back_fn   = f"{sample_id}_back.jpg"
            cv2.imwrite(os.path.join(training_folder, front_fn), front_card)
            cv2.imwrite(os.path.join(training_folder, back_fn),  back_card)
            append_training_record(
                sample_id=sample_id,
                grade_value=grade,
                card_title=title[:100],
                notes=f'eBay auto-import. Query: {search_query}',
                front_filename=front_fn,
                back_filename=back_fn,
            )
            saved.append({'title': title, 'grade': grade})
        except Exception as exc:
            skipped.append({'title': title, 'grade': grade, 'reason': str(exc)})
        finally:
            for p in (tmp_front, tmp_back):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        job['saved'] = len(saved)
        job['skipped'] = len(skipped)

    # Step 3: retrain model
    retrain_result = None
    if saved:
        job['status'] = 'training'
        try:
            rows = read_training_rows()
            samples, _ = build_training_samples(rows, training_folder)
            ml = reload_model()
            if len(samples) >= 10:
                meta = ml.train(samples)
                retrain_result = {
                    'retrained':      True,
                    'n_samples':      meta['n_samples'],
                    'grade_accuracy': meta.get('grade_accuracy_pct'),
                }
        except Exception as exc:
            retrain_result = {'retrained': False, 'error': str(exc)}

    rows    = read_training_rows()
    summary = summarize_training_dataset(rows)
    job.update({
        'status':      'done',
        'done':        True,
        'saved':       len(saved),
        'skipped':     len(skipped),
        'saved_items': saved[:30],
        'api_errors':  api_errors,
        'retrain':     retrain_result,
        'dataset':     summary,
    })


@app.route('/bulk-train-from-ebay', methods=['POST'])
@require_admin
def bulk_train_from_ebay():
    """Start a background eBay bulk training job. Returns job_id immediately."""
    body          = request.get_json(force=True, silent=True) or {}
    search_query  = body.get('search_query', '').strip()
    grades_raw    = body.get('grades', [10])
    max_per_grade = int(body.get('max_per_grade', 10))

    if not search_query:
        return jsonify({'success': False, 'error': 'search_query is required'}), 400

    max_per_grade = max(1, min(max_per_grade, 200))

    grades = []
    for g in grades_raw:
        try:
            gf = float(g)
            if gf in _VALID_PSA_GRADES:
                grades.append(gf)
        except (TypeError, ValueError):
            pass
    if not grades:
        return jsonify({'success': False, 'error': 'No valid PSA grades specified'}), 400

    job_id = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    _ebay_jobs[job_id] = {
        'status': 'starting', 'done': False,
        'total': 0, 'current': 0, 'saved': 0, 'skipped': 0,
    }

    t = threading.Thread(
        target=_run_ebay_bulk_job,
        args=(job_id, search_query, grades, max_per_grade,
              app.config['UPLOAD_FOLDER'], app.config['TRAINING_IMAGES_FOLDER']),
        daemon=True,
    )
    t.start()

    return jsonify({'success': True, 'job_id': job_id})


@app.route('/bulk-train-status/<job_id>', methods=['GET'])
def bulk_train_status(job_id):
    """Poll progress of a bulk eBay training job."""
    job = _ebay_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    return jsonify({'success': True, **job})


# ---------------------------------------------------------------------------
# PWCC / Goldin auction bulk training
# ---------------------------------------------------------------------------

_auction_jobs: dict = {}  # job_id -> progress dict


def _run_auction_bulk_job(job_id, search_query, grades, max_per_grade,
                          sources, upload_folder, training_folder):
    """Background thread: fetch PWCC/Goldin images, save samples, retrain model."""
    from image_analysis import CardImageAnalyzer
    from auction_fetcher import fetch_auction_candidates

    job = _auction_jobs[job_id]
    analyzer = CardImageAnalyzer()
    saved, skipped, api_errors = [], [], []

    # Step 1: fetch candidates from auction houses
    all_candidates = []
    for grade in grades:
        if job.get('cancelled'):
            break
        cands, errs = fetch_auction_candidates(
            search_query, grade, max_per_grade, sources=sources
        )
        api_errors.extend(errs)
        all_candidates.extend(cands)

    if api_errors and not all_candidates:
        job.update({'status': 'error', 'error': ' | '.join(api_errors), 'done': True})
        return

    job['total'] = len(all_candidates)
    job['status'] = 'downloading'

    # Step 2: download and save
    for i, candidate in enumerate(all_candidates):
        if job.get('cancelled'):
            break
        job['current'] = i + 1
        front_url = candidate['front_url']
        back_url  = candidate.get('back_url', '')
        title     = candidate['title']
        grade     = candidate['grade']
        source    = candidate.get('source', 'auction')
        tmp_front = tmp_back = None
        try:
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')

            _fn, tmp_front = resolve_image_input(
                uploaded_file=None, image_url=front_url,
                output_dir=upload_folder, output_prefix=f"auction_{ts}_f"
            )
            front_img = cv2.imread(tmp_front)
            if front_img is None:
                skipped.append({'title': title, 'grade': grade, 'reason': 'Could not load front image'})
                continue

            if back_url:
                try:
                    _fn2, tmp_back = resolve_image_input(
                        uploaded_file=None, image_url=back_url,
                        output_dir=upload_folder, output_prefix=f"auction_{ts}_b"
                    )
                    back_img = cv2.imread(tmp_back) or front_img
                except Exception:
                    back_img = front_img
            else:
                back_img = front_img

            try:
                front_card = analyzer.extract_card_from_slab(front_img)['card_image']
            except Exception:
                front_card = front_img
            try:
                back_card = analyzer.extract_card_from_slab(back_img)['card_image']
            except Exception:
                back_card = back_img

            MIN_DIM = 200
            fh, fw = front_card.shape[:2]
            bh, bw = back_card.shape[:2]
            if min(fh, fw) < MIN_DIM or min(bh, bw) < MIN_DIM:
                skipped.append({'title': title, 'grade': grade,
                                'reason': f'Too small ({fw}x{fh})'})
                continue

            sample_id = f"sample_{ts}_{source.lower()}"
            front_fn  = f"{sample_id}_front.jpg"
            back_fn   = f"{sample_id}_back.jpg"
            cv2.imwrite(os.path.join(training_folder, front_fn), front_card)
            cv2.imwrite(os.path.join(training_folder, back_fn),  back_card)
            append_training_record(
                sample_id=sample_id,
                grade_value=grade,
                card_title=title[:100],
                notes=f'{source} auto-import. Query: {search_query}',
                front_filename=front_fn,
                back_filename=back_fn,
            )
            saved.append({'title': title, 'grade': grade, 'source': source})
        except Exception as exc:
            skipped.append({'title': title, 'grade': grade, 'reason': str(exc)})
        finally:
            for p in (tmp_front, tmp_back):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        job['saved']   = len(saved)
        job['skipped'] = len(skipped)

    # Step 3: retrain model
    retrain_result = None
    if saved:
        job['status'] = 'training'
        try:
            rows = read_training_rows()
            samples, _ = build_training_samples(rows, training_folder)
            ml = reload_model()
            if len(samples) >= 10:
                meta = ml.train(samples)
                retrain_result = {
                    'retrained':      True,
                    'n_samples':      meta['n_samples'],
                    'grade_accuracy': meta.get('grade_accuracy_pct'),
                    'cv_mae':         meta.get('cv_mae'),
                }
        except Exception as exc:
            retrain_result = {'retrained': False, 'error': str(exc)}

    job.update({
        'status':   'done',
        'done':     True,
        'saved':    len(saved),
        'skipped':  len(skipped),
        'api_errors': api_errors,
        'retrain':  retrain_result,
    })


@app.route('/bulk-train-from-auction', methods=['POST'])
@require_admin
def bulk_train_from_auction():
    """Start a background PWCC/Goldin bulk training job."""
    data = request.get_json(silent=True) or {}
    search_query = data.get('search_query', '').strip()
    grades_raw   = data.get('grades', [10, 9, 8])
    max_per_grade = int(data.get('max_per_grade', 30))
    sources_raw   = data.get('sources', ['pwcc', 'goldin'])

    if not search_query:
        return jsonify({'success': False, 'error': 'search_query is required'}), 400

    grades = []
    for g in grades_raw:
        try:
            gf = float(g)
            if gf in _VALID_PSA_GRADES:
                grades.append(gf)
        except (TypeError, ValueError):
            pass
    if not grades:
        return jsonify({'success': False, 'error': 'No valid PSA grades specified'}), 400

    sources = [s for s in sources_raw if s in ('pwcc', 'goldin')]
    if not sources:
        sources = ['pwcc', 'goldin']

    job_id = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    _auction_jobs[job_id] = {
        'status': 'starting', 'done': False,
        'total': 0, 'current': 0, 'saved': 0, 'skipped': 0,
    }
    t = threading.Thread(
        target=_run_auction_bulk_job,
        args=(job_id, search_query, grades, max_per_grade, sources,
              app.config['UPLOAD_FOLDER'], app.config['TRAINING_IMAGES_FOLDER']),
        daemon=True,
    )
    t.start()
    return jsonify({'success': True, 'job_id': job_id})


@app.route('/bulk-train-auction-status/<job_id>', methods=['GET'])
def bulk_train_auction_status(job_id):
    """Poll progress of a PWCC/Goldin bulk training job."""
    job = _auction_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    return jsonify({'success': True, **job})


@app.route('/firecrawl-status', methods=['GET'])
def firecrawl_status():
    """Check whether a Firecrawl API key is configured."""
    from auction_fetcher import firecrawl_available
    return jsonify({'available': firecrawl_available()})


# ---------------------------------------------------------------------------
# Vision model (EfficientNet-B0) training
# ---------------------------------------------------------------------------

_vision_jobs: dict = {}  # job_id -> progress dict


def _run_vision_training_job(job_id, training_folder, epochs, batch_size):
    """Background thread: load all training images and fine-tune EfficientNet-B0."""
    from ml_model_vision import reload_vision_model

    job = _vision_jobs[job_id]
    job['status'] = 'loading_images'

    try:
        rows = read_training_rows()
        image_pairs = []
        for row in rows:
            grade_raw = row.get('grade_value') or row.get('psa_grade')
            try:
                grade = float(grade_raw)
            except (TypeError, ValueError):
                continue
            if grade not in _VALID_PSA_GRADES:
                continue

            front_path = os.path.join(training_folder, row.get('front_image', ''))
            back_path  = os.path.join(training_folder, row.get('back_image', ''))
            if not os.path.exists(front_path):
                continue

            notes = row.get('notes', '')
            weight = 5.0 if notes and 'personal' in notes.lower() else 1.0
            image_pairs.append((front_path, back_path, grade, weight))

        job['total_pairs'] = len(image_pairs)

        if len(image_pairs) < 20:
            job.update({
                'status': 'error',
                'error':  f'Need at least 20 labeled images (have {len(image_pairs)})',
                'done':   True,
            })
            return

        job['status'] = 'training'

        def _progress(epoch, total, loss):
            job['epoch']       = epoch
            job['total_epochs'] = total
            job['last_loss']   = round(loss, 4)

        vm = reload_vision_model()
        meta = vm.train(image_pairs, epochs=epochs, batch_size=batch_size,
                        progress_cb=_progress)

        job.update({
            'status':         'done',
            'done':           True,
            'n_samples':      meta['n_samples'],
            'n_pairs':        meta['n_pairs'],
            'train_mae':      meta['train_mae'],
            'grade_accuracy': meta['grade_accuracy_pct'],
            'device':         meta.get('device', 'cpu'),
        })

    except Exception as exc:
        job.update({'status': 'error', 'error': str(exc), 'done': True})


@app.route('/train-vision-model', methods=['POST'])
@require_admin
def train_vision_model_route():
    """Start background EfficientNet-B0 training job."""
    data = request.get_json(silent=True) or {}
    epochs     = int(data.get('epochs', 15))
    batch_size = int(data.get('batch_size', 16))

    job_id = datetime.utcnow().strftime('%Y%m%d%H%M%S%f') + '_v'
    _vision_jobs[job_id] = {
        'status': 'queued', 'done': False,
        'epoch': 0, 'total_epochs': epochs, 'last_loss': None,
        'total_pairs': 0,
    }
    t = threading.Thread(
        target=_run_vision_training_job,
        args=(job_id, app.config['TRAINING_IMAGES_FOLDER'], epochs, batch_size),
        daemon=True,
    )
    t.start()
    return jsonify({'success': True, 'job_id': job_id})


@app.route('/vision-model-status', methods=['GET'])
def vision_model_status_route():
    """Return current EfficientNet-B0 model status + latest job if any."""
    from ml_model_vision import get_vision_model
    vm = get_vision_model()
    status = vm.status()

    # Also return latest training job progress if one exists
    latest_job = None
    if _vision_jobs:
        latest_id = max(_vision_jobs.keys())
        latest_job = _vision_jobs[latest_id]

    return jsonify({'success': True, 'model': status, 'latest_job': latest_job})


@app.route('/vision-train-status/<job_id>', methods=['GET'])
def vision_train_status(job_id):
    """Poll a specific vision training job."""
    job = _vision_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    return jsonify({'success': True, **job})


# ---------------------------------------------------------------------------
# Card identification route
# ---------------------------------------------------------------------------

@app.route('/identify', methods=['POST'])
@_rate_limit("20 per minute")
def identify_route():
    """
    OCR-identify a card from its front image.
    Returns player name, year, set, card number, and a ready-made eBay search query.
    """
    front_file  = request.files.get('front_image')
    image_url   = request.form.get('front_image_url', '').strip()
    tmp_path    = None
    try:
        _filename, tmp_path = resolve_image_input(
            uploaded_file=front_file,
            image_url=image_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"id_{int(time.time())}"
        )
        card_id = identify_card(tmp_path)
        return jsonify({'success': True, 'card_id': card_id})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Market comps route
# ---------------------------------------------------------------------------

@app.route('/comps', methods=['POST'])
@_rate_limit("10 per minute")
def comps_route():
    """
    Fetch eBay sold listings for a card.
    Accepts: search_query (string), grade (optional float).
    """
    search_query = (request.form.get('search_query') or request.json and request.json.get('search_query') or '').strip()
    grade_raw    = request.form.get('grade') or (request.json and request.json.get('grade'))

    if not search_query:
        return jsonify({'success': False, 'error': 'search_query is required'}), 400

    grade = None
    if grade_raw:
        try:
            grade = float(grade_raw)
        except (TypeError, ValueError):
            pass

    result = get_comps(search_query, predicted_grade=grade)
    return jsonify({'success': True, **result})


@app.route('/deal-finder', methods=['POST'])
@_rate_limit("5 per minute")
def deal_finder_route():
    """
    Find good buy opportunities by comparing active eBay listings to sold comps.
    Accepts JSON or form data:
        search_query     (str, required)
        psa_grade        (float, optional) — predicted grade to focus on
        grading_cost     (float, optional) — PSA submission cost, default 25
        max_listings     (int, optional)  — how many active listings to check, default 20
    """
    data = request.get_json(silent=True) or {}
    search_query  = (request.form.get('search_query')  or data.get('search_query')  or '').strip()
    grading_cost  = request.form.get('grading_cost')   or data.get('grading_cost')
    max_listings  = request.form.get('max_listings')   or data.get('max_listings')
    grade_raw     = request.form.get('psa_grade')      or data.get('psa_grade')
    listing_type  = (request.form.get('listing_type')  or data.get('listing_type')  or '').strip().upper()

    if not search_query:
        return jsonify({'success': False, 'error': 'search_query is required'}), 400

    kwargs = {}
    if grading_cost is not None:
        try:
            kwargs['grading_cost'] = float(grading_cost)
        except (TypeError, ValueError):
            pass
    if max_listings is not None:
        try:
            kwargs['max_listings'] = int(max_listings)
        except (TypeError, ValueError):
            pass
    if grade_raw is not None:
        try:
            kwargs['psa_grade_estimate'] = float(grade_raw)
        except (TypeError, ValueError):
            pass
    if listing_type in ('FIXED_PRICE', 'AUCTION'):
        kwargs['listing_type'] = listing_type

    result = find_deals(search_query, **kwargs)
    return jsonify(result)


@app.route('/grade-slab', methods=['POST'])
@_rate_limit("15 per minute")
def grade_slab():
    """
    Grade a card from slab photos.
    - Extracts the card region from inside the plastic slab
    - OCRs the PSA grade from the label automatically
    - Analyzes the card (not the case) for CV metrics
    - Optionally saves as a training sample
    """
    from image_analysis import analyze_slab_images

    front_file = request.files.get('front_image')
    back_file  = request.files.get('back_image')
    front_url  = request.form.get('front_image_url', '')
    back_url   = request.form.get('back_image_url', '')
    save_as_sample = request.form.get('save_as_sample', 'false').lower() == 'true'
    card_title = (request.form.get('card_title') or '').strip()
    notes      = (request.form.get('notes') or '').strip()

    front_path = None
    back_path  = None
    try:
        timestamp = str(int(time.time()))

        _ff, front_path = resolve_image_input(
            uploaded_file=front_file, image_url=front_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"{timestamp}_slab_front"
        )
        _bf, back_path = resolve_image_input(
            uploaded_file=back_file, image_url=back_url,
            output_dir=app.config['UPLOAD_FOLDER'],
            output_prefix=f"{timestamp}_slab_back"
        )

        # OCR the grade from the front label
        detected_grade, ocr_message = detect_psa_grade_from_image(front_path)

        # Extract card from slab and analyze
        front_analysis, back_analysis, slab_info = analyze_slab_images(front_path, back_path)

        # Grade the extracted card
        grader = CardGrader()
        grading_result = grader.grade_card(front_analysis, back_analysis)

        # ML blending (same as /grade)
        ml_info = {}
        try:
            ml_model = get_model()
            if ml_model.is_trained:
                front_scores = grading_result.get('front_scores', {})
                back_scores  = grading_result.get('back_scores',  {})
                ml_grade, ml_raw = ml_model.predict(front_scores, back_scores)
                status = ml_model.status()
                n = status.get('n_samples', 0)
                ml_weight = min(0.80, max(0.0, (n - 10) / 90))
                _grade_to_score = {
                    10.0: 970, 9.0: 925, 8.5: 875, 8.0: 825,
                    7.5: 775, 7.0: 725, 6.5: 675, 6.0: 625, 5.5: 575,
                    5.0: 525, 4.5: 475, 4.0: 425, 3.5: 375, 3.0: 325,
                    2.5: 275, 2.0: 225, 1.5: 175, 1.0: 125
                }
                ml_score = _grade_to_score.get(ml_grade, grading_result['score'])
                blended  = int(round(grading_result['score'] * (1 - ml_weight) + ml_score * ml_weight))
                blended  = max(100, min(1000, blended))
                if blended != grading_result['score']:
                    from grading_system import PSAGradingCriteria
                    ng, nn, nd = PSAGradingCriteria.get_grade_from_score(blended)
                    grading_result.update({'score': blended, 'grade': ng, 'grade_name': nn, 'description': nd})
                ml_info = {'active': True, 'ml_grade': ml_grade, 'ml_raw': ml_raw,
                           'ml_weight': round(ml_weight, 2), 'n_samples': n}
        except Exception:
            ml_info = {'active': False}

        # Card identification
        card_id = {}
        try:
            card_id = identify_card(front_path)
        except Exception:
            pass

        # Auto-save as training sample if requested and grade was detected
        sample_id = None
        if save_as_sample and detected_grade is not None:
            try:
                import cv2 as _cv2
                from image_analysis import CardImageAnalyzer as _CIA
                _analyzer = _CIA()
                _front_img = _cv2.imread(front_path)
                _back_img  = _cv2.imread(back_path)
                _front_slab = _analyzer.extract_card_from_slab(_front_img)
                _back_slab  = _analyzer.extract_card_from_slab(_back_img)

                ts2 = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
                sample_id = f"sample_{ts2}"
                front_fn  = f"{sample_id}_front.jpg"
                back_fn   = f"{sample_id}_back.jpg"
                front_sp  = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], front_fn)
                back_sp   = os.path.join(app.config['TRAINING_IMAGES_FOLDER'], back_fn)
                _cv2.imwrite(front_sp, _front_slab['card_image'])
                _cv2.imwrite(back_sp,  _back_slab['card_image'])
                append_training_record(
                    sample_id=sample_id,
                    grade_value=detected_grade,
                    card_title=card_title or card_id.get('search_query', ''),
                    notes=notes or f'Auto-saved from slab. OCR: {ocr_message}',
                    front_filename=front_fn,
                    back_filename=back_fn,
                )
            except Exception as exc:
                sample_id = None
                notes = f'Save failed: {exc}'

        from grading_system import PSAGradingCriteria
        description    = grading_result['description']
        formatted_desc = PSAGradingCriteria.format_description(description)

        return jsonify({
            'success':          True,
            'score':            grading_result['score'],
            'grade':            grading_result['grade'],
            'grade_name':       grading_result['grade_name'],
            'description':      formatted_desc,
            'details':          grading_result['details'],
            'category_scores':  grading_result['category_scores'],
            'ml':               ml_info,
            'card_id':          card_id,
            'slab_info': {
                'detected_psa_grade': detected_grade,
                'ocr_message':        ocr_message,
                'front_extraction':   slab_info['front_method'],
                'back_extraction':    slab_info['back_method'],
                'front_card_bounds':  slab_info['front_card_bounds'],
                'back_card_bounds':   slab_info['back_card_bounds'],
            },
            'auto_saved':       sample_id is not None,
            'sample_id':        sample_id,
        })

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(exc)}), 500
    finally:
        for path in [front_path, back_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


if __name__ == '__main__':
    # Debug mode should only be enabled in development
    # Set FLASK_ENV=production in production environments
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    port = int(os.environ.get('PORT', 5051))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
