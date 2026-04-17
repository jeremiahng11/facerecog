"""
Face recognition utilities using face_recognition library (dlib-based).
Falls back gracefully if face_recognition is not installed.
"""
import base64
import io
import json
import logging
import os
import threading
import time
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
    logger.info("face_recognition library loaded successfully")
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning("face_recognition not installed. Run: pip install face_recognition")


# ─── In-memory face encoding cache ───────────────────────────────────────────
# Avoids querying the DB and JSON-parsing every user's encoding on every frame.
# The cache holds a pre-built numpy matrix of all enrolled encodings plus a
# parallel list of (user_pk, staff_id) tuples for O(1) lookup after batch
# distance computation.  Thread-safe via a simple lock.


class _EncodingCache:
    """Cache enrolled face encodings as a numpy matrix for batch comparison."""

    _TTL = 30  # seconds before stale data triggers a refresh

    def __init__(self):
        self._lock = threading.Lock()
        self._matrix: np.ndarray | None = None   # shape (N, 128)
        self._user_keys: list[tuple[int, str]] = []  # [(pk, staff_id), ...]
        self._user_map: dict[str, int] = {}       # staff_id → index
        self._ts: float = 0.0                     # last refresh timestamp

    def _refresh(self):
        from .models import StaffUser
        rows = (
            StaffUser.objects
            .filter(face_enabled=True, face_registered=True, is_active=True)
            .exclude(face_encoding__isnull=True)
            .exclude(face_encoding='')
            .values_list('pk', 'staff_id', 'face_encoding')
        )
        encodings = []
        keys = []
        for pk, staff_id, enc_json in rows:
            try:
                enc = json.loads(enc_json)
            except (json.JSONDecodeError, TypeError):
                continue
            encodings.append(enc)
            keys.append((pk, staff_id))

        if encodings:
            self._matrix = np.array(encodings, dtype=np.float64)
        else:
            self._matrix = None
        self._user_keys = keys
        self._user_map = {sid: i for i, (_, sid) in enumerate(keys)}
        self._ts = time.monotonic()

    def get(self) -> tuple[np.ndarray | None, list[tuple[int, str]]]:
        """Return (matrix, user_keys). Auto-refreshes if stale."""
        with self._lock:
            if time.monotonic() - self._ts > self._TTL:
                self._refresh()
            return self._matrix, list(self._user_keys)

    def invalidate(self):
        """Force a refresh on the next call (e.g. after enrollment)."""
        with self._lock:
            self._ts = 0.0

    def find_best_match(self, candidate: list, tolerance: float) -> dict | None:
        """
        Batch-compare candidate encoding against ALL enrolled users at once.
        Returns {'pk': int, 'staff_id': str, 'confidence': float, 'distance': float}
        for the best match within tolerance, or None.
        """
        matrix, keys = self.get()
        if matrix is None or len(keys) == 0:
            return None

        candidate_np = np.array(candidate, dtype=np.float64)
        # Single vectorised call — orders of magnitude faster than per-user loop
        distances = np.linalg.norm(matrix - candidate_np, axis=1)

        best_idx = int(np.argmin(distances))
        best_dist = float(distances[best_idx])

        if best_dist > tolerance:
            return None

        pk, staff_id = keys[best_idx]
        confidence = round(max(0.0, min(100.0, (1.0 - best_dist) * 100)), 1)
        return {
            'pk': pk,
            'staff_id': staff_id,
            'distance': round(best_dist, 4),
            'confidence': confidence,
        }


encoding_cache = _EncodingCache()


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """
    Convert a base64 data URL (from webcam capture) to a numpy array.
    Returns RGB numpy array or None on failure.
    """
    try:
        # Strip the data URL prefix e.g. "data:image/jpeg;base64,..."
        if ',' in data_url:
            data_url = data_url.split(',', 1)[1]
        img_bytes = base64.b64decode(data_url)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        return np.array(pil_img)
    except Exception as e:
        logger.error(f"Failed to decode base64 image: {e}")
        return None


def image_file_to_array(image_path: str) -> np.ndarray | None:
    """Load an image file as RGB numpy array."""
    try:
        pil_img = Image.open(image_path).convert('RGB')
        return np.array(pil_img)
    except Exception as e:
        logger.error(f"Failed to load image {image_path}: {e}")
        return None


