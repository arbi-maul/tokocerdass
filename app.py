from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import os
import requests 
import json
import pandas as pd 
from io import BytesIO
from functools import wraps

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_anda_disini'

# ==========================================
# KONFIGURASI
# ==========================================
TELEGRAM_BOT_TOKEN = '7564336114:AAHpiS4uhYmj90pQonb6Txzcb1PpUK7Jezc' 
TELEGRAM_CHAT_IDS = ['7895627762', '7888193325'] 

DB_NAME = 'arbi_pos_db'
DB_USER = 'root'
DB_PASS = '' 
DB_HOST = 'localhost'

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# MODELS
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='karyawan') # <-- KOLOM BARU

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default='Umum')
    stock = db.Column(db.Integer, default=0)
    modal = db.Column(db.Float, default=0)
    market_price = db.Column(db.Float, default=0)
    retail_price = db.Column(db.Float, default=0) 
    wholesale_price = db.Column(db.Float, default=0) 
    min_wholesale_quantity = db.Column(db.Integer, default=10)
    sale_type = db.Column(db.String(20), default='all')
    dozen_price = db.Column(db.Float, default=0)
    barcode = db.Column(db.String(50), nullable=True)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    total_penjualan = db.Column(db.Float, default=0)
    total_potongan = db.Column(db.Float, default=0)
    keuntungan = db.Column(db.Float, default=0)
    items = db.relationship('SaleItem', backref='sale', lazy=True)

class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    modal = db.Column(db.Float, default=0)       
    sale_type = db.Column(db.String(20))         
    subtotal = db.Column(db.Float, default=0)

class Pelanggan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    usia = db.Column(db.Integer, default=0)
    kategori_segmen = db.Column(db.String(50), default='Umum')
    total_hutang = db.Column(db.Float, default=0)
    harga_khusus = db.relationship('HargaKhusus', backref='pelanggan', lazy=True)

class HargaKhusus(db.Model):
    __tablename__ = 'harga_khusus' 
    id = db.Column(db.Integer, primary_key=True)
    pelanggan_id = db.Column(db.Integer, db.ForeignKey('pelanggan.id'), nullable=False)
    produk_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    harga = db.Column(db.Float, nullable=False)
    @property
    def produk_name(self):
        p = Product.query.get(self.produk_id)
        return p.name if p else "Produk Terhapus"

class OperationalCost(db.Model):
    __tablename__ = 'operational_cost'
    id = db.Column(db.Integer, primary_key=True)
    nama_biaya = db.Column(db.String(100), nullable=False)
    kategori = db.Column(db.String(50), nullable=False)
    jumlah = db.Column(db.Float, nullable=False)
    tanggal = db.Column(db.Date, nullable=False)

# ==========================================
# HELPER & TELEGRAM
# ==========================================
@app.template_filter('rupiah')
def format_rupiah(value):
    return "Rp {:,.0f}".format(value).replace(',', '.')

@app.context_processor
def inject_now():
    return {'now': datetime.now}

def send_telegram_message(text_message):
    if not TELEGRAM_BOT_TOKEN: return
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {'chat_id': chat_id, 'text': text_message, 'parse_mode': 'HTML'}
        try: requests.post(api_url, json=payload, timeout=5)
        except: pass

# ==========================================
# ROUTES UTAMA (SEMUA BISA AKSES)
# ==========================================
@app.route('/')
@app.route('/kasir')
def kasir():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    # Semua role (Admin & Karyawan) boleh akses kasir
    products = Product.query.all()
    pelanggans = Pelanggan.query.all()
    cart = session.get('cart', [])
    total = sum(item['subtotal'] for item in cart)
    selected_pelanggan_id = session.get('selected_pelanggan_id')
    return render_template('kasir.html', products=products, cart=cart, total=total, pelanggans=pelanggans)

