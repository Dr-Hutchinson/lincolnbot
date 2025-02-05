from ragatouille import RAGPretrainedModel
from sentence_transformers import SentenceTransformer
import pandas as pd
import os
from modules.data_utils import load_lincoln_speech_corpus
import streamlit as st

class ColBERTSearcher:
    def __init__(self, index_path="data/LincolnCorpus_1", lincoln_dict=None):
        self.index_path = index_path
        self.model = None
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")

        if lincoln_dict is None:
            lincoln_data_df = load_lincoln_speech_corpus()
            lincoln_data = lincoln_data_df.to_dict("records")
            # Don't modify the text_id when creating dictionary
            self.lincoln_dict = {item['text_id']: item for item in lincoln_data}
        else:
            self.lincoln_dict = lincoln_dict

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
                # Match the format in lincoln_dict
                doc_id = f"Text #: {result['document_id'].replace('Text #: ', '')}"
                lincoln_data = self.lincoln_dict.get(doc_id, {})

                processed_results.append({
                    "text_id": result['document_id'],
                    "colbert_score": float(result['score']),
                    "TopSegment": result['content'],
                    "source": lincoln_data.get('source', ''),
                    "summary": lincoln_data.get('summary', ''),
                    "search_type": "ColBERT"
                })

            return pd.DataFrame(processed_results)

        except Exception as e:
            st.write(f"ColBERT search error: {str(e)}")
            return pd.DataFrame()
