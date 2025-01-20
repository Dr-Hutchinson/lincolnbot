# modules/reranking.py

import cohere
import pandas as pd
import streamlit as st

# In reranking.py
def prepare_documents_for_reranking(combined_df, user_query, max_length=1000):
    """
    Prepares documents for Cohere's reranking in the correct format.
    """
    documents = []

    st.write("Preparing documents from DataFrame columns:")
    st.write(combined_df.columns.tolist())

    for idx, row in combined_df.iterrows():
        try:
            # Determine search type
            search_type = "Keyword" if "key_quote" in row and pd.notna(row["key_quote"]) else "Semantic"

            # Get text ID
            text_id = str(row.get("text_id", ""))

            # Get summary
            summary = str(row.get("summary", ""))[:200]

            # Get quote
            quote = str(row.get("key_quote" if search_type == "Keyword" else "TopSegment", ""))[:max_length]

            # Create document object
            doc = {
                "text": f"{search_type}|{text_id}|{summary}|{quote}".strip(),
                "id": str(idx)
            }

            # Debug document creation
            st.write(f"Created document {idx}:")
            st.write(doc)

            documents.append(doc)

        except Exception as e:
            st.error(f"Error preparing document {idx}: {str(e)}")
            continue

    return documents


def rerank_results(query, documents, cohere_client, model='rerank-english-v2.0', top_n=10):
    """
    Reranks documents using Cohere's reranking API with improved error handling.
    """
    try:
        # Verify inputs
        if not documents:
            raise ValueError("No documents provided for reranking")

        if not isinstance(query, str) or len(query.strip()) == 0:
            raise ValueError("Invalid query")

        # Debug document format
        st.write("Documents being sent to Cohere:")
        for doc in documents:
            st.write(f"Document: {doc}")

        # Call Cohere API
        reranked = cohere_client.rerank(
            query=query,
            documents=[d['text'] for d in documents],  # Extract just the text strings
            model=model,
            top_n=top_n
        )

        # Process results
        reranked_data = []
        for rank, result in enumerate(reranked.results, 1):
            try:
                # Get the original document text
                doc_text = result.document

                # Parse the document text safely
                doc_parts = doc_text.split('|')
                if len(doc_parts) >= 4:
                    search_type = doc_parts[0].strip()
                    text_id = doc_parts[1].strip()
                    summary = doc_parts[2].strip()
                    quote = doc_parts[3].strip()

                    reranked_data.append({
                        'Rank': rank,
                        'Search Type': search_type,
                        'Text ID': text_id,
                        'Summary': summary,
                        'Key Quote': quote,
                        'Relevance Score': result.relevance_score
                    })

                    # Debug successful parsing
                    st.write(f"Successfully processed result {rank}")

            except Exception as e:
                st.error(f"Error processing reranked result {rank}: {str(e)}")
                continue

        # Debug final results
        st.write(f"Created {len(reranked_data)} valid results")

        return pd.DataFrame(reranked_data)

    except Exception as e:
        st.error(f"Reranking error: {str(e)}")
        return pd.DataFrame()


def format_reranked_results_for_model_input(reranked_results):
    """
    Formats reranked results for input to the Nicolay model.
    """
    formatted_results = []
    top_three = reranked_results.head(3)

    for _, row in top_three.iterrows():
        formatted_entry = (
            f"Match {row['Rank']}: "
            f"Search Type - {row['Search Type']}, "
            f"Text ID - {row['Text ID']}, "
            f"Source - {row.get('Source', 'N/A')}, "
            f"Summary - {row['Summary']}, "
            f"Key Quote - {row['Key Quote']}, "
            f"Relevance Score - {row['Relevance Score']:.2f}"
        )
        formatted_results.append(formatted_entry)

    return "\n\n".join(formatted_results)