@app.route('/set_pelanggan', methods=['POST'])
def set_pelanggan():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
        
    pelanggan_id = request.form.get('pelanggan_id')
    
    if pelanggan_id and pelanggan_id.strip() != "":
        session['selected_pelanggan_id'] = int(pelanggan_id)
        pelanggan = Pelanggan.query.get(int(pelanggan_id))
        if pelanggan:
            session['current_pelanggan_name'] = pelanggan.nama
    else:
        session.pop('selected_pelanggan_id', None)
        session.pop('current_pelanggan_name', None)
    
    # Otomatis hitung ulang harga barang di keranjang berdasarkan katalog Harga Khusus pelanggan baru
    cart = session.get('cart', [])
    if cart:
        for item in cart:
            product = Product.query.get(item['id'])
            if product:
                price = product.retail_price
                price_type_ori = item['price_type']
                
                harga_khusus_active = False
                if pelanggan_id and pelanggan_id.strip() != "":
                    hk = HargaKhusus.query.filter_by(pelanggan_id=int(pelanggan_id), produk_id=product.id).first()
                    if hk:
                        price = hk.harga
                        harga_khusus_active = True
                        item['price_type'] = "Khusus"
                
                if not harga_khusus_active:
                    if price_type_ori.lower() == 'lusinan':
                        price = product.dozen_price if product.dozen_price > 0 else product.retail_price
                        item['price_type'] = "Lusinan"
                    elif price_type_ori.lower() == 'grosir':
                        price = product.wholesale_price
                        item['price_type'] = "Grosir"
                    else:
                        price = product.retail_price
                        item['price_type'] = "Eceran"
                
                item['price'] = price
                item['subtotal'] = item['quantity'] * price
        session['cart'] = cart
        session.modified = True
        
    return redirect(url_for('kasir'))

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        product_id = int(request.form.get('product_id'))
        quantity = int(request.form.get('quantity'))
        price_type = request.form.get('price_type') # eceran, grosir, lusinan
        pelanggan_id = request.form.get('pelanggan_id') 
        product = Product.query.get(product_id)
        if not product: return redirect(url_for('kasir'))

        # --- SIMPAN ID PELANGGAN KE SESSION AGAR TIDAK RE-SET ---
        if pelanggan_id and pelanggan_id.strip() != "":
            session['selected_pelanggan_id'] = int(pelanggan_id)
            pelanggan = Pelanggan.query.get(pelanggan_id)
            if pelanggan:
                session['current_pelanggan_name'] = pelanggan.nama
        else:
            session.pop('selected_pelanggan_id', None)
            session.pop('current_pelanggan_name', None)
        
        # --- PROTEKSI SUPER KETAT SERVER (MENCEGAH HUMAN ERROR) ---
        if product.sale_type == 'lusinan_only' and price_type != 'lusinan':
            flash(f"❌ SISTEM MENOLAK: {product.name} HANYA boleh dibeli secara LUSINAN!", "danger")
            return redirect(url_for('kasir'))
        
        if product.sale_type == 'eceran_only' and price_type == 'lusinan':
            flash(f"❌ SISTEM MENOLAK: {product.name} TIDAK BISA dibeli secara lusinan!", "danger")
            return redirect(url_for('kasir'))
        # -----------------------------------------------------------
        
        price = 0
        final_price_type = price_type.title()
        harga_khusus_active = False
        if pelanggan_id:
            hk = HargaKhusus.query.filter_by(pelanggan_id=pelanggan_id, produk_id=product_id).first()
            if hk:
                price = hk.harga
                harga_khusus_active = True
                final_price_type = "Khusus"
                pelanggan = Pelanggan.query.get(pelanggan_id)
                session['current_pelanggan_name'] = pelanggan.nama
                
        if not harga_khusus_active:
            if not pelanggan_id: session.pop('current_pelanggan_name', None)
            if price_type == 'lusinan': price = product.dozen_price if product.dozen_price > 0 else product.retail_price
            elif price_type == 'grosir': price = product.wholesale_price
            else: price = product.retail_price

        cart = session.get('cart', [])
        found = False
        for item in cart:
            if item['id'] == product_id and item['price_type'] == final_price_type:
                item['quantity'] += quantity
                item['subtotal'] = item['quantity'] * item['price']
                found = True
                break
        if not found:
            cart.append({
                'id': product.id, 'name': product.name, 'price': price,
                'quantity': quantity, 'price_type': final_price_type,
                'subtotal': price * quantity, 'original_id': product.id,
                'modal_saat_ini': product.modal 
            })
        session['cart'] = cart
        return redirect(url_for('kasir'))
    except Exception as e: 
        print(f"Cart Error: {e}")
        return redirect(url_for('kasir'))

