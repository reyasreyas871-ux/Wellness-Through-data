from flask import Flask, request, render_template_string, redirect, url_for, jsonify,Response
import io, base64, secrets
import qrcode
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import case
from db import IotDose,Prescription,AdherenceLog,Device,PharmacyDispense,IotDose
from flask import Response  # if not already added
from datetime import datetime
from datetime import date, datetime
from db import init_db, get_session, Patient, Prescription, AdherenceLog
from ml import recommend_antibiotic
import requests
import os

app = Flask(__name__)
init_db()

INDEX_HTML = """
<!doctype html>
<title>AMR Prototype</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<main class="container">
  <h1>AMR Localhost Prototype</h1>
  <ul>
    <li><a href="{{ url_for('prescribe') }}">Doctor: Create Prescription</a></li>
    <li><a href="{{ url_for('adherence') }}">Patient: Update Adherence</a></li>
    <li><a href="{{ url_for('predict') }}">AI Recommendation</a></li>
    <li><a href="{{ url_for('list_prescriptions') }}">Browse Prescriptions</a></li>
    <li><a href="{{ url_for('share_data') }}">Share anonymized data to WHO mock server</a></li>
    <li><a href="{{ url_for('iot_home') }}">IoT: QR / Pillbox / Confirm</a></li>
  </ul>
  <p>Run dashboard separately: <code>streamlit run dashboard.py</code></p>
</main>
"""

PRESCRIBE_HTML = """
<!doctype html>
<title>New Prescription</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<main class="container">
  <h2>Doctor: Create Prescription</h2>
  <form method="post">
    <fieldset>
      <legend>Patient</legend>
      <label>Name <input name="patient_name" required></label>
      <label>Age <input type="number" name="age" value="30" required></label>
      <label>Gender
        <select name="gender">
          <option>Male</option><option>Female</option><option>Other</option>
        </select>
      </label>
    </fieldset>
    <fieldset>
      <legend>Prescription</legend>
      <label>Antibiotic
       <select name="antibiotic" required>
        <option>Amoxicillin/Clavulanate</option>
        <option>Azithromycin</option>
        <option>Ciprofloxacin</option>
        <option>Doxycycline</option>
        <option>Cephalexin</option>
        <option>Metronidazole</option>
        <option>Clindamycin</option>
        <option>Levofloxacin</option>
        <option>Tetracycline</option>
        <option>Vancomycin</option>
       </select>
      </label>
      <label>Dosage (mg) <input type="number" name="dosage_mg" value="500" required></label>
      <label>Frequency per day <input type="number" name="frequency_per_day" value="3" required></label>
      <label>Days <input type="number" name="days" value="5" required></label>
      <label>Start date <input type="date" name="start_date" value="{{ today }}" required></label>
      <label>Notes <textarea name="notes"></textarea></label>
    </fieldset>
    <button type="submit">Save Prescription</button>
    <a href="{{ url_for('index') }}" role="button" class="secondary">Back</a>
  </form>
</main>
"""

ADHERENCE_HTML = """
<!doctype html>
<title>Adherence Update</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<main class="container">
  <h2>Patient: Update Adherence</h2>
  <form method="post">
    <label>Prescription
      <select name="prescription_id">
        {% for p in prescriptions %}
          <option value="{{ p.id }}">#{{ p.id }} - {{ p.patient.name }} - {{ p.antibiotic }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Action
      <select name="taken">
        <option value="1">Dose taken</option>
        <option value="0">Missed dose</option>
      </select>
    </label>
    <button type="submit">Submit</button>
    <a href="{{ url_for('index') }}" role="button" class="secondary">Back</a>
  </form>

  <h3>Recent Logs</h3>
  <table>
    <thead><tr><th>Time</th><th>Prescription</th><th>Patient</th><th>Taken?</th></tr></thead>
    <tbody>
      {% for log in logs %}
        <tr>
          <td>{{ log.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
          <td>#{{ log.prescription_id }}</td>
          <td>{{ log.prescription.patient.name }}</td>
          <td>{{ "Yes" if log.taken else "No" }}</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
</main>
"""

