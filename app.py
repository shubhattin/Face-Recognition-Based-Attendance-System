from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    Response,
)  # pyright: ignore[reportMissingImports]
import sqlite3
from datetime import datetime
import subprocess
import os
import csv
import io
from glob import glob

app = Flask(__name__)
app.secret_key = "dev-secret"


def _status():
    faces_dir = os.path.join(os.getcwd(), "data", "data_faces_from_camera")
    has_images = False
    people = []
    if os.path.isdir(faces_dir):
        for root, _, files in os.walk(faces_dir):
            imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if imgs:
                has_images = True
            if root != faces_dir and imgs:
                people.append(os.path.basename(root))
    features_csv = os.path.join("data", "features_all.csv")
    has_features = os.path.exists(features_csv)
    return has_images, has_features, people


@app.route("/")
def index():
    has_images, has_features, people = _status()
    return render_template(
        "index.html",
        selected_date="",
        no_data=False,
        has_images=has_images,
        has_features=has_features,
        people=people,
    )


@app.route("/attendance", methods=["POST"])
def attendance():
    selected_date = request.form.get("selected_date")
    selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
    formatted_date = selected_date_obj.strftime("%Y-%m-%d")

    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, time FROM attendance WHERE date = ?", (formatted_date,)
    )
    attendance_data = cursor.fetchall()

    conn.close()

    has_images, has_features, people = _status()
    if not attendance_data:
        return render_template(
            "index.html",
            selected_date=selected_date,
            no_data=True,
            has_images=has_images,
            has_features=has_features,
            people=people,
        )

    return render_template(
        "index.html",
        selected_date=selected_date,
        attendance_data=attendance_data,
        has_images=has_images,
        has_features=has_features,
        people=people,
    )


@app.route("/start_register", methods=["POST"])
def start_register():
    try:
        subprocess.Popen(
            [
                os.getenv("PYTHON_EXECUTABLE", __import__("sys").executable),
                os.path.join(os.getcwd(), "get_faces_from_camera_tkinter.py"),
            ],
            cwd=os.getcwd(),
        )
        flash("Face registration window launched. Save several images, then close it.")
    except Exception as e:
        flash(f"Failed to start registration: {e}")
    return redirect(url_for("index"))


@app.route("/start_attendance", methods=["POST"])
def start_attendance():
    try:
        # If no face images found, guide the user instead of launching empty recognizer
        has_images, _, _ = _status()
        if not has_images:
            flash(
                "No face images found. Please open Face Registration and save several images first."
            )
            return redirect(url_for("index"))

        # Auto-generate features before starting attendance if needed
        features_csv = os.path.join(os.getcwd(), "data", "features_all.csv")
        need_extract = True
        if os.path.exists(features_csv):
            need_extract = False
        if need_extract:
            subprocess.check_call(
                [
                    os.getenv("PYTHON_EXECUTABLE", __import__("sys").executable),
                    os.path.join(os.getcwd(), "features_extraction_to_csv.py"),
                ],
                cwd=os.getcwd(),
            )

        subprocess.Popen(
            [
                os.getenv("PYTHON_EXECUTABLE", __import__("sys").executable),
                os.path.join(os.getcwd(), "attendance_taker.py"),
            ],
            cwd=os.getcwd(),
        )
        flash("Attendance recognizer launched. Press 'q' in the window to quit.")
    except Exception as e:
        flash(f"Failed to start attendance recognizer: {e}")
    return redirect(url_for("index"))


@app.route("/export", methods=["GET"])
def export():
    selected_date = request.args.get("selected_date")
    try:
        selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
        formatted_date = selected_date_obj.strftime("%Y-%m-%d")
    except Exception:
        return redirect(url_for("index"))

    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, time, date FROM attendance WHERE date = ?", (formatted_date,)
    )
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "time", "date"])
    writer.writerows(rows)
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="attendance_{formatted_date}.csv"'
        },
    )


if __name__ == "__main__":
    # Run on an alternate port to avoid conflicts and listen on all interfaces
    app.run(host="0.0.0.0", port=5050, debug=True)