@app.route('/update_cart/<int:index>', methods=['POST'])
def update_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] = int(request.form.get('quantity'))
        cart[index]['subtotal'] = cart[index]['quantity'] * cart[index]['price']
        session['cart'] = cart
    return redirect(url_for('kasir'))

@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart.pop(index)
        session['cart'] = cart
    return redirect(url_for('kasir'))

@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    session.pop('selected_pelanggan_id', None)
    session.pop('current_pelanggan_name', None)
    return redirect(url_for('kasir'))

@app.route('/checkout')
def checkout():
    if not session.get('logged_in'): return redirect(url_for('login'))
    cart = session.get('cart', [])
    if not cart: return redirect(url_for('kasir'))
    total = sum(item['subtotal'] for item in cart)
    pelanggans = Pelanggan.query.all()
    
    # AMBIL ID & DATA PELANGGAN TERPILIH DARI SESSION UNTUK HALAMAN PEMBAYARAN
    selected_pelanggan_id = session.get('selected_pelanggan_id')
    pelanggan_aktif = None
    if selected_pelanggan_id:
        pelanggan_aktif = Pelanggan.query.get(selected_pelanggan_id)
        
    return render_template('pembayaran.html', cart=cart, total=total, pelanggans=pelanggans, selected_pelanggan_id=selected_pelanggan_id, pelanggan_aktif=pelanggan_aktif)

@app.route('/proses_pembayaran', methods=['POST'])
def proses_pembayaran():
    if not session.get('logged_in'): return redirect(url_for('login'))
    cart = session.get('cart', [])
    if not cart: return redirect(url_for('kasir'))
    
    total_belanja = sum(item['subtotal'] for item in cart)
    potongan = float(request.form.get('potongan', 0) or 0)
    uang_bayar = float(request.form.get('uang_bayar', 0) or 0)
    
    total_akhir = total_belanja - potongan
    kembalian = uang_bayar - total_akhir
    hutang_baru = 0
    
    # Ambil ID pelanggan dari form, jika kosong gunakan dari session
    pelanggan_id = request.form.get('pelanggan_id') or session.get('selected_pelanggan_id')
        
    pelanggan_nama = "Umum"
    if pelanggan_id:
        pelanggan = Pelanggan.query.get(pelanggan_id)
        if pelanggan:
            pelanggan_nama = pelanggan.nama
            if kembalian < 0:
                hutang_baru = abs(kembalian) 
                pelanggan.total_hutang += hutang_baru
                kembalian = 0 
                flash(f'Hutang Rp {hutang_baru:,.0f} berhasil dicatat untuk {pelanggan.nama}.', 'warning')
    else:
        if kembalian < 0:
            flash('Uang kurang! Wajib pilih pelanggan untuk hutang.', 'danger')
            return redirect(url_for('checkout'))

    # Hitung kembalian tunai yang sebenarnya (tidak boleh minus di Telegram)
    kembalian_nyata = max(0.0, uang_bayar - total_akhir) if hutang_baru == 0 else 0.0
    uang_masuk_nyata = total_akhir - hutang_baru
    
    new_sale = Sale(total_penjualan=uang_masuk_nyata, total_potongan=potongan, keuntungan=0)
    db.session.add(new_sale)
    db.session.flush()
    
    total_modal = 0
    list_barang_str = ""
    for item in cart:
        prod = Product.query.get(item['id'])
        if prod:
            prod.stock -= item['quantity']
            total_modal += (prod.modal * item['quantity'])
            db.session.add(SaleItem(
                sale_id=new_sale.id, product_name=item['name'], 
                quantity=item['quantity'], price=item['price'], 
                modal=prod.modal, sale_type=item['price_type'], 
                subtotal=item['subtotal']
            ))
            list_barang_str += f"▪️ {item['name']} ({item['quantity']}x) @ {item['price']:,.0f}\n"

    new_sale.keuntungan = uang_masuk_nyata - total_modal
    db.session.commit()
    
    # KIRIM NOTIFIKASI TELEGRAM DENGAN NAMA PELANGGAN DAN KEMBALIAN NYATA
    try: 
        pesan_telegram = (
            f"🛒 <b>TRANSAKSI BARU ({session.get('role', 'user').upper()})</b>\n"
            f"👤 Pelanggan: <b>{pelanggan_nama}</b>\n"
            f"📅 {datetime.now().strftime('%d/%m %H:%M')}\n"
            f"----------------\n"
            f"{list_barang_str}"
            f"----------------\n"
            f"💰 Total Akhir: Rp {total_akhir:,.0f}\n"
            f"💳 Tunai Masuk: Rp {uang_masuk_nyata:,.0f}\n"
            f"🔄 Kembalian: Rp {kembalian_nyata:,.0f}\n"
            f"📒 Hutang Kasbon: Rp {hutang_baru:,.0f}"
        )
        send_telegram_message(pesan_telegram)
    except Exception as e: 
        print(e)
    
    # Reset keranjang dan session pelanggan setelah transaksi selesai
    session.pop('cart', None)
    session.pop('selected_pelanggan_id', None)
    session.pop('current_pelanggan_name', None)
    
    return render_template('struk.html', cart=cart, total=total_belanja, potongan=potongan, total_akhir=total_akhir, uang_bayar=uang_bayar, kembalian=kembalian_nyata, pelanggan_nama=pelanggan_nama)

