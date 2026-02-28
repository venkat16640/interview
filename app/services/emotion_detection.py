"""
Emotion Detection Service — High Accuracy Edition
===================================================
Pipeline:
  1. Decode image bytes → BGR numpy array
  2. Preprocess: CLAHE + bilateral filter (handles poor lighting)
  3. Count faces via OpenCV Haar Cascade
  4. Run DeepFace with multi-backend fallback for emotion detection
  5. Apply temporal smoothing over the last N frames to reduce jitter
  6. Return rich emotion dict with all 7 emotion scores

Backends tried in order: retinaface → mtcnn → ssd → opencv
(retinaface is the most accurate; opencv is the fastest fallback)
"""

import cv2
import numpy as np
import io
from collections import deque
from PIL import Image

# ── Constants ─────────────────────────────────────────────────────────────────
_ALL_EMOTIONS   = ['happy', 'sad', 'angry', 'fear', 'surprise', 'disgust', 'neutral']
_DETECTOR_ORDER = ['retinaface', 'mtcnn', 'ssd', 'opencv']

# Temporal smoothing buffer: keeps the last N emotion result dicts
_SMOOTHING_WINDOW = 3
_emotion_buffer   = deque(maxlen=_SMOOTHING_WINDOW)


# ── Lazy DeepFace import ───────────────────────────────────────────────────────
def _get_deepface():
    """Lazily import DeepFace so a TF startup crash won't kill Flask."""
    try:
        from deepface import DeepFace
        return DeepFace
    except Exception as e:
        print(f"[WARN] DeepFace unavailable: {e}")
        return None


# ── Image preprocessing ───────────────────────────────────────────────────────
def _bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
    """Convert raw JPEG/PNG bytes from the browser → OpenCV BGR array."""
    image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _preprocess(image_bgr: np.ndarray) -> np.ndarray:
    """
    Enhance image quality before emotion analysis:
      • CLAHE on the luminance channel → better contrast in dim lighting
      • Bilateral filter → reduce noise while keeping edges sharp
      • Slight sharpening kernel → improve feature clarity

    Returns an enhanced BGR image.
    """
    # ── 1. CLAHE on L-channel (LAB colour space) ──
    lab   = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_eq  = clahe.apply(l)
    lab_eq = cv2.merge([l_eq, a, b])
    enhanced = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

    # ── 2. Bilateral filter – smooth noise, keep edges ──
    enhanced = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)

    # ── 3. Mild unsharp mask (sharpening) ──
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
    enhanced = cv2.addWeighted(enhanced, 1.4, gaussian, -0.4, 0)

    return enhanced


# ── Face counting (fast OpenCV Haar) ──────────────────────────────────────────
def _count_faces_opencv(image_bgr: np.ndarray) -> int:
    """
    Fast face count using Haar cascade with histogram equalization.
    Used for violation detection (no face / multiple faces).
    """
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.08,   # finer scale → catches more sizes
        minNeighbors=4,     # slight tolerance to catch partially occluded faces
        minSize=(40, 40)    # ignore tiny noise blobs
    )
    return len(faces)


# ── Temporal smoothing ─────────────────────────────────────────────────────────
def _smooth_emotions(current: dict) -> dict:
    """
    Average the current emotion scores with the previous N readings to
    suppress per-frame jitter (e.g. one frame showing 'angry' then back to 'happy').
    Returns a smoothed emotion dict with updated dominant_emotion and confidence.
    """
    _emotion_buffer.append(current['emotions'].copy())

    if len(_emotion_buffer) < 2:
        return current          # Not enough history yet — return raw

    # Weighted average: most-recent frame gets highest weight
    weights = list(range(1, len(_emotion_buffer) + 1))  # [1, 2, 3]
    total_w = sum(weights)

    smoothed: dict = {e: 0.0 for e in _ALL_EMOTIONS}
    for w, frame in zip(weights, _emotion_buffer):
        for emo in _ALL_EMOTIONS:
            smoothed[emo] += (w / total_w) * frame.get(emo, 0.0)

    dominant = max(smoothed, key=smoothed.get)
    confidence = smoothed[dominant] / 100.0

    return {
        'dominant_emotion': dominant,
        'confidence':       min(confidence, 1.0),
        'faces_count':      current['faces_count'],
        'emotions':         smoothed
    }


# ── DeepFace analysis with backend fallback ───────────────────────────────────
def _run_deepface(image_bgr: np.ndarray, DeepFace) -> dict:
    """
    Try each detector backend in order of accuracy until one succeeds.
    Returns raw DeepFace emotion result dict.
    """
    last_err = None
    for backend in _DETECTOR_ORDER:
        try:
            result = DeepFace.analyze(
                img_path        = image_bgr,
                actions         = ['emotion'],
                enforce_detection = False,   # never crash if face is partially visible
                detector_backend  = backend,
                silent            = True
            )
            if isinstance(result, list):
                result = result[0]
            return result
        except Exception as err:
            last_err = err
            continue

    raise RuntimeError(f"All DeepFace backends failed. Last error: {last_err}")


