"""
RAG 检索适配器 — FAISS 向量搜索
"""
import json
import os
import pickle
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 修复 huggingface_hub SSL 证书问题 ──
# 必须在 import sentence_transformers 之前设置
os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFY", "1")

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    HAS_RAG = True
except ImportError:
    HAS_RAG = False


class RAGAdapter:
    """FAISS 多域 RAG 检索"""

    def __init__(self, index_dir: Path, embedding_model: str = "shibing624/text2vec-base-chinese"):
        self.index_dir = Path(index_dir)
        self._model: Optional[SentenceTransformer] = None
        self._indexes: dict = {}
        self._chunks: dict = {}
        self._metadata: dict = {}
        self._domain_names: dict = {}

        if HAS_RAG and self.index_dir.exists():
            try:
                self._load(embedding_model)
            except Exception as e:
                logger.warning(f"RAG 加载失败（网络/SSL 问题？）: {e}")
                logger.warning("RAG 工具将返回 [未加载]")

    def _load(self, embedding_model: str):
        config_path = self.index_dir / "router_config.json"
        if not config_path.exists():
            logger.warning(f"router_config.json 不存在: {config_path}")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        logger.info(f"加载嵌入模型: {embedding_model}")

        # 优先本地缓存，未命中则自动下载（SSL 由模块级 HF_HUB_DISABLE_SSL_VERIFY 处理）
        try:
            self._model = SentenceTransformer(embedding_model, device="cpu",
                                              local_files_only=True)
        except Exception:
            logger.info("本地缓存未命中，从 HuggingFace 下载模型（首次约 1-2 分钟）...")
            self._model = SentenceTransformer(embedding_model, device="cpu")

        for domain, domain_info in config.get("domains", {}).items():
            try:
                faiss_path = self.index_dir / f"{domain}.faiss"
                chunks_path = self.index_dir / f"{domain}_chunks.pkl"
                meta_path = self.index_dir / f"{domain}_meta.pkl"

                if not faiss_path.exists():
                    continue

                self._indexes[domain] = faiss.read_index(str(faiss_path))
                with open(chunks_path, "rb") as f:
                    self._chunks[domain] = pickle.load(f)
                with open(meta_path, "rb") as f:
                    self._metadata[domain] = pickle.load(f)
                self._domain_names[domain] = domain_info.get("name", domain)
                logger.info(f"  域 [{domain}]: {self._indexes[domain].ntotal} 条")
            except Exception as e:
                logger.warning(f"  域 [{domain}] 加载失败: {e}")

    @property
    def is_loaded(self) -> bool:
        return len(self._indexes) > 0

    def search(self, query: str, top_k: int = 3) -> str:
        """搜索并返回格式化文本"""
        if not self.is_loaded:
            return "[RAG索引未加载]"

        try:
            q_emb = self._model.encode(
                [query], convert_to_numpy=True, normalize_embeddings=True
            ).astype(np.float32)
        except Exception as e:
            return f"[编码失败: {e}]"

        all_results = []
        for domain, index in self._indexes.items():
            k = min(top_k * 2, index.ntotal)
            dists, idxs = index.search(q_emb, k)
            for idx, dist in zip(idxs[0], dists[0]):
                if idx < 0 or idx >= len(self._metadata[domain]):
                    continue
                meta = self._metadata[domain][idx]
                all_results.append({
                    "domain": self._domain_names[domain],
                    "title": meta["title"],
                    "content": self._chunks[domain][idx],
                    "score": float(dist),
                })

        all_results.sort(key=lambda x: x["score"], reverse=True)

        # 去重
        seen = set()
        unique = []
        for r in all_results:
            key = r["title"]
            if key not in seen:
                seen.add(key)
                unique.append(r)
                if len(unique) >= top_k:
                    break

        lines = []
        for r in unique:
            lines.append(f"【{r['domain']} - {r['title']}】\n{r['content'][:300]}")

        return "\n\n".join(lines) if lines else "[未找到相关知识]"
