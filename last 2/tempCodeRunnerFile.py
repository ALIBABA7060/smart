from flask import Flask, render_template, request, send_file, redirect, url_for, session, flash
import os, json, shutil, csv
from datetime import datetime
import face_recognition
import numpy as np
from PIL import Image
from functools import wraps
# from twilio.rest import Client  # Uncomment if you use SMS

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for sessions

# -------------------------------
# Teacher accounts storage
# -------------------------------
accounts_file = "teachers.json"
if not os.path.exists(accounts_file):
    with open(accounts_file, "w") as f:
        json.dump({}, f)

def load_teachers():
    with open(accounts_file, "r") as f:
        return json.load(f)

def save_teachers(teachers):
    with open(accounts_file, "w") as f:
        json.dump(teachers, f)

# -------------------------------
# Login required decorator
# -------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher' not in session:
            flash("Please login first!", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------
# Student database setup
# -------------------------------
path = "students_db"
if not os.path.exists(path):
    os.makedirs(path)

images = []
student_names = []

# Replace with real parent numbers
student_parents = {
    "ali": "+7060293337",
    "bob": "+919876543210",
    "charlie": "+918888777666"
}

image_extensions = ('.jpg', '.jpeg', '.png')

def load_students():
    global images, student_names
    images.clear()
    student_names.clear()
    for file in os.listdir(path):
        if file.lower().endswith(image_extensions):
            try:
                pil_img = Image.open(os.path.join(path, file)).convert('RGB')
                img = np.array(pil_img)
                encodings = face_recognition.face_encodings(img)
                if len(encodings) > 0:
                    images.append(encodings[0])
                    student_names.append(os.path.splitext(file)[0].lower())
                else:
                    print(f"No face found in {file}, skipping.")
            except Exception as e:
                print(f"Error loading {file}: {e}")
    print("Loaded students:", student_names)

load_students()

# -------------------------------
# Routes: Signup & Login
# -------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == "POST":
        username = request.form.get("username").strip().lower()
        password = request.form.get("password").strip()
        if not username or not password:
            flash("Username and password required!", "warning")
            return redirect(url_for("signup"))

        teachers = load_teachers()
        if username in teachers:
            flash("Username already registered!", "danger")
            return redirect(url_for("signup"))

        teachers[username] = password
        save_teachers(teachers)
        flash("Account created! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip().lower()
        password = request.form.get("password").strip()
        teachers = load_teachers()
        if username in teachers and teachers[username] == password:
            session['teacher'] = username
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password!", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop('teacher', None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# -------------------------------
# Routes: Main App
# -------------------------------
@app.route('/')
@login_required
def index():
    return render_template("index.html")

@app.route('/attendance')
@login_required
def attendance_page():
    return render_template("attendance.html")

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['photo']
    filepath = "uploaded_group.jpg"
    file.save(filepath)

    pil_img = Image.open(filepath).convert('RGB')
    group_photo = np.array(pil_img)

    group_face_locations = face_recognition.face_locations(group_photo)
    group_face_encodings = face_recognition.face_encodings(group_photo, group_face_locations)

    attendance = {student: "Absent" for student in student_names}
    for face_encoding in group_face_encodings:
        matches = face_recognition.compare_faces(images, face_encoding, tolerance=0.6)
        face_distances = face_recognition.face_distance(images, face_encoding)
        best_match_index = np.argmin(face_distances)
        if matches[best_match_index]:
            name = student_names[best_match_index]
            attendance[name] = "Present"

    return render_template("result.html", attendance=attendance, today=datetime.now().strftime("%Y-%m-%d"))

@app.route('/save_attendance', methods=['POST'])
@login_required
def save_attendance():
    today = datetime.now().strftime("%Y-%m-%d")
    attendance = {}
    for student in student_names:
        status = request.form.get(student, "Absent")
        attendance[student] = status

    filename = f"attendance_{today}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Date", "Status"])
        for student, status in attendance.items():
            writer.writerow([student, today, status])

    # Optional Twilio SMS code here if needed

    return render_template("download.html", filename=filename)

@app.route('/download/<filename>')
@login_required
def download(filename):
    return send_file(filename, as_attachment=True)

# -------------------------------
# Student Management
# -------------------------------
@app.route('/students')
@login_required
def students():
    student_data = []
    for student in student_names:
        for ext in ['.jpg', '.jpeg', '.png']:
            img_path = os.path.join(path, f"{student}{ext}")
            if os.path.exists(img_path):
                static_path = os.path.join("static", f"{student}{ext}")
                if not os.path.exists(static_path):
                    shutil.copy(img_path, static_path)
                student_data.append({"name": student.title(), "image": f"/static/{student}{ext}"})
                break
    return render_template("students.html", students=student_data)

@app.route('/add_student', methods=['POST'])
@login_required
def add_student():
    name = request.form.get("name").strip().lower()
    photo = request.files['photo']

    if not name or not photo:
        return "Name and Photo required!", 400

    ext = os.path.splitext(photo.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png']:
        return "Only JPG, JPEG, PNG allowed!", 400

    save_path = os.path.join(path, f"{name}{ext}")
    photo.save(save_path)

    try:
        pil_img = Image.open(save_path).convert('RGB')
        img = np.array(pil_img)
        encodings = face_recognition.face_encodings(img)
        if len(encodings) > 0:
            images.append(encodings[0])
            student_names.append(name)
            print(f"Added new student: {name}")
        else:
            os.remove(save_path)
            return "No face detected in uploaded image!", 400
    except Exception as e:
        os.remove(save_path)
        return f"Error processing image: {e}", 400

    return redirect(url_for('students'))

@app.route('/take_attendance')
@login_required
def take_attendance():
    return render_template("take_attendance.html")

# -------------------------------
# Dashboard
# -------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    total_students = len(student_names)
    today_csv = f"attendance_{datetime.now().strftime('%Y-%m-%d')}.csv"
    present_count = 0
    absent_count = 0
    if os.path.exists(today_csv):
        with open(today_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Status"] == "Present":
                    present_count += 1
                else:
                    absent_count += 1

    now = datetime.now()
    return render_template("dashboard.html",
                           total_students=total_students,
                           present_count=present_count,
                           absent_count=absent_count,
                           now=now)

# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
