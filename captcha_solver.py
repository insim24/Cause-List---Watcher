"""
Reads the hcservices.ecourts.gov.in Securimage captcha with the ONNX text
recognition model from Prakash-Bandapalli/Captcha_Solver.

That repo has no licence file, so the model is not vendored here: it is
downloaded from GitHub at a pinned commit on first use, checked against a
known SHA-256, and cached under models/ (gitignored).

Only onnxruntime + numpy + Pillow are needed. The original server pulls in
torch/torchvision just for the resize/normalize transform and the argmax
decode, both of which are reproduced below with numpy.
"""
import hashlib
import io
import os
import tempfile

import numpy as np
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "captcha.onnx")
MODEL_COMMIT = "63f7cf507dab7083170f40c243bb45d9aaa44e4a"
MODEL_URL = (
    "https://raw.githubusercontent.com/Prakash-Bandapalli/Captcha_Solver/"
    f"{MODEL_COMMIT}/server/captcha.onnx"
)
MODEL_SHA256 = "2a672587ee82eb010dbef54dd0a38e99625293608ed4068c4bd20ebe467fede4"

# From server/main.py. The tokenizer builds its vocabulary as
# (EOS,) + tuple(charset + "[UNK]") + (BOS, PAD) -- note "[UNK]" is split
# into five single characters, which is how the model was exported.
CHARSET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" + "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
ITOS = ("[E]",) + tuple(CHARSET + "[UNK]") + ("[B]", "[P]")
EOS_ID = 0
IMG_W, IMG_H = 128, 32

_session = None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_model():
    """Downloads the model once and verifies it. Returns its local path."""
    if os.path.exists(MODEL_PATH) and _sha256(MODEL_PATH) == MODEL_SHA256:
        return MODEL_PATH
    os.makedirs(MODEL_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=MODEL_DIR, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f, requests.get(MODEL_URL, stream=True, timeout=120) as r:
            r.raise_for_status()
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        got = _sha256(tmp)
        if got != MODEL_SHA256:
            raise RuntimeError(f"captcha model checksum mismatch: {got}")
        os.replace(tmp, MODEL_PATH)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return MODEL_PATH


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as rt  # imported lazily: only needed when solving
        _session = rt.InferenceSession(ensure_model(), providers=["CPUExecutionProvider"])
    return _session


def solve(image_bytes):
    """Returns (text, confidence) for a captcha image. Confidence is the
    lowest per-character probability, so one doubtful character drags it down."""
    sess = _get_session()
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((IMG_W, IMG_H), Image.BICUBIC)
    x = (np.asarray(im, dtype=np.float32) / 255.0 - 0.5) / 0.5
    x = x.transpose(2, 0, 1)[None]
    logits = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    e = np.exp(logits - logits.max(-1, keepdims=True))
    probs = e / e.sum(-1, keepdims=True)
    chars, confs = [], []
    for pos, idx in enumerate(probs.argmax(-1)):
        if idx == EOS_ID:
            break
        chars.append(ITOS[idx])
        confs.append(float(probs[pos, idx]))
    return "".join(chars), (min(confs) if confs else 0.0)
