from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import os, hashlib, psycopg2, psycopg2.extras
from datetime import datetime, date, timedelta
from functools import wraps

# ── helpers ──────────────────────────────────────────────
def is_attendance_open(event_date_str):
    try:
        event_date = datetime.strptime(str(event_date_str), "%Y-%m-%d").date()
        today = date.today()
        return event_date <= today <= event_date + timedelta(days=2)
    except:
        return False

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── Config ───────────────────────────────────────────────
ADMIN_ID   = os.environ.get('ADMIN_ID',   '1234')
ADMIN_PASS = hash_password(os.environ.get('ADMIN_PASS', '5005'))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-insecure-key-change-in-prod')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
# Render PostgreSQL URLs start with postgres:// — psycopg2 needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ── DB connection ─────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def dict_row(cursor, row):
    """Convert a psycopg2 row to a dict."""
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))

def fetchall_dict(cursor):
    return [dict_row(cursor, r) for r in cursor.fetchall()]

def fetchone_dict(cursor):
    row = cursor.fetchone()
    return dict_row(cursor, row) if row else None

# ── init DB ───────────────────────────────────────────────
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS buildings (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY,
            building_id INTEGER NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
            room_number TEXT NOT NULL,
            capacity INTEGER DEFAULT 4,
            floor INTEGER DEFAULT 1
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            roll_number TEXT,
            phone TEXT,
            room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
            joining_date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'present',
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, student_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    c.execute("SELECT value FROM settings WHERE key='volunteer_password'")
    if not c.fetchone():
        c.execute("INSERT INTO settings (key,value) VALUES ('volunteer_password',%s)",
                  (hash_password('volunteer123'),))
    conn.commit()
    conn.close()

# ── AUTO MARK ABSENT ──────────────────────────────────────
def auto_mark_absent(event_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM students")
        all_students = [r[0] for r in c.fetchall()]
        c.execute("SELECT student_id FROM attendance WHERE event_id=%s", (event_id,))
        recorded = {r[0] for r in c.fetchall()}
        absent = [(event_id, sid, 'absent') for sid in all_students if sid not in recorded]
        if absent:
            psycopg2.extras.execute_values(
                c,
                "INSERT INTO attendance (event_id, student_id, status) VALUES %s ON CONFLICT DO NOTHING",
                absent
            )
        conn.commit()
    finally:
        conn.close()

def maybe_auto_mark_absent(event_id, event_date_str):
    try:
        edate = datetime.strptime(str(event_date_str), "%Y-%m-%d").date()
        if date.today() > edate + timedelta(days=2):
            auto_mark_absent(event_id)
    except:
        pass

# ── ALLOWED ROUTES ────────────────────────────────────────
VOLUNTEER_ALLOWED = {
    'volunteer_dashboard', 'volunteer_attendance', 'volunteer_report',
    'volunteer_login', 'volunteer_logout',
    'api_rooms', 'api_students', 'api_mark_attendance', 'api_unmark_attendance',
    'static'
}
PUBLIC_ROUTES = {'admin_login', 'admin_logout', 'volunteer_login', 'volunteer_logout', 'static'}

@app.before_request
def auth_guard():
    ep = request.endpoint
    if not ep or ep in PUBLIC_ROUTES:
        return
    is_admin     = session.get('admin')
    is_volunteer = session.get('volunteer')
    if is_volunteer and not is_admin:
        if ep not in VOLUNTEER_ALLOWED:
            return redirect(url_for('volunteer_dashboard'))
        return
    if not is_admin and not is_volunteer:
        if ep not in VOLUNTEER_ALLOWED:
            return redirect(url_for('admin_login'))

# ── ADMIN AUTH ────────────────────────────────────────────
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    error = None
    if session.get('admin'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        uid = request.form.get('admin_id','').strip()
        pw  = request.form.get('password','')
        if uid == ADMIN_ID and hash_password(pw) == ADMIN_PASS:
            session['admin'] = True
            session.permanent = True
            return redirect(request.args.get('next') or url_for('dashboard'))
        error = 'Invalid ID or password.'
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

# ── DASHBOARD ────────────────────────────────────────────
@app.route('/')
def dashboard():
    conn = get_db(); c = conn.cursor()
    stats = {}
    for key, table in [('buildings','buildings'),('rooms','rooms'),('students','students'),('events','events')]:
        c.execute(f'SELECT COUNT(*) FROM {table}')
        stats[key] = c.fetchone()[0]
    c.execute('SELECT * FROM events ORDER BY created_at DESC LIMIT 5')
    recent_events = fetchall_dict(c)
    conn.close()
    return render_template('dashboard.html', stats=stats, recent_events=recent_events)

# ── VOLUNTEER AUTH ────────────────────────────────────────
@app.route('/volunteer/login', methods=['GET','POST'])
def volunteer_login():
    if session.get('volunteer') or session.get('admin'):
        return redirect(url_for('volunteer_dashboard') if session.get('volunteer') else url_for('dashboard'))
    error = None
    if request.method == 'POST':
        pw = request.form.get('password','')
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='volunteer_password'")
        stored = c.fetchone()
        conn.close()
        if stored and hash_password(pw) == stored[0]:
            session['volunteer'] = True
            return redirect(url_for('volunteer_dashboard'))
        error = 'Incorrect password. Please try again.'
    return render_template('volunteer_login.html', error=error)

@app.route('/volunteer/logout')
def volunteer_logout():
    session.pop('volunteer', None)
    return redirect(url_for('volunteer_login'))

@app.route('/volunteer')
def volunteer_dashboard():
    if not session.get('volunteer') and not session.get('admin'):
        return redirect(url_for('volunteer_login'))
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT e.*, COUNT(a.id) as attendance_count
        FROM events e LEFT JOIN attendance a ON a.event_id=e.id
        GROUP BY e.id ORDER BY e.event_date DESC
    ''')
    all_events = fetchall_dict(c)
    conn.close()
    today = date.today()
    active = []
    for e in all_events:
        try:
            edate = datetime.strptime(str(e['event_date']), '%Y-%m-%d').date()
            if edate <= today <= edate + timedelta(days=2):
                e['window_open'] = True
                active.append(e)
        except:
            pass
    return render_template('volunteer_dashboard.html', active=active)

@app.route('/volunteer/attendance/<int:id>')
def volunteer_attendance(id):
    if not session.get('volunteer') and not session.get('admin'):
        return redirect(url_for('volunteer_login'))
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=%s', (id,))
    event = fetchone_dict(c)
    if not event:
        conn.close()
        return redirect(url_for('volunteer_dashboard'))
    c.execute('SELECT * FROM buildings ORDER BY name')
    buildings = fetchall_dict(c)
    c.execute('SELECT student_id FROM attendance WHERE event_id=%s', (id,))
    marked_ids = [r[0] for r in c.fetchall()]
    c.execute('''
        SELECT s.id, s.name, s.roll_number, r.room_number,
               b.name as building_name, b.id as building_id, r.id as room_id
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''')
    all_students = fetchall_dict(c)
    window_open = is_attendance_open(event['event_date'])
    conn.close()
    return render_template('attendance.html', event=event, buildings=buildings,
                           marked_ids=marked_ids, all_students=all_students,
                           window_open=window_open, volunteer_mode=True)

@app.route('/volunteer/report/<int:eid>')
def volunteer_report(eid):
    if not session.get('volunteer') and not session.get('admin'):
        return redirect(url_for('volunteer_login'))
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=%s', (eid,))
    event = fetchone_dict(c)
    conn.close()
    maybe_auto_mark_absent(eid, event['event_date'])
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT s.*, a.status, r.room_number, b.name as building_name
        FROM attendance a JOIN students s ON a.student_id=s.id
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        WHERE a.event_id=%s ORDER BY a.status ASC, b.name, r.room_number, s.name
    ''', (eid,))
    records = fetchall_dict(c)
    c.execute('SELECT COUNT(*) FROM students')
    total = c.fetchone()[0]
    conn.close()
    return render_template('attendance_report.html', event=event, records=records,
                           total=total, volunteer_mode=True)

# ── SETTINGS ─────────────────────────────────────────────
@app.route('/settings/volunteer-password', methods=['POST'])
def update_volunteer_password():
    new_pw = request.form.get('new_password','')
    if len(new_pw) >= 4:
        conn = get_db(); c = conn.cursor()
        c.execute("UPDATE settings SET value=%s WHERE key='volunteer_password'", (hash_password(new_pw),))
        conn.commit(); conn.close()
    return redirect(url_for('dashboard'))

# ── BUILDINGS ─────────────────────────────────────────────
@app.route('/buildings')
def buildings():
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT b.*, COUNT(r.id) as room_count,
        (SELECT COUNT(*) FROM students s JOIN rooms r2 ON s.room_id=r2.id WHERE r2.building_id=b.id) as student_count
        FROM buildings b LEFT JOIN rooms r ON r.building_id=b.id
        GROUP BY b.id ORDER BY b.name
    ''')
    buildings = fetchall_dict(c)
    conn.close()
    return render_template('buildings.html', buildings=buildings)

@app.route('/buildings/add', methods=['GET','POST'])
def add_building():
    if request.method == 'POST':
        conn = get_db(); c = conn.cursor()
        c.execute('INSERT INTO buildings (name, description) VALUES (%s,%s)',
                  (request.form['name'], request.form.get('description','')))
        conn.commit(); conn.close()
        return redirect(url_for('buildings'))
    return render_template('building_form.html', building=None)

@app.route('/buildings/<int:id>/edit', methods=['GET','POST'])
def edit_building(id):
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('UPDATE buildings SET name=%s, description=%s WHERE id=%s',
                  (request.form['name'], request.form.get('description',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('buildings'))
    c.execute('SELECT * FROM buildings WHERE id=%s', (id,))
    building = fetchone_dict(c)
    conn.close()
    return render_template('building_form.html', building=building)

@app.route('/buildings/<int:id>/delete', methods=['POST'])
def delete_building(id):
    conn = get_db(); c = conn.cursor()
    c.execute('DELETE FROM buildings WHERE id=%s', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('buildings'))

# ── ROOMS ─────────────────────────────────────────────────
@app.route('/buildings/<int:bid>/rooms')
def rooms(bid):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM buildings WHERE id=%s', (bid,))
    building = fetchone_dict(c)
    c.execute('''
        SELECT r.*, COUNT(s.id) as occupancy
        FROM rooms r LEFT JOIN students s ON s.room_id=r.id
        WHERE r.building_id=%s GROUP BY r.id ORDER BY r.floor, r.room_number
    ''', (bid,))
    rooms = fetchall_dict(c)
    conn.close()
    return render_template('rooms.html', rooms=rooms, building=building)

@app.route('/buildings/<int:bid>/rooms/add', methods=['GET','POST'])
def add_room(bid):
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('INSERT INTO rooms (building_id, room_number, capacity, floor) VALUES (%s,%s,%s,%s)',
                  (bid, request.form['room_number'], request.form.get('capacity',4), request.form.get('floor',1)))
        conn.commit(); conn.close()
        return redirect(url_for('rooms', bid=bid))
    c.execute('SELECT * FROM buildings WHERE id=%s', (bid,))
    building = fetchone_dict(c)
    conn.close()
    return render_template('room_form.html', room=None, building=building)

@app.route('/rooms/<int:id>/edit', methods=['GET','POST'])
def edit_room(id):
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('UPDATE rooms SET room_number=%s, capacity=%s, floor=%s WHERE id=%s',
                  (request.form['room_number'], request.form.get('capacity',4), request.form.get('floor',1), id))
        conn.commit()
        c.execute('SELECT * FROM rooms WHERE id=%s', (id,))
        room = fetchone_dict(c)
        conn.close()
        return redirect(url_for('rooms', bid=room['building_id']))
    c.execute('SELECT r.*, b.name as building_name FROM rooms r JOIN buildings b ON r.building_id=b.id WHERE r.id=%s', (id,))
    room = fetchone_dict(c)
    c.execute('SELECT * FROM buildings WHERE id=%s', (room['building_id'],))
    building = fetchone_dict(c)
    conn.close()
    return render_template('room_form.html', room=room, building=building)

@app.route('/rooms/<int:id>/delete', methods=['POST'])
def delete_room(id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT building_id FROM rooms WHERE id=%s', (id,))
    row = c.fetchone()
    bid = row[0]
    c.execute('UPDATE students SET room_id=NULL WHERE room_id=%s', (id,))
    c.execute('DELETE FROM rooms WHERE id=%s', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('rooms', bid=bid))

# ── STUDENTS ──────────────────────────────────────────────
@app.route('/students')
def students():
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT s.*, r.room_number, b.name as building_name
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''')
    students = fetchall_dict(c)
    conn.close()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET','POST'])
def add_student():
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('INSERT INTO students (name, roll_number, phone, room_id, joining_date) VALUES (%s,%s,%s,%s,%s)',
                  (request.form['name'], request.form.get('roll_number',''),
                   request.form.get('phone',''), request.form.get('room_id') or None,
                   request.form.get('joining_date', date.today().strftime('%Y-%m-%d'))))
        conn.commit(); conn.close()
        return redirect(url_for('students'))
    c.execute('SELECT * FROM buildings ORDER BY name')
    buildings = fetchall_dict(c)
    c.execute('SELECT r.*, b.name as bname FROM rooms r JOIN buildings b ON r.building_id=b.id ORDER BY b.name, r.room_number')
    rooms = fetchall_dict(c)
    conn.close()
    return render_template('student_form.html', student=None, buildings=buildings, rooms=rooms)

@app.route('/students/<int:id>/edit', methods=['GET','POST'])
def edit_student(id):
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('UPDATE students SET name=%s, roll_number=%s, phone=%s, room_id=%s, joining_date=%s WHERE id=%s',
                  (request.form['name'], request.form.get('roll_number',''),
                   request.form.get('phone',''), request.form.get('room_id') or None,
                   request.form.get('joining_date',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('students'))
    c.execute('SELECT * FROM students WHERE id=%s', (id,))
    student = fetchone_dict(c)
    c.execute('SELECT * FROM buildings ORDER BY name')
    buildings = fetchall_dict(c)
    c.execute('SELECT r.*, b.name as bname FROM rooms r JOIN buildings b ON r.building_id=b.id ORDER BY b.name, r.room_number')
    rooms = fetchall_dict(c)
    conn.close()
    return render_template('student_form.html', student=student, buildings=buildings, rooms=rooms)

@app.route('/students/<int:id>/delete', methods=['POST'])
def delete_student(id):
    conn = get_db(); c = conn.cursor()
    c.execute('DELETE FROM students WHERE id=%s', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('students'))

# ── YOUTH ASSEMBLY ────────────────────────────────────────
@app.route('/assembly')
def assembly():
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT e.*, COUNT(a.id) as attendance_count
        FROM events e LEFT JOIN attendance a ON a.event_id=e.id
        GROUP BY e.id ORDER BY e.event_date DESC
    ''')
    events_raw = fetchall_dict(c)
    conn.close()
    today = date.today()
    active, upcoming, past = [], [], []
    for e in events_raw:
        try:
            edate = datetime.strptime(str(e['event_date']), '%Y-%m-%d').date()
        except:
            past.append(e); continue
        if edate <= today <= edate + timedelta(days=2):
            e['status'] = 'active'; active.append(e)
        elif edate > today:
            e['status'] = 'upcoming'; upcoming.append(e)
        else:
            e['status'] = 'past'; past.append(e)
    upcoming.sort(key=lambda x: str(x['event_date']))
    return render_template('assembly.html', active=active, upcoming=upcoming, past=past,
                           today_str=today.strftime('%Y-%m-%d'))

@app.route('/assembly/add', methods=['GET','POST'])
def add_event():
    if request.method == 'POST':
        conn = get_db(); c = conn.cursor()
        c.execute('INSERT INTO events (title, event_date, description) VALUES (%s,%s,%s)',
                  (request.form['title'], request.form['event_date'], request.form.get('description','')))
        conn.commit(); conn.close()
        return redirect(url_for('assembly'))
    return render_template('event_form.html', event=None, today=date.today().strftime('%Y-%m-%d'))

@app.route('/assembly/<int:id>/edit', methods=['GET','POST'])
def edit_event(id):
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        c.execute('UPDATE events SET title=%s, event_date=%s, description=%s WHERE id=%s',
                  (request.form['title'], request.form['event_date'], request.form.get('description',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('assembly'))
    c.execute('SELECT * FROM events WHERE id=%s', (id,))
    event = fetchone_dict(c)
    conn.close()
    return render_template('event_form.html', event=event, today=date.today().strftime('%Y-%m-%d'))

@app.route('/assembly/<int:id>/delete', methods=['POST'])
def delete_event(id):
    conn = get_db(); c = conn.cursor()
    c.execute('DELETE FROM events WHERE id=%s', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('assembly'))

@app.route('/assembly/<int:id>/attendance')
def take_attendance(id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=%s', (id,))
    event = fetchone_dict(c)
    c.execute('SELECT * FROM buildings ORDER BY name')
    buildings = fetchall_dict(c)
    c.execute('SELECT student_id FROM attendance WHERE event_id=%s', (id,))
    marked_ids = [r[0] for r in c.fetchall()]
    c.execute('''
        SELECT s.id, s.name, s.roll_number, r.room_number,
               b.name as building_name, b.id as building_id, r.id as room_id
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''')
    all_students = fetchall_dict(c)
    window_open = is_attendance_open(event['event_date'])
    conn.close()
    return render_template('attendance.html', event=event, buildings=buildings,
                           marked_ids=marked_ids, all_students=all_students,
                           window_open=window_open, volunteer_mode=False)

@app.route('/assembly/<int:eid>/attendance/report')
def attendance_report(eid):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=%s', (eid,))
    event = fetchone_dict(c)
    conn.close()
    maybe_auto_mark_absent(eid, event['event_date'])
    conn = get_db(); c = conn.cursor()
    c.execute('''
        SELECT s.*, a.status, r.room_number, b.name as building_name
        FROM attendance a JOIN students s ON a.student_id=s.id
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        WHERE a.event_id=%s ORDER BY a.status ASC, b.name, r.room_number, s.name
    ''', (eid,))
    records = fetchall_dict(c)
    c.execute('SELECT COUNT(*) FROM students')
    total = c.fetchone()[0]
    conn.close()
    return render_template('attendance_report.html', event=event, records=records,
                           total=total, volunteer_mode=False)

# ── API ───────────────────────────────────────────────────
@app.route('/api/buildings/<int:bid>/rooms')
def api_rooms(bid):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id, room_number, floor FROM rooms WHERE building_id=%s ORDER BY floor, room_number', (bid,))
    rooms = fetchall_dict(c)
    conn.close()
    return jsonify(rooms)

@app.route('/api/rooms/<int:rid>/students')
def api_students(rid):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id, name, roll_number FROM students WHERE room_id=%s ORDER BY name', (rid,))
    students = fetchall_dict(c)
    conn.close()
    return jsonify(students)

@app.route('/api/attendance/mark', methods=['POST'])
def api_mark_attendance():
    data = request.get_json()
    conn = get_db(); c = conn.cursor()
    try:
        c.execute('SELECT event_date FROM events WHERE id=%s', (data['event_id'],))
        event = c.fetchone()
        if not event or not is_attendance_open(event[0]):
            conn.close()
            return jsonify({'success': False, 'error': 'Attendance window is closed for this event.'})
        c.execute('INSERT INTO attendance (event_id, student_id, status) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                  (data['event_id'], data['student_id'], 'present'))
        conn.commit()
        c.execute('SELECT COUNT(*) FROM attendance WHERE event_id=%s AND status=%s', (data['event_id'], 'present'))
        count = c.fetchone()[0]
        conn.close()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/attendance/unmark', methods=['POST'])
def api_unmark_attendance():
    data = request.get_json()
    conn = get_db(); c = conn.cursor()
    c.execute('DELETE FROM attendance WHERE event_id=%s AND student_id=%s', (data['event_id'], data['student_id']))
    conn.commit()
    c.execute('SELECT COUNT(*) FROM attendance WHERE event_id=%s AND status=%s', (data['event_id'], 'present'))
    count = c.fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'count': count})

# ── IMPORT ────────────────────────────────────────────────
@app.route('/import', methods=['GET','POST'])
def import_data():
    result = None
    if request.method == 'POST':
        f = request.files.get('datafile')
        if f:
            result = {'status': 'pending', 'filename': f.filename,
                      'message': 'File received. Auto-detection will be implemented once you share the actual file format.'}
    return render_template('import_data.html', result=result)

# ── STARTUP ───────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(debug=False)