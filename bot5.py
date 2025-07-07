# Pastikan Anda telah menginstal pustaka ini:
# pip install python-telegram-bot==20.x httpx

import logging
import httpx
import json
import time
from datetime import datetime, timedelta

from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging untuk melihat log dari bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Tetapkan level logging yang lebih rendah untuk pustaka httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Konfigurasi Bot Telegram ---
# Ganti dengan token bot Telegram Anda. Anda bisa mendapatkannya dari BotFather di Telegram.
TELEGRAM_BOT_TOKEN = "7792437914:AAHPH5y5BtlPSb5WsWs11JB7TS3PCyeAl2U"

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
        self.client = httpx.AsyncClient(base_url=base_url)
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
            headers["Content-Type"] = "application/json"

            response = await self.client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
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
            raw_response_text = response.text if response else "Tidak ada respons yang diterima."
            logger.error(f"Gagal mengurai respons JSON dari {path}. Respons mentah: '{raw_response_text}'")
            raise Exception("Respons tidak valid dari panel 3x-ui.")
        except Exception as e:
            logger.error(f"Kesalahan tak terduga saat melakukan permintaan ke {path}: {e}")
            raise Exception(f"Kesalahan tak terduga: {e}")

    async def login(self):
        """Melakukan login ke panel 3x-ui dan menyimpan cookie sesi."""
        logger.info("Mencoba login ke panel 3x-ui...")
        try:
            parsed_base_url = httpx.URL(self.base_url)
            login_url = f"{parsed_base_url.scheme}://{parsed_base_url.host}"
            if parsed_base_url.port:
                login_url += f":{parsed_base_url.port}"
            login_url += parsed_base_url.path

            response = await self.client.post(
                f"{login_url}/login",
                json={"username": self.username, "password": self.password},
                follow_redirects=False
            )
            response.raise_for_status()

            session_cookie_value = response.cookies.get("3x-ui")
            if session_cookie_value:
                self.session_cookie = f"3x-ui={session_cookie_value}"
                self.is_authenticated = True
                logger.info("Berhasil login ke 3x-ui.")
            else:
                logger.error(f"Gagal mendapatkan cookie sesi '3x-ui' setelah login. Respons: {response.text}")
                raise Exception("Gagal mendapatkan cookie sesi setelah login. Periksa kredensial.")
        except httpx.HTTPStatusError as e:
            logger.error(f"Login gagal dengan status HTTP {e.response.status_code}. Respons: {e.response.text}")
            raise Exception(f"Gagal login ke 3x-ui. Periksa URL dan kredensial Anda. Status: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Gagal login ke 3x-ui: {e}")
            raise Exception(f"Gagal login ke 3x-ui. Periksa URL dan kredensial Anda. Detail: {e}")

    async def fetch_all_inbounds(self):
        """Mendapatkan daftar semua inbounds dan menyimpannya di cache."""
        logger.info("Mendapatkan daftar semua inbounds...")
        data = await self._request("POST", "/panel/inbound/list")
        if data and data.get("success"):
            self.all_inbounds_cache = data.get("obj", [])
            return self.all_inbounds_cache
        raise Exception(f"Gagal mendapatkan daftar inbounds. Pesan dari panel: {data.get('msg', 'Tidak ada pesan')}")

    async def get_inbound_by_id(self, inbound_id: int):
        """Mendapatkan detail inbound berdasarkan ID dari cache."""
        if not self.all_inbounds_cache:
            await self.fetch_all_inbounds()
        
        for inbound in self.all_inbounds_cache:
            if inbound.get("id") == inbound_id:
                return inbound
        return None

    async def get_clients_for_inbound(self, inbound_id: int):
        """
        Mendapatkan daftar klien untuk inbound tertentu.
        Data klien sekarang diambil dari 'clientStats' di dalam respons 'inbound/list'.
        """
        logger.info(f"Mendapatkan klien untuk inbound ID: {inbound_id} dari cache...")
        inbound = await self.get_inbound_by_id(inbound_id)
        if inbound:
            return inbound.get("clientStats", [])
        return []

    async def add_client(self, inbound_id: int, settings: dict, total_gb: int, expire_days: int, enable: bool = True):
        """Menambahkan klien baru ke inbound."""
        logger.info(f"Menambahkan klien baru ke inbound ID: {inbound_id}...")
        total_bytes = total_gb * 1024 * 1024 * 1024 if total_gb else 0
        expire_time_ms = 0
        if expire_days > 0:
            expire_time_ms = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)

        payload = {
            "inboundId": inbound_id,
            "settings": json.dumps({"clients": [settings]}),
            "totalGB": total_bytes,
            "expireTime": expire_time_ms,
            "enable": enable,
            "tgId": "",
            "subId": ""
        }
        data = await self._request("POST", "/panel/inbound/addClient", json=payload)
        if data and data.get("success"):
            await self.fetch_all_inbounds()
            return True
        # Menangkap pesan error spesifik dari panel
        error_msg = data.get('msg', 'Unknown error') if data else 'Unknown error'
        raise Exception(f"Gagal menambahkan klien: {error_msg}") # <--- Diperbarui

    async def delete_client(self, inbound_id: int, client_idx: int):
        """Menghapus klien dari inbound."""
        logger.info(f"Menghapus klien di inbound ID: {inbound_id}, index: {client_idx}...")
        payload = {
            "inboundId": inbound_id,
            "clientIdx": client_idx
        }
        data = await self._request("POST", "/panel/inbound/delClient", json=payload)
        if data and data.get("success"):
            await self.fetch_all_inbounds()
            return True
        raise Exception(f"Gagal menghapus klien: {data.get('msg', 'Unknown error')}")

    async def update_client(self, inbound_id: int, client_idx: int, settings: dict, total_gb: int, expire_days: int, enable: bool):
        """Memperbarui klien di inbound."""
        logger.info(f"Memperbarui klien di inbound ID: {inbound_id}, index: {client_idx}...")
        total_bytes = total_gb * 1024 * 1024 * 1024 if total_gb else 0
        expire_time_ms = 0
        if expire_days > 0:
            expire_time_ms = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)

        updated_client_settings = {
            **settings,
            "totalGB": total_bytes,
            "expiryTime": expire_time_ms,
            "enable": enable,
        }

        payload = {
            "inboundId": inbound_id,
            "clientIdx": client_idx,
            "settings": json.dumps({"clients": [updated_client_settings]}),
        }
        data = await self._request("POST", "/panel/inbound/updateClient", json=payload)
        if data and data.get("success"):
            await self.fetch_all_inbounds()
            return True
        raise Exception(f"Gagal memperbarui klien: {data.get('msg', 'Unknown error')}")