PREDICT_HTML = """
<!doctype html>
<title>AI Recommendation</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<main class="container">
  <h2>AI Pathogen Recommendation</h2>
  <style>
    .form-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr); /* 3 equal columns */
      gap: 15px;
      margin-bottom: 20px;
    }
    .form-grid label {
      display: flex;
      flex-direction: column;
      font-weight: bold;
    }
     .form-grid input,
     .form-grid select {
       padding: 8px;
       font-size: 14px;
       margin-top: 5px;
       border: 1px solid #ccc;
       border-radius: 5px;
       min-width: 150px; /* ensures dropdowns are not too narrow */
    }

    /* Optional: make dropdowns show all options clearly */
    select {
      background-color: #fff;
    }
  </style>
  <form method="post">
    <div class="grid">
      <label>Age
        <input type="number" name="age" value="30" required>
      </label>
      <label>Fever (degC)
        <input type="number" step="0.1" name="fever_c" value="37.8" required>
      </label>
      <label>WBC (x10^3/uL)
        <input type="number" step="0.1" name="wbc_k" value="7.2" required>
      </label>
      <label>CRP (mg/L)
        <input type="number" step="0.1" name="crp_mgL" value="6.0" required>
      </label>
      <label>Shortness of breath
        <select name="breath"><option>No</option><option>Yes</option></select>
      </label>
      <label>Chest pain
        <select name="chest_pain"><option>No</option><option>Yes</option></select>
      </label>
      <label>Travel history
        <select name="travel"><option>No</option><option>Yes</option></select>
      </label>
      <label>Comorbidity (Diabetes/Hypertension)
        <select name="comorbidity"><option>No</option><option>Yes</option></select>
      </label>
      <label>Cough
        <select name="cough"><option value="0">No</option><option value="1">Yes</option></select>
      </label>
      <label>Sore throat
        <select name="sore_throat"><option value="0">No</option><option value="1">Yes</option></select>
      </label>
      <label>Rapid bacterial test positive?
        <select name="rapid_bacterial_flag"><option value="0">No</option><option value="1">Yes</option></select>
      </label>
    </div>
    <button type="submit">Get Recommendation</button>
    <a href="{{ url_for('index') }}" role="button" class="secondary">Back</a>
  </form>

  {% if result is not none %}
  <article style="margin-top:20px;">
    <header><strong>Result</strong></header>
    <p><b>Needs antibiotic?</b> {{ "Yes" if result.needs else "No" }}</p>
    <p><b>Suggested:</b> {{ result.antibiotic if result.antibiotic else "None" }}</p>
    <p><b>Reasons:</b></p>
    <ul>
      {% if result.reasons %}
        {% for r in result.reasons %}
          <li>{{ r }}</li>
        {% endfor %}
      {% else %}
        <li>No specific reasons provided.</li>
      {% endif %}
    </ul>
  </article>
  {% endif %}
</main>
"""

LIST_HTML = """
<!doctype html>
<title>Prescriptions</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<main class="container">
  <h2>All Prescriptions</h2>
  <table>
    <thead>
      <tr>
        <th>ID</th><th>Patient</th><th>Antibiotic</th>
        <th>Dosage</th><th>Freq/day</th><th>Days</th><th>Start</th><th>Created</th>
      </tr>
    </thead>
    <tbody>
      {% for p in prescriptions %}
      <tr>
        <td>{{ p.id }}</td>
        <td><a href="{{ url_for('prescription_detail', pres_id=p.id) }}">{{ p.patient.name }}</a></td>
        <td>{{ p.antibiotic }}</td>
        <td>{{ p.dosage_mg }} mg</td>
        <td>{{ p.frequency_per_day }}</td>
        <td>{{ p.days }}</td>
        <td>{{ p.start_date }}</td>
        <td>{{ p.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <br>
  <a href="{{ url_for('download_prescriptions') }}">
    <button type="button">Download Prescriptions (CSV)</button>
</a>
<br><br>
  <a href="{{ url_for('index') }}" role="button" class="secondary">Back</a>
</main>
"""

@app.get("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/prescribe", methods=["GET", "POST"])
def prescribe():
    if request.method == "POST":
        s = get_session()
        patient = Patient(
            name=request.form["patient_name"],
            age=int(request.form["age"]),
            gender=request.form["gender"],
        )
        s.add(patient)
        s.flush()

        prescription = Prescription(
            patient_id=patient.id,
            antibiotic=request.form["antibiotic"],
            dosage_mg=int(request.form["dosage_mg"]),
            frequency_per_day=int(request.form["frequency_per_day"]),
            days=int(request.form["days"]),
            start_date=date.fromisoformat(request.form["start_date"]),
            notes=request.form.get("notes") or None,
        )
        s.add(prescription)
        s.commit()
        s.close()
        return redirect(url_for("list_prescriptions"))
    return render_template_string(PRESCRIBE_HTML, today=date.today().isoformat())

