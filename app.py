import csv
import io
import shutil
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, send_file, send_from_directory, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static')
app.secret_key = 'smart-vehicle-management-system'

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'svams.db'
UPLOAD_DIR = BASE_DIR / 'uploads'
ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

FEATURE_GROUPS = [
    {
        'title': 'Customer Side',
        'features': [
            'Online Payment', 'Booking Cancellation', 'Reschedule Booking', 'Vehicle Tracking', 'Live Chat',
            'Download Invoice PDF', 'Service Reminder', 'Insurance Reminder', 'EMI Payment', 'Wallet',
            'Coupons', 'Referral System', 'Loyalty Points', 'Emergency Roadside Assistance', 'SOS Button',
            'Fuel Cost Calculator', 'Nearby Workshop', 'Book Test Drive', 'Sell Old Vehicle', 'Buy Accessories',
            'Service Packages', 'Subscription Plans', 'Vehicle Documents Upload', 'Pollution Certificate Reminder',
            'Insurance Renewal', 'Multi Vehicle Support', 'Favorite Workshop',
        ],
    },
    {
        'title': 'Admin Side',
        'features': [
            'Manage Customers', 'Manage Mechanics', 'Manage Services', 'Manage Offers', 'Revenue Reports',
            'Export Excel', 'Export PDF', 'Backup Database', 'Role Management', 'Notifications',
        ],
    },
    {
        'title': 'Mechanic Side',
        'features': [
            "Today's Jobs", 'Accept/Reject Work', 'Upload Vehicle Photos', 'Before/After Images',
            'Spare Parts Used', 'Estimated Time', 'Complete Job', 'Generate Bill',
        ],
    },
]


def ensure_upload_dir():
    UPLOAD_DIR.mkdir(exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(conn, table_name, columns):
    existing_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()}
    for column_name, column_definition in columns.items():
        if column_name not in existing_columns:
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}')


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def row_to_dict(row):
    return dict(row) if row is not None else None


