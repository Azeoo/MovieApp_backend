from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from flask_cors import CORS
import bcrypt
from datetime import datetime, UTC
from logger import LoggerFactory
from config import Config
from llm_service import get_ai_movie_response

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
mongo = PyMongo(app)
jwt = JWTManager(app)

users_collection = mongo.db.users

#Creating logger
logger = LoggerFactory.get_logger(__name__)


# User Register API
@app.route("/register", methods=["POST"])
def register():
    logger.info("API '/route' called...!!!")
    data = request.json
    name = data.get("name")
    username = data.get("username")
    password = data.get("password")
    
    if not name or not username or not password:
        return jsonify({"msg": "All fields are required"}), 400

    if users_collection.find_one({"username": username}):
        return jsonify({"msg": "User already exists"}), 400

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    users_collection.insert_one({
        "name": name,
        "username": username,
        "password": hashed_pw
    })

    return jsonify({"msg": "User registered successfully"}), 201


# User login API
@app.route("/login", methods=["POST"])
def login():
    logger.info("API '/login' called...!!!")
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"msg": "All fields are required"}), 400

    user = users_collection.find_one({"username": username})
    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"msg": "Invalid credentials"}), 401

    access_token = create_access_token(identity=username)

    return jsonify({
        "access_token": access_token
    }), 200


# AI Movie Analyze API
@app.route("/movie-ai-response", methods=["POST"])
@jwt_required()
def movie_description():
    logger.info("API '/movie-ai-response' called ...!!!")
    data = request.get_json()

    movie_name = data.get("movie_name")
    release_date = data.get("release_date")

    if not movie_name or not release_date:
        return jsonify({"error": "movie_name and release_date are required"}), 400

    return get_ai_movie_response(movie_name=movie_name, release_date=release_date)


@app.route("/health", methods=["GET"])
def health():
    logger.info("Health checked...!!!")
    return jsonify({
       "status": "ok",
        "message": "Server is running",
        "timestamp": datetime.now(UTC).isoformat()
    })


if __name__ == "__main__":
    logger.info("Starting Flask Application")
    app.run(debug=True)