# ── Public API ─────────────────────────────────────────────────────────────────
def detect_emotion(image_bytes: bytes) -> dict:
    """
    Main entry point for emotion detection.

    Args:
        image_bytes: Raw JPEG bytes from the browser (base64-decoded).

    Returns a dict:
        dominant_emotion : str         – e.g. 'happy'
        confidence       : float 0–1  – strength of dominant emotion
        faces_count      : int         – number of faces found by Haar cascade
        emotions         : dict        – all 7 emotion scores 0–100 (smoothed)
    """
    _FALLBACK_NEUTRAL = {
        'dominant_emotion': 'neutral',
        'confidence': 0.0,
        'faces_count': 0,
        'emotions': {e: 0.0 for e in _ALL_EMOTIONS}
    }

    try:
        # 1. Decode
        raw_bgr = _bytes_to_bgr(image_bytes)

        # 2. Preprocess for accuracy
        enhanced_bgr = _preprocess(raw_bgr)

        # 3. Fast face count
        faces_count = _count_faces_opencv(enhanced_bgr)

        if faces_count == 0:
            # Clear the smoothing buffer when there's no face
            _emotion_buffer.clear()
            return {**_FALLBACK_NEUTRAL, 'faces_count': 0}

        # 4. Load DeepFace (lazy)
        DeepFace = _get_deepface()
        if DeepFace is None:
            # No DeepFace → return uniform distribution (cannot detect)
            return {
                'dominant_emotion': 'neutral',
                'confidence': 0.5,
                'faces_count': faces_count,
                'emotions': {e: round(100.0 / 7, 2) for e in _ALL_EMOTIONS}
            }

        # 5. Run DeepFace with multi-backend fallback
        try:
            analysis = _run_deepface(enhanced_bgr, DeepFace)
        except Exception as df_err:
            print(f"[WARN] DeepFace failed entirely: {df_err}")
            return {
                'dominant_emotion': 'neutral',
                'confidence': 0.5,
                'faces_count': faces_count,
                'emotions': {e: round(100.0 / 7, 2) for e in _ALL_EMOTIONS}
            }

        # 6. Extract results
        raw_emotions     = analysis.get('emotion', {})
        dominant_emotion = analysis.get('dominant_emotion', 'neutral').lower()

        # Ensure all 7 keys are present and rounded
        emotions = {}
        for emo in _ALL_EMOTIONS:
            raw_val = raw_emotions.get(emo, raw_emotions.get(emo.capitalize(), 0.0))
            emotions[emo] = round(float(raw_val), 2)

        # Recalculate dominant in case DeepFace is inconsistent
        dominant_emotion = max(emotions, key=emotions.get)
        confidence       = emotions[dominant_emotion] / 100.0

        raw_result = {
            'dominant_emotion': dominant_emotion,
            'confidence':       min(confidence, 1.0),
            'faces_count':      faces_count,
            'emotions':         emotions
        }

        # 7. Temporal smoothing (reduces jitter across frames)
        return _smooth_emotions(raw_result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] detect_emotion: {e}")
        return {
            'dominant_emotion': 'error',
            'confidence':       0.0,
            'faces_count':      0,
            'emotions':         {e: 0.0 for e in _ALL_EMOTIONS},
            'error':            str(e)
        }


# ── Sequence Aggregation ───────────────────────────────────────────────────────
def analyze_emotion_sequence(emotion_logs: list) -> dict:
    """Aggregate a list of EmotionLog DB objects into summary statistics."""
    if not emotion_logs:
        return {
            'dominant_overall':    'neutral',
            'average_confidence':  0.0,
            'emotion_distribution': {},
            'violations_count':    0
        }

    emotion_counts: dict = {}
    total_confidence = 0.0
    violations = 0

    for log in emotion_logs:
        emo = log.emotion
        emotion_counts[emo] = emotion_counts.get(emo, 0) + 1
        total_confidence   += log.confidence
        if log.is_violation:
            violations += 1

    total        = len(emotion_logs)
    distribution = {e: round((c / total) * 100, 1) for e, c in emotion_counts.items()}
    dominant     = max(emotion_counts, key=emotion_counts.get)

    return {
        'dominant_overall':    dominant,
        'average_confidence':  round(total_confidence / total, 3),
        'emotion_distribution': distribution,
        'violations_count':    violations,
        'total_samples':       total
    }


# ── Face Verification ──────────────────────────────────────────────────────────
def verify_face(current_image_bytes: bytes, reference_image_path: str) -> dict:
    """
    Compare the live frame against the baseline photo captured at session start.
    Uses DeepFace.verify() with ArcFace model for high identity accuracy.
    """
    if not reference_image_path:
        return {'verified': True, 'message': 'No reference photo set'}

    try:
        import tempfile, os

        DeepFace = _get_deepface()
        if DeepFace is None:
            return {'verified': True, 'message': 'DeepFace unavailable – skipping check'}

        # Resolve relative paths
        if not os.path.isabs(reference_image_path):
            from flask import current_app
            reference_image_path = os.path.join(
                current_app.root_path, 'static', reference_image_path
            )

        if not os.path.exists(reference_image_path):
            return {'verified': False, 'error': 'Reference photo not found'}

        # Write live frame to temp file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(current_image_bytes)
            tmp_path = tmp.name

        try:
            result = DeepFace.verify(
                img1_path         = tmp_path,
                img2_path         = reference_image_path,
                model_name        = 'ArcFace',   # Most accurate face-recognition model
                detector_backend  = 'opencv',
                enforce_detection = False,
                silent            = True
            )
            return {
                'verified': result.get('verified', False),
                'distance': round(result.get('distance', 1.0), 4)
            }
        except Exception as err:
            print(f"[WARN] DeepFace.verify failed: {err}")
            return {'verified': True, 'distance': 0.0}   # Fail-open
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    except Exception as e:
        print(f"[ERROR] verify_face: {e}")
        return {'verified': True, 'error': str(e)}       # Fail-open
