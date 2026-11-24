import os
import threading
import asyncio
from flask import Flask, jsonify
from bot import start_polling, get_user, db
from psycopg2.extras import DictCursor

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

@app.route("/")
@app.route("/health")
def health():
    return "OK"

@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user_api(user_id):
    u = get_user(user_id)
    if not u:
        return jsonify({"error": "İstifadəçi tapılmadı"}), 404
    return jsonify({
        "full_name": u['full_name'],
        "azn_balance": float(u['azn_balance']),
        "coin_balance": u['coin_balance'],
        "referal_count": u['referal_count']
    })

@app.route('/api/products', methods=['GET'])
def get_products_api():
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT id, name, description, price, category FROM products WHERE is_active=TRUE")
    products = c.fetchall()
    c.close()
    conn.close()
    return jsonify([{
        "id": p['id'], 
        "name": p['name'], 
        "description": p['description'],
        "price": float(p['price']), 
        "category": p['category']
    } for p in products])

def run_bot():
    asyncio.run(start_polling())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