def allowed_upload(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def simple_pdf_bytes(title, lines):
    def escape_text(value):
        return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    content_lines = ['BT', '/F1 12 Tf', '72 760 Td', f'({escape_text(title)}) Tj']
    for line in lines:
        content_lines.append('0 -18 Td')
        content_lines.append(f'({escape_text(line)}) Tj')
    content_lines.append('ET')
    content = '\n'.join(content_lines).encode('latin-1', 'replace')

    objects = []
    objects.append(b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n')
    objects.append(b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n')
    objects.append(
        b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n'
    )
    objects.append(b'4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n')
    objects.append(b'5 0 obj << /Length ' + str(len(content)).encode() + b' >> stream\n' + content + b'\nendstream endobj\n')

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_offset = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n'.encode())
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n'.encode())
    pdf.extend(f'startxref\n{xref_offset}\n%%EOF'.encode())
    return bytes(pdf)


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
                payment_status TEXT DEFAULT 'Unpaid',
                payment_method TEXT,
                payment_reference TEXT,
                rescheduled_date TEXT,
                cancellation_reason TEXT,
                estimated_time TEXT,
                spare_parts_used TEXT,
                before_image TEXT,
                after_image TEXT,
                mechanic_notes TEXT,
                invoice_number TEXT,
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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nickname TEXT,
                vehicle_type TEXT,
                vehicle_number TEXT UNIQUE,
                is_favorite INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                loyalty_points INTEGER DEFAULT 0,
                referral_code TEXT,
                coupon_code TEXT,
                emi_due_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                title TEXT NOT NULL,
                reminder_date TEXT,
                status TEXT DEFAULT 'Active',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS support_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                request_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'Open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lead_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                lead_type TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                notes TEXT,
                status TEXT DEFAULT 'New',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS workshops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                address TEXT,
                contact TEXT,
                rating REAL DEFAULT 4.5,
                city TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS favorite_workshops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workshop_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, workshop_id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                vehicle_number TEXT,
                document_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                description TEXT,
                discount_type TEXT DEFAULT 'percent',
                discount_value REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                mechanic_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        ensure_columns(conn, 'bookings', {
            'payment_status': "TEXT DEFAULT 'Unpaid'",
            'payment_method': 'TEXT',
            'payment_reference': 'TEXT',
            'rescheduled_date': 'TEXT',
            'cancellation_reason': 'TEXT',
            'estimated_time': 'TEXT',
            'spare_parts_used': 'TEXT',
            'before_image': 'TEXT',
            'after_image': 'TEXT',
            'mechanic_notes': 'TEXT',
            'invoice_number': 'TEXT',
        })
        ensure_upload_dir()
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
        if conn.execute('SELECT COUNT(*) FROM wallets').fetchone()[0] == 0:
            conn.execute(
                'INSERT INTO wallets (user_id, balance, loyalty_points, referral_code) VALUES (?, ?, ?, ?)',
                (1, 0, 100, 'SVMS100'),
            )
        if conn.execute('SELECT COUNT(*) FROM workshops').fetchone()[0] == 0:
            conn.executemany(
                'INSERT INTO workshops (name, address, contact, rating, city) VALUES (?, ?, ?, ?, ?)',
                [
                    ('Central Auto Care', '12 Market Road', '+1 555 100 200', 4.8, 'Downtown'),
                    ('Prime Garage', '88 Industrial Street', '+1 555 200 300', 4.7, 'Uptown'),
                    ('Green Pit Stop', '44 Lake Avenue', '+1 555 300 400', 4.6, 'West End'),
                ],
            )
        if conn.execute('SELECT COUNT(*) FROM offers').fetchone()[0] == 0:
            conn.executemany(
                'INSERT INTO offers (code, description, discount_type, discount_value) VALUES (?, ?, ?, ?)',
                [
                    ('SAVE10', '10% off your next booking', 'percent', 10),
                    ('WELCOME500', 'Flat wallet bonus on first booking', 'flat', 500),
                ],
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


def get_wallet(conn, user_id):
    wallet = conn.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
    if wallet is None:
        conn.execute(
            'INSERT INTO wallets (user_id, balance, loyalty_points, referral_code) VALUES (?, ?, ?, ?)',
            (user_id, 0, 0, f'SVMS{user_id:04d}'),
        )
        wallet = conn.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
    return row_to_dict(wallet)


def get_customer_context(conn, user_id):
    bookings = rows_to_dicts(
        conn.execute(
            '''
            SELECT b.*, s.name AS service_name, s.price AS service_price
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.customer_id = ?
            ORDER BY b.created_at DESC
            ''',
            (user_id,),
        ).fetchall()
    )
    vehicles = rows_to_dicts(conn.execute('SELECT * FROM vehicles WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall())
    reminders = rows_to_dicts(conn.execute('SELECT * FROM reminders WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall())
    documents = rows_to_dicts(conn.execute('SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall())
    support_requests = rows_to_dicts(conn.execute('SELECT * FROM support_requests WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall())
    leads = rows_to_dicts(conn.execute('SELECT * FROM lead_requests WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall())
    workshops = rows_to_dicts(conn.execute('SELECT * FROM workshops ORDER BY rating DESC, name').fetchall())
    favorites = {
        row['workshop_id']
        for row in conn.execute('SELECT workshop_id FROM favorite_workshops WHERE user_id = ?', (user_id,)).fetchall()
    }
    wallet = get_wallet(conn, user_id)
    return {
        'bookings': bookings,
        'vehicles': vehicles,
        'reminders': reminders,
        'documents': documents,
        'support_requests': support_requests,
        'leads': leads,
        'workshops': workshops,
        'favorite_workshops': favorites,
        'wallet': wallet,
        'feedback_count': conn.execute('SELECT COUNT(*) AS count FROM feedbacks WHERE customer_id = ?', (user_id,)).fetchone()['count'],
    }


def add_notification(conn, user_id, message):
    conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (user_id, message))


def log_job_action(conn, booking_id, action, details=''):
    conn.execute(
        'INSERT INTO job_logs (booking_id, mechanic_id, action, details) VALUES (?, ?, ?, ?)',
        (booking_id, session.get('user_id'), action, details),
    )


@app.route('/features')
def features():
    return render_template('features.html', feature_groups=FEATURE_GROUPS)


@app.route('/feature-hub')
def feature_hub():
    return redirect(url_for('features'))


@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    if not session.get('user_id'):
        flash('Please login to manage your booking.', 'warning')
        return redirect(url_for('login'))
    reason = request.form.get('reason', 'Customer requested cancellation').strip()
    conn = get_db()
    try:
        booking = conn.execute('SELECT * FROM bookings WHERE id = ? AND customer_id = ?', (booking_id, session['user_id'])).fetchone()
        if booking is None:
            flash('Booking not found.', 'warning')
            return redirect(url_for('customer_dashboard'))
        conn.execute(
            'UPDATE bookings SET status = ?, cancellation_reason = ? WHERE id = ?',
            ('Cancelled', reason, booking_id),
        )
        add_notification(conn, session['user_id'], f'Booking #{booking_id} was cancelled.')
        conn.commit()
        flash(f'Booking #{booking_id} cancelled.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/booking/<int:booking_id>/reschedule', methods=['POST'])
def reschedule_booking(booking_id):
    if not session.get('user_id'):
        flash('Please login to manage your booking.', 'warning')
        return redirect(url_for('login'))
    new_date = request.form.get('new_date', '').strip()
    if not new_date:
        flash('Please select a new date.', 'warning')
        return redirect(url_for('customer_dashboard'))
    conn = get_db()
    try:
        booking = conn.execute('SELECT * FROM bookings WHERE id = ? AND customer_id = ?', (booking_id, session['user_id'])).fetchone()
        if booking is None:
            flash('Booking not found.', 'warning')
            return redirect(url_for('customer_dashboard'))
        conn.execute(
            'UPDATE bookings SET booking_date = ?, rescheduled_date = ?, status = ? WHERE id = ?',
            (new_date, new_date, 'Rescheduled', booking_id),
        )
        add_notification(conn, session['user_id'], f'Booking #{booking_id} was rescheduled to {new_date}.')
        conn.commit()
        flash(f'Booking #{booking_id} rescheduled.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/invoice/<int:booking_id>/pdf')
def download_invoice_pdf(booking_id):
    if not session.get('user_id'):
        flash('Please login to download your invoice.', 'warning')
        return redirect(url_for('login'))
    conn = get_db()
    try:
        booking = conn.execute(
            '''
            SELECT b.*, s.name AS service_name, s.price AS service_price, u.full_name, u.email, u.phone
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.customer_id = u.id
            WHERE b.id = ? AND b.customer_id = ?
            ''',
            (booking_id, session['user_id']),
        ).fetchone()
        if booking is None:
            abort(404)
        booking = row_to_dict(booking)
        if not booking.get('invoice_number'):
            booking['invoice_number'] = f'SVMS-{booking_id:06d}'
            conn.execute('UPDATE bookings SET invoice_number = ? WHERE id = ?', (booking['invoice_number'], booking_id))
            conn.commit()
        pdf = simple_pdf_bytes(
            f"Invoice {booking['invoice_number']}",
            [
                f"Customer: {booking['full_name']}",
                f"Service: {booking['service_name']}",
                f"Vehicle: {booking.get('vehicle_number') or '-'}",
                f"Booking Date: {booking.get('booking_date') or '-'}",
                f"Status: {booking.get('status') or '-'}",
                f"Amount: INR {booking['service_price']}",
            ],
        )
        return send_file(
            io.BytesIO(pdf),
            as_attachment=True,
            download_name=f"invoice-{booking['invoice_number']}.pdf",
            mimetype='application/pdf',
        )
    finally:
        conn.close()


@app.route('/customer/wallet', methods=['POST'])
def update_wallet():
    if not session.get('user_id'):
        flash('Please login to view your wallet.', 'warning')
        return redirect(url_for('login'))
    amount = float(request.form.get('amount', '0') or 0)
    coupon_code = request.form.get('coupon_code', '').strip().upper()
    conn = get_db()
    try:
        wallet = get_wallet(conn, session['user_id'])
        balance = wallet['balance'] + amount
        if coupon_code:
            coupon = conn.execute('SELECT * FROM offers WHERE code = ? AND is_active = 1', (coupon_code,)).fetchone()
            if coupon is not None:
                if coupon['discount_type'] == 'flat':
                    balance += float(coupon['discount_value'])
                else:
                    balance += max(amount * float(coupon['discount_value']) / 100.0, 0)
                conn.execute('UPDATE wallets SET coupon_code = ? WHERE user_id = ?', (coupon_code, session['user_id']))
                flash(f'Coupon {coupon_code} applied.', 'success')
            else:
                flash('Coupon not found.', 'warning')
        points = wallet['loyalty_points'] + max(int(amount // 100), 0)
        conn.execute('UPDATE wallets SET balance = ?, loyalty_points = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (balance, points, session['user_id']))
        conn.commit()
        flash('Wallet updated successfully.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/reminders', methods=['POST'])
def create_reminder():
    if not session.get('user_id'):
        flash('Please login to manage reminders.', 'warning')
        return redirect(url_for('login'))
    reminder_type = request.form.get('reminder_type', 'Service')
    title = request.form.get('title', '').strip()
    reminder_date = request.form.get('reminder_date', '').strip()
    notes = request.form.get('notes', '').strip()
    if not title:
        flash('Please enter a reminder title.', 'warning')
        return redirect(url_for('customer_dashboard'))
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO reminders (user_id, reminder_type, title, reminder_date, notes) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], reminder_type, title, reminder_date, notes),
        )
        conn.commit()
        flash('Reminder saved.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/support', methods=['POST'])
def create_support_request():
    if not session.get('user_id'):
        flash('Please login to contact support.', 'warning')
        return redirect(url_for('login'))
    request_type = request.form.get('request_type', 'Live Chat')
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()
    if not subject or not message:
        flash('Please complete the support form.', 'warning')
        return redirect(url_for('customer_dashboard'))
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO support_requests (user_id, request_type, subject, message) VALUES (?, ?, ?, ?)',
            (session['user_id'], request_type, subject, message),
        )
        add_notification(conn, session['user_id'], f'Support request submitted: {subject}')
        conn.commit()
        flash('Support request submitted.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/fuel-calculator', methods=['POST'])
def fuel_calculator():
    if not session.get('user_id'):
        flash('Please login to use the fuel cost calculator.', 'warning')
        return redirect(url_for('login'))
    distance = float(request.form.get('distance', '0') or 0)
    mileage = float(request.form.get('mileage', '0') or 0)
    fuel_price = float(request.form.get('fuel_price', '0') or 0)
    result = round((distance / mileage) * fuel_price, 2) if distance > 0 and mileage > 0 else 0
    flash(f'Estimated fuel cost: INR {result}', 'success')
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/leads', methods=['POST'])
def create_lead_request():
    if not session.get('user_id'):
        flash('Please login to submit a request.', 'warning')
        return redirect(url_for('login'))
    lead_type = request.form.get('lead_type', 'Test Drive')
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    notes = request.form.get('notes', '').strip()
    if not name:
        flash('Please provide your name.', 'warning')
        return redirect(url_for('customer_dashboard'))
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO lead_requests (user_id, lead_type, name, phone, notes) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], lead_type, name, phone, notes),
        )
        conn.commit()
        flash(f'{lead_type} request submitted.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/workshops/<int:workshop_id>/favorite', methods=['POST'])
def favorite_workshop(workshop_id):
    if not session.get('user_id'):
        flash('Please login to favorite a workshop.', 'warning')
        return redirect(url_for('login'))
    conn = get_db()
    try:
        conn.execute('INSERT OR IGNORE INTO favorite_workshops (user_id, workshop_id) VALUES (?, ?)', (session['user_id'], workshop_id))
        conn.commit()
        flash('Workshop added to favorites.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/documents', methods=['POST'])
def upload_document():
    if not session.get('user_id'):
        flash('Please login to upload documents.', 'warning')
        return redirect(url_for('login'))
    document = request.files.get('document_file')
    document_type = request.form.get('document_type', 'Vehicle Document').strip()
    vehicle_number = request.form.get('vehicle_number', '').strip()
    if document is None or document.filename == '':
        flash('Please choose a file to upload.', 'warning')
        return redirect(url_for('customer_dashboard'))
    if not allowed_upload(document.filename):
        flash('Unsupported file type.', 'warning')
        return redirect(url_for('customer_dashboard'))
    ensure_upload_dir()
    filename = secure_filename(f"{session['user_id']}_{datetime.now().timestamp()}_{document.filename}")
    file_path = UPLOAD_DIR / filename
    document.save(file_path)
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO documents (user_id, vehicle_number, document_type, file_name, file_path) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], vehicle_number, document_type, document.filename, filename),
        )
        conn.commit()
        flash('Document uploaded successfully.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/vehicles', methods=['POST'])
def add_vehicle():
    if not session.get('user_id'):
        flash('Please login to manage vehicles.', 'warning')
        return redirect(url_for('login'))
    nickname = request.form.get('nickname', '').strip()
    vehicle_type = request.form.get('vehicle_type', '').strip()
    vehicle_number = request.form.get('vehicle_number', '').strip()
    if not vehicle_number:
        flash('Vehicle number is required.', 'warning')
        return redirect(url_for('customer_dashboard'))
    conn = get_db()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO vehicles (user_id, nickname, vehicle_type, vehicle_number) VALUES (?, ?, ?, ?)',
            (session['user_id'], nickname or vehicle_number, vehicle_type, vehicle_number),
        )
        conn.commit()
        flash('Vehicle added successfully.', 'success')
    finally:
        conn.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/admin/export/<string:entity>.csv')
def export_csv(entity):
    if session.get('user_role') != 'admin':
        flash('Only admins can export data.', 'warning')
        return redirect(url_for('home'))
    queries = {
        'customers': ('SELECT id, full_name, email, phone, role, created_at FROM users ORDER BY id', ['id', 'full_name', 'email', 'phone', 'role', 'created_at']),
        'bookings': ('SELECT id, customer_id, service_id, vehicle_type, vehicle_number, booking_date, status, payment_status, created_at FROM bookings ORDER BY id', ['id', 'customer_id', 'service_id', 'vehicle_type', 'vehicle_number', 'booking_date', 'status', 'payment_status', 'created_at']),
        'mechanics': ('SELECT id, full_name, email, phone, role, created_at FROM users WHERE role = "mechanic" ORDER BY id', ['id', 'full_name', 'email', 'phone', 'role', 'created_at']),
    }
    if entity not in queries:
        abort(404)
    query, headers = queries[entity]
    conn = get_db()
    try:
        rows = rows_to_dicts(conn.execute(query).fetchall())
    finally:
        conn.close()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    response = app.response_class(buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename={entity}.csv'
    return response


@app.route('/admin/backup-database')
def backup_database():
    if session.get('user_role') != 'admin':
        flash('Only admins can back up the database.', 'warning')
        return redirect(url_for('home'))
    if not DB_PATH.exists():
        abort(404)
    return send_file(DB_PATH, as_attachment=True, download_name='svams-backup.db')


@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
def change_role(user_id):
    if session.get('user_role') != 'admin':
        flash('Only admins can change roles.', 'warning')
        return redirect(url_for('home'))
    role = request.form.get('role', 'customer')
    if role not in {'customer', 'admin', 'mechanic'}:
        flash('Invalid role selected.', 'warning')
        return redirect(url_for('admin_dashboard'))
    conn = get_db()
    try:
        conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        conn.commit()
        flash('Role updated successfully.', 'success')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/mechanic/bookings/<int:booking_id>/<string:action>', methods=['POST'])
def mechanic_job_action(booking_id, action):
    if session.get('user_role') != 'mechanic':
        flash('Only mechanics can update jobs.', 'warning')
        return redirect(url_for('home'))
    before_image = request.files.get('before_image')
    after_image = request.files.get('after_image')
    estimated_time = request.form.get('estimated_time', '').strip()
    spare_parts_used = request.form.get('spare_parts_used', '').strip()
    mechanic_notes = request.form.get('mechanic_notes', '').strip()
    conn = get_db()
    try:
        booking = conn.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        if booking is None:
            flash('Job not found.', 'warning')
            return redirect(url_for('mechanic_dashboard'))
        updates = {
            'accept': ('Accepted', 'Job accepted'),
            'reject': ('Rejected', 'Job rejected'),
            'complete': ('Completed', 'Job completed'),
        }
        if action not in updates:
            abort(404)
        new_status, log_message = updates[action]
        before_path = booking['before_image']
        after_path = booking['after_image']
        if before_image and before_image.filename and allowed_upload(before_image.filename):
            ensure_upload_dir()
            before_filename = secure_filename(f"booking-{booking_id}-before-{datetime.now().timestamp()}-{before_image.filename}")
            before_image.save(UPLOAD_DIR / before_filename)
            before_path = before_filename
        if after_image and after_image.filename and allowed_upload(after_image.filename):
            ensure_upload_dir()
            after_filename = secure_filename(f"booking-{booking_id}-after-{datetime.now().timestamp()}-{after_image.filename}")
            after_image.save(UPLOAD_DIR / after_filename)
            after_path = after_filename
        conn.execute(
            '''
            UPDATE bookings
            SET status = ?, estimated_time = COALESCE(?, estimated_time), spare_parts_used = COALESCE(?, spare_parts_used),
                mechanic_notes = COALESCE(?, mechanic_notes), before_image = ?, after_image = ?
            WHERE id = ?
            ''',
            (new_status, estimated_time or None, spare_parts_used or None, mechanic_notes or None, before_path, after_path, booking_id),
        )
        log_job_action(conn, booking_id, action, log_message)
        add_notification(conn, booking['customer_id'], f'Your booking #{booking_id} is now {new_status}.')
        conn.commit()
        flash(f'Booking #{booking_id} marked as {new_status}.', 'success')
    finally:
        conn.close()
    return redirect(url_for('mechanic_dashboard'))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


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
        payment_method = request.form.get('payment_method', 'Wallet')
        conn = get_db()
        try:
            service_row = conn.execute('SELECT id FROM services WHERE name = ?', (service_name,)).fetchone()
            if not service_row:
                flash('Selected service is unavailable.', 'warning')
                return redirect(url_for('book_service'))
            cursor = conn.execute(
                'INSERT INTO bookings (customer_id, service_id, vehicle_type, vehicle_number, booking_date, status, notes, payment_status, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (session['user_id'], service_row['id'], vehicle_type, vehicle_number, booking_date, 'Pending', notes, 'Pending', payment_method),
            )
            if vehicle_number:
                conn.execute(
                    'INSERT OR IGNORE INTO vehicles (user_id, nickname, vehicle_type, vehicle_number) VALUES (?, ?, ?, ?)',
                    (session['user_id'], vehicle_type or vehicle_number, vehicle_type, vehicle_number),
                )
            conn.commit()
            booking_id = cursor.lastrowid
            conn.execute('UPDATE bookings SET invoice_number = ? WHERE id = ?', (f'SVMS-{booking_id:06d}', booking_id))
            add_notification(conn, session['user_id'], f'Booking #{booking_id} created for {service_name}.')
            conn.commit()
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
    data = {
        'bookings': [],
        'feedback_count': 0,
        'vehicles': [],
        'wallet': {'balance': 0, 'loyalty_points': 0, 'referral_code': ''},
        'reminders': [],
        'documents': [],
        'support_requests': [],
        'leads': [],
        'workshops': [],
        'favorite_workshops': set(),
    }
    try:
        data.update(get_customer_context(conn, session['user_id']))
    finally:
        conn.close()
    return render_template('customer_dashboard.html', data=data)


@app.route('/admin-dashboard')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        flash('Only admins can view this page.', 'warning')
        return redirect(url_for('home'))
    conn = get_db()
    data = {'users': 0, 'bookings': 0, 'revenue': 0, 'mechanics': 0, 'offers': 0, 'recent_users': [], 'recent_bookings': [], 'services': [], 'users_list': []}
    try:
        users_count = conn.execute('SELECT COUNT(*) AS count FROM users').fetchone()
        mechanics_count = conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'mechanic'").fetchone()
        bookings_count = conn.execute('SELECT COUNT(*) AS count FROM bookings').fetchone()
        revenue_row = conn.execute('SELECT COALESCE(SUM(s.price), 0) AS total FROM bookings b JOIN services s ON b.service_id = s.id WHERE b.status != "Cancelled"').fetchone()
        data['users'] = users_count['count']
        data['mechanics'] = mechanics_count['count']
        data['bookings'] = bookings_count['count']
        data['revenue'] = revenue_row['total']
        data['offers'] = conn.execute('SELECT COUNT(*) AS count FROM offers WHERE is_active = 1').fetchone()['count']
        data['recent_users'] = rows_to_dicts(conn.execute('SELECT id, full_name, email, role, created_at FROM users ORDER BY created_at DESC LIMIT 6').fetchall())
        data['recent_bookings'] = rows_to_dicts(conn.execute('''
            SELECT b.*, s.name AS service_name, u.full_name AS customer_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.customer_id = u.id
            ORDER BY b.created_at DESC
            LIMIT 8
        ''').fetchall())
        data['services'] = get_services()
        data['users_list'] = rows_to_dicts(conn.execute('SELECT id, full_name, email, role FROM users ORDER BY full_name').fetchall())
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
    today_jobs = []
    stats = {'pending': 0, 'accepted': 0, 'completed': 0}
    try:
        rows = conn.execute('''
            SELECT b.*, s.name AS service_name, u.full_name AS customer_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.customer_id = u.id
            ORDER BY b.created_at DESC
        ''').fetchall()
        jobs = [dict(row) for row in rows]
        today = datetime.now().date().strftime('%Y-%m-%d')
        today_jobs = [job for job in jobs if (job.get('booking_date') or '') == today]
        stats['pending'] = sum(1 for job in jobs if job['status'] == 'Pending')
        stats['accepted'] = sum(1 for job in jobs if job['status'] == 'Accepted')
        stats['completed'] = sum(1 for job in jobs if job['status'] == 'Completed')
    finally:
        conn.close()
    return render_template('mechanic_dashboard.html', jobs=jobs, today_jobs=today_jobs, stats=stats)


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
            SELECT b.id, b.booking_date, b.status, b.payment_status, b.invoice_number, s.name AS service_name, s.price, u.full_name, u.email
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.customer_id = u.id
            WHERE b.customer_id = ?
            ORDER BY b.created_at DESC
            LIMIT 1
        ''', (session['user_id'],)).fetchone()
        invoice_data = dict(row) if row is not None else None
        if invoice_data and not invoice_data.get('invoice_number'):
            invoice_data['invoice_number'] = f"SVMS-{invoice_data['id']:06d}"
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
