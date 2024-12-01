import os
from sklearn.feature_extraction.text import CountVectorizer
import nltk
import re
from nltk.corpus import stopwords
from googletrans import Translator
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from nltk.sentiment import SentimentIntensityAnalyzer
from collections import Counter
from app.utils import load_file

# Initialize the VADER sentiment analyzer for English
sia = SentimentIntensityAnalyzer()

# Baixe a lista de stop words and 
nltk.download("stopwords")
nltk_stop_words = set(stopwords.words("english"))

DEFAULT_DATASET = os.path.join("data", "tripadvisor_hotel_reviews.csv")

def analyze_sentiment(review):
    """
    Split a review into positive and negative parts based on sentiment analysis.

    :param review: str, Input review to analyze
    :return: dict, containing:
        - positive_parts: list of str, Positive sentences from the review
        - negative_parts: list of str, Negative sentences from the review
    """
    # Use VADER for sentiment analysis
    scores = sia.polarity_scores(review)

    # Tranforma compound score em uma base de 0 a 10 e analisa o sentimento
    compound_score = (scores['compound'] + 1) / 2 * 10
    if compound_score >= 9:  # Sentimento positivo
        sentiment = "Positive"
    elif compound_score <= 6:  # Sentimento negativo
        sentiment = "Negative"
    else: # Sentimento neutro
        sentiment = "Neutral"

    # Divide o review em frases
    try:
        sentences = split_review_into_sentences(review)
    except:
        sentences = [review]

    positive_parts = []
    negative_parts = []

    # Analisa o sentimento de cada frase
    for sentence in sentences:
        sentence_scores = sia.polarity_scores(sentence)
        compound_score = sentence_scores['compound']

        # Classifica a frase como positiva ou negativa
        if compound_score >= 0.05:  # Sentimento positivo
            positive_parts.append((sentence, compound_score))  # Adiciona frase e score como tupla
        elif compound_score <= -0.05:  # Sentimento negativo
            negative_parts.append((sentence, compound_score))  # Adiciona frase e score como tupla

    return {
        "scores": scores,
        "sentiment": sentiment,
        "positive_parts": positive_parts,
        "negative_parts": negative_parts
    }

def split_review_into_sentences(review, max_words=20):
    # Divisão inicial por delimitadores comuns de sentenças
    sentences = re.split(r'(?<=[.,;!?])\s*', review)
    
    # Remove strings vazias e espaços desnecessários
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    
    # Divisão adicional para sentenças muito longas
    refined_sentences = []
    for sentence in sentences:
        words = sentence.split()  # Divide a sentença em palavras
        if len(words) > max_words:
            # Quebra em blocos de no máximo max_words palavras
            for i in range(0, len(words), max_words):
                refined_sentences.append(" ".join(words[i:i + max_words]))
        else:
            refined_sentences.append(sentence)
    
    return refined_sentences
    
def calculate_star_rating(scores):
    """
    Calculate a star rating between 1 and 5 based on the compound sentiment score.
    
    :param scores: dict, Sentiment scores from VADER.
    :return: float, Star rating between 1 and 5.
    """
    # Transform compound score from [-1, 1] to [1, 5]
    compound = scores['compound']
    rating = 1 + ((compound + 1) / 2) * 4  # Map to range 1-5
    return round(rating, 4)

def detect_original_language(reviews):
    """
    Determine the predominant language from the first 10 reviews.
    
    :param reviews: list, List of reviews
    :return: str, Detected predominant language code (e.g., "en", "pt")
    """
    detected_languages = []
    for review in reviews[:10]:
        try:
            detected_languages.append(detect(review))
        except LangDetectException:
            continue  # Skip reviews where language detection fails
    if detected_languages:
        # Return the most common language detected
        return Counter(detected_languages).most_common(1)[0][0]
    return "en"  # Default to English if detection fails

