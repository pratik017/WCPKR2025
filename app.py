from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
import csv
from io import StringIO
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
app.secret_key = "your-very-secret-key"  # Change this for production

# Simple admin password
ADMIN_PASSWORD = "admin123"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/checkin", methods=["POST"])
def checkin():
    data = request.json
    attendee_id = data.get("attendeeId")
    section = data.get("section")

    if not attendee_id or not section:
        return jsonify(success=False, message="Missing attendeeId or section."), 400

    doc_ref = db.collection("attendees").document(attendee_id)
    doc = doc_ref.get()

    if not doc.exists:
        return jsonify(success=False, message="Attendee not found."), 404

    attendee = doc.to_dict()
    checked_in = attendee.get("checkedIn", {})

    if checked_in.get(section) is True:
        return jsonify(success=False, message=f"Already checked in for {section}."), 409

    checked_in[section] = True
    doc_ref.update({"checkedIn": checked_in})

    return jsonify(success=True, message=f"Check-in for {section} successful!")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("admin.html", error="Invalid password")

    if not session.get("admin_logged_in"):
        return render_template("admin.html", login=True)

    attendees_ref = db.collection("attendees")
    docs = attendees_ref.stream()
    attendees = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        attendees.append(data)

    # Section-wise summary
    section_stats = {
        "registration": [],
        "breakfast": [],
        "lunch": [],
        "beforeParty": [],
        "afterParty": []
    }

    for attendee in attendees:
        ci = attendee.get("checkedIn", {})
        for section in section_stats:
            if ci.get(section):
                section_stats[section].append(attendee)

    return render_template("admin.html", attendees=attendees, section_stats=section_stats)

@app.route("/admin/reset", methods=["POST"])
def admin_reset():
    if not session.get("admin_logged_in"):
        return jsonify(success=False, message="Unauthorized"), 401

    attendees_ref = db.collection("attendees")
    docs = attendees_ref.stream()
    batch = db.batch()
    for doc in docs:
        batch.update(doc.reference, {"checkedIn": {}})
    batch.commit()
    return jsonify(success=True, message="All check-in statuses have been reset.")
@app.route("/admin/toggle_checkin", methods=["POST"])
def toggle_checkin():
    if "admin_logged_in" not in session:
        return jsonify(success=False, message="Not authorized."), 403

    data = request.get_json()
    attendee_id = data.get("attendee_id")
    section = data.get("section")

    if not attendee_id or not section:
        return jsonify(success=False, message="Missing data."), 400

    doc_ref = db.collection("attendees").document(attendee_id)
    doc = doc_ref.get()

    if not doc.exists:
        return jsonify(success=False, message="Attendee not found."), 404

    attendee = doc.to_dict()
    checked_in = attendee.get("checkedIn", {})
    current_status = checked_in.get(section, False)
    checked_in[section] = not current_status

    doc_ref.update({"checkedIn": checked_in})

    return jsonify(success=True, message="Check-in status toggled.")
@app.route("/admin/export_attendees")
def export_attendees():
    if "admin_logged_in" not in session:
        return "Unauthorized", 403

    attendees_ref = db.collection("attendees").stream()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Registration", "Breakfast", "Lunch", "Before Party", "After Party"])

    for doc in attendees_ref:
        data = doc.to_dict()
        checked = data.get("checkedIn", {})
        writer.writerow([
            doc.id,
            data.get("name", ""),
            data.get("email", ""),
            "Yes" if checked.get("registration") else "No",
            "Yes" if checked.get("breakfast") else "No",
            "Yes" if checked.get("lunch") else "No",
            "Yes" if checked.get("beforeParty") else "No",
            "Yes" if checked.get("afterParty") else "No"
        ])

    output.seek(0)
    return Response(output, mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=attendee_list.csv"})


@app.route("/admin/export_section/<section>")
def export_section(section):
    if "admin_logged_in" not in session:
        return "Unauthorized", 403

    attendees_ref = db.collection("attendees").stream()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email"])

    for doc in attendees_ref:
        data = doc.to_dict()
        checked = data.get("checkedIn", {})
        if checked.get(section):
            writer.writerow([
                doc.id,
                data.get("name", ""),
                data.get("email", "")
            ])

    output.seek(0)
    return Response(output, mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment;filename={section}_checkins.csv"})
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)
