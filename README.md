# Hostel & Youth Assembly Management System

## Setup

```bash
cd hostel_app
pip install flask
python app.py
```

Then open: http://localhost:5000

## Features

### Hostel Management

- **Buildings** — Add/Edit/Delete hostel buildings
- **Rooms** — CRUD rooms inside each building (floor, capacity, occupancy tracking)
- **Students** — Add students, assign to rooms, move between rooms anytime

### Youth Assembly

- **Events** — Create events with title, date, description
- **Attendance** — Step-by-step attendance taking:
  1. Select hostel building
  2. Select room number
  3. Click student name to mark present (click again to unmark)
- **Reports** — View attendance report with present/absent counts

## Project Structure

```
hostel_app/
├── app.py              # Flask routes + SQLite DB
├── requirements.txt
├── hostel.db           # Auto-created SQLite database
├── static/
│   ├── css/style.css   # Dark theme UI
│   └── js/app.js
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── buildings.html
    ├── building_form.html
    ├── rooms.html
    ├── room_form.html
    ├── students.html
    ├── student_form.html
    ├── assembly.html
    ├── event_form.html
    ├── attendance.html
    └── attendance_report.html
```
