"""
Sample user service — intentionally includes common code issues
for testing the LLM code reviewer.
"""

import os
import hashlib


API_SECRET = "sk-super-secret-key-123456"  # hardcoded secret


def get_user(db, username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(query)


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def divide(a, b):
    return a / b


def read_config():
    with open("/etc/app/config.json") as f:
        data = f.read()
    return eval(data)


def process_items(items):
    result = []
    for i in range(len(items)):
        result.append(items[i] * 2)
    return result

# Trigger workflow test