def extract_face_encoding(image_array: np.ndarray, num_jitters: int = 1) -> list | None:
    """
    Extract face encoding from an image array.
    num_jitters: re-sample the face N times and average the encodings.
    Higher values produce more accurate encodings at the cost of speed.
    Returns a list (128-dim vector) or None if no face detected.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return None
    try:
        encodings = face_recognition.face_encodings(
            image_array, num_jitters=num_jitters
        )
        if encodings:
            return encodings[0].tolist()
        return None
    except Exception as e:
        logger.error(f"Error extracting face encoding: {e}")
        return None


def extract_encoding_from_file(image_path: str) -> list | None:
    """Extract face encoding from an image file path."""
    arr = image_file_to_array(image_path)
    if arr is None:
        return None
    return extract_face_encoding(arr)


def extract_encoding_from_field_file(field_file) -> list | None:
    """
    Extract face encoding from a Django FieldFile, supporting both local
    filesystem storage and remote backends (e.g. Cloudinary).

    For local storage the file is read directly from disk via .path.
    For remote storage the file is streamed into memory so no local path
    is required (avoiding the AttributeError that .path raises on
    Cloudinary-backed fields).
    """
    if not field_file:
        return None
    try:
        # Local storage exposes a real filesystem path.
        path = field_file.path
        return extract_encoding_from_file(path)
    except NotImplementedError:
        # Remote storage backends (e.g. Cloudinary) raise NotImplementedError
        # for .path — read the file content directly instead.
        pass
    except Exception as e:
        logger.error(f"Error accessing field_file.path: {e}")

    # Fallback: stream the file into a PIL Image via its storage backend.
    try:
        with field_file.open('rb') as fh:
            pil_img = Image.open(fh).convert('RGB')
            pil_img.load()  # force read while the file handle is still open
        arr = np.array(pil_img)
        return extract_face_encoding(arr)
    except Exception as e:
        logger.error(f"Failed to load image from remote storage: {e}")
        return None


def extract_encoding_from_b64(data_url: str) -> list | None:
    """Extract face encoding from a base64 data URL."""
    arr = decode_base64_image(data_url)
    if arr is None:
        return None
    return extract_face_encoding(arr)


def compare_faces(known_encoding: list, candidate_encoding: list, tolerance: float = 0.5) -> dict:
    """
    Compare two face encodings.
    Returns dict with: match (bool), distance (float), confidence (float 0-100).
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {'match': False, 'distance': 1.0, 'confidence': 0.0, 'error': 'face_recognition not available'}

    try:
        known_np = np.array(known_encoding)
        candidate_np = np.array(candidate_encoding)
        distance = float(face_recognition.face_distance([known_np], candidate_np)[0])
        match = distance <= tolerance
        # Convert distance to a 0-100 confidence score
        confidence = max(0.0, min(100.0, (1.0 - distance) * 100))
        return {
            'match': match,
            'distance': round(distance, 4),
            'confidence': round(confidence, 1),
        }
    except Exception as e:
        logger.error(f"Error comparing faces: {e}")
        return {'match': False, 'distance': 1.0, 'confidence': 0.0, 'error': str(e)}


def save_face_snapshot(data_url: str, save_path: str) -> bool:
    """
    Save a base64 webcam snapshot to disk as JPEG.
    Returns True on success.
    """
    try:
        if ',' in data_url:
            data_url = data_url.split(',', 1)[1]
        img_bytes = base64.b64decode(data_url)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        pil_img.save(save_path, 'JPEG', quality=90)
        return True
    except Exception as e:
        logger.error(f"Failed to save face snapshot: {e}")
        return False


def detect_faces_in_b64(data_url: str) -> int:
    """Return the number of faces detected in a base64 image."""
    if not FACE_RECOGNITION_AVAILABLE:
        return 0
    arr = decode_base64_image(data_url)
    if arr is None:
        return 0
    try:
        locations = face_recognition.face_locations(arr)
        return len(locations)
    except Exception as e:
        logger.error(f"Error detecting faces: {e}")
        return 0


# ─── Face quality validation ──────────────────────────────────────────────────


