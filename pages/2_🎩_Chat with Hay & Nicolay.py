import streamlit as st
from modules.rag_process import RAGProcess
from modules.data_logging import DataLogger, log_keyword_search_results, log_semantic_search_results, log_reranking_results, log_nicolay_model_output
import json
import os
from openai import OpenAI
import cohere
import pygsheets
from google.oauth2 import service_account

# Streamlit app setup
st.set_page_config(
    page_title="Nicolay: Exploring the Speeches of Abraham Lincoln with AI (version 0.2)",
    layout='wide',
    page_icon='🎩'
)

# Initialize API clients
os.environ["OPENAI_API_KEY"] = st.secrets["openai_api_key"]
openai_api_key = st.secrets["openai_api_key"]
client = OpenAI(api_key=openai_api_key)

os.environ["CO_API_KEY"] = st.secrets["cohere_api_key"]
cohere_api_key = st.secrets["cohere_api_key"]
co = cohere.Client(api_key=cohere_api_key)

# Extract Google Cloud service account details
gcp_service_account = st.secrets["gcp_service_account"]
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials = service_account.Credentials.from_service_account_info(gcp_service_account, scopes=scope)
gc = pygsheets.authorize(custom_credentials=credentials)

# Initialize DataLogger objects
hays_data_logger = DataLogger(gc, 'hays_data')
keyword_results_logger = DataLogger(gc, 'keyword_search_results')
semantic_results_logger = DataLogger(gc, 'semantic_search_results')
reranking_results_logger = DataLogger(gc, 'reranking_results')
nicolay_data_logger = DataLogger(gc, 'nicolay_data')

# Initialize the RAG Process
rag = RAGProcess(openai_api_key, cohere_api_key, gcp_service_account, hays_data_logger)

# Streamlit Chatbot Interface
st.title("Chat with Hays and Nicolay - in development")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("Ask me anything about Abraham Lincoln's speeches:"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        # Process the user query
        st.write("Processing your query...")
        results = rag.run_rag_process(prompt)

        # Unpack the results
        response = results["response"]
        initial_answer = results["initial_answer"]
        final_answer = results["FinalAnswer"]

        # Display initial answer
        with st.chat_message("assistant"):
            st.markdown(f"Initial Answer: {initial_answer}")
        st.session_state.messages.append({"role": "assistant", "content": f"Initial Answer: {initial_answer}"})

        # Display final answer
        with st.chat_message("assistant"):
            st.markdown(f"Final Answer: {final_answer['Text']}")
        st.session_state.messages.append({"role": "assistant", "content": f"Final Answer: {final_answer['Text']}"})

        # Log the data
        search_results = results["search_results"]
        semantic_matches = results["semantic_matches"]
        reranked_results = results["reranked_results"]
        model_weighted_keywords = results["model_weighted_keywords"]
        model_year_keywords = results["model_year_keywords"]
        model_text_keywords = results["model_text_keywords"]

        log_keyword_search_results(keyword_results_logger, search_results, prompt, initial_answer, model_weighted_keywords, model_year_keywords, model_text_keywords)
        log_semantic_search_results(semantic_results_logger, semantic_matches, initial_answer)
        log_reranking_results(reranking_results_logger, reranked_results, prompt)
        log_nicolay_model_output(nicolay_data_logger, json.loads(response), prompt, initial_answer, {})

    except Exception as e:
        st.error(f"An error occurred: {e}")
