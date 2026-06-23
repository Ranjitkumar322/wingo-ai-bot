import sqlite3

def setup_database():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # गेम रिजल्ट्स की टेबल
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT UNIQUE,
            number INTEGER,
            color TEXT,
            size TEXT
        )
    ''')

    # AI के स्टेटस और ब्रेक की टेबल
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_status (
            id INTEGER PRIMARY KEY,
            consecutive_losses INTEGER,
            cooldown_until TIMESTAMP,
            last_prediction TEXT,
            last_prediction_period TEXT
        )
    ''')
    
    # डिफ़ॉल्ट स्टेटस डालना
    cursor.execute('INSERT OR IGNORE INTO ai_status (id, consecutive_losses, cooldown_until) VALUES (1, 0, NULL)')
    
    conn.commit()
    conn.close()
    print("Database Ready!")

if __name__ == '__main__':
    setup_database()
