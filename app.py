from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime

app = Flask(__name__)

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['expense_sharing']
users_collection = db['users']
expenses_collection = db['expenses']
groups_collection = db['groups']
settlements_collection = db['settlements']

def send_notification(user_email, message):
    print(f"Notification sent to {user_email}: {message}")

# User Endpoints
@app.route('/users', methods=['POST'])
def create_user():
    data = request.json
    email = data.get('email')
    name = data.get('name')
    mobile = data.get('mobile')

    if not email or not name or not mobile:
        return jsonify({'error': 'Missing fields: email, name, or mobile'}), 400

    existing_user = users_collection.find_one({'email': email})
    if existing_user:
        return jsonify({'error': 'User with this email already exists'}), 400

    user = {
        "email": email,
        "name": name,
        "mobile": mobile
    }

    users_collection.insert_one(user)
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/users', methods=['GET'])
def get_all_users():
    users = list(users_collection.find({}, {"_id": 0}))
    return jsonify(users), 200

@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    user = users_collection.find_one({'_id': ObjectId(user_id)})
    if not user:
        return jsonify({'error': 'User not found'}), 404
    user['_id'] = str(user['_id'])  
    return jsonify(user)


# Group Endpoints
@app.route('/groups', methods=['POST'])
def create_group():
    data = request.json
    group_name = data.get('name')
    participants = data.get('participants')

    if not group_name or not participants:
        return jsonify({'error': 'Missing fields: name or participants'}), 400

    for participant in participants:
        if 'user_id' not in participant or 'name' not in participant or 'amount' not in participant:
            return jsonify({'error': 'Each participant must have a user_id, name, and amount'}), 400

    group = {
        "name": group_name,
        "participants": participants  
    }

    groups_collection.insert_one(group)
    return jsonify({'message': 'Group created successfully', 'group_id': str(group['_id'])}), 201

@app.route('/groups/<group_id>', methods=['GET'])
def get_group_details(group_id):
    group = groups_collection.find_one({"_id": group_id})

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    return jsonify(group), 200


# Expense Endpoints

@app.route('/expenses', methods=['POST'])
def add_expense():
    data = request.json
    split_method = data['split_method']
    participants = data['participants']
    total_amount = data['total_amount']
    group_id = data.get('group_id')

    if split_method not in ['equal', 'exact', 'percentage']:
        return jsonify({'error': 'Invalid split method'}), 400

    if split_method == 'percentage':
        total_percentage = sum(participant['percentage'] for participant in participants)
        if total_percentage != 100:
            return jsonify({'error': 'Percentages must add up to 100'}), 400

    expense = {
        "total_amount": total_amount,
        "split_method": split_method,
        "participants": participants,
        "group_id": group_id,
        "created_at": datetime.datetime.utcnow()
    }
    expenses_collection.insert_one(expense)

    for participant in participants:
        user = users_collection.find_one({'_id': ObjectId(participant['user_id'])})
        send_notification(user['email'], f"You've been added to an expense of {total_amount}.")

    return jsonify({'message': 'Expense added successfully'}), 201


@app.route('/users/<user_id>/expenses', methods=['GET'])
def get_user_expenses(user_id):
    user_expenses = expenses_collection.find({"participants.user_id": user_id})
    expenses = []
    for expense in user_expenses:
        expense['_id'] = str(expense['_id'])  
        expenses.append(expense)
    return jsonify(expenses)


@app.route('/expenses', methods=['GET'])
def get_expenses():
    all_expenses = expenses_collection.find()
    expenses = []
    for expense in all_expenses:
        expense['_id'] = str(expense['_id'])  
        expenses.append(expense)
    return jsonify(expenses)


@app.route('/balance-sheet', methods=['GET'])
def download_balance_sheet():
    expenses = expenses_collection.find()
    balance_sheet = {}

    for expense in expenses:
        for participant in expense['participants']:
            user_id = participant['user_id']
            amount = participant.get('exact_amount') or (expense['total_amount'] * participant['percentage'] / 100)

            if user_id not in balance_sheet:
                balance_sheet[user_id] = 0
            balance_sheet[user_id] += amount

    return jsonify(balance_sheet)


# Settlement Feature 

@app.route('/settlements', methods=['POST'])
def settle_expense():
    data = request.json
    payer_id = data['payer_id']
    payee_id = data['payee_id']
    amount = data['amount']

    settlement = {
        "payer_id": payer_id,
        "payee_id": payee_id,
        "amount": amount,
        "created_at": datetime.datetime.utcnow()
    }
    settlements_collection.insert_one(settlement)

    payer = users_collection.find_one({'_id': ObjectId(payer_id)})
    payee = users_collection.find_one({'_id': ObjectId(payee_id)})

    send_notification(payer['email'], f"You've settled {amount} with {payee['name']}.")
    send_notification(payee['email'], f"You've received a settlement of {amount} from {payer['name']}.")

    return jsonify({'message': 'Settlement completed successfully'}), 201


@app.route('/users/<user_id>/summary', methods=['GET'])
def get_summary(user_id):
    user_expenses = expenses_collection.find({"participants.user_id": user_id})
    total_spent = 0
    total_owed = 0

    for expense in user_expenses:
        for participant in expense['participants']:
            if participant['user_id'] == user_id:
                if 'exact_amount' in participant:
                    total_spent += participant['exact_amount']
                elif 'percentage' in participant:
                    total_spent += expense['total_amount'] * (participant['percentage'] / 100)
            else:
                total_owed += participant['exact_amount'] if 'exact_amount' in participant else 0

    summary = {
        "total_spent": total_spent,
        "total_owed": total_owed
    }
    return jsonify(summary)

if __name__ == '__main__':
    app.run(debug=True)
