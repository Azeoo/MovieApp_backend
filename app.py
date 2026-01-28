from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from flask_cors import CORS
import bcrypt
from datetime import timedelta, datetime, UTC
from bson import ObjectId
from logger import LoggerFactory
from config import Config
from services.llm_service import get_ai_movie_response
from services.email_service import send_otp_email
import re
import random

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
mongo = PyMongo(app)
jwt = JWTManager(app)
# set expiry
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)

# MongoDB Table Collection
users_collection = mongo.db.users
subscriptions_collection = mongo.db.subscriptions
user_otp_collection = mongo.db.user_otp

#Creating logger
logger = LoggerFactory.get_logger(__name__)


# Email pattern matching regex
EMAIL_REGEX = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'

def is_valid_email(email: str) -> bool:
    return re.match(EMAIL_REGEX, email) is not None


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
        "profile_name": user["name"],
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


#Get dashboard route
@app.route("/subscriptions", methods=["GET"])
@jwt_required()
def get_user_dashboard():
    logger.info("API '/subscriptions' called ...!!!")
    try:
        # Get user identity from JWT
        username = get_jwt_identity()

        logger.info(f"User : {username}")

        subscription = None

        # Fetch dashboard data for this user
        try:
            subscription = subscriptions_collection.find_one(
                {"username": username},
                {"_id": 0}  # exclude Mongo _id from response
            )
            logger.info(f"Subscription : {subscription}")
        except Exception as e:
            logger.error(f"Error : {e}")
        finally:
            logger.info(f"Finally block subscription : {subscription}")

        if not subscription:
            return jsonify({
                "is_premium_member": False
            }), 201

        return jsonify({
            "is_premium_member": True,
            "score": subscription["score"],
            "watched_movies":subscription["watched_movies"]
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    

#Route for sending OTP
@app.route("/send-otp", methods=["POST"])
@jwt_required()
def send_otp():
        logger.info("API '/send-otp' called ...!!!")
        username = get_jwt_identity()

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({"msg": "User Not Found"}), 401

        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({
                "success": False,
                "message": "Email is required"
            }), 400
        
        if not is_valid_email(email):
            return jsonify({
                "success": False,
                "message": "Provide valid email address"
            }), 400
        
        try:
            # Generate 6-digit OTP
            otp = str(random.randint(100000, 999999))
            logger.info(f"OTP generated : {otp}")

            user_otp_collection.update_one(
                {"email": email, "username":username},
                {
                    "$set": {
                        "otp": otp,
                    },
                    "$setOnInsert": {
                        "email": email, "username":username
                    }
                },
                upsert=True
            )

            if send_otp_email(email, otp):
                return jsonify({
                    "success": True,
                    "message": "OTP sent successfully"
                }), 200
            
            return jsonify({
                "success": False,
                "message": "Failed to send OTP"
            }), 500

        except Exception as e:
            logger.exception(f"Exception occured while sending OTP :\n{e}")
            return jsonify({
                "success": False,
                "message": "Failed to send OTP",
            }), 500
        

#Route for verifying OTP
@app.route("/verify-otp", methods=["POST"])
@jwt_required()
def verify_otp():
        logger.info("API '/verify-otp' called ...!!!")
        username = get_jwt_identity()

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({"msg": "User Not Found"}), 401

        data = request.get_json()
        email = data.get("email")
        input_otp = str(data.get("otp"))

        if not email:
            return jsonify({
                "success": False,
                "message": "Email is required"
            }), 400
        
        if not is_valid_email(email):
            return jsonify({
                "success": False,
                "message": "Provide valid email address"
            }), 400
        

        result = user_otp_collection.find_one({
            "email": email,
            "username": username
        })

        if result is None:
            return jsonify({
                "success":False,
                "message":"Generate OTP first"
            }), 500

        otp_matches = input_otp == result["otp"]

        if not otp_matches:
            return jsonify({
                "success": False,
                "message": "Invalid OTP"
            }), 500
        

        document = {
            "username":username,
            "score":0,
            "watched_movies":[]
        }

        try:
            subscriptions_collection.insert_one(document)
            user_otp_collection.delete_one({
                "email":email,
                "username":username
            })
            return jsonify({
                "success": True,
                "message": "You're now Premium Member"
            }), 201
        except Exception as e:
            logger.exception(f"Exception occured while adding account premium : {e}")
            return jsonify({
                "success": False,
                "message": "Failed to add Membership details. Try again after sometime"
            }), 500
        

#Route for watched movies
@app.route("/watched", methods=["POST"])
@jwt_required()
def watched_movies_shows():

    logger.info(f"API '/watched' called ...!!!")
    username = get_jwt_identity()

    data = request.get_json()
    explore = data.get("explore")
    explore_id = data.get("id")

    if not explore or not explore_id:
        return jsonify({
            "success": False,
            "message": "Provide Explorer and ID"
        }), 500
    
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    appended_object = {
        "explore":explore,
        "explore_id":explore_id,
        "created_at":created_at
    }

    logger.info(f"Appended Object :\n{appended_object}")

    try:
        subscriptions_collection.update_one(
            {"username":username},
            {
                "$addToSet": {
                    "watched_movies": appended_object
                }
            }
        )

        return jsonify({
            "success": True,
            "message": "Added to watch history"
        }), 201
    except Exception as e:
        logger.exception(f"Exception occured while adding watched movies details : {e}")
        return jsonify({
            "success": False,
            "message": "Error occured while adding movie to watch history"
        }), 500





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
