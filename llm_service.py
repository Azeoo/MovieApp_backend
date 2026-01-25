from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from flask import current_app, jsonify
from logger import LoggerFactory

logger = LoggerFactory.get_logger(__name__)




def get_ai_movie_response(movie_name, release_date):
    logger.info("Generating movie's AI Response")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.3,
        google_api_key=current_app.config["GOOGLE_API_KEY"]
    )

    prompt = PromptTemplate(
        input_variables=["movie_name", "release_date"],
        template="""
    You are a movie expert.

    Movie Name: {movie_name}
    Release Date: {release_date}

    Write a concise and engaging movie description including:
    - Genre
    - Plot summary (no spoilers)
    - Mood and themes
    """
    )

    # LangChain Expression Language (LCEL)
    chain = prompt | llm | StrOutputParser()

    try:
        result = chain.invoke({
            "movie_name": movie_name,
            "release_date": release_date
        })

        return jsonify({
            "movie_name": movie_name,
            "release_date": release_date,
            "description": result
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500