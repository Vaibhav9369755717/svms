from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, static_folder='static')
app.secret_key = 'smart-vehicle-management-system'

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'svams.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'customer',
                phone TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                price REAL DEFAULT 0.0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                vehicle_type TEXT,
                vehicle_number TEXT,
                booking_date TEXT,
                status TEXT DEFAULT 'Pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                rating INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        if conn.execute('SELECT COUNT(*) FROM services').fetchone()[0] == 0:
            conn.executemany(
                'INSERT INTO services (name, description, price) VALUES (?, ?, ?)',
                [
                    ('Oil Change', 'Quick oil replacement service', 1200.00),
                    ('Car Wash', 'Exterior and interior cleaning', 800.00),
                    ('Brake Repair', 'Brake pad and rotor inspection', 3500.00),
                    ('Engine Repair', 'Advanced engine diagnostics and repair', 8000.00),
                    ('Battery Replacement', 'Premium battery replacement', 4500.00),
                    ('Tyre Replacement', 'New tyre installation', 6000.00),
                    ('Wheel Alignment', 'Precision wheel alignment', 2200.00),
                    ('Insurance Claim', 'Claim support and documentation', 1500.00),
                    ('Emergency Service', 'Rapid roadside assistance', 3000.00),
                ],
            )
        if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            conn.execute(
                'INSERT INTO users (full_name, email, password, role, phone) VALUES (?, ?, ?, ?, ?)',
                ('Admin User', 'admin@svms.com', generate_password_hash('admin123'), 'admin', '0000000000'),
            )
        conn.commit()
    finally:
        conn.close()


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_services():
    conn = get_db()
    try:
        rows = conn.execute('SELECT id, name, description, price FROM services ORDER BY id').fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/services')
def services():
    return render_template('services.html', services=get_services())


@app.route('/book-service', methods=['GET', 'POST'])
def book_service():
    if request.method == 'POST':
        if not session.get('user_id'):
            flash('Please login first to book a service.', 'warning')
            return redirect(url_for('login'))
        service_name = request.form.get('service')
        vehicle_type = request.form.get('vehicle_type', '')
        vehicle_number = request.form.get('vehicle_number', '')
        booking_date = request.form.get('booking_date') or datetime.now().date().strftime('%Y-%m-%d')
        notes = request.form.get('notes', '')
        conn = get_db()
        try:
            service_row = conn.execute('SELECT id FROM services WHERE name = ?', (service_name,)).fetchone()
            if not service_row:
                flash('Selected service is unavailable.', 'warning')
                return redirect(url_for('book_service'))
            cursor = conn.execute(
                'INSERT INTO bookings (customer_id, service_id, vehicle_type, vehicle_number, booking_date, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (session['user_id'], service_row['id'], vehicle_type, vehicle_number, booking_date, 'Pending', notes),
            )
            conn.commit()
            booking_id = cursor.lastrowid
            flash(f'Booking submitted successfully. Your booking number is #{booking_id}.', 'success')
            return redirect(url_for('track_booking'))
        finally:
            conn.close()

    return render_template('book_service.html', services=get_services())


@app.route('/track-booking', methods=['GET', 'POST'])
def track_booking():
    booking = None
    if request.method == 'POST':
        booking_id = request.form.get('booking_id', '').strip()
        vehicle_number = request.form.get('vehicle_number', '').strip()
        conn = get_db()
        try:
            if booking_id:
                row = conn.execute('''
                    SELECT b.*, s.name AS service_name
                    FROM bookings b
                    JOIN services s ON b.service_id = s.id
                    WHERE b.id = ?
                ''', (booking_id,)).fetchone()
            else:
                row = conn.execute('''
                    SELECT b.*, s.name AS service_name
                    FROM bookings b
                    JOIN services s ON b.service_id = s.id
                    WHERE b.vehicle_number = ?
                ''', (vehicle_number,)).fetchone()
            if not row:
                flash('No booking found. Please try another ID or vehicle number.', 'warning')
            else:
                booking = dict(row)
        finally:
            conn.close()
    return render_template('track_booking.html', booking=booking)


@app.route('/customer-dashboard')
def customer_dashboard():
    if not session.get('user_id'):
        flash('Please login to view your dashboard.', 'warning')
        return redirect(url_for('login'))
    conn = get_db()
    data = {'bookings': [], 'feedback_count': 0}
    try:
        rows = conn.execute('''
            SELECT b.*, s.name AS service_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.customer_id = ?
            ORDER BY b.created_at DESC
        ''', (session['user_id'],)).fetchall()
        data['bookings'] = [dict(row) for row in rows]
        feedback_count = conn.execute('SELECT COUNT(*) AS count FROM feedbacks WHERE customer_id = ?', (session['user_id'],)).fetchone()
        data['feedback_count'] = feedback_count['count']
    finally:
        conn.close()
    return render_template('customer_dashboard.html', data=data)


