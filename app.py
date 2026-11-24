import os
import threading
import asyncio
from flask import Flask, jsonify, request
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
def get_all_products():
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT id, name, description, price, category FROM products WHERE is_active=TRUE")
    products = c.fetchall()
    c.close()
    conn.close()
    return jsonify([{
        "id": p['id'], "name": p['name'], "description": p['description'],
        "price": float(p['price']), "category": p['category']
    } for p in products])

@app.route('/api/buy', methods=['POST'])
def buy_product():
    data = request.json
    user_id = data.get('user_id')
    product_id = data.get('product_id')
    
    if not user_id or not product_id:
        return jsonify({"error": "Məlumat çatmır"}), 400
        
    u = get_user(user_id)
    if not u:
        return jsonify({"error": "İstifadəçi tapılmadı"}), 404
        
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM products WHERE id=%s AND is_active=TRUE", (product_id,))
    p = c.fetchone()
    
    if not p:
        c.close(); conn.close()
        return jsonify({"error": "Məhsul tapılmadı"}), 404
        
    if float(u['azn_balance']) < float(p['price']):
        c.close(); conn.close()
        return jsonify({"error": "Balansınız kifayət etmir!"}), 400
        
    c.execute("UPDATE users SET azn_balance = azn_balance - %s WHERE user_id=%s", (p['price'], user_id))
    c.execute("INSERT INTO orders (user_id, product_id, product_name, price) VALUES (%s, %s, %s, %s) RETURNING id", 
              (user_id, product_id, p['name'], p['price']))
    order_id = c.fetchone()['id']
    conn.commit()
    c.close()
    conn.close()
    
    return jsonify({"success": True, "order_id": order_id, "message": f"Sifariş #OLDX-{order_id} qeydə alındı!"})

@app.route('/api/orders/<int:user_id>', methods=['GET'])
def get_user_orders(user_id):
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC", (user_id,))
    orders = c.fetchall()
    c.close()
    conn.close()
    return jsonify([{
        "id": o['id'], "product_name": o['product_name'], "price": float(o['price']),
        "status": o['status'], "created_at": o['created_at'].strftime("%d.%m.%Y %H:%M")
    } for o in orders])

@app.route('/api/withdraw', methods=['POST'])
def withdraw_request():
    data = request.json
    user_id = data.get('user_id')
    amount = float(data.get('amount', 0))
    method = data.get('method')
    destination = data.get('destination')
    
    u = get_user(user_id)
    if not u or float(u['azn_balance']) < amount:
        return jsonify({"error": "Balans kifayət etmir"}), 400
        
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET azn_balance = azn_balance - %s WHERE user_id=%s", (amount, user_id))
    c.execute("INSERT INTO withdrawals (user_id, amount, method, destination) VALUES (%s, %s, %s, %s)", 
              (user_id, amount, method, destination))
    conn.commit()
    c.close()
    conn.close()
    
    return jsonify({"success": True, "message": "Çıxarış tələbiniz qeydə alındı!"})

def run_bot():
    asyncio.run(start_polling())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
