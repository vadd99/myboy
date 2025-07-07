# Pastikan Anda telah menginstal pustaka ini:
# pip install python-telegram-bot==20.x httpx

import logging
import httpx
import json
import uuid
from datetime import datetime, timedelta

from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging untuk melihat log dari bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Tetapkan level logging yang lebih rendah untuk pustaka httpx agar tidak terlalu berisik
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Konfigurasi Bot Telegram ---
# Ganti dengan token bot Anda
TELEGRAM_BOT_TOKEN = "7737335907:AAEmlzn_59CU9-YoXOVuxwJcB-Mug8cUGa4"

# --- Konfigurasi 3x-ui Panel ---
# Ganti dengan URL panel 3x-ui Anda (termasuk port dan base path jika ada)
# Contoh: "https://sg1.vadd.my.id:99/OYrg3Smyrg"
THREE_XUI_PANEL_URL = "https://sg1.vadd.my.id:99/OYrg3Smyrg"
THREE_XUI_USERNAME = "vadd99"
THREE_XUI_PASSWORD = "bismillah33"

class ThreeXUIApi:
    """
    Kelas untuk berinteraksi dengan API panel 3x-ui.
    Mengelola login dan sesi cookie.
    """
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        # Atur batas waktu untuk mencegah bot macet tanpa batas waktu
        self.client = httpx.AsyncClient(base_url=base_url, verify=False, timeout=30.0)
        self.is_authenticated = False
        self.session_cookie = None
        self.all_inbounds_cache = [] # Cache untuk menyimpan semua inbounds

    async def _request(self, method: str, path: str, **kwargs):
        """Wrapper untuk permintaan HTTP, menangani otentikasi."""
        response = None
        try:
            if path != "/login" and not self.is_authenticated:
                await self.login()

            headers = kwargs.pop("headers", {})
            if self.session_cookie:
                headers["Cookie"] = self.session_cookie
            
            headers.setdefault("Accept", "application/json")
            if "json" in kwargs:
                    headers.setdefault("Content-Type", "application/json")

            response = await self.client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            
            if not response.text:
                return {"success": True, "msg": "Aksi berhasil tanpa konten balasan."}
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {path}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:
                self.is_authenticated = False
                raise Exception("Sesi 3x-ui kedaluwarsa atau tidak sah. Coba lagi.")
            raise Exception(f"Kesalahan HTTP: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error for {path}: {e}")
            raise Exception(f"Kesalahan jaringan atau koneksi ke panel 3x-ui: {e}")
        except json.JSONDecodeError:
            raw_response_text = response.text if response else "''"
            logger.error(f"Gagal mengurai respons JSON dari {path}. Respons mentah: '{raw_response_text}'")
            raise Exception("Respons tidak valid dari panel 3x-ui. Periksa URL atau metode API.")
        except Exception as e:
            logger.error(f"Kesalahan tak terduga saat melakukan permintaan ke {path}: {e}")
            raise Exception(f"Kesalahan tak terduga: {e}")

    async def login(self):
        """Melakukan login ke panel 3x-ui dan menyimpan cookie sesi."""
        logger.info("Mencoba login ke panel 3x-ui...")
        try:
            response = await self.client.post("/login", data={"username": self.username, "password": self.password})
            response.raise_for_status()
            session_cookie_value = response.cookies.get("session") or response.cookies.get("3x-ui")
            if session_cookie_value:
                cookie_name = "session" if response.cookies.get("session") else "3x-ui"
                self.session_cookie = f"{cookie_name}={session_cookie_value}"
                self.is_authenticated = True
                logger.info("Berhasil login ke 3x-ui.")
            else:
                raise Exception("Gagal mendapatkan cookie sesi setelah login.")
        except Exception as e:
            logger.error(f"Gagal login ke 3x-ui: {e}")
            raise Exception(f"Gagal login ke 3x-ui. Periksa URL dan kredensial Anda.")

    async def fetch_all_inbounds(self):
        """Mendapatkan daftar semua inbounds dan menyimpannya di cache."""
        logger.info("Mendapatkan daftar semua inbounds...")
        data = await self._request("POST", "/panel/inbound/list")
        if data and data.get("success"):
            self.all_inbounds_cache = data.get("obj", [])
            logger.info(f"Ditemukan {len(self.all_inbounds_cache)} inbound.")
            return self.all_inbounds_cache
        raise Exception(f"Gagal mendapatkan daftar inbounds: {data.get('msg', 'Tidak ada pesan')}")

    async def get_inbound_by_id(self, inbound_id: int):
        """Mendapatkan detail inbound berdasarkan ID dari cache."""
        if not self.all_inbounds_cache:
            await self.fetch_all_inbounds()
        for inbound in self.all_inbounds_cache:
            if inbound.get("id") == inbound_id:
                return inbound
        return None

    async def add_client(self, inbound_id: int, remark: str, total_gb: int, expire_days: int):
        """Menambahkan klien baru ke inbound menggunakan metode update."""
        logger.info(f"Menambahkan klien baru '{remark}' ke inbound ID: {inbound_id}...")
        
        inbound_data = await self.get_inbound_by_id(inbound_id)
        if not inbound_data:
            raise Exception(f"Inbound ID {inbound_id} tidak ditemukan.")
            
        try:
            settings = json.loads(inbound_data.get("settings", "{}"))
            clients = settings.get("clients", [])
            if any(client.get("email") == remark for client in clients):
                raise Exception(f"Gagal: Pengguna dengan remark '{remark}' sudah ada.")
        except json.JSONDecodeError:
            settings = {"clients": []}
            clients = []

        total_bytes = total_gb * 1024 * 1024 * 1024 if total_gb > 0 else 0
        expire_time_ms = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000) if expire_days > 0 else 0
        new_uuid = str(uuid.uuid4())
        
        new_client = {"id": new_uuid, "email": remark, "enable": True, "totalGB": total_bytes, "expiryTime": expire_time_ms, "flow": "", "limitIp": 0, "tgId": "", "subId": ""}
        clients.append(new_client)
        settings["clients"] = clients
        
        payload = {"id": inbound_id, "settings": json.dumps(settings)}
        
        data = await self._request("POST", "/panel/inbound/update", json=payload)

        if data and data.get("success"):
            await self.fetch_all_inbounds()
            return new_uuid
        raise Exception(f"Gagal menambahkan klien: {data.get('msg', 'Unknown error')}")

    # ===== FUNGSI YANG DIPERBAIKI (VERSI FINAL) =====
    async def delete_client(self, inbound_id: int, client_id_from_stats: str):
        """Menghapus klien menggunakan endpoint URL path yang spesifik."""
        logger.info(f"Mencari klien dengan ID Statistik {client_id_from_stats} di inbound {inbound_id}...")

        # Langkah 1 & 2: Dapatkan data inbound dan temukan email klien
        inbound_data = await self.get_inbound_by_id(inbound_id)
        if not inbound_data:
            raise Exception(f"Inbound ID {inbound_id} tidak ditemukan.")

        client_stats = inbound_data.get("clientStats", [])
        target_client_email = None
        for client_stat in client_stats:
            if str(client_stat.get("id")) == client_id_from_stats:
                target_client_email = client_stat.get("email")
                break
        
        if not target_client_email:
            raise Exception(f"Tidak dapat menemukan remark untuk klien dengan ID statistik {client_id_from_stats}.")

        logger.info(f"Ditemukan remark '{target_client_email}'. Mencari UUID klien...")

        # Langkah 3: Temukan UUID klien dari pengaturan (settings)
        try:
            settings = json.loads(inbound_data.get("settings", "{}"))
            config_clients = settings.get("clients", [])
        except json.JSONDecodeError:
            raise Exception(f"Gagal membaca pengaturan klien dari inbound ID {inbound_id}.")

        target_client_uuid = None
        for client in config_clients:
            if client.get("email") == target_client_email:
                target_client_uuid = client.get("id")
                break

        if not target_client_uuid:
            raise Exception(f"Tidak dapat menemukan UUID untuk klien dengan remark '{target_client_email}' di pengaturan inbound.")

        logger.info(f"Ditemukan UUID: {target_client_uuid}. Menghapus klien melalui URL path...")

        # Langkah 4: Bangun path URL dinamis dan panggil endpoint yang benar
        # Sesuai dengan format: /panel/inbound/{inbound_id}/delClient/{client_uuid}
        delete_path = f"/panel/inbound/{inbound_id}/delClient/{target_client_uuid}"
        
        # Menggunakan endpoint baru tanpa JSON payload. Umumnya ini adalah permintaan POST.
        data = await self._request("POST", delete_path)
        
        if data and data.get("success"):
            logger.info(f"Klien '{target_client_email}' berhasil dihapus dari panel.")
            await self.fetch_all_inbounds()  # Perbarui cache
            return True
        
        error_msg = data.get('msg', 'Unknown error from panel')
        raise Exception(f"Gagal menghapus klien: {error_msg}")