@app.route('/bayar_hutang', methods=['POST'])
def bayar_hutang():
    if not session.get('logged_in'): return redirect(url_for('login'))

    pelanggan_id = request.form.get('pelanggan_id')
    jumlah_bayar_input = request.form.get('jumlah_bayar', '0')
    jumlah_bayar = float(jumlah_bayar_input) if jumlah_bayar_input else 0
    redirect_to = request.form.get('redirect_to', 'kasbon')

    if pelanggan_id and jumlah_bayar > 0:
        pelanggan = Pelanggan.query.get(pelanggan_id)
        if pelanggan:
            if jumlah_bayar > pelanggan.total_hutang:
                jumlah_bayar = pelanggan.total_hutang
            if jumlah_bayar >= pelanggan.total_hutang:
                pelanggan.total_hutang = 0
                flash(f'Hutang {pelanggan.nama} telah LUNAS!', 'success')
            else:
                pelanggan.total_hutang -= jumlah_bayar
                flash(f'Pembayaran hutang {pelanggan.nama} sebesar Rp {jumlah_bayar:,.0f} berhasil dicatat.', 'success')

            new_payment = Sale(total_penjualan=jumlah_bayar, total_potongan=0, keuntungan=jumlah_bayar)
            db.session.add(new_payment)
            db.session.flush()
            db.session.add(SaleItem(sale_id=new_payment.id, product_name=f"Pelunasan Hutang: {pelanggan.nama}", quantity=1, price=jumlah_bayar, modal=0, sale_type="Bayar Hutang", subtotal=jumlah_bayar))
            db.session.commit()

    if redirect_to == 'checkout':
        return redirect(url_for('checkout'))
    return redirect(url_for('kasbon'))

@app.route('/get_sale_details/<int:sale_id>')
def get_sale_details(sale_id):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    items = SaleItem.query.filter_by(sale_id=sale_id).all()
    output = []
    for item in items:
        output.append({
            'name': item.product_name,
            'qty': item.quantity,
            'price': item.price,
            'subtotal': item.subtotal
        })
    return jsonify({"items": output})

