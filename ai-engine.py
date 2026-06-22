import time
import sqlite3
import requests
import threading
import os
from datetime import datetime, timedelta
from flask import Flask

app = Flask(__name__)

# --- 1. डेटाबेस सेटअप (पहली बार टेबल बनाने के लिए) ---
def setup_database():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Results टेबल
    cursor.execute('''CREATE TABLE IF NOT EXISTS results 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, number INTEGER, color TEXT, size TEXT)''')
    
    # AI Status टेबल
    cursor.execute('''CREATE TABLE IF NOT EXISTS ai_status 
                      (id INTEGER PRIMARY KEY, consecutive_losses INTEGER, cooldown_until TEXT, last_prediction TEXT, last_prediction_period TEXT)''')
    
    # डिफॉल्ट वैल्यू डालना
    cursor.execute("INSERT OR IGNORE INTO ai_status (id, consecutive_losses, last_prediction) VALUES (1, 0, 'Skip')")
    
    conn.commit()
    conn.close()

# --- 2. आपके पुराने रूल्स ---
def get_size(number):
    return "Small" if 0 <= number <= 4 else "Big"

def get_color(number):
    if number in [2, 4, 6, 8]: return "Red"
    elif number in [1, 3, 7, 9]: return "Green"
    elif number == 0: return "Red/Blue"
    elif number == 5: return "Green/Blue"

def fetch_live_result():
    try:
        current_ts = int(time.time() * 1000)
        url = f"https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json?ts={current_ts}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        }
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if 'data' in data: items = data['data']
        elif 'list' in data: items = data['list']
        else: items = data
            
        latest_item = items[0]
        latest_period = str(latest_item.get('issueNumber', latest_item.get('period')))
        latest_number = int(latest_item.get('number', latest_item.get('prizeNumber')))
        return latest_period, latest_number, get_color(latest_number), get_size(latest_number)
    except Exception as e:
        print("API एरर:", e)
        return None, None, None, None

def analyze_pattern(conn, current_sequence):
    cursor = conn.cursor()
    cursor.execute("SELECT size FROM results ORDER BY period ASC")
    all_data = [row[0] for row in cursor.fetchall()]
    
    if len(all_data) < 100: 
        return "Skip", 0

    seq_len = len(current_sequence)
    next_big, next_small = 0, 0

    for i in range(len(all_data) - seq_len):
        if all_data[i:i+seq_len] == current_sequence:
            next_result = all_data[i+seq_len]
            if next_result == "Big": next_big += 1
            if next_result == "Small": next_small += 1
            
    total_matches = next_big + next_small
    if total_matches == 0: return "Skip", 0
        
    big_chance = (next_big / total_matches) * 100
    small_chance = (next_small / total_matches) * 100
    
    if big_chance >= 90: return "Big", big_chance
    elif small_chance >= 90: return "Small", small_chance
    else: return "Skip", max(big_chance, small_chance)

# --- 3. मेन AI लूप (बैकग्राउंड में चलेगा) ---
def run_ai():
    while True:
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT consecutive_losses, cooldown_until, last_prediction, last_prediction_period FROM ai_status WHERE id = 1")
            status = cursor.fetchone()
            losses, cooldown, last_pred, pred_period = status[0], status[1], status[2], status[3]
            
            if cooldown:
                cooldown_time = datetime.strptime(cooldown, "%Y-%m-%d %H:%M:%S")
                if datetime.now() < cooldown_time:
                    time.sleep(30)
                    continue
                else:
                    cursor.execute("UPDATE ai_status SET cooldown_until = NULL, consecutive_losses = 0 WHERE id = 1")
                    conn.commit()

            period, number, color, size = fetch_live_result()
            
            if period:
                cursor.execute("SELECT id FROM results WHERE period = ?", (period,))
                if not cursor.fetchone():
                    print(f"नया रिजल्ट मिला: {period}")
                    time.sleep(10)
                    
                    cursor.execute("INSERT INTO results (period, number, color, size) VALUES (?, ?, ?, ?)", (period, number, color, size))
                    
                    if last_pred != "Skip" and pred_period:
                        if size != last_pred:
                            losses += 1
                            if losses >= 3:
                                break_time = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
                                cursor.execute("UPDATE ai_status SET cooldown_until = ?, consecutive_losses = ? WHERE id = 1", (break_time, losses))
                        else:
                            losses = 0
                            
                    cursor.execute("UPDATE ai_status SET consecutive_losses = ? WHERE id = 1", (losses,))
                    
                    cursor.execute("SELECT size FROM results ORDER BY period DESC LIMIT 5")
                    recent_sizes = [row[0] for row in cursor.fetchall()][::-1]
                    
                    prediction, confidence = analyze_pattern(conn, recent_sizes)
                    next_period = str(int(period) + 1)
                    
                    cursor.execute("UPDATE ai_status SET last_prediction = ?, last_prediction_period = ? WHERE id = 1", (prediction, next_period))
                    conn.commit()
                    print(f"Next Period: {next_period} | Prediction: {prediction} | Confidence: {confidence}%")

            conn.close()
        except Exception as e:
            print("लूप एरर:", e)
            
        time.sleep(5)

# --- 4. Render के लिए वेब सर्वर (ताकि ऐप क्रैश न हो) ---
@app.route('/')
def home():
    return "WinGo AI Prediction Bot is running 24/7!"

if __name__ == "__main__":
    setup_database() # पहले डेटाबेस तैयार करें
    
    # AI बॉट को बैकग्राउंड थ्रेड में स्टार्ट करें
    bot_thread = threading.Thread(target=run_ai)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Flask सर्वर स्टार्ट करें
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
