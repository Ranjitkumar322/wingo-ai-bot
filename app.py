from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

# API जो फ्रंटएंड को लाइव डेटा देगी
@app.route('/api/live_data')
def live_data():
    conn = get_db_connection()
    status = conn.execute('SELECT * FROM ai_status WHERE id = 1').fetchone()
    history = conn.execute('SELECT * FROM results ORDER BY period DESC LIMIT 10').fetchall()
    conn.close()
    
    return jsonify({
        'cooldown': status['cooldown_until'],
        'next_period': status['last_prediction_period'],
        'prediction': status['last_prediction'],
        'history': [dict(row) for row in history]
    })

if __name__ == '__main__':
    app.run(debug=True)
