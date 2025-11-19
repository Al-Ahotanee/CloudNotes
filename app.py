# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import os, sqlite3, hashlib, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cloudnotes-pro-2025")
UPLOAD_FOLDER = "uploaded_files"
DB_PATH = "notes_system.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Critical: Fix the "No filter named 'fromjson'" error
app.jinja_env.filters['fromjson'] = lambda v: json.loads(v) if v else []

class NotesDB:
    def __init__(self):
        self.user = None
        self.init_db()
        self.demo_data()

    def conn(self):
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        return c

    def hash(self, p): return hashlib.sha256(p.encode()).hexdigest()

    def init_db(self):
        with self.conn() as db:
            db.executescript("""
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
                    note_id INTEGER, user_id INTEGER, rating INTEGER,
                    PRIMARY KEY (note_id, user_id)
                );
            """)

    def demo_data(self):
        with self.conn() as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone(): return
            users = [("admin","admin123","admin@cloudnotes.pro","admin"), ("alice","pass123","alice@edu","student")]
            for u in users: db.execute("INSERT INTO users(username,password,email,role) VALUES(?,?,?,?)",
                                          (u[0], self.hash(u[1]), u[2], u[3]))
            notes = [
                ("Advanced Python", "Computer Science", "Programming", "OOP, Decorators, Async", 1, "python,oop,advanced", "python.pdf"),
                ("Linear Algebra", "Mathematics", "Algebra", "Vectors, Matrices, Eigenvalues", 2, "math,algebra,linear", "linear.pdf")
            ]
            for n in notes:
                path = os.path.join(UPLOAD_FOLDER, n[6])
                open(path, "w").write("Demo file")
                db.execute("""INSERT INTO notes(title,category,subject,description,uploader_id,tags,file_path,file_name,file_size)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                           (n[0],n[1],n[2],n[3],n[4],json.dumps(n[5].split(",")),path,n[6],1024))

    def login(self,u,p):
        with self.conn() as db:
            user = db.execute("SELECT * FROM users WHERE username=?",(u,)).fetchone()
            if user and user["password"] == self.hash(p):
                self.user = dict(user)
                return True
        return False

    def register(self,u,p,e):
        with self.conn() as db:
            try:
                db.execute("INSERT INTO users(username,password,email) VALUES(?,?,?)",(u,self.hash(p),e))
                return True
            except: return False

    def add_note(self,t,c,s,d,tags,file):
        if not self.user: return False
        fn = f"{int(datetime.now().timestamp())}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, fn)
        file.save(path)
        tags_list = [x.strip() for x in tags.split(",") if x.strip()]
        with self.conn() as db:
            db.execute("""INSERT INTO notes(title,category,subject,description,uploader_id,tags,file_path,file_name,file_size)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                      (t,c,s,d,self.user["id"],json.dumps(tags_list),path,file.filename,os.path.getsize(path)))
        return True

    def search(self,q="",cat="All",sort="recent"):
        with self.conn() as db:
            sql = """SELECT n.*, u.username as uploader,
                     CASE WHEN rating_count>0 THEN ROUND(rating_sum*1.0/rating_count,1) ELSE 0 END as avg_rating
                     FROM notes n JOIN users u ON n.uploader_id=u.id WHERE 1=1"""
            params = []
            if q:
                sql += " AND (title LIKE ? OR subject LIKE ? OR tags LIKE ?)"
                params += [f"%{q}%"] * 3
            if cat != "All": sql += " AND category=?"; params.append(cat)
            order = {"recent":"upload_date DESC", "popular":"downloads DESC", "rating":"avg_rating DESC"}.get(sort,"upload_date DESC")
            return [dict(r) for r in db.execute(sql + f" ORDER BY {order}", params)]

    def download(self,id):
        if not self.user: return False,None
        with self.conn() as db:
            n = db.execute("SELECT * FROM notes WHERE id=?",(id,)).fetchone()
            if not n: return False,None
            db.execute("UPDATE notes SET downloads=downloads+1 WHERE id=?",(id,))
            return True, n["file_path"]

    def rate(self,id,rating):
        if not self.user: return
        with self.conn() as db:
            db.execute("INSERT OR REPLACE INTO ratings VALUES(?,?,?)",(id,self.user["id"],rating))
            db.execute("""UPDATE notes SET 
                rating_sum = (SELECT SUM(rating) FROM ratings WHERE note_id=?),
                rating_count = (SELECT COUNT(*) FROM ratings WHERE note_id=?)
                WHERE id=?""",(id,id,id))

    def delete(self,id):
        if not self.user: return False
        with self.conn() as db:
            n = db.execute("SELECT * FROM notes WHERE id=?",(id,)).fetchone()
            if not n or (n["uploader_id"]!=self.user["id"] and self.user["role"]!="admin"): return False
            if os.path.exists(n["file_path"]): os.remove(n["file_path"])
            db.execute("DELETE FROM notes WHERE id=?",(id,))
            return True

    def categories(self):
        with self.conn() as db:
            return ["All"] + sorted([r[0] for r in db.execute("SELECT DISTINCT category FROM notes")])

db = NotesDB()

@app.route("/"); def home():
    if "user" in session: return redirect("/dashboard")
    return render_template("index.html")

@app.route("/login",methods=["POST"])
def login():
    if db.login(request.form["username"],request.form["password"]):
        session["user"] = db.user["username"]
        session["role"] = db.user["role"]
        flash("Welcome back, {session["user"]}!","success")
    else: flash("Invalid credentials","error")
    return redirect("/")

@app.route("/register",methods=["POST"])
def register():
    if db.register(request.form["username"],request.form["password"],request.form["email"]):
        flash("Account created! Please login","success")
    else: flash("Username taken","error")
    return redirect("/")

@app.route("/logout"); def logout(): session.clear(); flash("Logged out","info"); return redirect("/")
@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    notes = db.search(request.args.get("q",""), request.args.get("cat","All"), request.args.get("sort","recent"))
    return render_template("index.html", user=session["user"], role=session["role"],
                          notes=notes, categories=db.categories(),
                          q=request.args.get("q",""), cat=request.args.get("cat","All"))

@app.route("/upload",methods=["POST"])
def upload():
    if "user" not in session: return redirect("/")
    db.add_note(request.form["title"],request.form["category"],request.form["subject"],
                request.form.get("desc",""),request.form.get("tags",""),request.files["file"])
    flash("Note uploaded successfully!","success")
    return redirect("/dashboard")

@app.route("/download/<int:id>"); def download(id):
    ok,path = db.download(id)
    if not ok: flash("File not found","error"); return redirect("/dashboard")
    return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True)

@app.route("/rate/<int:id>",methods=["POST"]); def rate(id): db.rate(id,int(request.form["rating"])); flash("Thanks for rating!","success"); return redirect("/dashboard")
@app.route("/delete/<int:id>"); def delete(id): db.delete(id); flash("Note deleted","success"); return redirect("/dashboard")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=os.environ.get("PORT",5000))
