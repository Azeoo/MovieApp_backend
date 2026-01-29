import os
import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from flask import current_app, jsonify
from logger import LoggerFactory


logger = LoggerFactory.get_logger(__name__)


def extract_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if not match:
        raise ValueError("No JSON block found in LLM response")
    return json.loads(match.group(1))

def generate_quiz_questions(username:str):

    logger.info(f"Generating Quiz questions...!!!")
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.3,
        google_api_key=current_app.config["GOOGLE_API_KEY"]
    )


    prompt = PromptTemplate(
        template="""
        You are a quiz generator.

        Generate exactly 5 quiz questions related to Hollywood and Bollywood movies.

        Rules:
        - Each question must have exactly 4 options
        - Provide the correct option clearly
        - Response MUST be valid JSON only
        - Do NOT add explanations or extra text

        JSON format:
        {{
            "quiz": [
                {{
                "question": "Question text",
                "options": {{
                    "A": "Option 1",
                    "B": "Option 2",
                    "C": "Option 3",
                    "D": "Option 4"
                }},
                "correct_answer": "A"
                }}
            ]
        }}
    """
    )

    parser = StrOutputParser()

    chain = prompt | llm | parser

    try:
        logger.info(f"In try block...!!!")
        result = chain.invoke({})

        logger.info(f"result type : {type(result)}")
        logger.info(f"Raw Response :\n{result}")

        
        data = extract_json(result)
        logger.info(f"Type of data : {type(data)}")

        logger.info(f"Data :\n{data}")

        return jsonify({
            "username":username,
            "quiz":data["quiz"]
        }), 201

    except Exception as e:
        logger.exception(f"Error while preparing Quiz for you. Try again after sometime :\n{e}")
        return jsonify({
            "success":False,
            "message":"Error while preparing Quiz for you. Try again after sometime"
        }), 500
