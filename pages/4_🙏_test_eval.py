import streamlit as st
import pandas as pd
import json
from datetime import datetime as dt
import pygsheets
from google.oauth2 import service_account
import logging

# --- Our new pipeline orchestrator ---
from modules.rag_pipeline import run_rag_pipeline  # If you stored it differently, adjust the import path

# Logging Modules
from modules.data_logging import DataLogger

# Possibly still need these imports if you do advanced steps:
from modules.semantic_search import semantic_search
from modules.keyword_search import search_with_dynamic_weights_expanded
from modules.reranking import rerank_results
from modules.prompt_loader import load_prompts

# If you want to suppress debug messages globally, uncomment:
# logging.basicConfig(level=logging.WARNING)

# Streamlit App Initialization
st.set_page_config(page_title="RAG Benchmarking", layout="wide")
st.title("RAG Benchmarking and Evaluation Module")

# Google Sheets Client Initialization
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/drive"]
)
gc = pygsheets.authorize(custom_credentials=credentials)

# Optionally set your keys here if needed (though your rag_pipeline may also read from st.secrets):
# openai_api_key = st.secrets["openai_api_key"]
# cohere_api_key = st.secrets["cohere_api_key"]
# gcp_service_account = st.secrets["gcp_service_account"]

# Logger Instances
hays_data_logger = DataLogger(gc=gc, sheet_name="hays_data")
keyword_results_logger = DataLogger(gc=gc, sheet_name="keyword_search_results")
nicolay_data_logger = DataLogger(gc=gc, sheet_name="nicolay_data")
reranking_results_logger = DataLogger(gc=gc, sheet_name="reranking_results")
semantic_results_logger = DataLogger(gc=gc, sheet_name="semantic_search_results")

# Load Prompts into session_state
load_prompts()

# Initialize session state variables
if 'messages' not in st.session_state:
    st.session_state['messages'] = []
if 'response_model_system_prompt' not in st.session_state:
    st.session_state['response_model_system_prompt'] = st.session_state.get('response_model_system_prompt', "")

# Load Benchmark Questions from Google Sheets
try:
    benchmark_sheet = gc.open("benchmark_questions").sheet1
    benchmark_data = pd.DataFrame(benchmark_sheet.get_all_records())
    st.success("Benchmark questions loaded successfully.")
except Exception as e:
    st.error(f"Error loading benchmark questions: {e}")
    benchmark_data = pd.DataFrame()

# Preprocess the 'ideal_documents' column to handle comma-separated values
if not benchmark_data.empty and "ideal_documents" in benchmark_data.columns:
    benchmark_data["ideal_documents"] = benchmark_data["ideal_documents"].apply(
        lambda x: [doc.strip() for doc in x.split(",")] if isinstance(x, str) else []
    )

# Add dropdown to select a benchmark question
if not benchmark_data.empty:
    selected_question_index = st.selectbox(
        "Select a Benchmark Question:",
        options=range(len(benchmark_data)),
        format_func=lambda idx: f"{idx + 1}: {benchmark_data.iloc[idx]['question']}"
    )
else:
    st.warning("No benchmark data available.")
    selected_question_index = None