@app.route('/kasbon')
def kasbon():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # PROTEKSI: Jika Admin mencoba mengakses halaman kasbon kasir, alihkan ke Master Pelanggan
    if session.get('role') == 'admin':
        flash('Admin dapat mengelola piutang pelanggan langsung melalui halaman Master Pelanggan.', 'info')
        return redirect(url_for('pelanggan'))

    debtors = Pelanggan.query.filter(Pelanggan.total_hutang > 0).all()
    return render_template('kasbon.html', debtors=debtors)

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if not session.get('logged_in'): return redirect(url_for('login'))

    # PROTEKSI: Admin tidak perlu mengirim keluhan ke diri sendiri
    if session.get('role') == 'admin':
        flash('Halaman pengiriman aduan hanya dikhususkan untuk Karyawan/Kasir toko.', 'info')
        return redirect(url_for('kasir'))

    if request.method == 'POST':
        pengirim = session.get('role', 'karyawan').upper()
        isi_feedback = request.form.get('isi_feedback')

        pesan = (
            f"📢 <b>ADUAN & KELUHAN TOKO ({pengirim})</b>\n"
            f"📅 {datetime.now().strftime('%d/%m %H:%M')}\n"
            f"----------------\n"
            f"📝 Isi Aduan:\n<i>{isi_feedback}</i>"
        )
        send_telegram_message(pesan)
        flash('✅ Laporan aduan Anda telah berhasil dikirim langsung ke Telegram Owner!', 'success')
        return redirect(url_for('feedback'))
    return render_template('feedback.html')

# =========================================================
# ROUTES KHUSUS ADMIN (DIBLOKIR UNTUK KARYAWAN)
# =========================================================

# Helper untuk memblokir akses
def cek_admin():
    if session.get('role') != 'admin':
        flash('Akses ditolak! Halaman ini khusus Admin.', 'danger')
        return False
    return True

@app.route('/data_toko', methods=['GET', 'POST'])
def data_toko():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if not cek_admin(): return redirect(url_for('kasir')) 
    
    # 1. Fitur Simpan Biaya Operasional
    if request.method == 'POST' and 'tambah_biaya' in request.form:
        nama = request.form.get('nama_biaya')
        kategori = request.form.get('kategori')
        jumlah = float(request.form.get('jumlah'))
        tanggal = request.form.get('tanggal')
        db.session.add(OperationalCost(nama_biaya=nama, kategori=kategori, jumlah=jumlah, tanggal=datetime.strptime(tanggal, '%Y-%m-%d')))
        db.session.commit()
        return redirect(url_for('data_toko'))

    # 2. FITUR BARU: Restok Barang Massal (Sekali Klik)
    if request.method == 'POST' and 'restok_barang' in request.form:
        product_ids = request.form.getlist('product_id[]')
        qtys = request.form.getlist('qty_masuk[]')
        biayas = request.form.getlist('total_biaya[]')

        berhasil_count = 0
        for i in range(len(product_ids)):
            if not product_ids[i]: continue # Lewati jika baris kosong
            
            prod_id = int(product_ids[i])
            qty_masuk = int(qtys[i]) if qtys[i] else 0
            total_biaya = float(biayas[i]) if biayas[i] else 0

            if qty_masuk > 0:
                prod = Product.query.get(prod_id)
                if prod:
                    prod.stock += qty_masuk
                    # Otomatis menghitung ulang harga modal satuan
                    if total_biaya > 0:
                        prod.modal = total_biaya / qty_masuk
                    berhasil_count += 1
        
        db.session.commit()
        if berhasil_count > 0:
            flash(f'Berhasil! {berhasil_count} jenis barang telah direstok dan modal diperbarui.', 'success')
        return redirect(url_for('data_toko'))

    # Menampilkan data ke halaman HTML
    biaya_ops = OperationalCost.query.order_by(OperationalCost.tanggal.desc()).limit(20).all()
    products = Product.query.order_by(Product.name).all() # Diurutkan sesuai abjad
    current_month = datetime.now().month
    total_biaya = db.session.query(db.func.sum(OperationalCost.jumlah)).filter(db.extract('month', OperationalCost.tanggal) == current_month).scalar() or 0
    
    return render_template('data_toko.html', biaya_ops=biaya_ops, products=products, total_biaya=total_biaya)

