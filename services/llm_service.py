from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from flask import current_app, jsonify
from logger import LoggerFactory
import json
import re

logger = LoggerFactory.get_logger(__name__)


def extract_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if not match:
        raise ValueError("No JSON block found in LLM response")
    return json.loads(match.group(1))


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
You are a movie expert and a strict JSON formatter.

You will be given:
 - Movie Name: {movie_name}
 - Release Date: {release_date}

Your task:
 - Write a 4–5 line concise movie description that clearly conveys:
    Genre
    Spoiler-free plot summary
    Mood and themes

Formatting rules (MANDATORY):
 - Output ONLY valid JSON
 - Follow exactly the structure below
 - Do NOT add extra keys, text, or explanations
 - The description must be a single string with line breaks
 - Box office numbers must be realistic but fictional
 - Revenue would be in Dollar and in Integer
 - Required output format:
    {{
        "description": "4–5 line AI-generated movie description here",
        "box_office_data": {{
            "labels": ["Week 1", "Week 2"..., "Week 6"],
            "revenues": [Week 1 Revenue, Week 2 Revenue..., Week 6 Revenue]
        }}
    }}
    """
    )

    # LangChain Expression Language (LCEL)
    chain = prompt | llm | StrOutputParser()

    try:
        result = chain.invoke({
            "movie_name": movie_name,
            "release_date": release_date
        })

        # logger.info(f"result type : {type(result)}")
        # logger.info(f"Raw Response :\n{result}")

        
        data = extract_json(result)

        description = data["description"]
        box_office_data = data["box_office_data"]

        return jsonify({
            "movie_name": movie_name,
            "release_date": release_date,
            "description": description,
            "box_office_data": box_office_data
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500