@app.route("/adherence", methods=["GET", "POST"])
def adherence():
    s = get_session()
    if request.method == "POST":
        log = AdherenceLog(
            prescription_id=int(request.form["prescription_id"]),
            taken=bool(int(request.form["taken"])),
            timestamp=datetime.utcnow(),
        )
        s.add(log)
        s.commit()
    prescriptions = s.query(Prescription).all()
    logs = s.query(AdherenceLog).order_by(AdherenceLog.timestamp.desc()).limit(20).all()
    html = render_template_string(ADHERENCE_HTML, prescriptions=prescriptions, logs=logs)
    s.close()
    return html

@app.route("/predict", methods=["GET", "POST"])
def predict():
    result = None
    if request.method == "POST":
        needs, drug, reason = recommend_antibiotic(request.form)
        result = type("R", (), {"needs": needs, "drug": drug, "reason": reason})
    return render_template_string(PREDICT_HTML, result=result)

@app.get("/prescriptions")
def list_prescriptions():
    s = get_session()
    prescriptions = s.query(Prescription).order_by(Prescription.created_at.desc()).all()
    html = render_template_string(LIST_HTML, prescriptions=prescriptions)
    s.close()
    return html

@app.route("/api/metrics")
def api_metrics():
    try:
        with get_session() as db:
            total_prescriptions = db.query(Prescription).count()
            total_logs = db.query(AdherenceLog).count()
            doses_taken = db.query(AdherenceLog).filter_by(taken=True).count()
            doses_missed = db.query(AdherenceLog).filter_by(taken=False).count()
            adherence_rate = round((doses_taken / total_logs) * 100, 2) if total_logs else 0
            wellness_index = adherence_rate

        return jsonify({
            "total_prescriptions": total_prescriptions,
            "total_logs": total_logs,
            "doses_taken": doses_taken,
            "doses_missed": doses_missed,
            "adherence_rate": adherence_rate,
            "wellness_index": wellness_index,
            "dose_history": [],
            "generated_at": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.post("/share-data")
def share_data():
    target = os.getenv("WHO_URL", "http://127.0.0.1:5001/receive")
    with app.test_client() as c:
        metrics = c.get("/api/metrics").json
    payload = {
        "source": "localhost-amr-prototype",
        "version": "0.1",
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    try:
        r = requests.post(target, json=payload, timeout=5)
        ok = r.status_code in (200, 201, 202)
        return jsonify({"ok": ok, "status_code": r.status_code, "response": r.json() if ok else r.text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/prescription/<int:pres_id>")
def prescription_detail(pres_id):
    with get_session() as db:
        pres = db.get(Prescription, pres_id)
        if not pres:
            return "Prescription not found", 404
        logs = db.query(AdherenceLog).filter_by(prescription_id=pres.id).all()
    return render_template_string("""
    <h2>Prescription Detail</h2>
    <p><b>Patient:</b> {{ pres.patient.name }}</p>
    <p><b>Age:</b> {{ pres.patient.age }}</p>
    <p><b>Gender:</b> {{ pres.patient.gender }}</p>
    <p><b>Antibiotic:</b> {{ pres.antibiotic }}</p>
    <p><b>Dosage:</b> {{ pres.dosage_mg }} mg</p>
    <p><b>Frequency:</b> {{ pres.frequency_per_day }} times/day</p>
    <p><b>Days:</b> {{ pres.days }}</p>
    <p><b>Start Date:</b> {{ pres.start_date }}</p>
    <p><b>Notes:</b> {{ pres.notes }}</p>
    <p><b>Created:</b> {{ pres.created_at }}</p>

    <h3>Adherence Log</h3>
    <table border="1">
        <tr><th>ID</th><th>Taken</th><th>Timestamp</th></tr>
        {% for log in logs %}
          <tr>
            <td>{{ log.id }}</td>
            <td>{{ "✔ Taken" if log.taken else "✘ Missed" }}</td>
            <td>{{ log.timestamp }}</td>
          </tr>
        {% endfor %}
    </table>
    <br><a href="{{ url_for('prescriptions') }}">Back to All Prescriptions</a>
    """, pres=pres, logs=logs)


@app.route("/download_prescriptions")
def download_prescriptions():
    with get_session() as db:
        rows = []
        for p in db.query(Prescription).all():
            rows.append([
                p.id,
                p.patient.name if p.patient else "N/A",
                p.antibiotic,
                p.dosage_mg,
                p.frequency_per_day,
                p.days,
                p.start_date,
                p.created_at
            ])

    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Patient", "Antibiotic", "Dosage", "Frequency", "Days", "Start", "Created"])
    writer.writerows(rows)
    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=prescriptions.csv"}
    )
# ================== IoT / QR / Pillbox FLOW ==================

IOT_HTML = """
<!doctype html>
<html>
<head>
  <title>IoT / QR & Pillbox</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/picocss@1/css/pico.min.css">
  <style>
    .grid { display:grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 16px; }
    img.qr { max-width: 220px; height:auto; border:1px solid #eee; padding:8px; border-radius:8px; }
    table { width:100%; }
    .small { font-size: 0.9rem; color:#666; }
    code { background:#f6f8fa; padding:2px 6px; border-radius:4px; }
  </style>
</head>
<body>
<main class="container">
  <h2>IoT / QR & Pillbox</h2>

  <details open>
    <summary><b>1) Generate QR for Prescription</b></summary>
    <form method="get" action="{{ url_for('iot_show_qr') }}">
      <label>Prescription
        <select name="prescription_id" required>
          {% for p in prescriptions %}
            <option value="{{ p.id }}">#{{p.id}} - {{p.patient.name}} - {{p.antibiotic}}</option>
          {% endfor %}
        </select>
      </label>
      <button type="submit">Generate QR</button>
    </form>
    {% if qr_data %}
      <p class="small">Pharmacist scans this QR. It opens the “Dispense & Activate” page.</p>
      <img class="qr" src="data:image/png;base64,{{ qr_data }}" alt="QR">
      <p class="small">Encoded URL: <code>{{ dispense_url }}</code></p>
    {% endif %}
  </details>

  <details>
    <summary><b>2) Pharmacist: Dispense & Activate Device</b></summary>
    <form method="post" action="{{ url_for('iot_dispense') }}">
      <label>Prescription
        <select name="prescription_id" required>
          {% for p in prescriptions %}
            <option value="{{ p.id }}">#{{p.id}} - {{p.patient.name}} - {{p.antibiotic}}</option>
          {% endfor %}
        </select>
      </label>
      <label>Pharmacy name
        <input name="pharmacy_name" placeholder="Apollo / CVS / ..." required>
      </label>
      <label>Device ID (pillbox / blister)
        <input name="device_id" placeholder="PBX-123456" required>
      </label>
      <button type="submit">Record Dispense & Activate</button>
    </form>
  </details>

  <details>
    <summary><b>3) Pillbox / Blister Event (simulate device)</b></summary>
    <form method="post" action="{{ url_for('iot_blister_event') }}">
      <label>Prescription
        <select name="prescription_id" required>
          {% for p in prescriptions %}
            <option value="{{ p.id }}">#{{p.id}} - {{p.patient.name}} - {{p.antibiotic}}</option>
          {% endfor %}
        </select>
      </label>
      <label>Device ID
        <input name="device_id" placeholder="PBX-123456">
      </label>
      <label>Dose #
        <input type="number" name="dose_no" min="1" placeholder="1">
      </label>
      <label>Blister opened?
        <select name="opened">
          <option value="1">Yes (create PENDING confirmation)</option>
          <option value="0">No</option>
        </select>
      </label>
      <button type="submit">Send Event</button>
    </form>
    <p class="small">If opened=Yes, a <b>pending</b> dose is created and a confirmation link is generated for the patient.</p>
  </details>

  <details open>
    <summary><b>4) Pending IoT Doses</b></summary>
    <table>
      <thead><tr><th>ID</th><th>Presc</th><th>Device</th><th>Dose</th><th>Status</th><th>Created</th><th>Action</th></tr></thead>
      <tbody>
      {% for d in pending %}
        <tr>
          <td>{{ d.id }}</td>
          <td>#{{ d.prescription_id }}</td>
          <td>{{ d.device_id or "-" }}</td>
          <td>{{ d.dose_no or "-" }}</td>
          <td>{{ d.status }}</td>
          <td>{{ d.created_at }}</td>
          <td><a href="{{ url_for('iot_confirm', token=d.token) }}">Open confirm link</a></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </details>

  <p><a href="{{ url_for('index') }}" role="button" class="secondary">Back</a></p>
</main>
</body>
</html>
"""

# Main IoT tab
@app.route("/iot")
def iot_home():
    with get_session() as db:
        prescriptions = (
            db.query(Prescription)
              .options(joinedload(Prescription.patient))
              .all()
        )
        pending = (
            db.query(IotDose)
              .filter_by(status="pending")
              .order_by(IotDose.created_at.desc())
              .limit(50)
              .all()
        )
    return render_template_string(IOT_HTML,
                                  prescriptions=prescriptions,
                                  pending=pending,
                                  qr_data=None,
                                  dispense_url=None)

# Generate and show the QR (pharmacist scan)
@app.route("/iot/qr")
def iot_show_qr():
    pres_id = int(request.args["prescription_id"])
    dispense_url = url_for("iot_show_prescription", _external=True, prescription_id=pres_id)
    # Make QR
    img = qrcode.make(dispense_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    with get_session() as db:
        prescriptions = (
            db.query(Prescription)
              .options(joinedload(Prescription.patient))
              .all()
        )
        pending = (
            db.query(IotDose)
              .filter_by(status="pending")
              .order_by(IotDose.created_at.desc())
              .limit(50)
              .all()
        )

    return render_template_string(IOT_HTML,
                                  prescriptions=prescriptions,
                                  pending=pending,
                                  qr_data=qr_b64,
                                  dispense_url=dispense_url)

# Pharmacist opens QR → records dispense & activates device
@app.route("/api/dispense", methods=["GET", "POST"])
def iot_dispense():
    if request.method == "GET":
        return redirect(url_for("iot_home"))

    pres_id = int(request.form["prescription_id"])
    pharmacy_name = request.form["pharmacy_name"].strip()
    device_id = request.form["device_id"].strip()

    with get_session() as db:
        db.add(PharmacyDispense(prescription_id=pres_id, pharmacy_name=pharmacy_name))
        exists = db.query(Device).filter_by(device_id=device_id).first()
        if not exists:
            db.add(Device(device_id=device_id, prescription_id=pres_id))
        db.commit()

    return redirect(url_for("iot_home"))

# Device/blister event → creates pending dose
@app.route("/api/blister", methods=["POST"])
def iot_blister_event():
    pres_id = int(request.form["prescription_id"])
    opened = request.form.get("opened", "0") == "1"
    device_id = request.form.get("device_id") or None
    dose_no = request.form.get("dose_no")
    dose_no = int(dose_no) if dose_no else None

    if not opened:
        return redirect(url_for("iot_home"))

    token = secrets.token_urlsafe(24)
    with get_session() as db:
        evt = IotDose(
            prescription_id=pres_id,
            device_id=device_id,
            dose_no=dose_no,
            status="pending",
            source="blister",
            token=token,
        )
        db.add(evt)
        db.commit()

    return redirect(url_for("iot_confirm", token=token))

# Patient confirmation page
@app.route("/iot/confirm", methods=["GET", "POST"])
def iot_confirm():
    token = request.args.get("token") or request.form.get("token")
    if not token:
        return "Missing token", 400

    with get_session() as db:
        evt = db.query(IotDose).filter_by(token=token).first()
        if not evt:
            return "Invalid token", 404

        if request.method == "POST":
            action = request.form["action"]  # yes|no
            if action == "yes":
                evt.status = "taken"
                evt.resolved_at = datetime.utcnow()
                db.add(AdherenceLog(prescription_id=evt.prescription_id, taken=True))
            else:
                evt.status = "missed"
                evt.resolved_at = datetime.utcnow()
                db.add(AdherenceLog(prescription_id=evt.prescription_id, taken=False))
            db.commit()
            return render_template_string("""
                <main class="container"><h3>Thanks!</h3>
                <p>Status recorded: <b>{{ status }}</b></p>
                <p><a href="{{ url_for('iot_home') }}">Back to IoT page</a></p></main>
            """, status=evt.status)

    return render_template_string("""
    <!doctype html>
    <html><head>
      <title>Confirm Dose</title>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/picocss@1/css/pico.min.css">
    </head><body><main class="container">
      <h3>Confirm dose for Prescription #{{ evt.prescription_id }}</h3>
      <p>Device: <b>{{ evt.device_id or "-" }}</b> &middot; Dose #: <b>{{ evt.dose_no or "-" }}</b></p>
      <p>We detected your blister/pillbox was opened. Did you take this dose?</p>
      <form method="post">
        <input type="hidden" name="token" value="{{ evt.token }}">
        <button name="action" value="yes">Yes, taken</button>
        <button class="secondary" name="action" value="no">No / missed</button>
      </form>
      <p><a href="{{ url_for('iot_home') }}">Back</a></p>
    </main></body></html>
    """, evt=evt)

# Show Prescription via QR scan
@app.route("/iot/show_prescription")
def iot_show_prescription():
    pres_id = int(request.args["prescription_id"])
    with get_session() as db:
        pres = db.query(Prescription).get(pres_id)

    if not pres:
        return "Prescription not found", 404

    # Generate QR for this prescription (so it can be shared/printed again)
    qr_url = url_for("iot_show_prescription", prescription_id=pres.id, _external=True)
    img = qrcode.make(qr_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template_string("""
    <!doctype html>
    <html>
      <head>
        <title>Prescription #{{ pres.id }}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/picocss@1/css/pico.min.css">
        <style>
          .qr { text-align:center; margin:20px; }
          .details { margin:20px; }
          button { margin-top:15px; }
        </style>
      </head>
      <body>
        <main class="container">
          <h2>Prescription #{{ pres.id }}</h2>
          <div class="details">
            <p><b>Patient:</b> {{ pres.patient_name }}</p>
            <p><b>Antibiotic:</b> {{ pres.antibiotic }}</p>
            <p><b>Dosage:</b> {{ pres.dosage_mg }} mg</p>
            <p><b>Frequency:</b> {{ pres.frequency_per_day }} per day</p>
            <p><b>Days:</b> {{ pres.days }}</p>
            <p><b>Start:</b> {{ pres.start_date }}</p>
            <p><b>Created:</b> {{ pres.created_at }}</p>
          </div>
          <div class="qr">
            <img src="data:image/png;base64,{{ qr_b64 }}" alt="QR Code"><br>
            <button onclick="window.print()">🖨 Print Prescription</button>
          </div>
          <p><a href="{{ url_for('iot_home') }}">⬅ Back to IoT</a></p>
        </main>
      </body>
    </html>
    """, pres=pres, qr_b64=qr_b64)

CYBERSECURITY_HTML = """
<!doctype html>
<html>
<head>
  <title>Cybersecurity Monitoring</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/picocss@2/css/pico.min.css">
</head>
<body>
  <main class="container">
    <h1>Cybersecurity Tab: Pacemaker & Heart Surgery Patients</h1>

    <form method="POST" action="{{ url_for('cybersecurity_check') }}">
      <label for="patient_id">Select Patient:</label>
      <select name="patient_id">
        {% for p in patients %}
          <option value="{{p.id}}">{{p.name}} ({{p.condition}})</option>
        {% endfor %}
      </select>
      <button type="submit">Run Anomaly Detection</button>
    </form>

    <h2>Cybersecurity Logs</h2>
    <table>
      <tr><th>ID</th><th>Patient</th><th>Event</th><th>Details</th><th>Status</th><th>Created</th></tr>
      {% for log in logs %}
        <tr>
          <td>{{log.id}}</td>
          <td>{{log.patient.name}}</td>
          <td>{{log.event_type}}</td>
          <td>{{log.details}}</td>
          <td>{{log.status}}</td>
          <td>{{log.created_at}}</td>
        </tr>
      {% endfor %}
    </table>
  </main>
</body>
</html>
"""

@app.route("/cybersecurity", methods=["GET"])
def cybersecurity_home():
    with get_session() as db:
        patients = db.query(Patient).filter(Patient.condition.like("%pacemaker%")).all()
        logs = db.query(CybersecurityLog).order_by(CybersecurityLog.created_at.desc()).limit(20).all()
    return render_template_string(CYBERSECURITY_HTML, patients=patients, logs=logs)


@app.route("/cybersecurity/check", methods=["POST"])
def cybersecurity_check():
    patient_id = int(request.form["patient_id"])

    # Simple anomaly detection simulation
    import random
    anomaly_detected = random.choice([True, False])

    with get_session() as db:
        patient = db.get(Patient, patient_id)
        if anomaly_detected:
            event = CybersecurityLog(
                patient_id=patient_id,
                event_type="Anomaly Detected",
                details=f"Suspicious signal detected in {patient.name}'s pacemaker telemetry.",
                status="pending",
            )
        else:
            event = CybersecurityLog(
                patient_id=patient_id,
                event_type="Normal",
                details=f"No threats detected for {patient.name}.",
                status="resolved",
            )
        db.add(event)
        db.commit()

    return redirect(url_for("cybersecurity_home"))

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)