@app.route('/hapus_pelanggan/<int:id>', methods=['POST'])
def hapus_pelanggan(id):
    if not cek_admin(): return redirect(url_for('kasir'))
    
    pelanggan = Pelanggan.query.get(id)
    if pelanggan:
        # Proteksi jika pelanggan masih memiliki hutang aktif
        if pelanggan.total_hutang > 0:
            flash(f'❌ Gagal menghapus! {pelanggan.nama} masih memiliki hutang sebesar {format_rupiah(pelanggan.total_hutang)}.', 'danger')
            return redirect(url_for('pelanggan'))
            
        try:
            # 1. Hapus semua harga khusus milik pelanggan ini terlebih dahulu
            HargaKhusus.query.filter_by(pelanggan_id=id).delete()
            
            # 2. Baru hapus data pelanggan utama
            db.session.delete(pelanggan)
            db.session.commit()
            flash(f'✅ Pelanggan "{pelanggan.nama}" berhasil dihapus.', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"Error Database Hapus: {e}")
            flash('Gagal menghapus pelanggan dari database.', 'danger')
            
    return redirect(url_for('pelanggan'))

@app.route('/hapus_biaya/<int:id>')
def hapus_biaya(id):
    if not cek_admin(): return redirect(url_for('kasir'))
    c = OperationalCost.query.get(id)
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for('data_toko'))

@app.route('/analisis_produk')
def analisis_produk():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if not cek_admin(): return redirect(url_for('kasir')) # <--- PROTEKSI
    
    query_sensitivitas = db.session.query(
        SaleItem.product_name, 
        db.func.sum(SaleItem.quantity).label('total_qty'), 
        db.func.avg(SaleItem.price).label('avg_price'), 
        db.func.avg(SaleItem.modal).label('avg_modal')
    ).group_by(SaleItem.product_name).all()
    
    # PERBAIKAN 1: Pastikan total_vol menjadi float
    total_vol = sum(float(i.total_qty) for i in query_sensitivitas) if query_sensitivitas else 0
    avg_vol = total_vol / len(query_sensitivitas) if len(query_sensitivitas) > 0 else 0
    
    sensitivitas_data = []
    for item in query_sensitivitas:
        # PERBAIKAN 2: Ubah tipe data dari database menjadi float sebelum dihitung
        qty = float(item.total_qty) if item.total_qty else 0
        avg_p = float(item.avg_price) if item.avg_price else 0
        avg_m = float(item.avg_modal) if item.avg_modal else 0
        
        # Hitung margin
        margin = ((avg_p - avg_m) / avg_p) * 100 if avg_p > 0 else 0
        
        # Logika analisis (sekarang menggunakan variabel 'qty' yang sudah berupa float)
        if qty > avg_vol and margin < 15: 
            cls, badge = "Sangat Sensitif", "danger"
        elif margin > 30 and qty >= (avg_vol * 0.5): 
            cls, badge = "Tidak Sensitif", "success"
        elif qty < (avg_vol * 0.5) and margin > 40: 
            cls, badge = "Harga Terlalu Mahal", "warning"
        else: 
            cls, badge = "Sensitif Sedang", "primary"
            
        sensitivitas_data.append({'nama': item.product_name, 'qty': int(qty), 'klasifikasi': cls, 'badge': badge})
        
    sensitivitas_data.sort(key=lambda x: x['qty'], reverse=True)
    
    seven_days_ago = datetime.now() - timedelta(days=7)
    trend_harian = db.session.query(db.func.date(Sale.timestamp).label('tanggal'), db.func.sum(SaleItem.quantity).label('qty')).join(Sale).filter(Sale.timestamp >= seven_days_ago).group_by(db.func.date(Sale.timestamp)).all()
    trend_labels = [str(t.tanggal) for t in trend_harian]
    
    # PERBAIKAN 3: Jaga-jaga jika grafik trend harian juga error Decimal
    trend_values = [int(t.qty) if t.qty else 0 for t in trend_harian] 
    
    segmen_query = db.session.query(Pelanggan.kategori_segmen, db.func.count(Pelanggan.id)).group_by(Pelanggan.kategori_segmen).all()
    segmen_labels = [s[0] for s in segmen_query]
    segmen_values = [s[1] for s in segmen_query]

    return render_template('analisis_produk.html', sensitivitas_data=sensitivitas_data, trend_labels=json.dumps(trend_labels), trend_values=json.dumps(trend_values), segmen_labels=json.dumps(segmen_labels), segmen_values=json.dumps(segmen_values))

