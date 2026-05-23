import numpy as np
from sentence_transformers import SentenceTransformer

# Load embedding model once per process
_model = None

def get_embedding_model():
    global _model
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
    """Simple Jaccard similarity for keyword overlap."""
    if not requirement_text or not candidate_text:
        return 0.0
        
    req_words = set(requirement_text.lower().split())
    cand_words = set(candidate_text.lower().split())
    
    if not req_words:
        return 0.0
        
    intersection = req_words.intersection(cand_words)
    union = req_words.union(cand_words)
    
    return len(intersection) / len(union)
