from app import app
from extensions import db

with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully for Neon DB!")
    except Exception as e:
        print(f"Error creating tables: {e}")
