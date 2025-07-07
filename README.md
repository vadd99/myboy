# 🤖 Bot Telegram untuk Manajemen 3x-ui

Bot Telegram sederhana berbasis Python yang dirancang untuk membantu admin mengelola pengguna (klien) pada **panel 3x-ui** langsung dari percakapan Telegram. Dengan bot ini, Anda dapat menambahkan, menghapus, dan memantau pengguna dengan lebih cepat, efisien, dan **mobile-friendly** — tanpa perlu login ke dashboard web.

---

## ✨ Fitur Utama

- 🔐 **Manajemen Sesi Otomatis**  
  Bot secara otomatis login ke panel 3x-ui dan mempertahankan sesi aktif selama dibutuhkan.

- 📥 **Daftar Inbound**  
  Lihat semua *inbound* yang tersedia di panel Anda hanya dengan satu perintah.

- 👥 **Daftar Pengguna**  
  Tampilkan seluruh pengguna dalam sebuah *inbound* beserta kuota, masa aktif, dan ID statistik.

- 🧾 **Informasi Detail Pengguna**  
  Dapatkan UUID, data pemakaian (upload/download), serta informasi teknis lainnya dari pengguna tertentu.

- ➕ **Buat Pengguna Baru**  
  Tambahkan pengguna langsung dari Telegram dengan menentukan remark, kuota (dalam GB), dan masa aktif (hari).

- ❌ **Hapus Pengguna**  
  Hapus pengguna dari panel secara permanen berdasarkan ID Statistik mereka.

---

## ⚙️ Instalasi & Konfigurasi

Ikuti langkah-langkah berikut untuk men-deploy bot Anda sendiri.

### 1. Prasyarat

- Python **versi 3.8+**
- Akun Telegram + Bot dari [@BotFather](https://t.me/BotFather)
- Panel 3x-ui aktif (beserta URL, username, dan password)

### 2. Kloning Repositori

```bash
git clone https://github.com/vadd99/myboy.git
cd myboy
```

### 3. Instalasi Dependensi

```bash
pip install python-telegram-bot==20.* httpx
```

### 4. Konfigurasi Bot

Edit file utama bot `vadd.py' dengan nano : 
```bash
nano vadd.py
```
dan sesuaikan bagian berikut:

```python
# --- Konfigurasi Bot Telegram ---
TELEGRAM_BOT_TOKEN = "ISI_DENGAN_TOKEN_BOT_ANDA"

# --- Konfigurasi 3x-ui Panel ---
THREE_XUI_PANEL_URL = "https://domain-panel-anda.com:12345/path-rahasia"
THREE_XUI_USERNAME = "USERNAME_PANEL_ANDA"
THREE_XUI_PASSWORD = "PASSWORD_PANEL_ANDA"
```

---

## 🚀 Menjalankan Bot

Setelah konfigurasi selesai, jalankan bot Anda dengan:

```bash
python nama_bot.py
```

Jika berhasil, bot akan aktif dan dapat digunakan langsung melalui Telegram.

---

## 💡 Daftar Perintah

| Perintah | Deskripsi |
|----------|-----------|
| `/start` | Memulai interaksi dengan bot |
| `/help` | Menampilkan semua perintah yang tersedia |
| `/list_inbounds` | Menampilkan semua inbound yang terdaftar |
| `/list_users [id_inbound]` | Menampilkan semua pengguna dari sebuah inbound |
| `/info <id_statistik>` | Menampilkan detail pengguna |
| `/buat_user <remark> <gb> <hari> [id_inbound]` | Membuat pengguna baru |
| `/hapus_user <id_statistik>` | Menghapus pengguna berdasarkan ID statistik |

> 💬 Contoh:  
> `/buat_user usertrial 10 30`  
> `/hapus_user 7d9e4e7e-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

---

## 📄 Lisensi

Proyek ini menggunakan [Lisensi MIT](LICENSE).  
Silakan digunakan, dimodifikasi, dan dibagikan untuk kebutuhan Anda sendiri.

---

> Dibuat dengan ❤️ oleh [Nama Anda]  
> Bot ini bukan bagian resmi dari 3x-ui — digunakan untuk keperluan pribadi dan edukasi.
