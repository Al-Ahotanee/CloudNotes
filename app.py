# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import os, sqlite3, hashlib, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cloudnotes-final-2025"
UPLOAD_FOLDER = "uploaded_files"
DB_PATH = "notes_system.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# THIS FIXES THE fromjson ERROR
app.jinja_env.filters['fromjson'] = lambda v: json.loads(v) if v else []

class NotesDB:
    def __init__(self):
        self.user = None
        self.init_db()
        self.create_demo()

    def conn(self):
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        return c

    def init_db(self):
        with self.conn() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT DEFAULT 'student'
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT,
                    uploader_id INTEGER,
                    upload_date TEXT DEFAULT (datetime('now')),
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
                    PRIMARY KEY (note_id, user_id)
                );
            ''')

    def create_demo(self):
        with self.conn() as db:
3:
            if db.execute("SELECT 1 FROM users").fetchone():
                return
            # Create admin
            db.execute("INSERT INTO users(username,password,email,role) VALUES(?,?,?,?)",
                       ("admin", hashlib.sha256("admin123".encode()).hexdigest(), "a@cloudnotes.pro", "admin"))
            
            # Create demo file
            path = os.path.join(UPLOAD_FOLDER, "demo.pdf")
            with open(path, "w") as f:
                f.write("CloudNotes Pro - Demo File")

            # Insert demo note (9 columns, 9 values)
            db.execute("""INSERT INTO notes 
                (title, category, subject, description, uploader_id, tags, file_path, file_name, file_size)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                ("Python Programming", "Computer Science", "Programming", "Complete beginner guide", 1,
                 json.dumps(["python", "programming", "basics"]), path, "demo.pdf", 1234))

    def login(self, u, p):
        with self.conn() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
            if user and user["password"] == hashlib.sha256(p.encode()).hexdigest():
                self.user = dict(user)
                return True
        return False

    def register(self, u, p, e):
        with self.conn() as db:
            try:
                db.execute("INSERT INTO users(username,password,email) VALUES(?,?,?)",
                          (u, hashlib.sha256(p.encode()).hexdigest(), e))
                return True
            except:
                return False

    def add_note(self, title, cat, subj, desc, tags, file):
        if not self.user: return False
        fn = f"{int(datetime.now().timestamp())}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, fn)
        file.save(path)
        tags_json = json.dumps([t.strip() for t in tags.split(",") if t.strip()])
        with self.conn() as db:
            db.execute("""INSERT INTO notes(title,category,subject,description,uploader_id,tags,file_path,file_name,file_size)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (title, cat, subj, desc, self.user["id"], tags_json, path, file.filename, os.path.getsize(path)))
        return True

    def search(self, q="", cat="All", sort="recent"):
        with self.conn() as db:
            sql = """SELECT n.*, u.username as uploader,
                     CASE WHEN rating_count>0 THEN ROUND(rating_sum*1.0/rating_count,1) ELSE 0 END as avg
                     FROM notes n JOIN users u ON n.uploader_id=u.id WHERE 1=1"""
            params = []
            if q:
                sql += " AND (title LIKE ? OR subject LIKE ? OR tags LIKE ?)"
                params += [f"%{q}%"]*3
            if cat != "All":
                sql += " AND category=?"
                params.append(cat)
            order = {"recent":"upload_date DESC", "popular":"downloads DESC", "rating":"avg DESC"}.get(sort, "upload_date DESC")
            return [dict(r) for r in db.execute(sql + f" ORDER BY {order}", params)]

    def download(self, nid):
        if not self.user: return False, None
        with self.conn() as db:
            note = db.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
            if not note: return False, None
            db.execute("UPDATE notes SET downloads=downloads+1 WHERE id=?", (nid,))
            return True, note["file_path"]

    def rate(self, nid, rating):
        if not self.user: return
        with self.conn() as db:
            db.execute("INSERT OR REPLACE INTO ratings VALUES(?,?,?)", (nid, self.user["id"], rating))
            db.execute("UPDATE notes SET rating_sum=(SELECT SUM(rating) FROM ratings WHERE note_id=?), rating_count=(SELECT COUNT(*) FROM ratings WHERE note_id=?) WHERE id=?", (nid,nid,nid))

    def delete(self, nid):
        if not self.user: return False
        with self.conn() as db:
            note = db.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
            if not note or (note["uploader_id"] != self.user["id"] and self.user["role"] != "admin"):
                return False
            if os.path.exists(note["file_path"]):
                os.remove(note["file_path"])
            db.execute("DELETE FROM notes WHERE id=?", (nid,))
            return True

    def categories(self):
        with self.conn() as db:
            return ["All"] + [r[0] for r in db.execute("SELECT DISTINCT category FROM notes")]

db = NotesDB()

@app.route("/"); def index(): return redirect("/dashboard") if "user" in session else render_template("index.html")
@app.route("/login", methods=["POST"])
def login():
    if db.login(request.form["username"], request.form["password"]):
        session["user"] = db.user["username"]
        session["role"] = db.user["role"]
        flash("Welcome back!", "success")
    else:
        flash("Wrong credentials", "error")
    return redirect("/")
@app.route("/register", methods=["POST"])
def register():
    if db.register(request.form["username"], request.form["password"], request.form["email"]):
        flash("Registered! Login now", "success")
    else:
        flash("Username taken", "error")
    return redirect("/")
@app.route("/logout"); def logout(): session.clear(); return redirect("/")
@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    notes = db.search(request.args.get("q",""), request.args.get("cat","All"), request.args.get("sort","recent"))
    return render_template("index.html", user=session["user"], role=session["role"], notes=notes, categories=db.categories(),
                          q=request.args.get("q",""), cat=request.args.get("cat","All"))
@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session: return redirect("/")
    db.add_note(request.form["title"], request.form["category"], request.form["subject"],
                request.form.get("desc",""), request.form.get("tags",""), request.files["file"])
    flash("Uploaded!", "success")
    return redirect("/dashboard")
@app.route("/download/<int:nid>")
def download(nid):
    ok, path = db.download(nid)
    if not ok: flash("Not found", "error"); return redirect("/dashboard")
    return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True)
@app.route("/rate/<int:nid>", methods=["POST"])
def rate(nid):
    db.rate(nid, int(request.form["rating"]))
    flash("Rated!", "success")
    return redirect("/dashboard")
@app.route("/delete/<int:nid>")
def delete(nid):
    db.delete(nid)
    flash("Deleted", "success")
    return redirect("/dashboard")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
