from flask import Flask, request, jsonify, send_from_directory, make_response
import random
import string
import time
import datetime
import json
import os

app = Flask(__name__, static_folder='.')

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return make_response('', 204)

# ── In-memory "database" ──────────────────────────────────────────────────────
transactions = []
fraud_log = []
analytics = {
    "total_processed": 4_821_993,
    "total_volume": 9_243_817_452.37,
    "success_rate": 99.7,
    "avg_response_ms": 142,
}

CARD_NETWORKS = {
    "4": "Visa",
    "5": "Mastercard",
    "3": "Amex",
    "6": "Discover"
}

MERCHANTS = ["NexShop", "UrbanCart", "StreamFlix", "SkyTravel", "FoodRocket",
             "TechBay", "FashionVault", "PowerGym", "MediPlus", "EduLearn"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_txn_id():
    return "TXN-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))

def detect_card_network(number):
    cleaned = number.replace(" ", "")
    return CARD_NETWORKS.get(cleaned[0], "Unknown") if cleaned else "Unknown"

def luhn_check(number):
    cleaned = number.replace(" ", "")
    if not cleaned.isdigit():
        return False
    total = 0
    reverse = cleaned[::-1]
    for i, digit in enumerate(reverse):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

def fraud_score(card_number, amount, merchant):
    score = 0
    amount = float(amount)
    if amount > 5000: score += 30
    elif amount > 1000: score += 10
    if random.random() < 0.05: score += 45
    if not luhn_check(card_number): score += 60
    score += random.randint(0, 15)
    return min(score, 100)

def calculate_fees(amount):
    amount = float(amount)
    interchange = round(amount * 0.018, 2)
    assessment = round(amount * 0.0015, 2)
    processor = round(amount * 0.003 + 0.10, 2)
    total = round(interchange + assessment + processor, 2)
    return {
        "interchange": interchange,
        "assessment": assessment,
        "processor": processor,
        "total": total,
        "net": round(amount - total, 2)
    }

def generate_seed_transactions(n=20):
    txns = []
    statuses = ["approved", "approved", "approved", "approved", "declined", "flagged"]
    now = datetime.datetime.utcnow()
    for i in range(n):
        amount = round(random.uniform(12.99, 4999.99), 2)
        status = random.choice(statuses)
        merchant = random.choice(MERCHANTS)
        card_prefix = random.choice(["4111", "5500", "3782", "6011"])
        card_last4 = str(random.randint(1000, 9999))
        ts = now - datetime.timedelta(minutes=random.randint(1, 1440))
        txns.append({
            "id": generate_txn_id(),
            "amount": amount,
            "currency": "USD",
            "status": status,
            "merchant": merchant,
            "card_last4": card_last4,
            "card_network": CARD_NETWORKS.get(card_prefix[0], "Visa"),
            "timestamp": ts.isoformat() + "Z",
            "fees": calculate_fees(amount) if status == "approved" else None,
            "fraud_score": random.randint(0, 95),
            "country": random.choice(["US", "UK", "CA", "DE", "AU", "JP", "FR"]),
            "risk_level": random.choice(["low", "low", "low", "medium", "high"]),
        })
    return sorted(txns, key=lambda x: x["timestamp"], reverse=True)

transactions = generate_seed_transactions(20)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/validate-card', methods=['POST'])
def validate_card():
    data = request.json
    card_number = data.get('card_number', '')
    expiry = data.get('expiry', '')
    cvv = data.get('cvv', '')
    name = data.get('name', '')

    errors = {}
    cleaned = card_number.replace(' ', '')

    if not cleaned or len(cleaned) < 13:
        errors['card_number'] = 'Card number too short'
    elif not luhn_check(cleaned):
        errors['card_number'] = 'Invalid card number (Luhn check failed)'

    if expiry:
        parts = expiry.split('/')
        if len(parts) == 2:
            try:
                month, year = int(parts[0]), int('20' + parts[1]) if len(parts[1]) == 2 else int(parts[1])
                now = datetime.datetime.now()
                if month < 1 or month > 12:
                    errors['expiry'] = 'Invalid month'
                elif year < now.year or (year == now.year and month < now.month):
                    errors['expiry'] = 'Card is expired'
            except:
                errors['expiry'] = 'Invalid expiry format'
        else:
            errors['expiry'] = 'Use MM/YY format'

    if cvv and (len(cvv) < 3 or len(cvv) > 4):
        errors['cvv'] = 'CVV must be 3-4 digits'

    network = detect_card_network(card_number)
    valid = len(errors) == 0

    return jsonify({
        "valid": valid,
        "errors": errors,
        "card_network": network,
        "card_type": "credit",
        "luhn_passed": luhn_check(cleaned) if cleaned else False,
        "masked": "**** **** **** " + cleaned[-4:] if len(cleaned) >= 4 else ""
    })

@app.route('/api/process', methods=['POST'])
def process_payment():
    data = request.json
    card_number = data.get('card_number', '')
    amount = float(data.get('amount', 0))
    merchant = data.get('merchant', 'Unknown')
    currency = data.get('currency', 'USD')
    name = data.get('name', '')

    if amount <= 0:
        return jsonify({"success": False, "error": "Invalid amount"}), 400

    time.sleep(random.uniform(0.1, 0.4))  # Simulate processing

    score = fraud_score(card_number, amount, merchant)
    cleaned = card_number.replace(' ', '')
    network = detect_card_network(card_number)
    fees = calculate_fees(amount)
    txn_id = generate_txn_id()

    if score >= 70:
        status = "declined"
        reason = "High fraud risk detected"
    elif score >= 45:
        status = "flagged"
        reason = "Manual review required"
    elif not luhn_check(cleaned):
        status = "declined"
        reason = "Invalid card number"
    else:
        status = "approved"
        reason = "Transaction approved"

    txn = {
        "id": txn_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "merchant": merchant,
        "card_last4": cleaned[-4:] if len(cleaned) >= 4 else "****",
        "card_network": network,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "fees": fees if status == "approved" else None,
        "fraud_score": score,
        "risk_level": "high" if score >= 70 else "medium" if score >= 45 else "low",
        "reason": reason,
        "cardholder": name,
        "country": "US",
        "response_time_ms": random.randint(80, 280),
    }

    transactions.insert(0, txn)
    analytics["total_processed"] += 1
    if status == "approved":
        analytics["total_volume"] += amount

    return jsonify({
        "success": status == "approved",
        "transaction": txn,
        "fees": fees,
        "fraud_score": score,
        "auth_code": ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)) if status == "approved" else None,
        "message": reason
    })

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    status_filter = request.args.get('status', '')
    start = (page - 1) * per_page
    filtered = [t for t in transactions if not status_filter or t['status'] == status_filter]
    return jsonify({
        "transactions": filtered[start:start + per_page],
        "total": len(filtered),
        "page": page,
        "pages": max(1, (len(filtered) + per_page - 1) // per_page)
    })

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    statuses = [t['status'] for t in transactions]
    networks = [t['card_network'] for t in transactions]
    approved = statuses.count('approved')
    declined = statuses.count('declined')
    flagged = statuses.count('flagged')
    total = len(transactions)

    risk_distribution = {"low": 0, "medium": 0, "high": 0}
    for t in transactions:
        risk_distribution[t.get('risk_level', 'low')] += 1

    hourly = {}
    for t in transactions:
        hour = t['timestamp'][:13]
        hourly[hour] = hourly.get(hour, 0) + 1

    return jsonify({
        "total_processed": analytics["total_processed"],
        "total_volume": analytics["total_volume"],
        "success_rate": round((approved / total * 100) if total else 99.7, 1),
        "avg_response_ms": analytics["avg_response_ms"],
        "status_breakdown": {"approved": approved, "declined": declined, "flagged": flagged},
        "network_breakdown": {n: networks.count(n) for n in set(networks)},
        "risk_distribution": risk_distribution,
        "recent_count": total,
    })

@app.route('/api/fees/calculate', methods=['POST'])
def calc_fees():
    data = request.json
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400
    return jsonify(calculate_fees(amount))

@app.route('/api/luhn', methods=['POST'])
def check_luhn():
    data = request.json
    number = data.get('number', '')
    return jsonify({
        "valid": luhn_check(number),
        "network": detect_card_network(number),
        "masked": "**** **** **** " + number.replace(' ', '')[-4:] if len(number.replace(' ', '')) >= 4 else ""
    })

@app.route('/api/live-feed', methods=['GET'])
def live_feed():
    """Returns a single simulated live transaction"""
    amount = round(random.uniform(9.99, 2499.99), 2)
    card_prefix = random.choice(["4", "5", "3", "6"])
    status = random.choices(["approved", "approved", "approved", "declined", "flagged"], weights=[70, 10, 10, 7, 3])[0]
    return jsonify({
        "id": generate_txn_id(),
        "amount": amount,
        "status": status,
        "merchant": random.choice(MERCHANTS),
        "card_network": CARD_NETWORKS.get(card_prefix, "Visa"),
        "card_last4": str(random.randint(1000, 9999)),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "country": random.choice(["US", "UK", "CA", "DE", "AU", "JP"]),
        "fraud_score": random.randint(0, 60),
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
