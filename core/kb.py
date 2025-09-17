# core/kb.py
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import os, re, json
import numpy as np
from sentence_transformers import SentenceTransformer

# Reranker opcional
ENABLE_RERANKER = os.getenv("ENABLE_RERANKER", "1") == "1"
RERANK_MODEL = os.getenv("RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")
try:
    from sentence_transformers import CrossEncoder
    _CrossEncoder = CrossEncoder if ENABLE_RERANKER else None
except Exception:
    _CrossEncoder = None

@dataclass
class KBChunk:
    doc_id: str
    title: str
    text: str
    path: str

def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-_]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "doc"

def _chunk_text(text: str, max_chars=650):
    """
    Segmenta respetando encabezados Markdown como límites fuertes,
    luego por párrafos en blanco, y si hace falta por oraciones.
    """
    parts, buf = [], []
    # dividir por encabezados (conservándolos) y por párrafos
    blocks = re.split(r"(?m)^(?=#)", (text or "").strip())
    blocks = [b.strip() for b in blocks if b.strip()]
    for block in blocks:
        for para in re.split(r"\n{2,}", block):
            para = para.strip()
            if not para:
                continue
            if len(para) > max_chars:
                for frag in re.split(r"(?<=[\.\!\?])\s+", para):
                    if len(" ".join(buf)) + len(frag) + 1 > max_chars and buf:
                        parts.append(" ".join(buf).strip()); buf = []
                    buf.append(frag)
            else:
                if len(" ".join(buf)) + len(para) + 1 > max_chars and buf:
                    parts.append(" ".join(buf).strip()); buf = []
                buf.append(para)
    if buf: parts.append(" ".join(buf).strip())
    return parts or [text[:max_chars]]

class SimpleKB:
    """
    Base de conocimiento simple con embeddings E5 (multilingüe) y reranker opcional.
    - Archivos admitidos: .md, .txt en 'kb_dir'.
    - Indexa en kb/_kb_index.json y mantiene embeddings en memoria.
    """
    def __init__(self, kb_dir="kb", model_name="intfloat/multilingual-e5-small"):
        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        # detectar E5 por nombre
        self._uses_e5 = "e5" in model_name.lower()

        # Reranker
        self.reranker = None
        if _CrossEncoder is not None:
            try:
                self.reranker = _CrossEncoder(RERANK_MODEL)
            except Exception:
                self.reranker = None

        self.chunks: list[KBChunk] = []
        self.emb: np.ndarray | None = None
        self._load_index()

    # ---------- Persistencia ----------
    def _load_index(self):
        idx = self.kb_dir / "_kb_index.json"
        if idx.exists():
            data = json.loads(idx.read_text(encoding="utf-8"))
            self.chunks = [KBChunk(**x) for x in data.get("chunks", [])]
            if self.chunks:
                self.emb = self._embed([c.text for c in self.chunks], mode="passage")
        else:
            self.reindex()

    def _save_index(self):
        (self.kb_dir / "_kb_index.json").write_text(
            json.dumps({"chunks": [c.__dict__ for c in self.chunks]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- Embeddings ----------
    def _embed(self, texts: list[str], mode: str) -> np.ndarray:
        """
        mode: "query" | "passage"
        Para E5 se antepone 'query:' / 'passage:' para mejor calidad.
        """
        if self._uses_e5:
            if mode == "query":
                texts = [f"query: {t}" for t in texts]
            else:
                texts = [f"passage: {t}" for t in texts]
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    # ---------- Operaciones ----------
    def reindex(self):
        self.chunks = []
        for p in sorted(self.kb_dir.glob("**/*")):
            if p.is_dir() or p.name.startswith("_"):
                continue
            if p.suffix.lower() not in {".md", ".txt"}:
                continue
            title = p.stem.replace("-", " ").title()
            text = p.read_text(encoding="utf-8", errors="ignore")
            for i, ck in enumerate(_chunk_text(text, max_chars=650)):
                self.chunks.append(KBChunk(doc_id=f"{p.stem}-{i}", title=title, text=ck, path=str(p)))
        self.emb = self._embed([c.text for c in self.chunks], mode="passage") if self.chunks else None
        self._save_index()

    def add_text(self, title: str, text: str) -> str:
        path = self.kb_dir / f"{_slug(title)}.txt"
        path.write_text((text or "").strip() + "\n", encoding="utf-8")
        self.reindex()
        return str(path)

    def list_docs(self):
        seen: dict[str, dict] = {}
        for c in self.chunks:
            seen.setdefault(c.path, {"title": c.title, "chunks": 0})
            seen[c.path]["chunks"] += 1
        return [{"path": k, **v} for k, v in seen.items()]

    def topics(self):
        t = []
        for c in self.chunks:
            if c.title not in t:
                t.append(c.title)
        return t

    # ---------- Búsqueda ----------
    def search(self, query: str, k=4, max_chars=1200):
        """
        Devuelve (contexto, fuentes, best_sim).
        - contexto: string listo para inyectar en el prompt
        - fuentes: títulos únicos de los docs usados
        - best_sim: similitud coseno del mejor párrafo (0..1)
        """
        if not query or self.emb is None or not len(self.chunks):
            return "", [], 0.0

        q = self._embed([query], mode="query")[0]       # [d]
        sims = (self.emb @ q)                           # coseno (embeddings normalizados)

        # Top-N por embedding y luego reranking (opcional)
        prelim = np.argsort(-sims)[: max(12, k)]
        if self.reranker is not None and len(prelim) > k:
            cands = [self.chunks[int(i)].text.strip() for i in prelim]
            try:
                from sentence_transformers.util import batch_to_device  # noqa: F401 (solo asegura dependencia)
                pairs = [(query, c) for c in cands]
                scores = self.reranker.predict(pairs)
                order = np.argsort(-scores)
                prelim = [prelim[i] for i in order]
            except Exception:
                # si falla el reranker, seguimos con el orden por embedding
                pass

        # Armar contexto hasta max_chars
        ctx_parts, sources, total = [], [], 0
        best = float(sims[prelim[0]]) if len(prelim) else 0.0
        for i in prelim:
            c = self.chunks[int(i)]
            part = c.text.strip()
            if total + len(part) > max_chars and total > 0:
                break
            ctx_parts.append(f"[{c.title}] {part}")
            sources.append(c.title)
            total += len(part)
            if len(ctx_parts) >= k:
                break

        # dedupe fuentes manteniendo orden
        seen = set()
        sources = [s for s in sources if not (s in seen or seen.add(s))]
        return "\n\n".join(ctx_parts), sources, best
