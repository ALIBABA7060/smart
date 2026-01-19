from flask import Flask, render_template, request, send_file, redirect, url_for, session, flash
import os, json, shutil, csv
from datetime import datetime
import face_recognition
import numpy as np
from PIL import Image
from functools import wraps
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -------------------------------
# Twilio setup
# -------------------------------
TWILIO_SID = "YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH = "YOUR_TWILIO_AUTH_TOKEN"
TWILIO_NUMBER = "+1234567890"
client = Client(TWILIO_SID, TWILIO_AUTH)

def send_sms(to_number, message):
    try:
        client.messages.create(body=message, from_=TWILIO_NUMBER, to=to_number)
        print(f"SMS sent to {to_number}")
    except Exception as e:
        print(f"Failed to send SMS to {to_number}: {e}")

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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher' not in session:
            flash("Please login first!", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------
# SMS Log
# -------------------------------
sms_log_file = "sms_log.json"
if not os.path.exists(sms_log_file):
    with open(sms_log_file, "w") as f:
        json.dump({}, f)

def load_sms_log():
    with open(sms_log_file, "r") as f:
        return json.load(f)

def save_sms_log(log):
    with open(sms_log_file, "w") as f:
        json.dump(log, f)

# -------------------------------
# Helper: Convert image to RGB
# -------------------------------
def convert_to_rgb(img_path):
    try:
        with Image.open(img_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
                img.save(img_path)
                print(f"Converted {os.path.basename(img_path)} to RGB")
    except Exception as e:
        print(f"Failed to convert {os.path.basename(img_path)}: {e}")

# -------------------------------
# Robust image loader for face_recognition
# -------------------------------
def load_image_for_face_recognition(img_path, resize_max=1600):
    with Image.open(img_path) as img:
        if img.mode not in ["RGB", "L"]:
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > resize_max:
            scale = resize_max / float(max(w, h))
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        arr = np.array(img)
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)
        return arr

# -------------------------------
# Student database setup
# -------------------------------
path = "students_db"
if not os.path.exists(path):
    os.makedirs(path)

image_extensions = ('.jpg', '.jpeg', '.png')

# -------------------------------
# Convert existing images to RGB at startup
# -------------------------------
for file in os.listdir(path):
    if file.lower().endswith(image_extensions):
        convert_to_rgb(os.path.join(path, file))

# -------------------------------
# Load students
# -------------------------------
images = []
student_names = []

student_parents = {
    "ali": "+7060293337",
    "bob": "+919876543210",
    "charlie": "+918888777666"
}

def load_students():
    global images, student_names
    images.clear()
    student_names.clear()
    for file in os.listdir(path):
        if file.lower().endswith(image_extensions):
            img_path = os.path.join(path, file)
            try:
                convert_to_rgb(img_path)  # ensure RGB
                img_array = load_image_for_face_recognition(img_path)
                encodings = face_recognition.face_encodings(img_array)
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
# Main Pages
# -------------------------------
@app.route('/')
@login_required
def index():
    return render_template("index.html")

@app.route('/attendance')
@login_required
def attendance_page():
    return render_template("attendance.html")

@app.route('/take_attendance')
@login_required
def take_attendance():
    return render_template("take_attendance.html")

# -------------------------------
# Upload & Automatic SMS
# -------------------------------
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['photo']
    filepath = "uploaded_group.jpg"
    file.save(filepath)

    try:
        group_photo = load_image_for_face_recognition(filepath)
    except Exception as e:
        flash(f"Cannot process this image. Error: {e}", "danger")
        return redirect(url_for("take_attendance"))

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

    # Automatic SMS to absent students
    sms_log = load_sms_log()
    today = datetime.now().strftime("%Y-%m-%d")
    sms_log[today] = []

    for student, status in attendance.items():
        if status == "Absent" and student in student_parents:
            msg = f"Dear parent, your child {student.title()} was absent on {today}."
            send_sms(student_parents[student], msg)
            sms_log[today].append(student.title())

    save_sms_log(sms_log)
    flash(f"Attendance marked! SMS sent to absent students' parents: {', '.join(sms_log[today])}", "success")

    return render_template("result.html", attendance=attendance, today=today, sms_sent=sms_log[today])

# -------------------------------
# Save Attendance as CSV
# -------------------------------
@app.route('/save_attendance', methods=['POST'])
@login_required
def save_attendance():
    today = datetime.now().strftime("%Y-%m-%d")
    attendance = {}
    sms_sent = []

    sms_log = load_sms_log()
    sms_log[today] = []

    for student in student_names:
        status = request.form.get(student, "Absent")
        attendance[student] = status
        if status == "Absent" and student in student_parents:
            msg = f"Dear parent, your child {student.title()} was absent on {today}."
            send_sms(student_parents[student], msg)
            sms_sent.append(student.title())
            sms_log[today].append(student.title())

    filename = f"attendance_{today}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Date", "Status"])
        for student, status in attendance.items():
            writer.writerow([student, today, status])

    save_sms_log(sms_log)
    flash(f"Attendance saved! SMS sent to absent students' parents: {', '.join(sms_log[today])}", "success")
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

    try:
        # Convert uploaded image to RGB
        photo_img = Image.open(photo)
        photo_img = photo_img.convert("RGB")
        photo_img.save(save_path)

        # Load and encode face
        img_array = load_image_for_face_recognition(save_path, resize_max=1200)
        encodings = face_recognition.face_encodings(img_array)
        if len(encodings) > 0:
            images.append(encodings[0])
            student_names.append(name)
            print(f"Added new student: {name}")
        else:
            os.remove(save_path)
            return "No face detected in uploaded image!", 400
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        return f"Error processing image: {e}", 400

    return redirect(url_for('students'))



@app.route('/delete_student/<student_name>', methods=['POST'])
@login_required
def delete_student(student_name):
    global student_names, images
    student_name = student_name.lower()
    
    # Remove student from lists
    if student_name in student_names:
        index = student_names.index(student_name)
        student_names.pop(index)
        images.pop(index)
    
    # Delete student images from students_db
    for ext in ['.jpg', '.jpeg', '.png']:
        img_path = os.path.join(path, f"{student_name}{ext}")
        if os.path.exists(img_path):
            os.remove(img_path)
    
    # Also remove from static folder if copied
    static_img_path = os.path.join("static", f"{student_name}.jpg")
    if os.path.exists(static_img_path):
        os.remove(static_img_path)
    
    flash(f"Student '{student_name.title()}' deleted successfully.", "success")
    return redirect(url_for('students'))
# -------------------------------
# Dashboard
# -------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    total_students = len(student_names)
    today = datetime.now().strftime("%Y-%m-%d")
    today_csv = f"attendance_{today}.csv"
    present_count = 0
    absent_count = 0

    sms_log = load_sms_log()
    sms_sent = sms_log.get(today, [])

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
                           sms_sent=sms_sent,
                           now=now)

if __name__ == "__main__":
    app.run(debug=True)
