# modules/data_logging.py

from datetime import datetime as dt
import pandas as pd
import json

class DataLogger:
    def __init__(self, gc, sheet_name):
        self.gc = gc
        self.sheet = self.gc.open(sheet_name).sheet1

    def record_api_outputs(self, data_dict):
        now = dt.now()
        data_dict['Timestamp'] = now  # Add timestamp to the data

        # Convert the data dictionary to a DataFrame
        df = pd.DataFrame([data_dict])

        # Find the next empty row in the sheet to avoid overwriting existing data
        end_row = len(self.sheet.get_all_records()) + 2

        # Append the new data row to the sheet
        self.sheet.set_dataframe(df, (end_row, 1), copy_head=False, extend=True)

def log_keyword_search_results(keyword_results_logger, search_results, user_query, initial_answer, model_weighted_keywords, model_year_keywords, model_text_keywords):
    now = dt.now()  # Current timestamp

    for idx, result in search_results.iterrows():
        # Create a record for each search result
        record = {
            'Timestamp': now,
            'UserQuery': user_query,
            "initial_Answer": initial_answer,
            'Weighted_Keywords': model_weighted_keywords,
            'Year_Keywords': model_year_keywords,
            'Text_Keywords': model_text_keywords,
            'TextID': result['text_id'],
            'KeyQuote': result['key_quote'],
            'WeightedScore': result['weighted_score'],
            'KeywordCounts': json.dumps(result['keyword_counts'])  # Convert dict to JSON string
        }

        # Log the record
        keyword_results_logger.record_api_outputs(record)

def log_semantic_search_results(semantic_results_logger, semantic_matches, initial_answer):
    now = dt.now()  # Current timestamp

    for idx, row in semantic_matches.iterrows():
        record = {
            'Timestamp': now,
            'UserQuery': row['UserQuery'],
            'HyDE_Query': initial_answer,
            'TextID': row['text_id'],  # Assuming 'text_id' is correct
            'SimilarityScore': row['similarities'],
            'TopSegment': row['TopSegment']
        }

        # Log the record
        semantic_results_logger.record_api_outputs(record)

def log_reranking_results(reranking_results_logger, reranked_df, user_query):
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

        # Log the record
        reranking_results_logger.record_api_outputs(record)

def log_nicolay_model_output(nicolay_data_logger, model_output, user_query, initial_answer, highlight_success_dict):
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

        if match_key in highlight_success_dict:
            # Add highlight success flag if available
            match_data[f'{match_key}_HighlightSuccess'] = highlight_success_dict[match_key]

    # Meta analysis
    meta_strategy = model_output.get("Meta Analysis", {}).get("Strategy for Response Composition", {})
    meta_synthesis = model_output.get("Meta Analysis", {}).get("Synthesis", "")

    # Construct a record for logging
    record = {
        'Timestamp': dt.now(),
        'UserQuery': user_query,
        'Initial_Answer': initial_answer,
        'FinalAnswer': final_answer_text,
        'References': references,
        'QueryIntent': query_intent,
        'HistoricalContext': historical_context,
        'AnswerEvaluation': answer_evaluation,
        'QuoteIntegration': quote_integration,
        'MetaStrategy': str(meta_strategy),  # Convert dictionary to string if needed
        'MetaSynthesis': meta_synthesis,
        'ResponseEffectiveness': response_effectiveness,
        'Suggestions': suggestions_for_improvement
    }

    # Unpack match_data into the record
    record.update(match_data)

    # Log the record
    nicolay_data_logger.record_api_outputs(record)