# Inisialisasi API 3x-ui
three_xui_api = ThreeXUIApi(THREE_XUI_PANEL_URL, THREE_XUI_USERNAME, THREE_XUI_PASSWORD)

# --- Handler Perintah Bot Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(f"Halo {user.mention_html()}! 👋\n" "Gunakan /help untuk melihat daftar perintah.", reply_markup=ForceReply(selective=True))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Perintah yang tersedia:\n\n"
        "• /list_inbounds\n"
        "  Menampilkan semua inbound.\n\n"
        "• /list_users `[inbound_id]`\n"
        "  Menampilkan pengguna di inbound tertentu.\n\n"
        "• /info `<id_statistik>`\n"
        "  Info detail pengguna berdasarkan ID Statistik.\n\n"
        "• /buat_user `<remark>` `<gb>` `<hari>` `[inbound_id]`\n"
        "  Membuat pengguna baru.\n\n"
        "• /hapus_user `<id_statistik>`\n"
        "  Menghapus pengguna berdasarkan **ID Statistik** yang ditampilkan di /list_users."
    )

async def list_inbounds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Mendapatkan daftar inbounds...")
    try:
        inbounds = await three_xui_api.fetch_all_inbounds()
        if not inbounds:
            await update.message.reply_text("Tidak ada inbound ditemukan.")
            return
        message_parts = ["📌 *Daftar Inbound:*\n"]
        for inbound in inbounds:
            message_parts.append(f"----------------------------------------\n*ID:* `{inbound.get('id', 'N/A')}`\n*Remark:* {inbound.get('remark', 'N/A')}\n*Protokol:* {inbound.get('protocol', 'N/A')}\n*Port:* {inbound.get('port', 'N/A')}\n")
        await update.message.reply_text("".join(message_parts), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Terjadi kesalahan: {e}")

async def get_default_inbound_id(update: Update) -> int | None:
    if not three_xui_api.all_inbounds_cache:
        try:
            await three_xui_api.fetch_all_inbounds()
        except Exception as e:
            await update.message.reply_text(f"Gagal mengambil daftar inbounds: {e}")
            return None
    if not three_xui_api.all_inbounds_cache:
        await update.message.reply_text("Tidak ada inbound ditemukan.")
        return None
    return three_xui_api.all_inbounds_cache[0]["id"]

async def get_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Penggunaan: /info <id_statistik_pengguna>")
        return
    user_id_to_check = context.args[0]
    await update.message.reply_text(f"Mencari info untuk ID `{user_id_to_check}`...", parse_mode='Markdown')
    try:
        await three_xui_api.fetch_all_inbounds()
        found_client, inbound_id_of_client = None, None
        for inbound in three_xui_api.all_inbounds_cache:
            for client in inbound.get("clientStats", []):
                if str(client.get("id")) == user_id_to_check:
                    found_client, inbound_id_of_client = client, inbound.get("id")
                    break
            if found_client: break
        if not found_client:
            await update.message.reply_text(f"Pengguna dengan ID `{user_id_to_check}` tidak ditemukan.", parse_mode='Markdown')
            return
            
        inbound_data = await three_xui_api.get_inbound_by_id(inbound_id_of_client)
        settings = json.loads(inbound_data.get("settings", "{}"))
        config_clients = settings.get("clients", [])
        config_map = {c.get("email"): c for c in config_clients}
        config_client = config_map.get(found_client.get("email"))
        real_uuid = config_client.get("id") or config_client.get("password", "N/A") if config_client else "N/A"

        total_gb = found_client.get("totalGB", 0) / (1024**3)
        up_gb, down_gb = found_client.get("up", 0) / (1024**3), found_client.get("down", 0) / (1024**3)
        remaining_gb = total_gb - (up_gb + down_gb) if total_gb > 0 else float('inf')
        expire_time_ms = found_client.get("expiryTime", 0)
        expire_date = "Tidak Terbatas"
        if expire_time_ms > 0: expire_date = datetime.fromtimestamp(expire_time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        message = (f"👤 *Informasi Pengguna*\n" f"----------------------------------------\n" 
                   f"*Remark:* {found_client.get('email', 'N/A')}\n" 
                   f"*UUID Asli:* `{real_uuid}`\n"
                   f"*ID Statistik:* `{found_client.get('id', 'N/A')}`\n" 
                   f"*Status:* {'✅ Aktif' if found_client.get('enable', False) else '❌ Nonaktif'}\n" 
                   f"*Inbound ID:* `{inbound_id_of_client}`\n\n" 
                   f"📊 *Penggunaan Data*\n" 
                   f"*Batas Data:* {f'{total_gb:.2f} GB' if total_gb > 0 else 'Tidak Terbatas'}\n" 
                   f"*Upload:* {up_gb:.2f} GB\n" 
                   f"*Download:* {down_gb:.2f} GB\n" 
                   f"*Sisa Data:* {f'{remaining_gb:.2f} GB' if total_gb > 0 else 'Tak Terbatas'}\n\n" 
                   f"🗓️ *Masa Aktif*\n" f"*Kedaluwarsa:* {expire_date}\n")
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Terjadi kesalahan: {e}")

async def create_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not 3 <= len(context.args) <= 4:
        await update.message.reply_text("Penggunaan: /buat_user `<remark>` `<gb>` `<hari>` `[inbound_id]`", parse_mode='Markdown')
        return
    remark, inbound_id = context.args[0], None
    try:
        limit_gb, expire_days = int(context.args[1]), int(context.args[2])
        if limit_gb < 0 or expire_days < 0: raise ValueError("Nilai tidak boleh negatif.")
        if len(context.args) == 4: inbound_id = int(context.args[3])
    except (ValueError, IndexError):
        await update.message.reply_text("Input tidak valid, pastikan gb, hari, dan id adalah angka.")
        return
    if not inbound_id:
        inbound_id = await get_default_inbound_id(update)
        if not inbound_id: return
    await update.message.reply_text(f"Mencoba membuat pengguna '{remark}' di inbound ID {inbound_id}...")
    try:
        new_uuid = await three_xui_api.add_client(inbound_id, remark, limit_gb, expire_days)
        await update.message.reply_text(f"✅ Pengguna '{remark}' berhasil dibuat!\nUUID: `{new_uuid}`\nInbound ID: `{inbound_id}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Terjadi kesalahan: {e}")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus pengguna dari 3x-ui berdasarkan ID Statistik."""
    if not context.args:
        await update.message.reply_text("Penggunaan: /hapus_user <id_statistik>")
        return
    
    user_id_to_delete = context.args[0]
    await update.message.reply_text(f"Mencoba menghapus pengguna dengan ID Statistik `{user_id_to_delete}`...", parse_mode='Markdown')
    try:
        await three_xui_api.fetch_all_inbounds()
        inbound_id_of_client = None
        for inbound in three_xui_api.all_inbounds_cache:
            for client in inbound.get("clientStats", []):
                if str(client.get("id")) == user_id_to_delete:
                    inbound_id_of_client = inbound.get("id")
                    break
            if inbound_id_of_client: break
        
        if not inbound_id_of_client:
            await update.message.reply_text(f"Pengguna dengan ID Statistik `{user_id_to_delete}` tidak ditemukan.", parse_mode='Markdown')
            return

        success = await three_xui_api.delete_client(inbound_id_of_client, user_id_to_delete)
        if success:
            await update.message.reply_text(f"✅ Pengguna dengan ID Statistik `{user_id_to_delete}` berhasil dihapus.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Terjadi kesalahan: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target_inbound_id = None
    if context.args:
        try:
            target_inbound_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID inbound harus berupa angka.")
            return
            
    if not target_inbound_id:
        target_inbound_id = await get_default_inbound_id(update)
        if not target_inbound_id: return

    await update.message.reply_text(f"Mendapatkan daftar pengguna untuk inbound ID {target_inbound_id}...")
    try:
        inbound_data = await three_xui_api.get_inbound_by_id(target_inbound_id)
        if not inbound_data:
            await update.message.reply_text(f"Gagal mendapatkan data untuk inbound ID {target_inbound_id}.")
            return

        stats_clients = inbound_data.get("clientStats", [])
        try:
            settings = json.loads(inbound_data.get("settings", "{}"))
            config_clients = settings.get("clients", [])
        except json.JSONDecodeError:
            await update.message.reply_text("Gagal membaca pengaturan klien dari inbound.")
            return

        if not stats_clients:
            await update.message.reply_text(f"Tidak ada pengguna ditemukan di inbound ID {target_inbound_id}.")
            return

        config_map = {client.get("email"): client for client in config_clients}

        message_parts = [f"👥 *Daftar Pengguna di Inbound ID {target_inbound_id}:*\n"]
        
        for stat_client in stats_clients:
            remark = stat_client.get("email", "N/A")
            config_client = config_map.get(remark)

            if config_client:
                display_uuid = config_client.get("id") or config_client.get("password", "N/A")
            else:
                display_uuid = "N/A" 

            stat_id = stat_client.get("id", "N/A")
            total_gb = stat_client.get("totalGB", 0) / (1024**3)
            up_gb, down_gb = stat_client.get("up", 0) / (1024**3), stat_client.get("down", 0) / (1024**3)
            remaining_gb = total_gb - (up_gb + down_gb) if total_gb > 0 else float('inf')
            expire_time_ms = stat_client.get("expiryTime", 0)
            expire_date = "Tak Terbatas"
            if expire_time_ms > 0: expire_date = datetime.fromtimestamp(expire_time_ms / 1000).strftime('%Y-%m-%d')
            
            message_parts.append(
                f"----------------------------------------\n"
                f"*Remark:* {remark}\n"
                f"*UUID Asli:* `{display_uuid}`\n"
                f"*ID Statistik (untuk hapus):* `{stat_id}`\n"
                f"*Status:* {'✅ Aktif' if stat_client.get('enable', False) else '❌ Nonaktif'}\n"
                f"*Sisa Data:* {f'{remaining_gb:.2f} GB' if total_gb > 0 else 'Tak Terbatas'}\n"
                f"*Kedaluwarsa:* {expire_date}\n"
            )
        
        full_message = "".join(message_parts)
        for x in range(0, len(full_message), 4096):
            await update.message.reply_text(full_message[x:x+4096], parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Gagal menampilkan daftar pengguna: {e}")
        await update.message.reply_text(f"Terjadi kesalahan: {e}")


def main() -> None:
    """Memulai bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_inbounds", list_inbounds))
    application.add_handler(CommandHandler("list_users", list_users))
    application.add_handler(CommandHandler("info", get_user_info))
    application.add_handler(CommandHandler("buat_user", create_new_user))
    application.add_handler(CommandHandler("hapus_user", delete_user))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
