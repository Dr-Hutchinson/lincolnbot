import json
import numpy as np
import pandas as pd
from datetime import datetime as dt
from google.oauth2 import service_account
from openai import OpenAI
import cohere
import re
from concurrent.futures import ThreadPoolExecutor
import pygsheets
import streamlit as st
from modules.data_utils import load_lincoln_speech_corpus, load_voyant_word_counts, load_lincoln_index_embedded
import time

class RAGProcess:
    def __init__(self, openai_api_key, cohere_api_key, gcp_service_account, hays_data_logger):
        # Initialize OpenAI and Cohere clients
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.cohere_client = cohere.Client(api_key=cohere_api_key)

        # Initialize Google Sheets client
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = service_account.Credentials.from_service_account_info(gcp_service_account, scopes=scope)
        self.gc = pygsheets.authorize(custom_credentials=credentials)

        # Store the hays_data_logger
        self.hays_data_logger = hays_data_logger

        # Load data using cached functions
        self.lincoln_data = load_lincoln_speech_corpus()
        self.voyant_data = load_voyant_word_counts()
        self.lincoln_index_df = load_lincoln_index_embedded()

    def load_json(self, file_path):
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data

    def get_embedding(self, text, model="text-embedding-ada-002"):
        text = text.replace("\n", " ")
        response = self.openai_client.embeddings.create(input=[text], model=model)
        return np.array(response.data[0].embedding)

    def cosine_similarity(self, vec1, vec2):
        dot_product = np.dot(vec1, vec2)
        norm_vec1 = np.linalg.norm(vec1)
        norm_vec2 = np.linalg.norm(vec2)
        return dot_product / (norm_vec1 * norm_vec2)

    def search_with_dynamic_weights_expanded(self, user_keywords, json_data, year_keywords=None, text_keywords=None, top_n_results=5, lincoln_data=None):
        # Calculate the total number of words for normalization
        total_words = sum(term['rawFreq'] for term in json_data['corpusTerms']['terms'])
        relative_frequencies = {term['term'].lower(): term['rawFreq'] / total_words for term in json_data['corpusTerms']['terms']}

        # Calculate inverse weights based on the relative frequencies
        inverse_weights = {keyword: 1 / relative_frequencies.get(keyword.lower(), 1) for keyword in user_keywords}

        # Normalize weights for dynamic weighting
        max_weight = max(inverse_weights.values())
        normalized_weights = {keyword: (weight / max_weight) * 10 for keyword, weight in inverse_weights.items()}

        results = self.find_instances_expanded_search(
            dynamic_weights=normalized_weights,
            original_weights=user_keywords,
            data=lincoln_data,
            year_keywords=year_keywords,
            text_keywords=text_keywords,
            top_n=top_n_results
        )
        return pd.DataFrame(results)  # Ensure the results are returned as a DataFrame

    def find_instances_expanded_search(self, dynamic_weights, original_weights, data, year_keywords=None, text_keywords=None, top_n=5):
        instances = []

        if text_keywords:
            if isinstance(text_keywords, list):
                text_keywords_list = [keyword.strip().lower() for keyword in text_keywords]
            else:
                text_keywords_list = [keyword.strip().lower() for keyword in text_keywords.split(',')]
        else:
            text_keywords_list = []

        for entry in data:
            if 'full_text' in entry and 'source' in entry:
                entry_text_lower = entry['full_text'].lower()
                source_lower = entry['source'].lower()
                summary_lower = entry.get('summary', '').lower()
                keywords_lower = ' '.join(entry.get('keywords', [])).lower()

                match_source_year = not year_keywords or any(str(year) in source_lower for year in year_keywords)
                match_source_text = not text_keywords or any(re.search(r'\b' + re.escape(keyword.lower()) + r'\b', source_lower) for keyword in text_keywords_list)

                if match_source_year and match_source_text:
                    total_dynamic_weighted_score = 0
                    keyword_counts = {}
                    keyword_positions = {}
                    combined_text = entry_text_lower + ' ' + summary_lower + ' ' + keywords_lower

                    for keyword in original_weights.keys():
                        keyword_lower = keyword.lower()
                        for match in re.finditer(r'\b' + re.escape(keyword_lower) + r'\b', combined_text):
                            count = len(re.findall(r'\b' + re.escape(keyword_lower) + r'\b', combined_text))
                            dynamic_weight = dynamic_weights.get(keyword, 0)
                            if count > 0:
                                keyword_counts[keyword] = count
                                total_dynamic_weighted_score += count * dynamic_weight
                                keyword_index = match.start()
                                original_weight = original_weights[keyword]
                                keyword_positions[keyword_index] = (keyword, original_weight)

                    # Ensure keyword_positions is not empty before calling max()
                    if keyword_positions:
                        highest_original_weighted_position = max(keyword_positions.items(), key=lambda x: x[1][1])[0]
                        context_length = 300
                        start_quote = max(0, highest_original_weighted_position - context_length)
                        end_quote = min(len(entry_text_lower), highest_original_weighted_position + context_length)
                        snippet = entry['full_text'][start_quote:end_quote]
                        instances.append({
                            "text_id": entry['text_id'],
                            "source": entry['source'],
                            "summary": entry.get('summary', ''),
                            "quote": snippet.replace("\n", " "),
                            "weighted_score": total_dynamic_weighted_score,
                            "keyword_counts": keyword_counts
                        })
        instances.sort(key=lambda x: x['weighted_score'], reverse=True)
        return instances  # Ensure this returns a list of dictionaries

    def search_text(self, df, user_query, n=5):
        user_query_embedding = self.get_embedding(user_query)
        df["similarities"] = df['embedding'].apply(lambda x: self.cosine_similarity(x, user_query_embedding))
        top_n = df.sort_values("similarities", ascending=False).head(n)
        top_n["UserQuery"] = user_query  # Add 'UserQuery' column to the DataFrame
        return top_n, user_query_embedding

    def compare_segments_with_query_parallel(self, segments, query_embedding):
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self.get_embedding, segment) for segment in segments]
            segment_embeddings = [future.result() for future in futures]
            return [(segments[i], self.cosine_similarity(segment_embeddings[i], query_embedding)) for i in range(len(segments))]

    def remove_duplicates(self, search_results, semantic_matches):
        combined_results = pd.concat([search_results, semantic_matches])
        deduplicated_results = combined_results.drop_duplicates(subset='text_id', keep='first')
        return deduplicated_results

    def rerank_results(self, user_query, combined_data):
        try:
            combined_data_strs = [cd if isinstance(cd, str) else cd['text'] for cd in combined_data]
            reranked_response = self.cohere_client.rerank(
                model='rerank-english-v2.0',
                query=user_query,
                documents=combined_data_strs,
                top_n=10
            )

            full_reranked_results = []
            for idx, result in enumerate(reranked_response.results):
                combined_data_text = result.document['text'] if isinstance(result.document, dict) and 'text' in result.document else result.document
                data_parts = combined_data_text.split("|")
                if len(data_parts) >= 4:
                    search_type = data_parts[0].strip()
                    text_id_part = data_parts[1].strip()
                    summary = data_parts[2].strip()
                    quote = data_parts[3].strip()

                    text_id = text_id_part.replace("Text ID:", "").replace("Text #:", "").strip()
                    summary = summary.replace("Summary:", "").strip()
                    quote = quote.strip()

                    source = self.lincoln_dict.get(f"Text #: {text_id}", {}).get('source', 'Source information not available')

                    full_reranked_results.append({
                        'Rank': idx + 1,
                        'Search Type': search_type,
                        'Text ID': text_id,
                        'Source': source,
                        'Summary': summary,
                        'Key Quote': quote,
                        'Relevance Score': result.relevance_score
                    })
            return full_reranked_results
        except Exception as e:
            st.write(f"Rerank results error: {e}")
            raise Exception("Error in reranking: " + str(e))

    def get_final_model_response(self, user_query, initial_answer, formatted_input_for_model):
        messages_for_second_model = [
            {"role": "system", "content": response_prompt},
            {"role": "user", "content": f"User Query: {user_query}\n\nInitial Answer: {initial_answer}\n\n{formatted_input_for_model}"}
        ]
        response = self.openai_client.chat.completions.create(
            model="ft:gpt-3.5-turbo-1106:personal::8clf6yi4",
            messages=messages_for_second_model,
            temperature=0,
            max_tokens=2000,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )

        #st.write("Raw final response content:", response.choices[0].message.content)
        return response.choices[0].message.content

    def run_rag_process(self, user_query):
        try:
            start_time = time.time()

            lincoln_data = self.lincoln_data
            keyword_data = self.voyant_data
            df = self.lincoln_index_df

            lincoln_dict = {item['text_id']: item for item in lincoln_data.to_dict('records')}
            self.lincoln_dict = lincoln_dict

            df['embedding'] = df['embedding'].apply(lambda x: list(map(float, x.strip("[]").split(","))))

            df['full_text'] = df['combined'].apply(extract_full_text)

            df['source'], df['summary'] = zip(*df['text_id'].map(lambda text_id: get_source_and_summary(text_id, lincoln_dict)))

            st.write(f"Data loading and preparation took {time.time() - start_time:.2f} seconds.")
            step_time = time.time()

            response = self.openai_client.chat.completions.create(
                model="ft:gpt-3.5-turbo-1106:personal::8XtdXKGK",
                messages=[
                    {"role": "system", "content": keyword_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0,
                max_tokens=500,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )

            st.write(f"Query processed with OpenAI model in {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            api_response_data = json.loads(response.choices[0].message.content)

            initial_answer = api_response_data['initial_answer']
            model_weighted_keywords = api_response_data['weighted_keywords']

            model_year_keywords = api_response_data['year_keywords']
            model_text_keywords = api_response_data['text_keywords']

            hays_data = {
                'query': user_query,
                'initial_answer': initial_answer,
                'weighted_keywords': model_weighted_keywords,
                'year_keywords': model_year_keywords,
                'text_keywords': model_text_keywords,
                'full_output': response.choices[0].message.content
            }

            self.hays_data_logger.record_api_outputs(hays_data)
            st.write(f"Data logged in {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            # Display initial answer
            with st.chat_message("assistant"):
                st.markdown(f"Hays' Response: {initial_answer}")
            st.session_state.messages.append({"role": "assistant", "content": f"Hays' Response: {initial_answer}"})

            # Handle the corpusTerms based on its structure
            corpus_terms_json = keyword_data.at[0, 'corpusTerms']
            if isinstance(corpus_terms_json, str):
                corpus_terms = json.loads(corpus_terms_json)['terms']
            elif isinstance(corpus_terms_json, dict):
                corpus_terms = corpus_terms_json['terms']
            else:
                raise ValueError("Unexpected format for 'corpusTerms'")

            search_results = self.search_with_dynamic_weights_expanded(
                user_keywords=model_weighted_keywords,
                json_data={'corpusTerms': {'terms': corpus_terms}},
                year_keywords=model_year_keywords,
                text_keywords=model_text_keywords,
                top_n_results=5,
                lincoln_data=lincoln_data
            )

            # Debugging statement to check the type of search_results
            st.write(f"Type of search_results: {type(search_results)}")

            if not isinstance(search_results, pd.DataFrame):
                raise ValueError("search_results should be a DataFrame")

            # Log keyword search results
            #log_keyword_search_results(self.hays_data_logger, search_results, user_query, initial_answer, model_weighted_keywords, model_year_keywords, model_text_keywords)

            semantic_matches, user_query_embedding = self.search_text(df, user_query + initial_answer, n=5)

            semantic_matches.rename(columns={df.index.name: 'text_id'}, inplace=True)

            top_segments = []
            for idx, row in semantic_matches.iterrows():
                if not pd.isna(row['full_text']) and row['full_text'].strip() != "":  # Check for empty or NaN 'full_text'
                    segments = segment_text(row['full_text'])
                    segment_scores = self.compare_segments_with_query_parallel(segments, user_query_embedding)
                    if segment_scores:  # Ensure segment_scores is not empty before calling max()
                        top_segment = max(segment_scores, key=lambda x: x[1])
                        top_segments.append(top_segment[0])
                    else:
                        top_segments.append("")  # Add empty string for rows with empty 'full_text'
                else:
                    top_segments.append("")  # Add empty string for rows with empty 'full_text'

            semantic_matches["TopSegment"] = top_segments

            st.write(f"Semantic search completed in {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            deduplicated_results = self.remove_duplicates(search_results, semantic_matches)

            # Ensure any missing columns like 'quote' are added with default values
            if 'quote' not in deduplicated_results.columns:
                deduplicated_results['quote'] = ''

            all_combined_data = [
                f"Keyword|Text ID: {row['text_id']}|Summary: {row['summary']}|{row['quote']}" for idx, row in deduplicated_results.iterrows()
            ] + [
                f"Semantic|Text ID: {row['text_id']}|Summary: {row['summary']}|{row['TopSegment']}" for idx, row in semantic_matches.iterrows()
            ]

            st.write(f"Duplicate removal and result combination took {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            reranked_results = self.rerank_results(user_query, all_combined_data)
            reranked_results_df = pd.DataFrame(reranked_results)

            # Log reranking results
            log_reranking_results(self.hays_data_logger, reranked_results_df, user_query)

            st.write(f"Reranking results took {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            formatted_input_for_model = format_reranked_results_for_model_input(reranked_results)
            final_model_response = self.get_final_model_response(user_query, initial_answer, formatted_input_for_model)

            st.write(f"Final model response generated in {time.time() - step_time:.2f} seconds.")
            step_time = time.time()

            st.write("Generated final model response successfully.")

            return {
                "initial_answer": initial_answer,
                "response": final_model_response,
                "search_results": search_results,
                "semantic_matches": semantic_matches,
                "reranked_results": reranked_results_df,
                "model_weighted_keywords": model_weighted_keywords,
                "model_year_keywords": model_year_keywords,
                "model_text_keywords": model_text_keywords
            }
        except Exception as e:
            st.write(f"Error in run_rag_process: {e}")
            raise Exception("An error occurred during the RAG process.")

# Helper Functions

def extract_full_text(combined_text):
    markers = ["Full Text:\n", "Full Text: \n", "Full Text:"]  # List of potential variations of the marker
    if isinstance(combined_text, str):
        for marker in markers:
            marker_index = combined_text.find(marker)
            if (marker_index != -1):
                # Extract the full text starting from the marker
                full_text = combined_text[marker_index + len(marker):].strip()
                return full_text
        # If none of the markers are found
        return ""
    else:
        return ""

def get_source_and_summary(text_id, lincoln_dict):
    return lincoln_dict.get(text_id, {}).get('source'), lincoln_dict.get(text_id, {}).get('summary')

def format_reranked_results_for_model_input(reranked_results):
    formatted_results = []
    top_three_results = reranked_results[:3]
    for result in top_three_results:
        formatted_entry = f"Match {result['Rank']}: Search Type - {result['Search Type']}, Text ID - {result['Text ID']}, Source - {result['Source']}, Summary - {result['Summary']}, Key Quote - {result['Key Quote']}, Relevance Score - {result['Relevance Score']:.2f}"
        formatted_results.append(formatted_entry)
    return "\n\n".join(formatted_results)

def segment_text(text, segment_size=100):
    words = text.split()
    return [' '.join(words[i:i+segment_size]) for i in range(0, len(words), segment_size)]

# System prompt
def load_prompt(file_name):
    """Load prompt from a file."""
    with open(file_name, 'r') as file:
        return file.read()

# Function to ensure prompts are loaded into session state
def load_prompts():
    if 'keyword_model_system_prompt' not in st.session_state:
        st.session_state['keyword_model_system_prompt'] = load_prompt('prompts/keyword_model_system_prompt.txt')
    if 'response_model_system_prompt' not in st.session_state:
        st.session_state['response_model_system_prompt'] = load_prompt('prompts/response_model_system_prompt.txt')

# Ensure prompts are loaded
load_prompts()

# Now you can use the prompts from session state
keyword_prompt = st.session_state['keyword_model_system_prompt']
response_prompt = st.session_state['response_model_system_prompt']

# Data logging functions


def log_reranking_results(reranking_results_logger, reranked_df, user_query):
    if isinstance(reranked_df, pd.DataFrame):
        now = dt.now()  # Current timestamp

        for idx, row in reranked_df.iterrows():
            record = {
                'Timestamp': now,
                'UserQuery': user_query,
                'Rank': row['Rank'],
                'SearchType': row['Search Type'],
                'TextID': row['Text ID'],
                'KeyQuote': row['Key Quote'],
                'Relevance_Score': row['Relevance Score']
            }
            reranking_results_logger.record_api_outputs(record)
    else:
        raise ValueError("reranked_df should be a DataFrame")

def log_nicolay_model_output(nicolay_data_logger, model_output, user_query, initial_answer, highlight_success_dict):
    """
    Logs the final model output from Nicolay to Google Sheets.
    """
    try:
        # If model_output is a string, we should handle it correctly
        if isinstance(model_output, str):
            model_output = json.loads(model_output)

        # Extract key information from model output
        final_answer_text = model_output.get("FinalAnswer", {}).get("Text", "No response available")
        references = ", ".join(model_output.get("FinalAnswer", {}).get("References", []))

        # User query analysis
        query_intent = model_output.get("User Query Analysis", {}).get("Query Intent", "")
        historical_context = model_output.get("User Query Analysis", {}).get("Historical Context", "")

        # Initial answer review
        answer_evaluation = model_output.get("Initial Answer Review", {}).get("Answer Evaluation", "")
        quote_integration = model_output.get("Initial Answer Review", {}).get("Quote Integration Points", "")

        # Response effectiveness and suggestions
        response_effectiveness = model_output.get("Model Feedback", {}).get("Response Effectiveness", "")
        suggestions_for_improvement = model_output.get("Model Feedback", {}).get("Suggestions for Improvement", "")

        # Match analysis - concatenating details of each match into single strings
        match_analysis = model_output.get("Match Analysis", {})
        match_fields = ['Text ID', 'Source', 'Summary', 'Key Quote', 'Historical Context', 'Relevance Assessment']
        match_data = {}

        for match_key, match_details in match_analysis.items():
            match_info = [f"{field}: {match_details.get(field, '')}" for field in match_fields]
            match_data[match_key] = "; ".join(match_info)  # Concatenate with a separator

            if 'speech' in match_details:
                highlight_success_dict[match_key] = match_details['speech']
            else:
                highlight_success_dict[match_key] = False

        # Meta analysis
        meta_strategy = model_output.get("Meta Analysis", {}).get("Strategy for Response Composition", {})
        meta_synthesis = model_output.get("Meta Analysis", {}).get("Synthesis", "")

        # Construct a record for logging
        record = {
            'Timestamp': dt.now(),
            'UserQuery': user_query,
            'initial_Answer': initial_answer,
            'FinalAnswer': final_answer_text,
            'References': references,
            'QueryIntent': query_intent,
            'HistoricalContext': historical_context,
            'AnswerEvaluation': answer_evaluation,
            'QuoteIntegration': quote_integration,
            **match_data,  # Unpack match data into the record
            'MetaStrategy': str(meta_strategy),  # Convert dictionary to string if needed
            'MetaSynthesis': meta_synthesis,
            'ResponseEffectiveness': response_effectiveness,
            'Suggestions': suggestions_for_improvement
        }

        # Add highlight success information for each match
        for match_key, success in highlight_success_dict.items():
            record[f'{match_key}_HighlightSuccess'] = success

        # Log the record
        nicolay_data_logger.record_api_outputs(record)

    except Exception as e:
        st.error(f"Error in logging Nicolay model output: {e}")