# Function to generate most common words for positive and negative parts
def generate_common_words(parts, original_language, translator):
    stop_words = list(nltk_stop_words)
    vectorizer = CountVectorizer(stop_words=stop_words)
    word_counts = vectorizer.fit_transform(parts)
    word_sum = word_counts.sum(axis=0)
    words_freq = [
        (word, word_sum[0, idx])
        for word, idx in vectorizer.vocabulary_.items()
    ]
    most_common_words = sorted(words_freq, key=lambda x: x[1], reverse=True)[:10]

    # Convert most common words to original language
    original_language_words = []
    for word, count in most_common_words:
        try:
            if original_language != "en":
                # Convert to original language
                original_word = translator.translate(word, src="en", dest=original_language).text
            else:
                original_word = word
            original_language_words.append({"word": original_word, "count": count})
        except Exception as e:
            print(f"Error translating word '{word}': {e}")
            original_language_words.append({"word": word, "count": count})
    return original_language_words

def analyze(dataset_path=DEFAULT_DATASET):
    """
    Analyzes the sentiment of hotel reviews, calculates NPS score, and returns
    detailed results, including most common words, sentiment distribution,
    number of reviews, detractors, promoters, and most relevant comments.
    
    Args:
        dataset_path (str): Path to the dataset file (.csv).
    
    Returns:
        dict: Results of the analysis.
    """
    data = load_file(dataset_path)
    reviews = data["Review"]
    sentiments = []
    sentiment_scores = []
    star_ratings = []
    positive_parts = []
    negative_parts = []

    # Detect the predominant language
    original_language = detect_original_language(reviews)

    # Initialize translator
    translator = Translator()

    # Analyze sentiment for each review
    for review in reviews:
        try:
            # Translate non-English reviews to English
            if original_language != "en":
                review = translator.translate(review, src=original_language, dest="en").text
            analyze_result = analyze_sentiment(review)
            sentiment_scores.append(analyze_result['scores'])
            sentiments.append(analyze_result['sentiment'])
            star_rating = calculate_star_rating(analyze_result['scores'])  # Calculate star rating
            star_ratings.append(star_rating)
            for positive_part in analyze_result['positive_parts']:
                positive_parts.append(positive_part)
            for negative_part in analyze_result['negative_parts']:
                negative_parts.append(negative_part)
        except Exception as e:
            print(f"Error analyzing review: {e}")
            sentiments.append("Error")
            sentiment_scores.append({})
            star_ratings.append(3)  # Default to 3 star in case of error

    data["sentiment"] = sentiments
    data["sentiment_scores"] = sentiment_scores
    data["star_rating"] = star_ratings

    # Calculate NPS (Net Promoter Score)
    positive_count = (data["sentiment"] == "Positive").sum()
    negative_count = (data["sentiment"] == "Negative").sum()
    total_reviews = len(data)
    nps_score = ((positive_count - negative_count) / total_reviews) * 100

    # Detractors, Passives, and Promoters
    detractors = data[data["sentiment"] == "Negative"]
    passives = data[data["sentiment"] == "Neutral"]
    promoters = data[data["sentiment"] == "Positive"]

    # Extraindo apenas o texto das tuplas (primeiro elemento)
    positive_sentences = [sentence for sentence, _ in positive_parts]
    negative_sentences = [sentence for sentence, _ in negative_parts]

    positive_common_words = generate_common_words(positive_sentences, original_language, translator)
    negative_common_words = generate_common_words(negative_sentences, original_language, translator)

    # Ordena os comentários positivos e negativos pelas pontuações
    sorted_positive_parts = sorted(positive_parts, key=lambda x: x[1], reverse=True)  # Ordena por score decrescente
    sorted_negative_parts = sorted(negative_parts, key=lambda x: x[1])  # Ordena por score crescente

    # Extrai os 3 comentários mais relevantes (positivos e negativos)
    most_relevant_positive = [comment for comment, score in sorted_positive_parts[:3]]
    most_relevant_negative = [comment for comment, score in sorted_negative_parts[:3]]

    # Calculate the overall star rating (average)
    overall_star_rating = round(sum(star_ratings) / len(star_ratings), 2)

    # Prepare results to be returned
    results = {
        "nps_score": round(nps_score, 2),
        "total_reviews": total_reviews,
        "promoters_count": len(promoters),
        "detractors_count": len(detractors),
        "neutral_count": len(passives),
        "positive_common_words": positive_common_words,
        "negative_common_words": negative_common_words,
        "most_relevant_comments": {
            "positive": most_relevant_positive,
            "negative": most_relevant_negative
        },
        "star_ratings": overall_star_rating,  # Return only the overall rating
    }

    return results
