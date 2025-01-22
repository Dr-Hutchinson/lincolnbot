# modules/data_logging.py

import pygsheets
import pandas as pd
from datetime import datetime as dt
import json
import streamlit as st

class DataLogger:
    def __init__(self, gc, sheet_name):
        self.gc = gc
        self.sheet = self.gc.open(sheet_name).sheet1

    def record_api_outputs(self, data_dict):
        """
        Records a dictionary of data to the specified Google Sheet.

        Parameters:
        - data_dict (dict): Dictionary containing data to log.
        """
        now = dt.now()
        data_dict['Timestamp'] = now  # Add timestamp to the data

        # Convert the data dictionary to a DataFrame
        df = pd.DataFrame([data_dict])

        # Find the next empty row in the sheet to avoid overwriting existing data
        end_row = len(self.sheet.get_all_records()) + 2

        # Append the new data row to the sheet
        self.sheet.set_dataframe(df, (end_row, 1), copy_head=False, extend=True)

def log_keyword_search_results(keyword_results_logger, search_results, user_query, initial_answer, model_weighted_keywords, model_year_keywords, model_text_keywords):
    """
    Logs the keyword search results to Google Sheets.

    Parameters:
    - keyword_results_logger (DataLogger): Instance of DataLogger for keyword search.
    - search_results (pd.DataFrame): DataFrame containing keyword search results.
    - user_query (str): The user's search query.
    - initial_answer (str): The initial answer generated by the model.
    - model_weighted_keywords (dict): Weighted keywords generated by the model.
    - model_year_keywords (list): Year keywords generated by the model.
    - model_text_keywords (list): Text keywords generated by the model.
    """
    now = dt.now()  # Current timestamp

    for idx, result in search_results.iterrows():
        # Ensure 'KeyQuote' is a string
        key_quote = result.get('quote', "")
        if pd.isna(key_quote) or not isinstance(key_quote, str):
            key_quote = "No key quote available."

        # Create a record for each search result
        record = {
            'Timestamp': now,
            'UserQuery': user_query,
            "initial_Answer": initial_answer,
            'Weighted_Keywords': json.dumps(model_weighted_keywords),  # Convert dict to JSON string
            'Year_Keywords': json.dumps(model_year_keywords),
            'Text_Keywords': json.dumps(model_text_keywords),
            'TextID': result['text_id'],
            'KeyQuote': key_quote,
            'WeightedScore': result['weighted_score'],
            'KeywordCounts': json.dumps(result['keyword_counts'])  # Convert dict to JSON string
        }

        # Log the record
        keyword_results_logger.record_api_outputs(record)

def log_semantic_search_results(semantic_results_logger, semantic_matches, initial_answer=None):
    """
    Logs the semantic search results to Google Sheets.

    Parameters:
    - semantic_results_logger (DataLogger): Instance of DataLogger for semantic search.
    - semantic_matches (pd.DataFrame): DataFrame containing semantic search results.
    - initial_answer (str, optional): Initial answer from Hay model.
    """
    now = dt.now()  # Current timestamp

    for idx, row in semantic_matches.iterrows():
        record = {
            'Timestamp': now,
            'UserQuery': row.get('UserQuery', ''),
            'HyDE_Query': initial_answer if initial_answer else '',  # Use passed initial_answer
            'TextID': row.get('text_id', row.get('Unnamed: 0', '')),  # Try both column names
            'SimilarityScore': row.get('similarities', 0.0),
            'TopSegment': row.get('TopSegment', '')
        }
        semantic_results_logger.record_api_outputs(record)

def log_reranking_results(reranking_results_logger, reranked_df, user_query):
    """
    Logs the reranking results to Google Sheets.

    Parameters:
    - reranking_results_logger (DataLogger): Instance of DataLogger for reranking.
    - reranked_df (pd.DataFrame): DataFrame containing reranked results.
    - user_query (str): Original user query.
    """
    now = dt.now()  # Current timestamp

    for idx, row in reranked_df.iterrows():
        record = {
            'Timestamp': now,
            'UserQuery': user_query,
            'Rank': row.get('Rank', ''),
            'SearchType': row.get('Search Type', ''),
            'TextID': row.get('Text ID', ''),
            'KeyQuote': row.get('Key Quote', ''),
            'Relevance_Score': row.get('Relevance Score', 0.0)
        }

        # Log the record
        reranking_results_logger.record_api_outputs(record)

