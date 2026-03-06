from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from flask_cors import CORS
import bcrypt
import os
from datetime import timedelta, datetime, UTC
from logger import LoggerFactory
from config import Config
from services.ai_movie_analyze_service import get_ai_movie_response
from services.email_service import send_otp_email
from services.quiz_service import generate_quiz_questions
from services.predict_churn_service import predict_churn
from services.chatbot_service import chatbot
import re
import string
import random
from flask_socketio import SocketIO, emit, join_room, leave_room


app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

# print(app.config["CORS_ORIGIN"])
# print(type(app.config["CORS_ORIGIN"]))
mongo = PyMongo(app)
jwt = JWTManager(app)
# set expiry
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)


# -----------------------------------------------------------
# 1. Initialize SocketIO on your existing Flask app
#    (replace your current app.run with socketio.run)
# -----------------------------------------------------------
socketio = SocketIO(
    app,
    cors_allowed_origins="*",   # tighten this to your frontend URL in production
    async_mode="eventlet"
)

# MongoDB Table Collection
users_collection = mongo.db.users
subscriptions_collection = mongo.db.subscriptions
user_otp_collection = mongo.db.user_otp
group_watch_collection = mongo.db.group_watch
user_watched_movie_collection = mongo.db.user_watched_movies
watch_parties_collection = mongo.db.watch_parties

#Creating logger
logger = LoggerFactory.get_logger(__name__)


# ADD this dict after your collections
socket_room_map = {}  # tracks sid -> {room, username}


# ── Helper: generate short unique code like "XR7T9" ─────────────
def generate_room_code(length=6):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=length))
        # ensure uniqueness in DB
        if not watch_parties_collection.find_one({"code": code}):
            return code

