from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

# Database setup
DATABASE = 'database.db'

def get_db():
    """Create a database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables"""
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("Database initialized successfully")

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/items', methods=['GET'])
def get_items():
    """Get all items from the database"""
    try:
        db = get_db()
        items = db.execute('SELECT * FROM items ORDER BY created_at DESC').fetchall()
        db.close()
        return jsonify([dict(row) for row in items]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/items', methods=['POST'])
def create_item():
    """Create a new item"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        db = get_db()
        cursor = db.execute(
            'INSERT INTO items (name, description) VALUES (?, ?)',
            (name, description)
        )
        db.commit()
        item_id = cursor.lastrowid
        
        # Fetch the created item to return complete data
        item = db.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        db.close()
        
        return jsonify(dict(item)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    """Delete an item by ID"""
    try:
        db = get_db()
        result = db.execute('DELETE FROM items WHERE id = ?', (item_id,))
        db.commit()
        db.close()
        
        if result.rowcount == 0:
            return jsonify({'error': 'Item not found'}), 404
        
        return jsonify({'success': True, 'message': 'Item deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    """Update an item by ID"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        db = get_db()
        result = db.execute(
            'UPDATE items SET name = ?, description = ? WHERE id = ?',
            (name, description, item_id)
        )
        db.commit()
        
        if result.rowcount == 0:
            db.close()
            return jsonify({'error': 'Item not found'}), 404
        
        item = db.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        db.close()
        
        return jsonify(dict(item)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Initialize database before starting the app
    init_db()
    
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get('PORT', 10000))
    
    # Run the app
    app.run(host='0.0.0.0', port=port, debug=False)