def validate_face_quality(data_url: str, min_face_pct: float = 0.04) -> dict:
    """
    Check that a base64 webcam frame contains exactly one well-positioned,
    sufficiently large face. Returns a dict:

        {'ok': True}                          — frame is usable
        {'ok': False, 'reason': '...'}        — frame should be rejected

    Checks performed:
    1. Exactly one face detected (not zero, not multiple).
    2. Face bounding box covers at least min_face_pct of the total frame
       area (default 4%). Prevents recognition from tiny/far-away faces.
    3. Face is roughly centred — its centre must be within the middle 70%
       of the frame in both axes. Prevents heavily off-centre captures
       that produce unreliable encodings.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {'ok': False, 'reason': 'Face recognition library not available.'}

    arr = decode_base64_image(data_url)
    if arr is None:
        return {'ok': False, 'reason': 'Could not decode image.'}

    try:
        locations = face_recognition.face_locations(arr)
    except Exception as e:
        logger.error(f"Error detecting faces for quality check: {e}")
        return {'ok': False, 'reason': 'Error detecting face.'}

    if len(locations) == 0:
        return {'ok': False, 'reason': 'No face detected. Please centre your face.'}
    if len(locations) > 1:
        return {'ok': False, 'reason': 'Multiple faces detected. Please be alone in frame.'}

    # face_recognition returns (top, right, bottom, left)
    top, right, bottom, left = locations[0]
    face_h = bottom - top
    face_w = right - left
    img_h, img_w = arr.shape[:2]

    # ── Size check ────────────────────────────────────────────────
    face_area = face_h * face_w
    frame_area = img_h * img_w
    if frame_area > 0 and (face_area / frame_area) < min_face_pct:
        return {
            'ok': False,
            'reason': 'Face is too small. Please move closer to the camera.',
        }

    # ── Centre check ──────────────────────────────────────────────
    face_cx = (left + right) / 2
    face_cy = (top + bottom) / 2
    margin = 0.15  # face centre must be within 15%-85% of frame
    if not (img_w * margin < face_cx < img_w * (1 - margin)):
        return {
            'ok': False,
            'reason': 'Face is off-centre. Please centre your face in frame.',
        }
    if not (img_h * margin < face_cy < img_h * (1 - margin)):
        return {
            'ok': False,
            'reason': 'Face is off-centre. Please centre your face in frame.',
        }

    return {'ok': True}


# ─── Accuracy helpers ────────────────────────────────────────────────────────


def extract_encoding_from_b64_jittered(data_url: str, num_jitters: int = 3) -> list | None:
    """
    Extract a higher-quality face encoding from a base64 image by
    re-sampling the face num_jitters times and averaging. Use this
    during enrollment for a more robust template.
    """
    arr = decode_base64_image(data_url)
    if arr is None:
        return None
    return extract_face_encoding(arr, num_jitters=num_jitters)


def average_encodings(encodings: list[list]) -> list:
    """
    Average multiple 128-dim face encoding vectors into a single
    representative template. Averaging across multiple captures reduces
    noise from lighting variation, slight head angle differences, and
    expression changes — producing a more reliable template for matching.
    """
    arr = np.array(encodings)
    return np.mean(arr, axis=0).tolist()


def check_encoding_variance(encodings: list[list], min_std: float = 0.01) -> bool:
    """
    Basic liveness check: verify that multiple face encodings exhibit
    enough variance to indicate a live person rather than a static photo.

    Real faces produce slight encoding variation across frames due to
    micro-expressions, blinking, and head micro-movements. A static
    photo held up to the camera produces nearly identical encodings.

    Returns True if the variance is sufficient (likely live), False if
    the encodings are suspiciously identical (likely a static image).
    """
    if len(encodings) < 2:
        return True  # can't check variance with fewer than 2 samples
    arr = np.array(encodings)
    mean_std = float(np.mean(np.std(arr, axis=0)))
    return mean_std >= min_std


def validate_and_extract(data_url: str, min_face_pct: float = 0.04) -> dict:
    """
    Combined face quality validation AND encoding extraction in a single
    pass.  This avoids the major performance bottleneck of the old flow
    which called face_locations() twice per frame (once in
    validate_face_quality, once implicitly inside face_encodings).

    Returns:
        {'ok': True,  'encoding': [...128 floats...]}
        {'ok': False, 'reason': '...'}
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {'ok': False, 'reason': 'Face recognition library not available.'}

    arr = decode_base64_image(data_url)
    if arr is None:
        return {'ok': False, 'reason': 'Could not decode image.'}

    try:
        locations = face_recognition.face_locations(arr, model='hog')
    except Exception as e:
        logger.error(f"Error detecting faces: {e}")
        return {'ok': False, 'reason': 'Error detecting face.'}

    if len(locations) == 0:
        return {'ok': False, 'reason': 'No face detected. Please centre your face.'}
    if len(locations) > 1:
        return {'ok': False, 'reason': 'Multiple faces detected. Please be alone in frame.'}

    top, right, bottom, left = locations[0]
    face_h = bottom - top
    face_w = right - left
    img_h, img_w = arr.shape[:2]

    # Size check
    face_area = face_h * face_w
    frame_area = img_h * img_w
    if frame_area > 0 and (face_area / frame_area) < min_face_pct:
        return {'ok': False, 'reason': 'Face is too small. Please move closer to the camera.'}

    # Centre check
    face_cx = (left + right) / 2
    face_cy = (top + bottom) / 2
    margin = 0.15
    if not (img_w * margin < face_cx < img_w * (1 - margin)):
        return {'ok': False, 'reason': 'Face is off-centre. Please centre your face in frame.'}
    if not (img_h * margin < face_cy < img_h * (1 - margin)):
        return {'ok': False, 'reason': 'Face is off-centre. Please centre your face in frame.'}

    # Extract encoding using the ALREADY-KNOWN face location — no second detection
    try:
        encodings = face_recognition.face_encodings(arr, known_face_locations=locations, num_jitters=1)
        if not encodings:
            return {'ok': False, 'reason': 'Could not encode face. Please try again.'}
        return {'ok': True, 'encoding': encodings[0].tolist(), 'location': locations[0]}
    except Exception as e:
        logger.error(f"Error extracting encoding: {e}")
        return {'ok': False, 'reason': 'Error processing face.'}