# Inisialisasi API 3x-ui
three_xui_api = ThreeXUIApi(THREE_XUI_PANEL_URL, THREE_XUI_USERNAME, THREE_XUI_PASSWORD)

# --- Handler Perintah Bot Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan saat perintah /start dikeluarkan."""
    user = update.effective_user
    await update.message.reply_html(
        f"Halo {user.mention_html()}! 👋\n"
        "Saya adalah bot manajemen 3x-ui Anda.\n"
        "Gunakan perintah berikut:\n"
        "/list_inbounds - Untuk melihat semua ID inbound yang tersedia\n"
        "/list_users [inbound_id] - Untuk melihat daftar pengguna di inbound tertentu (default: inbound pertama)\n"
        "/info &lt;uuid&gt; - Untuk mendapatkan info pengguna dari inbound default\n"
        "/buat_user &lt;remark&gt; &lt;limit_gb&gt; &lt;expire_days&gt; - Untuk membuat pengguna baru di inbound default\n"
        "   &lt;limit_gb&gt;: Batas data dalam GB (gunakan 0 untuk tidak terbatas)\n"
        "   CATATAN: Remark/email harus unik di setiap inbound.\n" # <--- Diperbarui
        "/hapus_user &lt;uuid&gt; - Untuk menghapus pengguna dari inbound default\n"
        "/help - Untuk melihat daftar perintah",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan saat perintah /help dikeluarkan."""
    await update.message.reply_text(
        "Berikut adalah perintah yang bisa Anda gunakan:\n"
        "• /list_inbounds - Menampilkan daftar semua inbound yang tersedia beserta ID dan keterangannya.\n"
        "• /list_users [inbound_id] - Menampilkan daftar semua pengguna di inbound tertentu.\n"
        "   Jika <inbound_id> tidak diberikan, akan menampilkan dari inbound default.\n"
        "• /info <uuid> - Dapatkan informasi tentang pengguna 3x-ui tertentu (gunakan UUID klien) dari inbound default.\n"
        "• /buat_user <remark> <limit_gb> <expire_days> - Buat pengguna baru di inbound default. \n"
        "   <remark>: Nama/keterangan pengguna\n"
        "   <limit_gb>: Batas data dalam GB (gunakan 0 untuk tidak terbatas)\n"
        "   <expire_days>: Jumlah hari kedaluwarsa (gunakan 0 untuk tidak kedaluwarsa)\n"
        "   CATATAN: Remark/email harus unik di setiap inbound.\n" # <--- Diperbarui
        "• /hapus_user <uuid> - Hapus pengguna berdasarkan UUID mereka dari inbound default.\n"
        "• /help - Menampilkan daftar perintah ini"
    )

async def list_inbounds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mendaftar semua inbounds yang tersedia."""
    await update.message.reply_text("Mendapatkan daftar semua inbounds...")
    try:
        inbounds = await three_xui_api.fetch_all_inbounds()
        if not inbounds:
            await update.message.reply_text("Tidak ada inbound yang ditemukan di panel 3x-ui.")
            return

        message_parts = ["Daftar Inbound yang Tersedia:\n"]
        for inbound in inbounds:
            message_parts.append(
                f"----------------------------------------\n"
                f"ID: {inbound.get('id', 'N/A')}\n"
                f"Remark: {inbound.get('remark', 'N/A')}\n"
                f"Protokol: {inbound.get('protocol', 'N/A')}\n"
                f"Port: {inbound.get('port', 'N/A')}\n"
            )
        await update.message.reply_text("".join(message_parts))
    except Exception as e:
        logger.error(f"Gagal mendapatkan daftar inbounds: {e}")
        await update.message.reply_text(f"Terjadi kesalahan saat mencoba mendapatkan daftar inbounds: {e}")

async def get_default_inbound_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Mendapatkan atau mengatur ID inbound default."""
    if not three_xui_api.all_inbounds_cache:
        try:
            await three_xui_api.fetch_all_inbounds()
        except Exception as e:
            await update.message.reply_text(f"Gagal mengambil daftar inbounds dari panel 3x-ui: {e}")
            return None

    if not three_xui_api.all_inbounds_cache:
        await update.message.reply_text("Tidak ada inbound yang ditemukan di panel 3x-ui. Tidak dapat melanjutkan.")
        return None
    
    default_inbound_id = three_xui_api.all_inbounds_cache[0]["id"]
    logger.info(f"Menggunakan inbound default ID: {default_inbound_id}")
    return default_inbound_id

async def get_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mendapatkan info pengguna dari 3x-ui berdasarkan UUID."""
    if not context.args:
        await update.message.reply_text("Penggunaan: /info <uuid_pengguna>")
        return

    user_uuid_to_check = context.args[0]
    await update.message.reply_text(f"Mencari info untuk pengguna dengan UUID '{user_uuid_to_check}'...")

    inbound_id = await get_default_inbound_id(update, context)
    if not inbound_id:
        return

    try:
        clients = await three_xui_api.get_clients_for_inbound(inbound_id)
        found_client = None
        for client in clients:
            if client.get("id") == user_uuid_to_check:
                found_client = client
                break

        if not found_client:
            await update.message.reply_text(f"Pengguna dengan UUID '{user_uuid_to_check}' tidak ditemukan di inbound ID {inbound_id}.")
            return

        total_gb = found_client.get("totalGB", 0) / (1024 * 1024 * 1024) if found_client.get("totalGB") else 0
        up_gb = found_client.get("up", 0) / (1024 * 1024 * 1024) if found_client.get("up") else 0
        down_gb = found_client.get("down", 0) / (1024 * 1024 * 1024) if found_client.get("down") else 0
        remaining_gb = total_gb - (up_gb + down_gb) if total_gb > 0 else "Tidak Terbatas"

        expire_time_ms = found_client.get("expiryTime", 0)
        expire_date = "Tidak Kedaluwarsa"
        if expire_time_ms > 0:
            expire_date = datetime.fromtimestamp(expire_time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

        message = (
            f"Informasi Pengguna (UUID: {found_client.get('id', 'N/A')}):\n"
            f"Keterangan: {found_client.get('email', 'N/A')} (Email sering digunakan sebagai Remark)\n"
            f"Status: {'Aktif' if found_client.get('enable', False) else 'Nonaktif'}\n"
            f"Batas Data: {f'{total_gb:.2f} GB' if total_gb > 0 else 'Tidak Terbatas'}\n"
            f"Penggunaan Upload: {up_gb:.2f} GB\n"
            f"Penggunaan Download: {down_gb:.2f} GB\n"
            f"Sisa Data: {f'{remaining_gb:.2f} GB' if isinstance(remaining_gb, float) else remaining_gb}\n"
            f"Tanggal Kedaluwarsa: {expire_date}\n"
            f"Inbound ID: {inbound_id}"
        )
        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Gagal mendapatkan info pengguna dari 3x-ui: {e}")
        await update.message.reply_text(f"Terjadi kesalahan saat mencoba mendapatkan info pengguna: {e}")

async def create_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Membuat pengguna baru di 3x-ui."""
    if len(context.args) != 3:
        await update.message.reply_text("Penggunaan: /buat_user <remark> <limit_gb> <expire_days>\n"
                                        "Contoh: /buat_user user_baru 10 30 (untuk 10GB, 30 hari)\n"
                                        "Gunakan 0 untuk <limit_gb> atau <expire_days> untuk tidak terbatas.\n"
                                        "CATATAN: Remark/email harus unik di setiap inbound.") # <--- Diperbarui
        return

    remark = context.args[0]
    try:
        limit_gb = int(context.args[1])
        if limit_gb < 0:
            raise ValueError("Limit GB tidak boleh negatif.")
    except ValueError:
        await update.message.reply_text("Limit GB harus berupa angka bulat non-negatif.")
        return

    try:
        expire_days = int(context.args[2])
        if expire_days < 0:
            raise ValueError("Jumlah hari kedaluwarsa tidak boleh negatif.")
    except ValueError:
        await update.message.reply_text("Jumlah hari kedaluwarsa harus berupa angka bulat non-negatif.")
        return

    inbound_id = await get_default_inbound_id(update, context)
    if not inbound_id:
        return

    await update.message.reply_text(f"Mencoba membuat pengguna '{remark}' dengan limit {limit_gb}GB dan {expire_days} hari di inbound ID {inbound_id}...")

    try:
        import uuid
        new_uuid = str(uuid.uuid4())
        
        client_settings = {
            "id": new_uuid,
            "flow": "",
            "email": remark,
            "alterId": 0,
            "limitIp": 0,
            "totalGB": 0,
            "expiryTime": 0,
            "enable": True,
            "tgId": "",
            "subId": ""
        }

        success = await three_xui_api.add_client(inbound_id, client_settings, limit_gb, expire_days, enable=True)
        if success:
            await update.message.reply_text(f"Pengguna '{remark}' (UUID: {new_uuid}) berhasil dibuat di 3x-ui pada inbound ID {inbound_id}.")
        else:
            await update.message.reply_text(f"Gagal membuat pengguna '{remark}' di 3x-ui.")
    except Exception as e:
        logger.error(f"Gagal membuat pengguna di 3x-ui: {e}")
        await update.message.reply_text(f"Terjadi kesalahan saat mencoba membuat pengguna: {e}")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus pengguna dari 3x-ui berdasarkan UUID."""
    if not context.args:
        await update.message.reply_text("Penggunaan: /hapus_user <uuid_pengguna>")
        return

    user_uuid_to_delete = context.args[0]
    await update.message.reply_text(f"Mencoba menghapus pengguna dengan UUID '{user_uuid_to_delete}'...")

    inbound_id = await get_default_inbound_id(update, context)
    if not inbound_id:
        return

    try:
        inbound = await three_xui_api.get_inbound_by_id(inbound_id)
        if not inbound:
            await update.message.reply_text(f"Inbound ID {inbound_id} tidak ditemukan.")
            return

        clients_in_inbound = inbound.get("clientStats", [])
        client_idx_to_delete = -1
        for idx, client in enumerate(clients_in_inbound):
            if client.get("id") == user_uuid_to_delete:
                client_idx_to_delete = idx
                break

        if client_idx_to_delete == -1:
            await update.message.reply_text(f"Pengguna dengan UUID '{user_uuid_to_delete}' tidak ditemukan di inbound ID {inbound_id}.")
            return

        success = await three_xui_api.delete_client(inbound_id, client_idx_to_delete)
        if success:
            await update.message.reply_text(f"Pengguna dengan UUID '{user_uuid_to_delete}' berhasil dihapus dari inbound ID {inbound_id}.")
        else:
            await update.message.reply_text(f"Gagal menghapus pengguna dengan UUID '{user_uuid_to_delete}'.")
    except Exception as e:
        logger.error(f"Gagal menghapus pengguna dari 3x-ui: {e}")
        await update.message.reply_text(f"Terjadi kesalahan saat mencoba menghapus pengguna: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mendaftar semua pengguna di inbound yang ditentukan atau default."""
    target_inbound_id = None
    if context.args:
        try:
            target_inbound_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID inbound harus berupa angka. Penggunaan: /list_users [inbound_id]")
            return

    if not target_inbound_id:
        target_inbound_id = await get_default_inbound_id(update, context)
        if not target_inbound_id:
            return

    await update.message.reply_text(f"Mendapatkan daftar pengguna untuk inbound ID {target_inbound_id}...")

    try:
        clients = await three_xui_api.get_clients_for_inbound(target_inbound_id)
        if not clients:
            await update.message.reply_text(f"Tidak ada pengguna yang ditemukan di inbound ID {target_inbound_id}.")
            return

        message_parts = [f"Daftar Pengguna di Inbound ID {target_inbound_id}:\n"]
        for client in clients:
            total_gb = client.get("totalGB", 0) / (1024 * 1024 * 1024) if client.get("totalGB") else 0
            up_gb = client.get("up", 0) / (1024 * 1024 * 1024) if client.get("up") else 0
            down_gb = client.get("down", 0) / (1024 * 1024 * 1024) if client.get("down") else 0
            remaining_gb = total_gb - (up_gb + down_gb) if total_gb > 0 else "Tidak Terbatas"

            expire_time_ms = client.get("expiryTime", 0)
            expire_date = "Tidak Kedaluwarsa"
            if expire_time_ms > 0:
                expire_date = datetime.fromtimestamp(expire_time_ms / 1000).strftime('%Y-%m-%d')

            message_parts.append(
                f"----------------------------------------\n"
                f"Remark: {client.get('email', 'N/A')} (Email sering digunakan sebagai Remark)\n"
                f"UUID: {client.get('id', 'N/A')}\n"
                f"Status: {'Aktif' if client.get('enable', False) else 'Nonaktif'}\n"
                f"Batas Data: {f'{total_gb:.2f} GB' if total_gb > 0 else 'Tidak Terbatas'}\n"
                f"Penggunaan Upload: {up_gb:.2f} GB\n"
                f"Penggunaan Download: {down_gb:.2f} GB\n"
                f"Sisa Data: {f'{remaining_gb:.2f} GB' if isinstance(remaining_gb, float) else remaining_gb}\n"
                f"Kedaluwarsa: {expire_date}\n"
            )
        await update.message.reply_text("".join(message_parts))

    except Exception as e:
        logger.error(f"Gagal mendapatkan daftar pengguna dari 3x-ui: {e}")
        await update.message.reply_text(f"Terjadi kesalahan saat mencoba mendapatkan daftar pengguna: {e}")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menggemakan pesan teks yang diterima."""
    await update.message.reply_text(update.message.text)

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

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

