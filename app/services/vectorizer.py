import os
import sys
import json
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from app.core.config import EMBEDDING_MODEL_NAME, CHROMA_DIR, BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")

def create_vector_database(json_file_path, db_directory):
    print(f"⏳ در حال بارگذاری مدل Embedding: {EMBEDDING_MODEL_NAME}...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    
    print("✅ مدل بارگذاری شد. در حال خواندن فایل قطعات (Chunks)...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
        
    texts_to_embed = [chunk['text'] for chunk in chunks]
    
    print(f"⏳ در حال تولید بردار برای {len(texts_to_embed)} قطعه...")
    embeddings = model.encode(texts_to_embed, batch_size=64, show_progress_bar=True).tolist()
    
    print("⏳ در حال اتصال به ChromaDB...")
    chroma_client = chromadb.PersistentClient(
        path=db_directory,
        settings=Settings(anonymized_telemetry=False)
    )
    
    collection_name = "university_rules"
    
    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"🗑️ کلکسیون قدیمی '{collection_name}' پاکسازی شد.")
    except ValueError:
        pass
    
    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    
    ids = [str(chunk['chunk_id']) for chunk in chunks]
    metadatas = []
    
    for chunk in chunks:
        meta = {
            "type": str(chunk.get("type", "unknown")),
            "section": str(chunk.get("section", "unknown"))
        }
        try:
            if "article_number" in chunk and chunk["article_number"]:
                meta["article_number"] = int(chunk["article_number"])
            if "tabsareh_number" in chunk and chunk["tabsareh_number"]:
                meta["tabsareh_number"] = int(chunk["tabsareh_number"])
        except ValueError:
            if "article_number" in chunk: meta["article_number_str"] = str(chunk["article_number"])
            if "tabsareh_number" in chunk: meta["tabsareh_number_str"] = str(chunk["tabsareh_number"])
            
        metadatas.append(meta)

    print("🚀 در حال تزریق داده‌ها به دیتابیس برداری (به صورت دسته‌ای)...")
    
    CHROMA_BATCH_SIZE = 1000
    
    for i in range(0, len(ids), CHROMA_BATCH_SIZE):
        end_idx = min(i + CHROMA_BATCH_SIZE, len(ids))
        collection.add(
            ids=ids[i:end_idx],
            embeddings=embeddings[i:end_idx],
            documents=texts_to_embed[i:end_idx],
            metadatas=metadatas[i:end_idx]
        )
        print(f"   > تزریق دسته {i} تا {end_idx} با موفقیت انجام شد.")
    
    print(f"\n🎉 عملیات با موفقیت پایان یافت!")
    print(f"📊 تعداد کل قطعات ایندکس شده: {len(ids)}")
    print(f"📁 مسیر دیتابیس: {db_directory}")

if __name__ == "__main__":
    
    os.makedirs(CHROMA_DIR, exist_ok=True)
    
    input_json = os.path.join(DATA_DIR, "Rules_chunks.json")
    output_db_dir = CHROMA_DIR

    try:
        if not os.path.exists(input_json):
            raise FileNotFoundError(f"فایل قطعات پیدا نشد: {input_json}")
            
        create_vector_database(input_json, output_db_dir)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        sys.exit(1)