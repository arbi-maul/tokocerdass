# Aplikasi Kasir (Point of Sale) - Arbi Collection

Ini adalah aplikasi kasir berbasis web yang dibuat menggunakan Python dan framework Flask. Aplikasi ini dirancang untuk membantu manajemen penjualan di toko Arbi Collection.

## Fitur Utama

* **Manajemen Produk:** Menambah, melihat, mengedit, dan menghapus produk.
* **Sistem Kasir:** Menambahkan barang ke keranjang dengan pilihan harga Eceran/Grosir.
* **Fitur Diskon & Pembayaran:** Memasukkan potongan harga dan menghitung uang kembali.
* **Manajemen Keuangan:** Laporan keuntungan harian, bulanan, dan total.
* **Analisis Produk:** Diagram visual untuk produk terlaris mingguan dan tahunan.
* **Notifikasi Telegram:** Struk penjualan otomatis terkirim ke Telegram.
* **Sistem Login:** Halaman manajemen dilindungi oleh username dan password.
* **Export ke Excel:** Mengekspor data riwayat transaksi ke dalam file Excel.

## Teknologi yang Digunakan

* **Backend:** Python, Flask, Flask-SQLAlchemy
* **Frontend:** HTML, Bootstrap 5, Javascript
* **Database:** Bisa menggunakan SQLite (default) atau MySQL.
* **Grafik/Diagram:** Matplotlib
* **Export Excel:** Pandas

## Cara Menjalankan Aplikasi

1.  **Clone repository ini.**
2.  **Buat virtual environment:** `python -m venv venv`
3.  **Aktifkan virtual environment.**
4.  **Install semua library yang dibutuhkan:** `pip install -r requirements.txt` (Anda perlu membuat file `requirements.txt` terlebih dahulu).
5.  **Inisialisasi database:** `python -m flask init-db`
6.  **Jalankan aplikasi:** `python -m flask run --host=0.0.0.0`
