# modules/colbert_search.py

from ragatouille import RAGPretrainedModel
from sentence_transformers import SentenceTransformer
import pandas as pd
import os
import streamlit as st

class ColBERTSearcher:
    def __init__(self, index_path="data/LincolnCorpus_1"):
        self.index_path = index_path
        self.model = None
        self.lincoln_dict = lincoln_dict
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")

    def load_index(self):
        if not os.path.exists(self.index_path):
            raise FileNotFoundError(f"ColBERT index not found at {self.index_path}")
        self.model = RAGPretrainedModel.from_index(self.index_path)

    def search(self, query, k=5):
        if not self.model:
            self.load_index()

        try:
            results = self.model.search(query=query, k=k)
            processed_results = []
            for result in results:
                doc_id = result['document_id'].replace('Text #: ', '')

                # Get source and summary from lincoln_dict
                lincoln_data = self.lincoln_dict.get(doc_id, {})
                source = lincoln_data.get('source', '')
                summary = lincoln_data.get('summary', '')

                processed_results.append({
                    "text_id": f"Text #: {doc_id}",
                    "colbert_score": float(result['score']),
                    "TopSegment": result['content'],
                    "source": source,
                    "summary": summary,
                    "search_type": "ColBERT"
                })
            return pd.DataFrame(processed_results)
        except Exception as e:
            print(f"ColBERT search error: {str(e)}")
            return pd.DataFrame()

# End colbert_search.py