@app.route('/admin-dashboard')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        flash('Only admins can view this page.', 'warning')
        return redirect(url_for('home'))
    conn = get_db()
    data = {'users': 0, 'bookings': 0, 'revenue': 0}
    try:
        users_count = conn.execute('SELECT COUNT(*) AS count FROM users').fetchone()
        bookings_count = conn.execute('SELECT COUNT(*) AS count FROM bookings').fetchone()
        revenue_row = conn.execute('SELECT COALESCE(SUM(s.price), 0) AS total FROM bookings b JOIN services s ON b.service_id = s.id').fetchone()
        data['users'] = users_count['count']
        data['bookings'] = bookings_count['count']
        data['revenue'] = revenue_row['total']
    finally:
        conn.close()
    return render_template('admin_dashboard.html', data=data)


@app.route('/mechanic-dashboard')
def mechanic_dashboard():
    if session.get('user_role') != 'mechanic':
        flash('Only mechanics can view this page.', 'warning')
        return redirect(url_for('home'))
    conn = get_db()
    jobs = []
    try:
        rows = conn.execute('''
            SELECT b.*, s.name AS service_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            ORDER BY b.created_at DESC
        ''').fetchall()
        jobs = [dict(row) for row in rows]
    finally:
        conn.close()
    return render_template('mechanic_dashboard.html', jobs=jobs)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        try:
            user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['user_role'] = user['role']
                session['user_name'] = user['full_name']
                flash('Login successful.', 'success')
                if user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                if user['role'] == 'mechanic':
                    return redirect(url_for('mechanic_dashboard'))
                return redirect(url_for('customer_dashboard'))
            flash('Invalid email or password.', 'danger')
        finally:
            conn.close()
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'customer')
        if not full_name or not email or not password:
            flash('Please complete all required fields.', 'warning')
            return redirect(url_for('register'))
        conn = get_db()
        try:
            existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
            if existing:
                flash('An account with this email already exists.', 'warning')
                return redirect(url_for('register'))
            conn.execute(
                'INSERT INTO users (full_name, email, password, role, phone) VALUES (?, ?, ?, ?, ?)',
                (full_name, email, generate_password_hash(password), role, phone),
            )
            conn.commit()
            flash('Registration successful. You can now log in.', 'success')
            return redirect(url_for('login'))
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if not session.get('user_id'):
        flash('Please login to leave feedback.', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        rating = request.form.get('rating', '5')
        conn = get_db()
        try:
            conn.execute('INSERT INTO feedbacks (customer_id, message, rating) VALUES (?, ?, ?)', (session['user_id'], message, rating))
            conn.commit()
            flash('Thank you for your feedback.', 'success')
            return redirect(url_for('customer_dashboard'))
        finally:
            conn.close()
    return render_template('feedback.html')


@app.route('/invoice')
def invoice():
    if not session.get('user_id'):
        flash('Please login to view your invoice.', 'warning')
        return redirect(url_for('login'))
    conn = get_db()
    invoice_data = None
    try:
        row = conn.execute('''
            SELECT b.id, b.booking_date, b.status, s.name AS service_name, s.price
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.customer_id = ?
            ORDER BY b.created_at DESC
            LIMIT 1
        ''', (session['user_id'],)).fetchone()
        invoice_data = dict(row) if row is not None else None
    finally:
        conn.close()
    return render_template('invoice.html', invoice=invoice_data)


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash('Please login to update your profile.', 'warning')
        return redirect(url_for('login'))
    user = get_current_user()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        conn = get_db()
        try:
            conn.execute('UPDATE users SET full_name = ?, phone = ?, address = ? WHERE id = ?', (full_name, phone, address, session['user_id']))
            conn.commit()
            flash('Profile updated successfully.', 'success')
            session['user_name'] = full_name
            return redirect(url_for('profile'))
        finally:
            conn.close()
    return render_template('profile.html', user=user)


@app.route('/service-history')
def service_history():
    if not session.get('user_id'):
        flash('Please login to view your service history.', 'warning')
        return redirect(url_for('login'))
    conn = get_db()
    bookings = []
    try:
        rows = conn.execute('''
            SELECT b.*, s.name AS service_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.customer_id = ?
            ORDER BY b.created_at DESC
        ''', (session['user_id'],)).fetchall()
        bookings = [dict(row) for row in rows]
    finally:
        conn.close()
    return render_template('service_history.html', bookings=bookings)


@app.route('/health')
def health():
    return {'status': 'ok'}


init_db()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