@app.route('/produk', methods=['GET', 'POST'])
def produk():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if not cek_admin(): return redirect(url_for('kasir')) # <--- PROTEKSI

    if request.method == 'POST':
        # Menangkap data dengan .get() agar lebih aman jika form kosong
        sale_type_input = request.form.get('sale_type', 'all')
        
        # Tangkap barcode (jika suatu saat form produk.html ditambah input barcode)
        barcode_input = request.form.get('barcode', '').strip()
        barcode_val = barcode_input if barcode_input else None

        try:
            db.session.add(Product(
                name=request.form.get('name'), 
                category=request.form.get('category', 'Umum'), 
                stock=request.form.get('stock', 0), 
                modal=request.form.get('modal', 0), 
                retail_price=request.form.get('retail_price', 0), 
                wholesale_price=request.form.get('wholesale_price', 0), 
                min_wholesale_quantity=request.form.get('min_wholesale_quantity', 12), 
                sale_type=sale_type_input, # <--- DISIMPAN DI SINI
                dozen_price=request.form.get('dozen_price', 0),
                barcode=barcode_val
            ))
            db.session.commit()
            flash('Produk berhasil ditambahkan!', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"Error Tambah Produk: {e}")
            flash('Gagal menambah produk. Cek koneksi database.', 'danger')
            
        return redirect(url_for('produk'))
        
    products = Product.query.all()
    return render_template('produk.html', products=products)

@app.route('/edit_produk/<int:id>', methods=['GET', 'POST'])
def edit_produk(id):
    # Cek Login & Admin
    if not session.get('logged_in'): return redirect(url_for('login'))
    if session.get('role') != 'admin': return redirect(url_for('kasir'))
    
    p = Product.query.get(id)
    
    if request.method == 'POST':
        # --- PERBAIKAN DI SINI (MENGGUNAKAN .get) ---
        # Ini mencegah Error 400 jika input di HTML tidak ditemukan
        p.name = request.form.get('name', p.name)
        p.category = request.form.get('category', 'Umum') # Default ke 'Umum' jika error
        p.stock = request.form.get('stock', p.stock)
        p.modal = request.form.get('modal', p.modal)
        p.retail_price = request.form.get('retail_price', p.retail_price)
        p.wholesale_price = request.form.get('wholesale_price', p.wholesale_price)
        p.min_wholesale_quantity = request.form.get('min_wholesale_quantity', p.min_wholesale_quantity)
        p.sale_type = request.form.get('sale_type', p.sale_type)
        p.dozen_price = request.form.get('dozen_price', 0)
        
        # --- FIX BARCODE DI SINI ---
        barcode_input = request.form.get('barcode', '').strip()
        p.barcode = barcode_input if barcode_input else None
        
        try:
            db.session.commit()
            flash('Produk berhasil diperbarui!', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"Database Error: {e}")
            flash('Gagal update database.', 'danger')
            
        return redirect(url_for('produk'))
        
    return render_template('edit_produk.html', product=p)

@app.route('/hapus_produk/<int:id>', methods=['POST'])
def hapus_produk(id):
    if not cek_admin(): return redirect(url_for('kasir'))
    p = Product.query.get(id)
    if p:
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('produk'))

@app.route('/pelanggan')
def pelanggan():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if not cek_admin(): return redirect(url_for('kasir')) # <--- PROTEKSI
    pelanggans = Pelanggan.query.all()
    products = Product.query.all()
    return render_template('pelanggan.html', pelanggans=pelanggans, products=products)