def fast_extract(data_url: str, known_location: tuple | None = None) -> list | None:
    """
    Fast-path encoding for a follow-up frame.

    When known_location (top, right, bottom, left) is supplied — taken from
    the first frame's already-validated face region — we skip HOG detection
    entirely and pass it directly to face_encodings().  This halves the
    number of expensive dlib operations per request.

    Falls back to running face_locations() if no location is provided.
    Returns 128-dim encoding list, or None if no face found.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return None
    arr = decode_base64_image(data_url)
    if arr is None:
        return None
    try:
        if known_location is not None:
            locations = [known_location]
        else:
            locations = face_recognition.face_locations(arr, model='hog')
            if len(locations) != 1:
                return None
        encodings = face_recognition.face_encodings(arr, known_face_locations=locations, num_jitters=1)
        return encodings[0].tolist() if encodings else None
    except Exception:
        return None


def check_duplicate_face(
    candidate_encoding: list,
    tolerance: float,
    exclude_user_pk: int | None = None,
) -> dict | None:
    """
    Compare a candidate face encoding against every enrolled user in
    the database. If any existing user's encoding is within tolerance,
    return {'user': StaffUser, 'distance': float, 'confidence': float}.
    Otherwise return None (no duplicate).

    exclude_user_pk: skip this user (used when re-enrolling an existing
    user's face so they don't match against themselves).
    """
    # Import here to avoid circular imports (face_utils ← models).
    from .models import StaffUser

    qs = StaffUser.objects.filter(
        face_registered=True,
        is_active=True,
    ).exclude(face_encoding__isnull=True).exclude(face_encoding='')

    if exclude_user_pk is not None:
        qs = qs.exclude(pk=exclude_user_pk)

    # Batch-load only the fields we need to avoid pulling full model
    # instances with profile pictures etc.
    rows = qs.values_list('pk', 'staff_id', 'full_name', 'face_encoding')
    candidate_np = np.array(candidate_encoding)

    for pk, staff_id, full_name, face_encoding_json in rows:
        try:
            known = json.loads(face_encoding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        known_np = np.array(known)
        distance = float(face_recognition.face_distance([known_np], candidate_np)[0])
        if distance <= tolerance:
            # Return a lightweight dict (no full model instance needed).
            return {
                'user': type('User', (), {'pk': pk, 'staff_id': staff_id, 'full_name': full_name})(),
                'distance': round(distance, 4),
                'confidence': round(max(0.0, min(100.0, (1.0 - distance) * 100)), 1),
            }
    return None
