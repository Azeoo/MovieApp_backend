from pymongo import MongoClient
from datetime import datetime, timedelta
import joblib
import numpy as np
import os


# -------------------------------
# Load Model
# -------------------------------
model = joblib.load(os.path.join("model", "random_forest_churn_model.pkl"))

# -------------------------------
# MongoDB Connection
# -------------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client["movie_app_db"]

watch_collection = db["user_watched_movies"]
login_collection = db["users"]

# -------------------------------
# Helper: Convert String to Datetime
# -------------------------------
def parse_date(date_string):
    return datetime.strptime(date_string, "%d-%m-%Y %H:%M:%S")


# -------------------------------
# Predict Churn Function
# -------------------------------
def predict_churn(username='raj'):

    print("churn prediction started")
    now = datetime.now()
    five_days_ago = now - timedelta(days=5)

    # ---------------------------------
    # LOGIN Data
    # ---------------------------------
    login_doc = login_collection.find_one({"username": username})

    if not login_doc or "login_data" not in login_doc:
        print("No login data found")

    login_dates = [parse_date(d) for d in login_doc["login_data"]]
    login_dates.sort()

    # Days since last login
    last_login = login_dates[-1]
    days_since_last_login = (now - last_login).days

    # Login count last 5 days
    login_count_last5d = sum(1 for d in login_dates if d >= five_days_ago)

    # ---------------------------------
    # 2️⃣ WATCH FEATURES
    # ---------------------------------
    watch_docs = list(watch_collection.find({"username": username}))

    recent_watches = []
    for doc in watch_docs:
        watched_at = parse_date(doc["watched_at"])
        if watched_at >= five_days_ago:
            recent_watches.append(doc)

    # Unique movies watched
    unique_movies = set()
    for doc in recent_watches:
        unique_id = f"{doc['explore']}_{doc['explore_id']}"
        unique_movies.add(unique_id)

    movies_watched_last5d = len(unique_movies)

    # Average completion rate
    if recent_watches:
        avg_completion_rate = sum(doc["completion_rate"] for doc in recent_watches) / len(recent_watches)
    else:
        avg_completion_rate = 0

    # ---------------------------------
    # 3️⃣ Prepare Model Input
    # ---------------------------------
    features = np.array([[
        days_since_last_login,
        login_count_last5d,
        movies_watched_last5d,
        avg_completion_rate
    ]])

    # ---------------------------------
    # 4️⃣ Prediction
    # ---------------------------------
    prediction = model.predict(features)[0]
    probability = model.predict_proba(features)[0][1]

    result = {
        "username": username,
        "features": {
            "daysSinceLastLogin": days_since_last_login,
            "loginCountLast5d": login_count_last5d,
            "moviesWatchedLast5d": movies_watched_last5d,
            "avgCompletionRate": round(avg_completion_rate, 3)
        },
        "churn_prediction": int(prediction),
        "churn_probability": round(float(probability), 3),
        "meaning": "User likely to churn" if prediction == 1 else "User likely to stay"
    }

    print(result)


predict_churn()