@app.route('/tambah_pelanggan', methods=['POST'])
def tambah_pelanggan():
    if not cek_admin(): return redirect(url_for('kasir'))
    db.session.add(Pelanggan(nama=request.form.get('nama'), usia=request.form.get('usia', 0), kategori_segmen=request.form.get('kategori_segmen', 'Umum')))
    db.session.commit()
    return redirect(url_for('pelanggan'))

@app.route('/set_harga_khusus', methods=['POST'])
def set_harga_khusus():
    if not cek_admin(): return redirect(url_for('kasir'))
    pid, prid, hrg = request.form.get('pelanggan_id'), request.form.get('produk_id'), request.form.get('harga_khusus')
    if pid and prid:
        ex = HargaKhusus.query.filter_by(pelanggan_id=pid, produk_id=prid).first()
        if ex: ex.harga = float(hrg)
        else: db.session.add(HargaKhusus(pelanggan_id=pid, produk_id=prid, harga=float(hrg)))
        db.session.commit()
    return redirect(url_for('pelanggan'))

@app.route('/hapus_harga_khusus/<int:id>')
def hapus_harga_khusus(id):
    if not cek_admin(): return redirect(url_for('kasir'))
    hk = HargaKhusus.query.get(id)
    db.session.delete(hk)
    db.session.commit()
    return redirect(url_for('pelanggan'))

@app.route('/keuangan')
def keuangan():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if not cek_admin(): return redirect(url_for('kasir'))
    
    current_month = datetime.now().month
    # 1. Hitung keuntungan kotor bulan ini
    sales_month = Sale.query.filter(db.extract('month', Sale.timestamp) == current_month).all()
    gross_profit_month = sum(s.keuntungan for s in sales_month)
    
    # 2. Hitung pengeluaran operasional bulan ini
    ops_month = db.session.query(func.sum(OperationalCost.jumlah)).filter(db.extract('month', OperationalCost.tanggal) == current_month).scalar() or 0
    
    # 3. Hitung keuntungan bersih
    net_profit_month = gross_profit_month - ops_month
    
    # 4. Ambil 15 transaksi terbaru
    recent_sales = Sale.query.order_by(Sale.timestamp.desc()).limit(15).all()
    
    # KUNCI PERBAIKAN: Nama variabel di kanan disesuaikan dengan yang dipanggil HTML
    return render_template('keuangan.html', 
                           profit_month=gross_profit_month, 
                           ops_month=ops_month, 
                           net_profit=net_profit_month,
                           recent_sales=recent_sales)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method=='POST':
        user = User.query.filter_by(username=request.form['username'], password=request.form['password']).first()
        if user:
            session['logged_in']=True
            session['role'] = user.role # <--- SIMPAN ROLE DI SESSION
            return redirect(url_for('kasir'))
        flash('Username/Password salah', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/export_excel')
def export_excel(): 
    if not session.get('logged_in'): return redirect(url_for('login'))
    if session.get('role') != 'admin': return redirect(url_for('kasir'))

    # Ambil data penjualan bulan ini
    current_month = datetime.now().month
    current_year = datetime.now().year
    sales = Sale.query.filter(
        db.extract('month', Sale.timestamp) == current_month,
        db.extract('year', Sale.timestamp) == current_year
    ).order_by(Sale.timestamp.desc()).all()

    # Siapkan data untuk dimasukkan ke Excel
    data = []
    for s in sales:
        data.append({
            'ID Transaksi': s.id,
            'Tanggal & Waktu': s.timestamp.strftime('%Y-%m-%d %H:%M'),
            'Total Belanja (Rp)': s.total_penjualan,
            'Potongan/Diskon (Rp)': s.total_potongan,
            'Keuntungan Bersih (Rp)': s.keuntungan
        })

    # Ubah data menjadi format DataFrame Pandas
    df = pd.DataFrame(data)

    # Buat file Excel di dalam memori (tanpa harus menyimpannya di harddisk server)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Penjualan')
    
    output.seek(0) # Kembalikan kursor file ke awal

    # Kirim file ke browser agar langsung terunduh
    nama_file = f'Laporan_Keuangan_{current_month}_{current_year}.xlsx'
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nama_file
    )