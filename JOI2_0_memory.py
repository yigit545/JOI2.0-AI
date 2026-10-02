import chromadb
import os
from chromadb.utils import embedding_functions
import uuid

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

class JOIMemory:
    def __init__(self, db_path="./joi_memory_db"):
        try:
            self.db = chromadb.PersistentClient(path=db_path)
            self.local_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.db.get_or_create_collection(
                name="joi_knowledge_base",
                embedding_function=self.local_embedding_fn
            )
        except Exception as e:
            print(f"Uyarı: Bellek (ChromaDB) modeli yüklenemedi. İnternet yok veya model hiç indirilmemiş. Hata: {e}")
            self.local_embedding_fn = None
            self.db = None
            self.collection = None

    def add_document(self, text, source_name="unknown"):
        if not self.collection:
            print("[MEMORY ERROR]: Hafıza modülü başlatılamadığı için kayıt yapılamıyor.")
            return False
            
        try:
            self.collection.add(
                documents=[text],
                metadatas=[{"source": source_name}],
                ids=[str(uuid.uuid4())]
            )
            print(f"[MEMORY]: '{source_name}' başarıyla uzun süreli YEREL hafızaya işlendi.")
            return True
        except Exception as e:
            print(f"[MEMORY ERROR]: Yerel kayıt başarısız. Detay: {e}")
            return False

    def recall(self, query, n_results=3, max_distance=1.2):
        if not self.collection:
            return []
            
        try:
            # Sadece dokümanları değil, 'distances' (mesafe) değerlerini de istiyoruz
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "distances"] 
            )

            valid_memories = []
            if results['documents'] and len(results['documents'][0]) > 0:
                docs = results['documents'][0]
                distances = results['distances'][0]
                
                # Sınırın altındaki (yani yeterince alakalı olan) anıları seç
                for doc, dist in zip(docs, distances):
                    if dist < max_distance:
                        valid_memories.append(doc)
                        
            return valid_memories
        except Exception as e:
            print(f"[MEMORY ERROR]: Hatırlama işlemi başarısız. Detay: {e}")
            return []