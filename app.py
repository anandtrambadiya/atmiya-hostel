from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import sqlite3, os, hashlib
from datetime import datetime, date, timedelta
from functools import wraps

# ── helpers ──────────────────────────────────────────────
def is_attendance_open(event_date_str):
    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        today = date.today()
        return event_date <= today <= event_date + timedelta(days=2)
    except:
        return False

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

ADMIN_ID   = '1234'
ADMIN_PASS = hash_password('5005')

app = Flask(__name__)
app.secret_key = 'hostel_secret_key_2024'
DB = 'hostel.db'

# ── ALLOWED ROUTES per role ───────────────────────────────
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

    # Volunteer: block all except volunteer pages
    if is_volunteer and not is_admin:
        if ep not in VOLUNTEER_ALLOWED:
            return redirect(url_for('volunteer_dashboard'))
        return

    # Neither admin nor volunteer: redirect non-public to admin login
    if not is_admin and not is_volunteer:
        if ep not in VOLUNTEER_ALLOWED:
            return redirect(url_for('admin_login'))

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id INTEGER NOT NULL, room_number TEXT NOT NULL,
            capacity INTEGER DEFAULT 4, floor INTEGER DEFAULT 1,
            FOREIGN KEY (building_id) REFERENCES buildings(id)
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, roll_number TEXT, phone TEXT,
            room_id INTEGER, joining_date TEXT,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, event_date TEXT NOT NULL, description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, student_id),
            FOREIGN KEY (event_id) REFERENCES events(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
    ''')
    existing = conn.execute("SELECT value FROM settings WHERE key='volunteer_password'").fetchone()
    if not existing:
        conn.execute("INSERT INTO settings (key,value) VALUES ('volunteer_password',?)",
                     (hash_password('volunteer123'),))
    conn.commit()
    conn.close()

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
    conn = get_db()
    stats = {
        'buildings': conn.execute('SELECT COUNT(*) FROM buildings').fetchone()[0],
        'rooms':     conn.execute('SELECT COUNT(*) FROM rooms').fetchone()[0],
        'students':  conn.execute('SELECT COUNT(*) FROM students').fetchone()[0],
        'events':    conn.execute('SELECT COUNT(*) FROM events').fetchone()[0],
    }
    recent_events = conn.execute('SELECT * FROM events ORDER BY created_at DESC LIMIT 5').fetchall()
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
        conn = get_db()
        stored = conn.execute("SELECT value FROM settings WHERE key='volunteer_password'").fetchone()
        conn.close()
        if stored and hash_password(pw) == stored['value']:
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
    conn = get_db()
    all_events = conn.execute('''
        SELECT e.*, COUNT(a.id) as attendance_count
        FROM events e LEFT JOIN attendance a ON a.event_id=e.id
        GROUP BY e.id ORDER BY e.event_date DESC
    ''').fetchall()
    conn.close()
    today = date.today()
    active = []
    for e in all_events:
        d = dict(e)
        try:
            edate = datetime.strptime(e['event_date'], '%Y-%m-%d').date()
            d['window_open'] = edate <= today <= edate + timedelta(days=2)
            if d['window_open']:
                active.append(d)
        except:
            pass
    return render_template('volunteer_dashboard.html', active=active)

@app.route('/volunteer/attendance/<int:id>')
def volunteer_attendance(id):
    if not session.get('volunteer') and not session.get('admin'):
        return redirect(url_for('volunteer_login'))
    conn = get_db()
    event = conn.execute('SELECT * FROM events WHERE id=?', (id,)).fetchone()
    if not event:
        conn.close()
        return redirect(url_for('volunteer_dashboard'))
    buildings   = conn.execute('SELECT * FROM buildings ORDER BY name').fetchall()
    marked      = conn.execute('SELECT student_id FROM attendance WHERE event_id=?', (id,)).fetchall()
    marked_ids  = [r['student_id'] for r in marked]
    all_students= conn.execute('''
        SELECT s.id, s.name, s.roll_number, r.room_number, b.name as building_name, b.id as building_id, r.id as room_id
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''').fetchall()
    window_open = is_attendance_open(event['event_date'])
    conn.close()
    return render_template('attendance.html', event=event, buildings=buildings,
                           marked_ids=marked_ids, all_students=[dict(s) for s in all_students],
                           window_open=window_open, volunteer_mode=True)

@app.route('/volunteer/report/<int:eid>')
def volunteer_report(eid):
    if not session.get('volunteer') and not session.get('admin'):
        return redirect(url_for('volunteer_login'))
    conn = get_db()
    event   = conn.execute('SELECT * FROM events WHERE id=?', (eid,)).fetchone()
    present = conn.execute('''
        SELECT s.*, r.room_number, b.name as building_name
        FROM attendance a
        JOIN students s ON a.student_id=s.id
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        WHERE a.event_id=? ORDER BY b.name, r.room_number, s.name
    ''', (eid,)).fetchall()
    total = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    conn.close()
    return render_template('attendance_report.html', event=event, present=present,
                           total=total, volunteer_mode=True)

# ── SETTINGS ─────────────────────────────────────────────
@app.route('/settings/volunteer-password', methods=['POST'])
def update_volunteer_password():
    new_pw = request.form.get('new_password','')
    if len(new_pw) >= 4:
        conn = get_db()
        conn.execute("UPDATE settings SET value=? WHERE key='volunteer_password'", (hash_password(new_pw),))
        conn.commit(); conn.close()
    return redirect(url_for('dashboard'))

# ── BUILDINGS ─────────────────────────────────────────────
@app.route('/buildings')
def buildings():
    conn = get_db()
    buildings = conn.execute('''
        SELECT b.*, COUNT(r.id) as room_count,
        (SELECT COUNT(*) FROM students s JOIN rooms r2 ON s.room_id=r2.id WHERE r2.building_id=b.id) as student_count
        FROM buildings b LEFT JOIN rooms r ON r.building_id=b.id
        GROUP BY b.id ORDER BY b.name
    ''').fetchall()
    conn.close()
    return render_template('buildings.html', buildings=buildings)

@app.route('/buildings/add', methods=['GET','POST'])
def add_building():
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT INTO buildings (name, description) VALUES (?,?)',
                     (request.form['name'], request.form.get('description','')))
        conn.commit(); conn.close()
        return redirect(url_for('buildings'))
    return render_template('building_form.html', building=None)

@app.route('/buildings/<int:id>/edit', methods=['GET','POST'])
def edit_building(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute('UPDATE buildings SET name=?, description=? WHERE id=?',
                     (request.form['name'], request.form.get('description',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('buildings'))
    building = conn.execute('SELECT * FROM buildings WHERE id=?', (id,)).fetchone()
    conn.close()
    return render_template('building_form.html', building=building)

@app.route('/buildings/<int:id>/delete', methods=['POST'])
def delete_building(id):
    conn = get_db()
    conn.execute('DELETE FROM buildings WHERE id=?', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('buildings'))

# ── ROOMS ─────────────────────────────────────────────────
@app.route('/buildings/<int:bid>/rooms')
def rooms(bid):
    conn = get_db()
    building = conn.execute('SELECT * FROM buildings WHERE id=?', (bid,)).fetchone()
    rooms = conn.execute('''
        SELECT r.*, COUNT(s.id) as occupancy
        FROM rooms r LEFT JOIN students s ON s.room_id=r.id
        WHERE r.building_id=? GROUP BY r.id ORDER BY r.floor, r.room_number
    ''', (bid,)).fetchall()
    conn.close()
    return render_template('rooms.html', rooms=rooms, building=building)

@app.route('/buildings/<int:bid>/rooms/add', methods=['GET','POST'])
def add_room(bid):
    conn = get_db()
    if request.method == 'POST':
        conn.execute('INSERT INTO rooms (building_id, room_number, capacity, floor) VALUES (?,?,?,?)',
                     (bid, request.form['room_number'], request.form.get('capacity',4), request.form.get('floor',1)))
        conn.commit(); conn.close()
        return redirect(url_for('rooms', bid=bid))
    building = conn.execute('SELECT * FROM buildings WHERE id=?', (bid,)).fetchone()
    conn.close()
    return render_template('room_form.html', room=None, building=building)

@app.route('/rooms/<int:id>/edit', methods=['GET','POST'])
def edit_room(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute('UPDATE rooms SET room_number=?, capacity=?, floor=? WHERE id=?',
                     (request.form['room_number'], request.form.get('capacity',4), request.form.get('floor',1), id))
        conn.commit()
        room = conn.execute('SELECT * FROM rooms WHERE id=?', (id,)).fetchone()
        conn.close()
        return redirect(url_for('rooms', bid=room['building_id']))
    room = conn.execute('SELECT r.*, b.name as building_name FROM rooms r JOIN buildings b ON r.building_id=b.id WHERE r.id=?', (id,)).fetchone()
    building = conn.execute('SELECT * FROM buildings WHERE id=?', (room['building_id'],)).fetchone()
    conn.close()
    return render_template('room_form.html', room=room, building=building)

@app.route('/rooms/<int:id>/delete', methods=['POST'])
def delete_room(id):
    conn = get_db()
    room = conn.execute('SELECT * FROM rooms WHERE id=?', (id,)).fetchone()
    bid = room['building_id']
    conn.execute('UPDATE students SET room_id=NULL WHERE room_id=?', (id,))
    conn.execute('DELETE FROM rooms WHERE id=?', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('rooms', bid=bid))

# ── STUDENTS ──────────────────────────────────────────────
@app.route('/students')
def students():
    conn = get_db()
    students = conn.execute('''
        SELECT s.*, r.room_number, b.name as building_name
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''').fetchall()
    conn.close()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET','POST'])
def add_student():
    conn = get_db()
    if request.method == 'POST':
        conn.execute('INSERT INTO students (name, roll_number, phone, room_id, joining_date) VALUES (?,?,?,?,?)',
                     (request.form['name'], request.form.get('roll_number',''),
                      request.form.get('phone',''), request.form.get('room_id') or None,
                      request.form.get('joining_date', datetime.now().strftime('%Y-%m-%d'))))
        conn.commit(); conn.close()
        return redirect(url_for('students'))
    buildings = conn.execute('SELECT * FROM buildings ORDER BY name').fetchall()
    rooms = conn.execute('SELECT r.*, b.name as bname FROM rooms r JOIN buildings b ON r.building_id=b.id ORDER BY b.name, r.room_number').fetchall()
    conn.close()
    return render_template('student_form.html', student=None, buildings=buildings, rooms=rooms)

@app.route('/students/<int:id>/edit', methods=['GET','POST'])
def edit_student(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute('UPDATE students SET name=?, roll_number=?, phone=?, room_id=?, joining_date=? WHERE id=?',
                     (request.form['name'], request.form.get('roll_number',''),
                      request.form.get('phone',''), request.form.get('room_id') or None,
                      request.form.get('joining_date',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('students'))
    student  = conn.execute('SELECT * FROM students WHERE id=?', (id,)).fetchone()
    buildings= conn.execute('SELECT * FROM buildings ORDER BY name').fetchall()
    rooms    = conn.execute('SELECT r.*, b.name as bname FROM rooms r JOIN buildings b ON r.building_id=b.id ORDER BY b.name, r.room_number').fetchall()
    conn.close()
    return render_template('student_form.html', student=student, buildings=buildings, rooms=rooms)

@app.route('/students/<int:id>/delete', methods=['POST'])
def delete_student(id):
    conn = get_db()
    conn.execute('DELETE FROM students WHERE id=?', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('students'))

# ── YOUTH ASSEMBLY ────────────────────────────────────────
@app.route('/assembly')
def assembly():
    conn = get_db()
    events_raw = conn.execute('''
        SELECT e.*, COUNT(a.id) as attendance_count
        FROM events e LEFT JOIN attendance a ON a.event_id=e.id
        GROUP BY e.id ORDER BY e.event_date DESC
    ''').fetchall()
    conn.close()
    events = []
    for e in events_raw:
        d = dict(e)
        d['window_open'] = is_attendance_open(e['event_date'])
        events.append(d)
    today_str = date.today().strftime('%Y-%m-%d')
    return render_template('assembly.html', events=events, today_str=today_str)

@app.route('/assembly/add', methods=['GET','POST'])
def add_event():
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT INTO events (title, event_date, description) VALUES (?,?,?)',
                     (request.form['title'], request.form['event_date'], request.form.get('description','')))
        conn.commit(); conn.close()
        return redirect(url_for('assembly'))
    today = date.today().strftime('%Y-%m-%d')
    return render_template('event_form.html', event=None, today=today)

@app.route('/assembly/<int:id>/edit', methods=['GET','POST'])
def edit_event(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute('UPDATE events SET title=?, event_date=?, description=? WHERE id=?',
                     (request.form['title'], request.form['event_date'], request.form.get('description',''), id))
        conn.commit(); conn.close()
        return redirect(url_for('assembly'))
    event = conn.execute('SELECT * FROM events WHERE id=?', (id,)).fetchone()
    conn.close()
    today = date.today().strftime('%Y-%m-%d')
    return render_template('event_form.html', event=event, today=today)

@app.route('/assembly/<int:id>/delete', methods=['POST'])
def delete_event(id):
    conn = get_db()
    conn.execute('DELETE FROM attendance WHERE event_id=?', (id,))
    conn.execute('DELETE FROM events WHERE id=?', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('assembly'))

@app.route('/assembly/<int:id>/attendance')
def take_attendance(id):
    conn = get_db()
    event = conn.execute('SELECT * FROM events WHERE id=?', (id,)).fetchone()
    buildings   = conn.execute('SELECT * FROM buildings ORDER BY name').fetchall()
    marked      = conn.execute('SELECT student_id FROM attendance WHERE event_id=?', (id,)).fetchall()
    marked_ids  = [r['student_id'] for r in marked]
    all_students= conn.execute('''
        SELECT s.id, s.name, s.roll_number, r.room_number, b.name as building_name, b.id as building_id, r.id as room_id
        FROM students s
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        ORDER BY s.name
    ''').fetchall()
    window_open = is_attendance_open(event['event_date'])
    conn.close()
    return render_template('attendance.html', event=event, buildings=buildings,
                           marked_ids=marked_ids, all_students=[dict(s) for s in all_students],
                           window_open=window_open, volunteer_mode=False)

@app.route('/assembly/<int:eid>/attendance/report')
def attendance_report(eid):
    conn = get_db()
    event   = conn.execute('SELECT * FROM events WHERE id=?', (eid,)).fetchone()
    present = conn.execute('''
        SELECT s.*, r.room_number, b.name as building_name
        FROM attendance a JOIN students s ON a.student_id=s.id
        LEFT JOIN rooms r ON s.room_id=r.id
        LEFT JOIN buildings b ON r.building_id=b.id
        WHERE a.event_id=? ORDER BY b.name, r.room_number, s.name
    ''', (eid,)).fetchall()
    total = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    conn.close()
    return render_template('attendance_report.html', event=event, present=present,
                           total=total, volunteer_mode=False)

# ── API ───────────────────────────────────────────────────
@app.route('/api/buildings/<int:bid>/rooms')
def api_rooms(bid):
    conn = get_db()
    rooms = conn.execute('SELECT id, room_number, floor FROM rooms WHERE building_id=? ORDER BY floor, room_number', (bid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rooms])

@app.route('/api/rooms/<int:rid>/students')
def api_students(rid):
    conn = get_db()
    students = conn.execute('SELECT id, name, roll_number FROM students WHERE room_id=? ORDER BY name', (rid,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in students])

@app.route('/api/attendance/mark', methods=['POST'])
def api_mark_attendance():
    data = request.get_json()
    conn = get_db()
    try:
        event = conn.execute('SELECT event_date FROM events WHERE id=?', (data['event_id'],)).fetchone()
        if not event or not is_attendance_open(event['event_date']):
            conn.close()
            return jsonify({'success': False, 'error': 'Attendance window is closed for this event.'})
        conn.execute('INSERT OR IGNORE INTO attendance (event_id, student_id) VALUES (?,?)',
                     (data['event_id'], data['student_id']))
        conn.commit()
        count = conn.execute('SELECT COUNT(*) FROM attendance WHERE event_id=?', (data['event_id'],)).fetchone()[0]
        conn.close()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/attendance/unmark', methods=['POST'])
def api_unmark_attendance():
    data = request.get_json()
    conn = get_db()
    conn.execute('DELETE FROM attendance WHERE event_id=? AND student_id=?',
                 (data['event_id'], data['student_id']))
    conn.commit()
    count = conn.execute('SELECT COUNT(*) FROM attendance WHERE event_id=?', (data['event_id'],)).fetchone()[0]
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)