# Add a button to process the selected question
if selected_question_index is not None and st.button("Run Benchmark Question"):
    # Get the selected question
    row = benchmark_data.iloc[selected_question_index]
    user_query = row["question"]
    expected_documents = row["ideal_documents"]  # Preprocessed list

    # Display the question we're processing
    st.subheader(f"Benchmark Question {selected_question_index + 1}")
    st.write(f"Processing query: {user_query}")

    try:
        # --- 1. Execute the RAG Pipeline ---
        pipeline_results = run_rag_pipeline(
            user_query=user_query,
            perform_keyword_search=True,
            perform_semantic_search=True,
            perform_reranking=True,
            # Provide references to your loggers, so the pipeline can log
            hays_data_logger=hays_data_logger,
            keyword_results_logger=keyword_results_logger,
            nicolay_data_logger=nicolay_data_logger,
            reranking_results_logger=reranking_results_logger,
            semantic_results_logger=semantic_results_logger,
            # Provide the file paths or read from st.secrets if needed
            keyword_json_path='data/voyant_word_counts.json',
            lincoln_speeches_json='data/lincoln_speech_corpus.json',
            lincoln_embedded_csv='lincoln_index_embedded.csv',
            # If you want to pass your keys explicitly:
            # openai_api_key=openai_api_key,
            # cohere_api_key=cohere_api_key,
            #gc=gc  # if you want GSheets access in the pipeline
        )

        # --- 2. Unpack the pipeline results ---
        hay_output = pipeline_results.get("hay_output", {})
        search_results = pipeline_results.get("keyword_results", pd.DataFrame())
        semantic_matches = pipeline_results.get("semantic_results", pd.DataFrame())
        reranked_results = pipeline_results.get("reranked_results", pd.DataFrame())
        nicolay_output = pipeline_results.get("nicolay_output", {})

        # Extract items from hay_output
        initial_answer = hay_output.get("initial_answer", "")
        weighted_keywords = hay_output.get("weighted_keywords", {})
        year_keywords = hay_output.get("year_keywords", [])
        text_keywords = hay_output.get("text_keywords", [])

        # --- 3. Display the Hay Initial Answer ---
        st.write("### Hay's Initial Answer")
        st.markdown(initial_answer)
        # Also optionally show the extracted keywords:
        st.write("**Keywords from Hay**:", weighted_keywords)
        st.write("**Year Keywords**:", year_keywords)
        st.write("**Text Keywords**:", text_keywords)

        # --- 4. Display the RAG Search Results ---
        st.write("### Keyword Search Results")
        st.dataframe(search_results)

        st.write("### Semantic Search Results")
        st.dataframe(semantic_matches)

        st.write("### Reranked Results")
        st.dataframe(reranked_results)

        # --- 5. Compare to Benchmark ---
        st.write("### Benchmark Analysis")
        top_reranked_ids = reranked_results["Text ID"].head(3).tolist() if not reranked_results.empty else []
        matching_expected = len(set(expected_documents) & set(top_reranked_ids))
        st.write(f"Expected documents matched in top 3: {matching_expected}/{len(expected_documents)}")

        # --- 6. Display Nicolay's Final Response ---
        # nicolay_output should be a dict with something like:
        # { "FinalAnswer": {"Text": "...", "References": [...]}, ...}
        final_answer_dict = nicolay_output.get("FinalAnswer", {})
        final_answer_text = final_answer_dict.get("Text", "")

        st.write("### Nicolay's Final Response")
        st.markdown(final_answer_text)

        # If references exist, display them
        references = final_answer_dict.get("References", [])
        if references:
            st.write("**References:**")
            for ref in references:
                st.write(f"- {ref}")

        # --- 7. Optional: Evaluate Nicolay's response with a separate LLM ---
        # You can replicate the old approach if you want:
        """
        evaluation_prompt = st.session_state['response_model_system_prompt']
        # Suppose you have a function that does a final model check:
        # llm_evaluation = evaluate_nicolay_answer(openai_api_key, user_query, initial_answer, final_answer_text)
        # st.write("### LLM Evaluation of Nicolay's Response")
        # st.json(llm_evaluation)
        """

        # --- 8. Log final results, if desired ---
        # For example, in the nicolay_data logger:
        nicolay_data_logger.record_api_outputs({
            'Benchmark Question': user_query,
            'Ideal Documents': expected_documents,
            'Matched Documents': top_reranked_ids,
            'Nicolay_Final_Answer': final_answer_text,
            'Timestamp': dt.now(),
        })

    except Exception as e:
        st.error(f"Error processing query {selected_question_index + 1}: {e}")

# Summary/Visualization or further analysis
st.write("### Summary and Visualization")
st.write("Additional charts or summary metrics can go here.")
