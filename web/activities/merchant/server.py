from flask import Flask, request, jsonify
import asyncio
import os
import sys

# ensure root of project on path so we can import existing modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shop_commands.merchant.database import get_user_kkcoin, update_user_kkcoin

app = Flask(__name__)

@app.route('/api/balance')
def get_balance():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'missing user_id'}), 400
    try:
        bal = asyncio.run(get_user_kkcoin(int(user_id)))
        return jsonify({'balance': bal})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bet', methods=['POST'])
def do_bet():
    data = request.get_json()
    user_id = data.get('user_id')
    amount = data.get('amount')
    if user_id is None or amount is None:
        return jsonify({'error': 'missing fields'}), 400
    try:
        # simplistic bet: subtract amount
        asyncio.run(update_user_kkcoin(int(user_id), -int(amount)))
        bal = asyncio.run(get_user_kkcoin(int(user_id)))
        return jsonify({'success': True, 'balance': bal})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # allow CORS for local dev
    from flask_cors import CORS
    CORS(app)
    app.run(host='0.0.0.0', port=5000)
