import os
from flask import Flask, request, session, redirect, render_template, url_for, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me-in-production")


# DB-Connection aus Umgebungsvariable (Render setzt DATABASE_URL automatisch)
def get_db():
  return psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=RealDictCursor)


# Login-Required Decorator
def login_required(f):
  @wraps(f)
  def decorated(*args, **kwargs):
    if "employee_id" not in session:
      return redirect(url_for("login"))
    return f(*args, **kwargs)

  return decorated


# Admin-Required Decorator (einfache PIN-Liste für Demo)
def admin_required(f):
  @wraps(f)
  def decorated(*args, **kwargs):
    admin_pins = os.getenv("ADMIN_PINS", "0000").split(",")
    if session.get("pin") not in admin_pins:
      flash("Admin-Zugriff erforderlich", "error")
      return redirect(url_for("dashboard"))
    return f(*args, **kwargs)

  return decorated


@app.route("/", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    pin = request.form.get("pin", "").strip()
    if len(pin) != 4:
      flash("PIN muss 4-stellig sein", "error")
      return render_template("login.html")

    try:
      with get_db() as conn:
        with conn.cursor() as cur:
          cur.execute("SELECT id, name, is_present FROM employees WHERE pin = %s AND active = TRUE", (pin,))
          emp = cur.fetchone()
          if emp:
            session["employee_id"] = emp["id"]
            session["employee_name"] = emp["name"]
            session["pin"] = pin  # Für Admin-Check
            session["is_present"] = emp["is_present"]
            flash(f"Willkommen, {emp['name']}!", "success")
            return redirect(url_for("dashboard"))
      flash("Ungültige PIN oder Mitarbeiter inaktiv", "error")
    except Exception as e:
      app.logger.error(f"Login error: {e}")
      flash("Verbindungsfehler", "error")
  return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
  emp_id = session["employee_id"]

  # POST: IN/OUT buchen
  if request.method == "POST":
    action = request.form.get("action")  # "IN" or "OUT"
    if action in ("IN", "OUT"):
      try:
        with get_db() as conn:
          with conn.cursor() as cur:
            cur.execute(
              "INSERT INTO scans (employee_id, event_type, scan_time) VALUES (%s, %s, NOW())",
              (emp_id, action)
            )
            cur.execute("UPDATE employees SET is_present = %s WHERE id = %s", (action == "IN", emp_id))
        session["is_present"] = (action == "IN")
        flash(f"✅ {action} gebucht um {datetime.now().strftime('%H:%M')}", "success")
      except Exception as e:
        app.logger.error(f"Scan error: {e}")
        flash("Fehler beim Buchen", "error")
    return redirect(url_for("dashboard"))

  # GET: Daten laden
  try:
    with get_db() as conn:
      with conn.cursor() as cur:
        # Heutige Scans
        cur.execute("""
                    SELECT TO_CHAR(scan_time, 'HH24:MI') as time, event_type
                    FROM scans
                    WHERE employee_id = %s AND DATE(scan_time) = CURRENT_DATE
                    ORDER BY scan_time DESC
                """, (emp_id,))
        today_scans = cur.fetchall()

        # Diese Woche (für Übersicht)
        cur.execute("""
                    SELECT TO_CHAR(scan_time, 'DD.MM. HH24:MI') as time, event_type
                    FROM scans
                    WHERE employee_id = %s AND scan_time >= %s
                    ORDER BY scan_time DESC
                    LIMIT 20
                """, (emp_id, datetime.now() - timedelta(days=7)))
        recent_scans = cur.fetchall()
  except Exception as e:
    app.logger.error(f"Load error: {e}")
    today_scans, recent_scans = [], []

  return render_template("dashboard.html",
                         name=session["employee_name"],
                         is_present=session.get("is_present", False),
                         today_scans=today_scans,
                         recent_scans=recent_scans)


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
  # POST: Neuen Mitarbeiter anlegen
  if request.method == "POST":
    name = request.form.get("name", "").strip()
    pin = request.form.get("pin", "").strip()
    if name and len(pin) == 4:
      try:
        with get_db() as conn:
          with conn.cursor() as cur:
            cur.execute("INSERT INTO employees (name, pin) VALUES (%s, %s)", (name, pin))
        flash(f"Mitarbeiter '{name}' angelegt", "success")
      except psycopg2.IntegrityError:
        flash("PIN bereits vergeben", "error")
      except Exception as e:
        app.logger.error(f"Add employee error: {e}")
        flash("Fehler", "error")
    else:
      flash("Name und 4-stellige PIN erforderlich", "error")

  # GET: Mitarbeiterliste
  try:
    with get_db() as conn:
      with conn.cursor() as cur:
        cur.execute("SELECT id, name, pin, active, is_present, created_at FROM employees ORDER BY name")
        employees = cur.fetchall()
  except:
    employees = []

  return render_template("admin.html", employees=employees)


@app.route("/admin/toggle/<int:emp_id>")
@admin_required
def toggle_active(emp_id):
  try:
    with get_db() as conn:
      with conn.cursor() as cur:
        cur.execute("UPDATE employees SET active = NOT active WHERE id = %s", (emp_id,))
    flash("Status aktualisiert", "success")
  except:
    flash("Fehler", "error")
  return redirect(url_for("admin"))


@app.route("/logout")
def logout():
  session.clear()
  flash("Abgemeldet", "info")
  return redirect(url_for("login"))


# Fehlerseiten
@app.errorhandler(404)
def not_found(e):
  return render_template("base.html", content="<h2>Seite nicht gefunden</h2>"), 404


if __name__ == "__main__":
  # Nur für lokal: DB-URL aus .env laden
  from dotenv import load_dotenv

  load_dotenv()
  app.run(debug=True, host="0.0.0.0", port=5000)
