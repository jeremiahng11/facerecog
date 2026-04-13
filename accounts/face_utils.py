"""
Face recognition utilities using face_recognition library (dlib-based).
Falls back gracefully if face_recognition is not installed.
"""
import base64
import io
import json
import logging
import os
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

    users_with_face = StaffUser.objects.filter(
        face_registered=True,
        is_active=True,
    ).exclude(face_encoding__isnull=True).exclude(face_encoding='')

    if exclude_user_pk is not None:
        users_with_face = users_with_face.exclude(pk=exclude_user_pk)

    for user in users_with_face:
        known_encoding = user.get_face_encoding()
        if not known_encoding:
            continue
        result = compare_faces(known_encoding, candidate_encoding, tolerance)
        if result['match']:
            return {
                'user': user,
                'distance': result['distance'],
                'confidence': result['confidence'],
            }
    return None
