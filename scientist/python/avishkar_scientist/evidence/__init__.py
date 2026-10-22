"""Evidence layer (spec sections 15-18, 40-42): sources, claims, evidence
links, provenance, independence, confidence and contradictions. Everything
here is deterministic except claim extraction and contradiction resolution,
which ask the TierRouter and fall back to deterministic paths."""
