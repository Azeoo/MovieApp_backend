
import json
import re
from flask import current_app, jsonify
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from logger import LoggerFactory

logger = LoggerFactory.get_logger(__name__)


def extract_json(raw: str) -> dict:
    """
    Extract JSON from LLM output. Handles triple backticks.
    Fallbacks to plain json.loads if no backticks found.
    """
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    try:
        if match:
            return json.loads(match.group(1))
        else:
            return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.exception(f"Failed to parse JSON from LLM output:\n{raw}")
        raise ValueError("Invalid JSON format from LLM") from e


def chatbot(user_query: str):
    logger.info(f"Generating movie recommendations for query: {user_query}")

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.3,
            google_api_key=current_app.config["GOOGLE_API_KEY"]
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                    You are a Movie Recommendation Chatbot.

Your purpose is to greet users and recommend movies based on their query. You must ONLY respond to greetings or movie-related requests. If the user asks anything unrelated to movies, politely refuse and say you can only help with movie recommendations.

Behavior Rules:

1. Greetings
- If the user message contains greetings such as "hi", "hello", "hey", or similar, respond with a short friendly greeting and invite them to ask for movie recommendations.

2. Movie Recommendations
- Always recommend exactly 5 movies.
- Never ask questions.
- Never provide explanations, reviews, or extra text beyond the required format.

3. Consider User Context
When recommending movies, analyze the user's query and adapt recommendations accordingly:

- Emotion / Tone:
  If the user expresses emotions (sad, happy, bored, romantic, excited, stressed, etc.), recommend movies that match the mood.

- Genre:
  If the user specifies a genre (e.g., action, comedy, horror, thriller, romance, sci-fi, animation, drama), recommend movies from that genre.

- Runtime Constraint:
  If the user specifies a time limit (e.g., under 120 minutes, less than 2 hours, quick movie), recommend movies that fit within that runtime.

4. Output Format Rules

If runtime is requested or relevant:
<Movie Title> of <runtime> min, <Movie Title> of <runtime> min, <Movie Title> of <runtime> min, <Movie Title> of <runtime> min, <Movie Title> of <runtime> min

If no runtime is requested:
<Movie Title>, <Movie Title>, <Movie Title>, <Movie Title>, <Movie Title>

5. Strict Limitations
- Always output exactly 5 movie titles.
- Do not include numbering, bullet points, descriptions, or commentary.
- Do not answer non-movie-related questions.
- Do not break format.
- Response format plain text only.

Your responses must always remain concise and strictly follow the output format.
                    """
                ),
                ("human", "{user_query}")
            ]
        )

        # LCEL chain: prompt | llm | StrOutputParser
        chain = prompt | llm | StrOutputParser()
        result = chain.invoke({"user_query": user_query})

        logger.info(f"LLM plain text output: {result}")

        # Since output is plain text, return it directly
        return jsonify({
            "success": True,
            "reply": result.strip()  # remove extra whitespace
        }), 200

    except Exception as e:
        logger.exception(f"Error generating movie recommendations:\n{e}")
        return jsonify({
            "success": False,
            "message": "Error while generating response. Try again later."
        }), 500