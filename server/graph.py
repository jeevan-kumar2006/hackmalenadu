"""TF-IDF based graph builder — connects files by concept similarity."""
import math
from collections import defaultdict


def build_graph(file_concepts):
    """
    file_concepts: dict of {file_id: [(concept_name, weight), ...]}
    Returns list of edges: [(src_id, tgt_id, similarity, shared_concepts), ...]
    """
    if len(file_concepts) < 2:
        return []

    # Build vocabulary
    all_concepts = set()
    for concepts in file_concepts.values():
        for name, _ in concepts:
            all_concepts.add(name)
    vocab = {name: i for i, name in enumerate(sorted(all_concepts))}
    vocab_size = len(vocab)
    if vocab_size == 0:
        return []

    doc_count = len(file_concepts)

    # Compute IDF
    doc_freq = defaultdict(int)
    for concepts in file_concepts.values():
        seen = set()
        for name, _ in concepts:
            if name not in seen:
                doc_freq[name] += 1
                seen.add(name)

    idf = {}
    for name, df in doc_freq.items():
        idf[name] = math.log((doc_count + 1) / (df + 1)) + 1

    # Build TF-IDF vectors
    vectors = {}
    for fid, concepts in file_concepts.items():
        vec = [0.0] * vocab_size
        for name, weight in concepts:
            if name in vocab:
                vec[vocab[name]] = weight * idf.get(name, 1.0)
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        vectors[fid] = vec

    # Compute pairwise cosine similarity
    fids = list(vectors.keys())
    edges = []
    threshold = 0.08  # Minimum similarity to create an edge

    for i in range(len(fids)):
        for j in range(i + 1, len(fids)):
            a, b = vectors[fids[i]], vectors[fids[j]]
            dot = sum(x * y for x, y in zip(a, b))
            # dot is already cosine similarity since vectors are normalized
            if dot >= threshold:
                # Find shared concepts
                concepts_a = {name for name, _ in file_concepts[fids[i]]}
                concepts_b = {name for name, _ in file_concepts[fids[j]]}
                shared = list(concepts_a & concepts_b)
                # Sort by IDF weight (more informative first)
                shared.sort(key=lambda s: idf.get(s, 0), reverse=True)
                edges.append((fids[i], fids[j], dot, shared[:10]))

    # Sort by weight descending
    edges.sort(key=lambda e: e[2], reverse=True)
    return edges
