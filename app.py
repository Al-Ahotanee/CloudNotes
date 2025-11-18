# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
import os
import sqlite3
import hashlib
import shutil
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = "super-secret-key-change-in-production-123"
UPLOAD_FOLDER = "uploaded_files"
DB_PATH = "notes_system.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================================
# DATABASE CLASS (Embedded fully)
# ================================
class NotesDatabase:
    def __init__(self):
        self.current_user = None
        self._init_db()
        self._create_demo_data()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _hash(self, p): return hashlib.sha256(p.encode()).hexdigest()

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            uploader_id INTEGER,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            downloads INTEGER DEFAULT 0,
            tags TEXT,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER,
            rating_sum INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ratings (
            note_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            review TEXT,
            PRIMARY KEY (note_id, user_id)
        );
        """)
        conn.commit()
        conn.close()

    def _create_demo_data(self):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] > 0:
            conn.close()
            return

        users = [("admin","admin123","admin@edu","admin"), ("student1","pass123","s1@edu","student"), ("professor","prof123","prof@edu","teacher")]
        for u in users:
            c.execute("INSERT INTO users (username,password,email,role) VALUES (?,?,?,?)", (u[0], self._hash(u[1]), u[2], u[3]))

        samples = [
            ("Intro to Python", "Computer Science", "Programming", "Beginner guide", 1, "python,basics", "intro_python.pdf"),
            ("Calculus I", "Mathematics", "Calculus", "Derivatives & Integrals", 2, "math,calculus", "calculus.pdf"),
            ("DBMS Notes", "Computer Science", "Databases", "SQL & Normalization", 1, "sql,db", "dbms.pdf")
        ]
        for s in samples:
            path = os.path.join(UPLOAD_FOLDER, s[6])
            with open(path, "w") as f: f.write("Demo file")
            size = os.path.getsize(path)
            c.execute("""INSERT INTO notes (title,category,subject,description,uploader_id,tags,file_path,file_name,file_size)
                         VALUES (?,?,?,?,?,?,?,?,?)""", (*s[:5], json.dumps(s[5].split(",")), path, s[6], size))
        conn.commit()
        conn.close()

    def login(self, u, p):
        conn = self._conn()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        conn.close()
        if user and user["password"] == self._hash(p):
            self.current_user = dict(user)
            return True
        return False

    def register(self, u, p, e):
        conn = self._conn()
        try:
            conn.execute("INSERT INTO users (username,password,email) VALUES (?,?,?)", (u, self._hash(p), e))
            conn.commit()
            conn.close()
            return True
        except: 
            conn.close()
            return False

    def add_note(self, title, category, subject, desc, tags, file):
        if not self.current_user: return False
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        size = os.path.getsize(path)
        tags_json = json.dumps([t.strip() for t in tags.split(",") if t.strip()])
        conn = self._conn()
        conn.execute("""INSERT INTO notes 
            (title,category,subject,description,uploader_id,tags,file_path,file_name,file_size)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (title, category, subject, desc, self.current_user["id"], tags_json, path, file.filename, size))
        conn.commit()
        conn.close()
        return True

    def search(self, q="", cat="All", sort="recent"):
        conn = self._conn()
        sql = "SELECT n.*, u.username as uploader, (n.rating_sum*1.0/NULLIF(n.rating_count,0)) as avg FROM notes n JOIN users u ON n.uploader_id=u.id WHERE 1=1"
        params = []
        if q:
            sql += " AND (title LIKE ? OR description LIKE ? OR tags LIKE ?)"
            params += [f"%{q}%"]*3
        if cat != "All": sql += " AND category=?"; params.append(cat)
        order = {"recent": "upload_date DESC", "popular": "downloads DESC", "rating": "avg DESC, downloads DESC"}.get(sort, "upload_date DESC")
        sql += f" ORDER BY {order}"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def download(self, note_id):
        if not self.current_user: return False, None
        conn = self._conn()
        note = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not note: 
            conn.close()
            return False, None
        conn.execute("UPDATE notes SET downloads=downloads+1 WHERE id=?", (note_id,))
        conn.commit()
        conn.close()
        return True, note["file_path"]

    def rate(self, note_id, rating, review=""):
        if not self.current_user: return False
        conn = self._conn()
        conn.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?,?)", (note_id, self.current_user["id"], rating, review))
        conn.execute("UPDATE notes SET rating_sum=(SELECT SUM(rating) FROM ratings WHERE note_id=?), rating_count=(SELECT COUNT(*) FROM ratings WHERE note_id=?) WHERE id=?", (note_id,note_id,note_id))
        conn.commit()
        conn.close()
        return True

    def delete(self, note_id):
        if not self.current_user: return False
        conn = self._conn()
        note = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not note or (note["uploader_id"] != self.current_user["id"] and self.current_user["role"] != "admin"):
            conn.close()
            return False
        if os.path.exists(note["file_path"]): os.remove(note["file_path"])
        conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.execute("DELETE FROM ratings WHERE note_id=?", (note_id,))
        conn.commit()
        conn.close()
        return True

    def categories(self):
        conn = self._conn()
        cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM notes").fetchall()]
        conn.close()
        return ["All"] + sorted(cats)

db = NotesDatabase()

# ================================
# ROUTES
# ================================
@app.route("/")
def index():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    if db.login(request.form["username"], request.form["password"]):
        session["user"] = db.current_user["username"]
        session["role"] = db.current_user["role"]
        flash("Login successful!", "success")
        return redirect("/dashboard")
    flash("Invalid credentials", "error")
    return redirect("/")

@app.route("/register", methods=["POST"])
def register():
    if db.register(request.form["username"], request.form["password"], request.form["email"]):
        flash("Registered! Now login.", "success")
    else:
        flash("Username taken", "error")
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    notes = db.search(request.args.get("q",""), request.args.get("cat","All"), request.args.get("sort","recent"))
    return render_template("index.html", 
                          user=session["user"],
                          notes=notes,
                          categories=db.categories(),
                          q=request.args.get("q",""),
                          cat=request.args.get("cat","All"),
                          sort=request.args.get("sort","recent"))

@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session: return redirect("/")
    db.add_note(
        request.form["title"],
        request.form["category"],
        request.form["subject"],
        request.form.get("desc", ""),
        request.form.get("tags", ""),
        request.files["file"]
    )
    flash("Note uploaded!", "success")
    return redirect("/dashboard")

@app.route("/download/<int:nid>")
def download(nid):
    if "user" not in session: return redirect("/")
    ok, path = db.download(nid)
    if not ok or not path or not os.path.exists(path):
        flash("File not found", "error")
        return redirect("/dashboard")
    return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True)

@app.route("/rate/<int:nid>", methods=["POST"])
def rate(nid):
    if "user" in session:
        db.rate(nid, int(request.form["rating"]), request.form.get("review",""))
        flash("Thanks for rating!", "success")
    return redirect("/dashboard")

@app.route("/delete/<int:nid>")
def delete(nid):
    if db.delete(nid):
        flash("Note deleted", "success")
    else:
        flash("Cannot delete", "error")
    return redirect("/dashboard")

# ================================
# RUN
# ================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
