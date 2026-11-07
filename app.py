# Nama File: app.py
# Lokasi: Folder utama (delivery-app/app.py)

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

# 1. SETUP APLIKASI
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci-rahasia-aplikasi-ini'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///delivery.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 2. STRUKTUR DATABASE
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    food_items = db.Column(db.Text, nullable=False)
    address = db.Column(db.Text, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Menunggu Driver') 
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 3. ROUTING DASHBOARD
@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    if session.get('role') == 'admin': return redirect(url_for('admin_dashboard'))
    return redirect(url_for('driver_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    
    if request.method == 'POST':
        tracking_id = secrets.token_hex(4).upper() 
        new_order = Order(
            tracking_id=tracking_id, customer_name=request.form['customer_name'],
            customer_phone=request.form['customer_phone'], food_items=request.form['food_items'],
            address=request.form['address'], lat=float(request.form['lat']),
            lng=float(request.form['lng']), delivery_fee=int(request.form['delivery_fee']),
            notes=request.form.get('notes', '')
        )
        db.session.add(new_order)
        db.session.commit()
        socketio.emit('new_order_event', {'message': 'Pesanan baru!'})
        flash('Pesanan berhasil dibuat!', 'success')
        return redirect(url_for('admin_dashboard'))

    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin.html', orders=orders)

@app.route('/driver')
def driver_dashboard():
    if session.get('role') != 'driver': return redirect(url_for('login'))
    active_orders = Order.query.filter(~Order.status.in_(['Selesai', 'Dibatalkan'])).order_by(Order.created_at.desc()).all()
    return render_template('driver.html', orders=active_orders)

@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if session.get('role') != 'driver': return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    new_status = data.get('status')
    
    order = Order.query.get_or_404(order_id)
    order.status = new_status
    if new_status == 'Diterima': order.driver_id = session['user_id']
    db.session.commit()
    
    socketio.emit('status_update', {'order_id': order.id, 'status': new_status})
    return jsonify({'success': True, 'message': 'Status diperbarui!'})

# --- FITUR LIVE TRACKING BARU ---

# Halaman publik untuk customer melihat posisi driver
@app.route('/track/<tracking_id>')
def track_order(tracking_id):
    # Cari order berdasarkan token acak
    order = Order.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template('tracking.html', order=order)

# Menerima lokasi dari driver dan membagikannya ke customer
@socketio.on('driver_update_location')
def handle_location(data):
    # data berisi: {'tracking_id': 'TOKEN123', 'lat': -6.123, 'lng': 106.123}
    # Teruskan data ini ke semua pengguna (Nanti difilter di halaman HTML pembeli)
    emit('location_broadcast', data, broadcast=True)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password=generate_password_hash('admin123'), role='admin'))
    if not User.query.filter_by(username='driver').first():
        db.session.add(User(username='driver', password=generate_password_hash('driver123'), role='driver'))
    db.session.commit()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)