# ADD after: logger = LoggerFactory.get_logger(__name__)
def get_user_from_token(token):
    try:
        # flask-jwt-extended stores identity in "sub" claim
        payload = JWTManager._decode_jwt_from_config  # not used — decode manually
        import base64, json
        parts = token.split(".")
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        username = decoded.get("sub") or "User"
        return {"username": username, "avatar": username[0].upper()}
    except Exception:
        return {"username": "Guest", "avatar": "G"}


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
        "username": username.lower(),
        "password": hashed_pw,
        "login_data":[],
        "watched_data":[],
        "taken_subscription":False,
        "subscription_valid":"",
        "max_streak":0,
        "movie_count":0
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
    
    username = username.lower()

    user = users_collection.find_one({"username": username})
    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"msg": "Invalid credentials"}), 401

    access_token = create_access_token(identity=username)

    subscription = subscriptions_collection.find_one(
        {"username": username},
        {"_id": 0}  # exclude Mongo _id from response
    )

    premium_member = False

    if subscription is not None:
        premium_member = True
        

    churn_detected = False
    redirect_to = True
    if user['taken_subscription'] == True:
        logger.info("inside prediction")
        login_doc = users_collection.find_one({"username": username})
        watch_docs = list(user_watched_movie_collection.find({"username": username}))
        result = predict_churn(username, login_doc, watch_docs)
        churn_detected = bool(result['churn_prediction'])

        logger.info(f"In App.py Predict churn result :\n{result}")

        subscription_valid = user["subscription_valid"]  # from MongoDB

        # convert string to date
        valid_date = datetime.strptime(subscription_valid, "%Y-%m-%d").date()
        today = datetime.today().date()

        

        if today > (valid_date - timedelta(days=3)):
            logger.info("true")
            redirect_to = True
        else:
            logger.info("false")
            redirect_to = False

        logger.info(redirect_to)



    users_collection.update_one(
        {"username": username},
        {
            "$push": {
                "login_data": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            }
        }
    )



    return jsonify({
        "profile_name": user["name"],
        "access_token": access_token,
        "premium_member":premium_member,
        "churn_detected": churn_detected,
        "redirect_to":redirect_to
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

        # logger.info(f"User : {username}")

        subscription = None

        # Fetch dashboard data for this user
        try:
            subscription = subscriptions_collection.find_one(
                {"username": username},
                {"_id": 0}  # exclude Mongo _id from response
            )
            # logger.info(f"Subscription Details : {subscription}")
        except Exception as e:
            logger.error(f"Error : {e}")

        if not subscription:
            return jsonify({
                "is_premium_member": False
            }), 201
        
        watched_movies = subscription.get("watched_movies", [])

        latest_five = sorted(
            watched_movies,
            key=lambda x: datetime.strptime(x["created_at"], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )[:5]


        user = users_collection.find_one(
            {"username": username},
            {"_id": 0, "watched_data": 1, "max_streak":1}   # projection (only return watched_data)
        )

        logger.info(f"User :\n{user}")

        logger.info(f"User Watched movie data :\n{user}")

        three_months_ago = datetime.utcnow() - timedelta(days=90)

        pipeline = [
            {
                "$match": {
                    "username": username
                }
            },
            {
                "$addFields": {
                    "watched_at_date": {
                        "$dateFromString": {
                            "dateString": "$watched_at",
                            "format": "%d-%m-%Y %H:%M:%S"
                        }
                    }
                }
            },
            {
                "$match": {
                    "watched_at_date": {"$gte": three_months_ago}
                }
            },
            {
                "$sort": {"completion_rate": -1}
            },
            {
                "$group": {
                    "_id": "$username",
                    "explores": {
                        "$push": {
                            "explore": "$explore",
                            "explore_id": "$explore_id"
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "username": "$_id",
                    "top_explores": {"$slice": ["$explores", 3]}
                }
            }
        ]

        result = list(user_watched_movie_collection.aggregate(pipeline))
        logger.info(f"Response result for recommendation :\n{result}")
        top_explores=[]
        top_explores = result[0].get("top_explores") if result and len(result) > 0 else None
        if top_explores:
            logger.info(f"Top 3 completed movies explore and id {top_explores}")


        temp = {
            "is_premium_member": True,
            "score": subscription["score"],
            "watched_movies":latest_five,
            "heatmap_data": user["watched_data"],
            "recommendation":top_explores,
            "max_streak":user['max_streak']
        }

        logger.info(f"Result in subscription  :\n{temp}")

        return jsonify({
            "is_premium_member": True,
            "score": subscription["score"],
            "watched_movies":latest_five,
            "heatmap_data": user["watched_data"],
            "recommendation":top_explores,
            "max_streak":user['max_streak']
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
            # logger.info(f"OTP generated : {otp}")

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

    if not explore or not explore_id or not username:
        return jsonify({
            "success": False,
            "message": "Data not found"
        }), 500
    
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    user = users_collection.find_one({"username": username})

    if not user:
        logger.info("User data not found in database")
        

    watched_data = user.get("watched_data", [])

    # 🔎 Check if today's date already exists
    today_entry = next((item for item in watched_data if item["date"] == today), None)

    if today_entry:
        # ✅ Increase frequency only
        users_collection.update_one(
            {
                "username": username,
                "watched_data.date": today
            },
            {
                "$inc": {"watched_data.$.frequency": 1}
            }
        )
        logger.info("Today's frequency incremented")

    else:
        # ❌ Today's entry not present → Add new entry
        users_collection.update_one(
            {"username": username},
            {
                "$push": {
                    "watched_data": {
                        "date": today,
                        "frequency": 1
                    }
                }
            }
        )

        # 🔥 Streak Logic (ONLY when new day entry)
        yesterday_present = any(item["date"] == yesterday for item in watched_data)

        if yesterday_present:
            movie_count = user.get("movie_count", 0) + 1
        else:
            movie_count = 1

        max_streak = user.get("max_streak", 0)

        if movie_count > max_streak:
            max_streak = movie_count

        users_collection.update_one(
            {"username": username},
            {
                "$set": {
                    "movie_count": movie_count,
                    "max_streak": max_streak
                }
            }
        )

        logger.info("New day added + streak updated")

    try:
        result = subscriptions_collection.update_one(
            {
                "username": username,
                "watched_movies.explore": explore,
                "watched_movies.explore_id": explore_id
            },
            {
                "$set": {
                    "watched_movies.$.created_at": created_at
                }
            }
        )

        if result.matched_count == 0:
            appended_object = {
                "explore": explore,
                "explore_id": explore_id,
                "created_at": created_at
            }

            subscriptions_collection.update_one(
                {"username": username},
                {
                    "$push": {
                        "watched_movies": appended_object
                    }
                }
            )

        return jsonify({
            "success": True,
            "message": "Watch history updated"
        }), 201

    except Exception as e:
        logger.exception(f"Exception occured while adding watched movies details : {e}")
        return jsonify({
            "success": False,
            "message": "Error occured while adding movie to watch history"
        }), 500



#Route for watch together
@app.route("/watch-together", methods=["POST"])
@jwt_required()
def watch_together():
    logger.info("API '/watch-together' called ...!!!")
    username = get_jwt_identity()

    data = request.get_json()
    explore = data.get("explore")
    explore_id = data.get("id")

    if not explore or not explore_id:
        return jsonify({
            "success": False,
            "message": "Provide Media and Media ID"
        }), 400

    result = group_watch_collection.find_one({
        "username": username,
        "explore": explore,
        "explore_id": explore_id
    })

    now = datetime.now()

    if result:
        added_at = datetime.strptime(result["added_at"], "%Y-%m-%d %H:%M:%S")
        seven_days_ago = now - timedelta(days=7)

        if added_at >= seven_days_ago:
            return jsonify({
                "success": False,
                "message": "Already added to Spotlight"
            }), 409
        else:
            group_watch_collection.update_one(
                {"_id": result["_id"]},
                {"$set": {"added_at": now.strftime("%Y-%m-%d %H:%M:%S")}}
            )

            return jsonify({
                "success": True,
                "message": "Added to Spotlight"
            }), 201


    document = {
        "username": username,
        "explore": explore,
        "explore_id": explore_id,
        "added_at": now.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        group_watch_collection.insert_one(document)
        return jsonify({
            "success": True,
            "message": "Added to Spotlight"
        }), 201
    except Exception:
        logger.exception("Exception occurred while adding media to Group Watch")
        return jsonify({
            "success": False,
            "message": "Failed to add"
        }), 500

    
#Route for get watch together list
@app.route("/watch-together-list", methods=["GET"])
@jwt_required()
def get_watch_together():
    logger.info("API '/watch-together-list' called ...!!!")

    try:

        username = get_jwt_identity()
        seven_days_ago = datetime.now() - timedelta(days=7)

        # Fetch all records
        records = group_watch_collection.find({
            "username": {"$ne": username}
        })

        user_map = {}

        for doc in records:
            try:
                added_at = datetime.strptime(doc["added_at"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue  # skip invalid dates

            # Skip records older than 7 days
            if added_at < seven_days_ago:
                continue

            username = doc["username"]

            if username not in user_map:
                user_map[username] = {
                    "username": username,
                    "user_movie_list": []
                }

            user_map[username]["user_movie_list"].append({
                "explore": doc["explore"],
                "explore_id": doc["explore_id"]
            })

        return jsonify({
            "group_watch_list": list(user_map.values())
        }), 200
    except Exception as e:
        logger.exception(f"Exception occured while creating group watch list")
        return jsonify({
            "success": False,
            "message": "Failure occured while fetching data"
        }), 500


# Route for updating Score
@app.route("/update-score", methods=["POST"])
@jwt_required()
def update_user_score():
    logger.info("API '/update-score' called ...!!!")

    data = request.get_json()
    # logger.info(f"Data :\n{data}")
    username = data.get("username")
    score = data.get("score")

    if not username:
        return jsonify({
            "success": False,
            "message": "Username is required"
        }), 400


    records = subscriptions_collection.find_one({
        "username": username
    })

    if not records:
        return jsonify({
            "success": False,
            "message": "User not found"
        }), 400
    
    # logger.info(f"Username : {username} previous score : {records["score"]}")
    updated_score = int(records["score"]) + int(score)
    # logger.info(f"Username : {username} updated score : {updated_score}")

    try:
        subscriptions_collection.update_one(
                {"username":username},
                {"$set": {"score":updated_score}}
            )
        logger.info(f"Score updated successfully")
        return jsonify({
            "success": True,
            "message":"User score updated successfully"
        }), 200
    except Exception as e:
        logger.exception(f"Error occured while updating the user movie points")
        return jsonify({
            "success": False,
            "message" : "Failed to updated user score"
        }), 500

    

# Route for play quiz
@app.route("/quiz", methods=["GET"])
@jwt_required()
def generate_quiz():
    logger.info(f"API '/quiz' called...!!!")

    username = get_jwt_identity()
    return generate_quiz_questions(username)

# Route for user watch activity
@app.route("/watch-progress", methods=["POST"])
@jwt_required()
def save_watch_progress():
    try:
        logger.info(f"API '/watch-progress' called...!!!")
        data = request.get_json()

        username = get_jwt_identity()
        explore = data.get("explore")
        explore_id = data.get("id")
        watched_seconds = data.get("watchedSeconds", 0)
        total_duration = data.get("totalDuration", 0)
        completion_rate = data.get("completionRate", 0)

        if not explore or not explore_id:
            return jsonify({"error": "Missing Data"}), 400

        # Update if record exists (prevents duplicates)
        user_watched_movie_collection.insert_one(
            {
                "username": username,
                "explore": explore,
                "explore_id": explore_id,
                "watched_seconds": watched_seconds,
                "total_duration": total_duration,
                "completion_rate": completion_rate,
                "watched_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            }
        )

        return jsonify({"message": "Watch progress saved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# payment route
@app.route('/payment', methods=['POST'])
@jwt_required()
def payment():
    data = request.get_json()

    logger.info("API /payment called...!!!")

    username = get_jwt_identity()
    duration = int(data.get("duration_of_subscription"))

    user = users_collection.find_one({"username": username})

    try:
        if not user:
            return jsonify({"error": "User not found"}), 404

        taken_subscription = user.get("taken_subscription")
        subscription_valid = user.get("subscription_valid")

        # convert string date to datetime
        if subscription_valid:
            sub_date = datetime.strptime(subscription_valid, "%Y-%m-%d")
        else:
            sub_date = datetime.today()

        # check subscription
        if taken_subscription == "true" or taken_subscription is True:
            new_valid_date = sub_date + timedelta(days=duration)
        else:
            new_valid_date = datetime.today() + timedelta(days=duration)

        new_valid_date_str = new_valid_date.strftime("%Y-%m-%d")

        logger.info("updating user to premium")
        users_collection.update_one(
            {"username": username},
            {
                "$set": {
                    "subscription_valid": new_valid_date_str,
                    "taken_subscription": True
                }
            }
        )
        logger.info("updated user to premium")

        document = {
            "username": username,
            "score": 0,
            "watched_movies": []
        }

        existing_user = subscriptions_collection.find_one({"username": username})

        if not existing_user:
            subscriptions_collection.insert_one(document)

        return jsonify({
            "success": True,
            "message":"Subscription Extended"
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message":"Failed to extend subscription"
        }), 400
    


# chatbot route
@app.route('/chat-bot', methods=['POST'])
@jwt_required()
def chatbot_method():
    logger.info("API /chatbot called...!!!")

    data = request.get_json()
    if not data:
        logger.warning("Empty request body received")
        return jsonify({
            "success": False,
            "message": "Request body is empty"
        }), 400

    query = data.get("query")
    if not query or not isinstance(query, str) or query.strip() == "":
        logger.warning("Invalid query received: %s", query)
        return jsonify({
            "success": False,
            "message": "Query not found or invalid"
        }), 400

    logger.info("Processing chatbot query: %s", query)
    return chatbot(query)





# -----------------------------------------------------------
# 3. Join a movie room
#    Frontend emits: { room: "movie-278", token: "..." }
# -----------------------------------------------------------
# UPDATE your existing on_join to also store sid mapping:
@socketio.on("join")
def on_join(data):
    token = data.get("token", "")
    room  = data.get("room", "")
    user  = get_user_from_token(token)

    if not room:
        return

    join_room(room)
    socket_room_map[request.sid] = {"room": room, "username": user["username"]}  # ADD this line

    emit("system_message", {
        "message": f"{user['username']} joined the chat",
    }, to=room)


# ADD after the on_join function
@socketio.on("send_message")
def handle_message(data):
    token   = data.get("token", "")
    room    = data.get("room", "")
    message = data.get("message", "").strip()
    user    = get_user_from_token(token)

    if not room or not message:
        return

    timestamp = datetime.now().strftime("%I:%M %p")

    emit("receive_message", {
        "user":      user["username"],
        "avatar":    user["avatar"],
        "message":   message,
        "timestamp": timestamp,
    }, to=room)


# ADD this new handler anywhere after on_join:
@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    info = socket_room_map.pop(sid, None)  # remove from map
    if info:
        emit("system_message", {
            "message": f"{info['username']} left the room",
        }, to=info["room"])
    logger.info(f"Client disconnected: {sid}")



# ADD after on_disconnect:
@socketio.on("leave")
def on_leave(data):
    token = data.get("token", "")
    room  = data.get("room", "")
    user  = get_user_from_token(token)

    if not room:
        return

    leave_room(room)
    socket_room_map.pop(request.sid, None)

    emit("system_message", {
        "message": f"{user['username']} left the room",
    }, to=room)






# ================================================================
# ROUTE 1 — Create a watch party
# POST /create-watch-party
# Body: { "movie_id": 278, "media_type": "movie" }
# Only premium members can create
# ================================================================
@app.route("/create-watch-party", methods=["POST"])
@jwt_required()
def create_watch_party():
    logger.info("API '/create-watch-party' called...!!!")
    try:
        username = get_jwt_identity()

        # ── Premium check ────────────────────────────────────────
        subscription = subscriptions_collection.find_one({"username": username})
        if not subscription:
            return jsonify({
                "success": False,
                "message": "Only premium members can start a watch party"
            }), 403

        data       = request.get_json()
        movie_id   = data.get("movie_id")
        media_type = data.get("media_type", "movie")

        if not movie_id:
            return jsonify({"success": False, "message": "movie_id is required"}), 400

        code = generate_room_code()

        watch_parties_collection.insert_one({
            "code":       code,
            "movie_id":   movie_id,
            "media_type": media_type,
            "host":       username,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "active":     True
        })

        logger.info(f"Watch party created: code={code} movie_id={movie_id} host={username}")

        return jsonify({
            "success": True,
            "code":    code,
            "link":    f"/live-watch/{code}"
        }), 201

    except Exception as e:
        logger.exception("Error creating watch party")
        return jsonify({"success": False, "message": str(e)}), 500
    


# ================================================================
# ROUTE 2 — Join / fetch watch party info
# GET /watch-party/<code>
# Returns movie_id + media_type so frontend can load the video
# Only logged-in (JWT) users can join
# ================================================================
@app.route("/watch-party/<code>", methods=["GET"])
@jwt_required()
def get_watch_party(code):
    logger.info(f"API '/watch-party/{code}' called...!!!")
    try:
        username = get_jwt_identity()

        # ── Premium check ────────────────────────────────────────
        subscription = subscriptions_collection.find_one({"username": username})
        if not subscription:
            return jsonify({
                "success": False,
                "message": "Only premium members can join a watch party"
            }), 403

        party = watch_parties_collection.find_one({"code": code}, {"_id": 0})

        if not party:
            return jsonify({"success": False, "message": "Watch party not found"}), 404

        if not party.get("active", True):
            return jsonify({"success": False, "message": "This watch party has ended"}), 410

        return jsonify({
            "success":    True,
            "code":       party["code"],
            "movie_id":   party["movie_id"],
            "media_type": party["media_type"],
            "host":       party["host"],
        }), 200

    except Exception as e:
        logger.exception("Error fetching watch party")
        return jsonify({"success": False, "message": str(e)}), 500
    



# ================================================================
# SOCKET EVENT — Host ends the party
# Frontend emits: { code: "XR7T9", token: "..." }
# Broadcasts "party_ended" to everyone in the room
# Marks party as inactive in MongoDB
# ================================================================
@socketio.on("end_party")
def on_end_party(data):
    token = data.get("token", "")
    code  = data.get("code", "")
    user  = get_user_from_token(token)

    if not code:
        return

    # Mark as inactive in DB
    watch_parties_collection.update_one(
        {"code": code},
        {"$set": {"active": False, "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
    )

    logger.info(f"Watch party ended: code={code} by host={user['username']}")

    # Notify everyone in the room
    emit("party_ended", {
        "message": f"{user['username']} has ended the session"
    }, to=code)



@app.route("/health", methods=["GET"])
def health():
    logger.info("Health checked...!!!")
    return jsonify({
       "status": "ok",
        "message": "Server is running",
        "timestamp": datetime.now(UTC).isoformat()
    })


# if __name__ == "__main__":
#     logger.info("Starting Flask Application")
#     app.run(
#         host="0.0.0.0",
#         port=int(os.environ.get("PORT", 5000)),
#         debug=True,
        
#     )


# WITH this:
if __name__ == "__main__":
    logger.info("Starting Flask Application")
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )
