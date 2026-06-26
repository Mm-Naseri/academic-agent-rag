import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from app.core.config import EMBEDDING_MODEL_NAME, CHROMA_DIR
from rank_bm25 import BM25Okapi
import hazm

class HybridRulesRetriever:
    def __init__(self, db_directory=CHROMA_DIR, collection_name="university_rules"):
        print("⏳ در حال بارگذاری مدل‌ها و ساخت ایندکس جستجوی ترکیبی...")
        
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self.chroma_client = chromadb.PersistentClient(
            path=db_directory, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_collection(name=collection_name)
        
        all_data = self.collection.get(include=['documents', 'metadatas'])
        
        self.doc_map = {
            doc_id: {'text': text, 'meta': meta}
            for doc_id, text, meta in zip(all_data['ids'], all_data['documents'], all_data['metadatas'])
        }
        self.all_ids = all_data['ids']
        
        self.word_tokenizer = hazm.WordTokenizer()
        
        tokenized_corpus = [self._tokenize(doc) for doc in all_data['documents']]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        print(f"✅ سیستم Hybrid آماده است! (تعداد کل قطعات: {len(self.all_ids)})\n" + "-"*40)

    def _tokenize(self, text):
        return self.word_tokenizer.tokenize(text)

    def search(self, semantic_query: str, keyword_query: str, top_k: int = 7, metadata_filter: dict = None):
        query_embedding = self.model.encode([semantic_query], show_progress_bar=False).tolist()
        vector_results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k * 2,
            where=metadata_filter
        )
        vector_ids = vector_results['ids'][0] if vector_results['ids'] else []
        
        bm25_target = keyword_query if keyword_query.strip() else semantic_query
        tokenized_query = self._tokenize(bm25_target)
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        valid_indices_and_scores = []
        for i, doc_id in enumerate(self.all_ids):
            if not metadata_filter or all(self.doc_map[doc_id]['meta'].get(k) == v for k, v in metadata_filter.items()):
                score = bm25_scores[i]
                if score > 0:
                    valid_indices_and_scores.append((doc_id, score))
                    
        valid_indices_and_scores.sort(key=lambda x: x[1], reverse=True)
        bm25_ids = [doc_id for doc_id, _ in valid_indices_and_scores[:top_k * 2]]

        rrf_scores = {}
        k_constant = 60
        
        vector_weight = 1.0
        bm25_weight = 1.5

        for rank, doc_id in enumerate(vector_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (vector_weight / (k_constant + rank + 1))
            
        for rank, doc_id in enumerate(bm25_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (bm25_weight / (k_constant + rank + 1))
            
        final_ranked_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
        
        final_results = []
        for doc_id in final_ranked_ids:
            meta = self.doc_map[doc_id]['meta']
            doc_type = meta.get('type')
            if doc_type == 'ماده':
                title = f"ماده {meta.get('article_number', '?')}"
            elif doc_type == 'تبصره':
                title = f"تبصره {meta.get('tabsareh_number', '?')} از ماده {meta.get('article_number', '?')}"
            elif doc_type == 'تعریف':
                title = "تعاریف"
            else:
                title = "بخش نامشخص"

            final_results.append({
                'id': doc_id,
                'title': title,
                'text': self.doc_map[doc_id]['text'],
                'score': round(rrf_scores[doc_id], 4)
            })

        return final_results