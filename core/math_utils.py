import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

# Load embedding model once per process
_model = None

def get_embedding_model():
    global _model
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers is not installed")
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def get_embedding(text: str) -> np.ndarray:
    if not text or not text.strip():
        return np.zeros(384)  # Size for all-MiniLM-L6-v2
    model = get_embedding_model()
    return model.encode(text)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def calculate_keyword_overlap(requirement_text: str, candidate_text: str) -> float:
    """Requirement-precision keyword overlap: what fraction of required keywords
    appear in the candidate's text.

    Uses intersection / len(req_words) rather than Jaccard (intersection / union)
    so that candidates with broad skill sets are not penalised for knowing more
    than the job requires.
    """
    if not requirement_text or not candidate_text:
        return 0.0

    req_words = set(requirement_text.lower().split())
    cand_words = set(candidate_text.lower().split())

    if not req_words:
        return 0.0

    intersection = req_words & cand_words
    return len(intersection) / len(req_words)
