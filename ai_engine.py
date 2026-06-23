import time
import sqlite3
import requests
import threading
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify 

app = Flask(__name__)

# --- 1. डेटाबेस सेटअप ---
def setup_database():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS results 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, number INTEGER, color TEXT, size TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ai_status 
                      (id INTEGER PRIMARY KEY, consecutive_losses INTEGER, cooldown_until TEXT, last_prediction TEXT, last_prediction_period TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO ai_status (id, consecutive_losses, last_prediction) VALUES (1, 0, 'Skip')")
    conn.commit()
    conn.close()

# --- 2. रूल्स ---
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
        url = f"https://api.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json?ts={current_ts}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://ar-lottery01.com/"
        }
        
        # Naya Log: Pata chalega ki bot request bhej raha hai ya nahi
        print(f"बॉट सर्वर से पूछ रहा है... (Time: {current_ts})", flush=True)
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data: items = data['data']
            elif 'list' in data: items = data['list']
            else: items = data
                
            latest_item = items[0]
            latest_period = str(latest_item.get('issueNumber', latest_item.get('period')))
            latest_number = int(latest_item.get('number', latest_item.get('prizeNumber')))
            return latest_period, latest_number, get_color(latest_number), get_size(latest_number)
        else:
            # Agar Cloudflare ya server ne roka, toh yeh line Render logs me dikhegi
            print(f"⚠️ गेम सर्वर ने ब्लॉक कर दिया! Status Code: {response.status_code}", flush=True)
            print(f"सर्वर का जवाब: {response.text[:200]}", flush=True)
            return None, None, None, None
            
    except Exception as e:
        print(f"API भयंकर एरर: {e}", flush=True)
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

# --- 3. मेन AI लूप ---
def run_ai():
    while True:
        try:
            conn = sqlite3.connect('database.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute("SELECT consecutive_losses, cooldown_until, last_prediction, last_prediction_period FROM ai_status WHERE id = 1")
            status = cursor.fetchone()
            losses, cooldown, last_pred, pred_period = status[0], status[1], status[2], status[3]
            
            if cooldown:
                cooldown_time = datetime.strptime(cooldown, "%Y-%m-%d %H:%M:%S")
                if datetime.now() < cooldown_time:
                    time.sleep(30)
                    conn.close()
                    continue
                else:
                    cursor.execute("UPDATE ai_status SET cooldown_until = NULL, consecutive_losses = 0 WHERE id = 1")
                    conn.commit()

            period, number, color, size = fetch_live_result()
            
            if period:
                next_period = str(int(period) + 1)
                
                if pred_period is None or pred_period == "":
                    cursor.execute("UPDATE ai_status SET last_prediction_period = ? WHERE id = 1", (next_period,))
                    conn.commit()

                cursor.execute("SELECT id FROM results WHERE period = ?", (period,))
                if not cursor.fetchone():
                    print(f"नया रिजल्ट मिला: {period}", flush=True)
                    time.sleep(10)
                    
                    cursor.execute("INSERT INTO results (period, number, color, size) VALUES (?, ?, ?, ?)", (period, number, color, size))
                    
                    if last_pred != "Skip" and pred_period == period:
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
                    
                    cursor.execute("UPDATE ai_status SET last_prediction = ?, last_prediction_period = ? WHERE id = 1", (prediction, next_period))
                    conn.commit()
                    print(f"Next Period: {next_period} | Prediction: {prediction} | Confidence: {confidence}%", flush=True)

            conn.close()
        except Exception as e:
            print("लूप एरर:", e, flush=True)
            
        time.sleep(5)

# --- 4. Render के लिए वेब सर्वर (API & Frontend) ---

def get_db_connection():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/live_data')
def live_data():
    try:
        conn = get_db_connection()
        status = conn.execute('SELECT * FROM ai_status WHERE id = 1').fetchone()
        history = conn.execute('SELECT * FROM results ORDER BY period DESC LIMIT 10').fetchall()
        conn.close()
        
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if status is None or status['last_prediction_period'] is None:
            return jsonify({'cooldown': None, 'next_period': 'Loading ID...', 'prediction': 'Analyzing...', 'time': current_time, 'history': []})
            
        return jsonify({
            'cooldown': status['cooldown_until'],
            'next_period': status['last_prediction_period'],
            'prediction': status['last_prediction'],
            'time': current_time,
            'history': [dict(row) for row in history]
        })
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == "__main__":
    setup_database()
    
    bot_thread = threading.Thread(target=run_ai)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
