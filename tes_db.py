import mysql.connector

# Ganti detail di bawah ini agar SAMA PERSIS dengan yang ada di app.py
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "arbi_pos_db" # Pastikan nama ini benar!

try:
    mydb = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    print("\n>>> SELAMAT! Koneksi ke database MySQL berhasil.")
    print(f">>> Anda terhubung ke database bernama '{DB_NAME}'.")
    mydb.close()
except mysql.connector.Error as err:
    print(f"\n>>> GAGAL! Terjadi error saat mencoba koneksi: {err}")
    print(">>> PERIKSA KEMBALI: Pastikan server XAMPP MySQL sudah berjalan dan detail koneksi (host, user, password, nama db) sudah benar.")