def log_nicolay_model_output(nicolay_data_logger, model_output, user_query, highlight_success_dict, initial_answer):
    final_answer_text = model_output.get("FinalAnswer", {}).get("Text", "No response available")
    references = ", ".join(model_output.get("FinalAnswer", {}).get("References", []))

    # User Query Analysis
    user_query_analysis = model_output.get("User Query Analysis", {})
    query_intent = user_query_analysis.get("Query Intent", "")
    historical_context = user_query_analysis.get("Historical Context", "")

    # Initial Answer Review
    initial_review = model_output.get("Initial Answer Review", {})
    answer_evaluation = initial_review.get("Answer Evaluation", "")
    quote_integration = initial_review.get("Quote Integration Points", "")

    # Match Analysis
    match_analysis = model_output.get("Match Analysis", {})
    match_1 = json.dumps(match_analysis.get("RerankedMatch1", {}))
    match_2 = json.dumps(match_analysis.get("RerankedMatch2", {}))
    match_3 = json.dumps(match_analysis.get("RerankedMatch3", {}))

    # Meta Analysis
    meta_analysis = model_output.get("Meta Analysis", {})
    synthesis = meta_analysis.get("Synthesis", "")

    # Model Feedback
    model_feedback = model_output.get("Model Feedback", {})
    response_effectiveness = model_feedback.get("Response Effectiveness", "")
    suggestions = model_feedback.get("Suggestions for Improvement", "")

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
        'Match1Analysis': match_1,
        'Match2Analysis': match_2,
        'Match3Analysis': match_3,
        'MetaAnalysis': json.dumps(meta_analysis),
        'Synthesis': synthesis,
        'ResponseEffectiveness': response_effectiveness,
        'SuggestionsImprovement': suggestions
    }

    nicolay_data_logger.record_api_outputs(record)

def log_benchmark_results(benchmark_logger, user_query, expected_documents,
                        bleu_rouge_results, llm_results, reranked_results):
    """
    Logs benchmark evaluation results to Google Sheets.

    Parameters:
    - benchmark_logger (DataLogger): Instance of DataLogger for benchmark results
    - user_query (str): The user's query
    - expected_documents (list): List of expected document IDs
    - bleu_rouge_results (dict): Results from BLEU/ROUGE evaluation
    - llm_results (dict): Results from LLM evaluation
    - reranked_results (pd.DataFrame): Reranked search results
    """
    # Extract BLEU/ROUGE scores
    aggregate_scores = bleu_rouge_results.get('aggregate_scores', {})
    retrieval_metrics = bleu_rouge_results.get('retrieval_metrics', {})

    # Extract LLM evaluation scores
    eval_scores = llm_results.get('evaluation_scores', {})
    overall_assessment = llm_results.get('overall_assessment', {})

    # Get top retrieved documents
    top_retrieved = reranked_results['Text ID'].head(3).tolist() if not reranked_results.empty else []

    # Create benchmark record
    record = {
        'Timestamp': dt.now(),
        'Query': user_query,
        'ExpectedDocuments': json.dumps(expected_documents),
        'RetrievedDocuments': json.dumps(top_retrieved),

        # BLEU/ROUGE Metrics
        'BLEU_Score': aggregate_scores.get('bleu_score', 0),
        'ROUGE1_Score': aggregate_scores.get('rouge1_score', 0),
        'ROUGE_L_Score': aggregate_scores.get('rougeL_score', 0),

        # Retrieval Metrics
        'MRR': retrieval_metrics.get('mrr', 0),
        'NDCG': retrieval_metrics.get('ndcg', 0),
        'Precision_at_1': retrieval_metrics.get('P@1', 0),
        'Precision_at_3': retrieval_metrics.get('P@3', 0),
        'Recall_at_1': retrieval_metrics.get('R@1', 0),
        'Recall_at_3': retrieval_metrics.get('R@3', 0),

        # LLM Evaluation Scores
        'QueryResponse_Score': eval_scores.get('query_response_quality', {}).get('score', 0),
        'QuoteUsage_Score': eval_scores.get('quote_usage', {}).get('score', 0),
        'CitationAccuracy_Score': eval_scores.get('citation_accuracy', {}).get('score', 0),
        'SourceIntegration_Score': eval_scores.get('source_integration', {}).get('score', 0),
        'HistoricalContext_Score': eval_scores.get('historical_context', {}).get('score', 0),
        'ResponseStructure_Score': eval_scores.get('response_structure', {}).get('score', 0),

        # Overall LLM Assessment
        'TotalLLMScore': overall_assessment.get('total_score', 0),
        'Strengths': json.dumps(overall_assessment.get('strengths', [])),
        'Weaknesses': json.dumps(overall_assessment.get('weaknesses', [])),
        'ImprovementPriorities': json.dumps(overall_assessment.get('improvement_priorities', [])),

        # Document Match Statistics
        'MatchedDocumentCount': len(set(expected_documents) & set(top_retrieved)),
        'TotalExpectedDocs': len(expected_documents),
        'TotalRetrievedDocs': len(top_retrieved)
    }

    # Log the record
    benchmark_logger.record_api_outputs(record)
