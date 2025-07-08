# Pastikan Anda telah menginstal pustaka ini:
# pip install python-telegram-bot==20.x httpx

import logging
import httpx
import json
import uuid
import base64
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# --- Konfigurasi Awal ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Konfigurasi Bot, Panel, dan Server ---
TELEGRAM_BOT_TOKEN = "7737335907:AAEmlzn_59CU9-YoXOVuxwJcB-Mug8cUGa4"
THREE_XUI_PANEL_URL = "https://sg1.vadd.my.id:99/OYrg3Smyrg"
THREE_XUI_USERNAME = "vadd99"
THREE_XUI_PASSWORD = "bismillah33"
SERVER_ADDRESS = "sg1.vadd.my.id"

# --- Konfigurasi Inbound ---
INBOUND_MAPPING = {"VMess TLS": 7, "VMess Non-TLS": 8}

# --- State untuk ConversationHandler ---
(SELECT_TYPE_CREATE, GET_DETAILS_CREATE, GET_ID_DELETE) = range(3)

# ===== Sistem Multi-Bahasa =====
LANG_STRINGS = {
    "en": {
        "welcome": "Welcome boss {user_mention}!\n\nPlease select a menu below:",
        "main_menu_text": "Main Menu:",
        "btn_account": "👤 Account", "btn_create": "➕ Create Account", "btn_lang": "🌐 Language",
        "select_account_type": "Select account type to view:",
        "loading_list": "⏳ Getting user list for <b>{name}</b>...",
        "no_users": "No users found in <b>{name}</b>.",
        "user_list_header": "<b>👥 User List - {name}</b>",
        "remark": "<b>Remark:</b>", "stat_id": "<b>Statistic ID:</b>", "uuid": "<b>Original UUID:</b>", "expired": "<b>Expired:</b>",
        "unlimited": "Unlimited", "choose_other_menu": "Choose another menu.",
        "delete_account_btn": "Delete Account 🗑️", "back_btn": "« Back",
        "create_choose_type": "Choose account type to create:",
        "create_details_prompt": "<b>{name}</b> selected.\nSend details: <code>&lt;name&gt; &lt;quota_gb&gt; &lt;days&gt;</code>",
        "creating_account": "⏳ Creating account <b>{remark}</b>...",
        "create_success_header": "✅ Account Created Successfully!",
        "create_failed": "❌ Failed: {e}\nFormat: `<name> <quota> <days>`",
        "delete_prompt": "Enter the Statistic ID of the account to delete:",
        "deleting_account": "⏳ Deleting ID <code>{user_id}</code>...",
        "delete_success": "✅ Account ID <code>{user_id}</code> has been deleted.",
        "delete_failed": "❌ Failed to delete: {e}",
        "action_cancelled": "Action cancelled.",
        "copy_tip": "TIP: Press the code above to copy it."
    },
    "id": {
        "welcome": "Selamat datang bos ku {user_mention}!\n\nSilahkan pilih menu di bawah ini:",
        "main_menu_text": "Menu Utama:",
        "btn_account": "👤 Akun", "btn_create": "➕ Buat Akun", "btn_lang": "🌐 Bahasa",
        "select_account_type": "Pilih jenis akun untuk dilihat:",
        "loading_list": "⏳ Mendapatkan daftar untuk <b>{name}</b>...",
        "no_users": "Tidak ada pengguna di <b>{name}</b>.",
        "user_list_header": "<b>👥 Daftar Pengguna - {name}</b>",
        "remark": "<b>Remark:</b>", "stat_id": "<b>ID Statistik:</b>", "uuid": "<b>UUID Asli:</b>", "expired": "<b>Expired:</b>",
        "unlimited": "Tak Terbatas", "choose_other_menu": "Pilih menu lain.",
        "delete_account_btn": "Hapus Akun 🗑️", "back_btn": "« Kembali",
        "create_choose_type": "Pilih tipe akun yang akan dibuat:",
        "create_details_prompt": "<b>{name}</b> dipilih.\nKirim detail: <code>&lt;nama&gt; &lt;kuota_gb&gt; &lt;hari&gt;</code>",
        "creating_account": "⏳ Membuat akun <b>{remark}</b>...",
        "create_success_header": "✅ Akun Berhasil Dibuat!",
        "create_failed": "❌ Gagal: {e}\nFormat: `<nama> <kuota> <hari>`",
        "delete_prompt": "Ketik id statistik akun yg ingin di hapus :",
        "deleting_account": "⏳ Menghapus ID <code>{user_id}</code>...",
        "delete_success": "✅ Akun ID <code>{user_id}</code> berhasil dihapus.",
        "delete_failed": "❌ Gagal menghapus: {e}",
        "action_cancelled": "Aksi dibatalkan.",
        "copy_tip": "TIPS: Tekan pada kode URI untuk menyalinnya."
    },
    "ru": {"welcome": "Добро пожаловать, босс {user_mention}!", "btn_lang": "🌐 Язык",},
    "ar": {"welcome": "أهلاً بك يا رئيس {user_mention}!", "btn_lang": "🌐 اللغة",},
    "zh": {"welcome": "欢迎老板 {user_mention}!", "btn_lang": "🌐 语言",},
}

def get_text(key: str, lang: str) -> str:
    # Default ke English jika terjemahan tidak ditemukan
    return LANG_STRINGS.get(lang, LANG_STRINGS["en"]).get(key, LANG_STRINGS["en"].get(key, f"_{key}_"))

# --- Kelas API (Tidak Berubah) ---
class ThreeXUIApi:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url, self.username, self.password = base_url, username, password
        self.client = httpx.AsyncClient(base_url=self.base_url, verify=False, timeout=30.0)
        self.is_authenticated, self.session_cookie, self.all_inbounds_cache = False, None, []
    async def _request(self, method: str, path: str, **kwargs):
        if path != "/login" and not self.is_authenticated: await self.login()
        headers = kwargs.pop("headers", {})
        if self.session_cookie: headers["Cookie"] = self.session_cookie
        headers.setdefault("Accept", "application/json")
        try:
            r = await self.client.request(method, path, headers=headers, **kwargs); r.raise_for_status()
            return r.json() if r.text else {"success": True}
        except json.JSONDecodeError: return {"success": True}
        except Exception as e: logger.error(f"Kesalahan API: {e}"); raise
    async def login(self):
        logger.info("Mencoba login...")
        try:
            response = await self.client.post("/login", data={"username": self.username, "password": self.password}); response.raise_for_status()
            cookie_val = response.cookies.get("session") or response.cookies.get("3x-ui")
            if not cookie_val: raise Exception("Cookie sesi tidak ditemukan.")
            self.session_cookie = f"{'session' if 'session' in response.cookies else '3x-ui'}={cookie_val}"
            self.is_authenticated = True; logger.info("Login berhasil.")
        except Exception as e: logger.error(f"Login gagal: {e}"); raise
    async def fetch_all_inbounds(self):
        data=await self._request("POST","/panel/inbound/list"); self.all_inbounds_cache=data.get("obj",[]) if data.get("success") else []; return self.all_inbounds_cache
    async def get_inbound_by_id(self, inbound_id: int):
        if not self.all_inbounds_cache: await self.fetch_all_inbounds()
        return next((ib for ib in self.all_inbounds_cache if ib.get("id") == inbound_id), None)
    async def add_client(self, inbound_id: int, remark: str, total_gb: int, expire_days: int):
        new={"id":str(uuid.uuid4()),"email":remark,"enable":True,"totalGB":total_gb*1024**3 if total_gb>0 else 0,"expiryTime":int((datetime.now()+timedelta(days=expire_days)).timestamp()*1000) if expire_days>0 else 0}
        data=await self._request("POST","/panel/inbound/addClient",data={"id":inbound_id,"settings":json.dumps({"clients":[new]})}); await self.fetch_all_inbounds()
        return new["id"] if data.get("success") else exec(f"raise Exception('Gagal: {data.get('msg','error')}')")
    async def delete_client(self, client_stat_id: str):
        if not self.all_inbounds_cache: await self.fetch_all_inbounds()
        inbound_id=next((ib["id"] for ib in self.all_inbounds_cache for cs in ib.get("clientStats",[]) if str(cs.get("id"))==client_stat_id),None)
        if not inbound_id: raise Exception(f"ID {client_stat_id} tidak ditemukan.")
        inbound=await self.get_inbound_by_id(inbound_id); email=next((cs["email"] for cs in inbound["clientStats"] if str(cs["id"])==client_stat_id),None)
        settings=json.loads(inbound["settings"]); uuid_to_del=next((c["id"] for c in settings["clients"] if c["email"]==email),None)
        if not uuid_to_del: raise Exception(f"UUID untuk '{email}' tidak ditemukan.")
        data=await self._request("POST",f"/panel/inbound/{inbound_id}/delClient/{uuid_to_del}")
        if not data.get("success"): raise Exception(f"Gagal hapus: {data.get('msg','error')}")
        await self.fetch_all_inbounds(); return True

# --- Fungsi UI & Helper ---
def build_main_menu(lang: str): return InlineKeyboardMarkup([[InlineKeyboardButton(get_text("btn_account", lang), callback_data="menu_akun_select")],[InlineKeyboardButton(get_text("btn_create", lang), callback_data="create_start"), InlineKeyboardButton(get_text("btn_lang", lang), callback_data="menu_lang")]])
def build_lang_menu(lang: str): return InlineKeyboardMarkup([[InlineKeyboardButton("Bahasa Indonesia 🇮🇩", callback_data="set_lang_id")],[InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")],[InlineKeyboardButton(get_text("back_btn", lang), callback_data="main_menu")]]) # Contoh 2 bahasa
def build_account_type_menu(lang: str): return InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=f"list_users_{id}") for name,id in INBOUND_MAPPING.items()],[InlineKeyboardButton(get_text("back_btn", lang), callback_data="main_menu")]])
def build_account_management_menu(lang: str): return InlineKeyboardMarkup([[InlineKeyboardButton(get_text("delete_account_btn", lang), callback_data="delete_start")],[InlineKeyboardButton(name, callback_data=f"list_users_{id}") for name,id in INBOUND_MAPPING.items()],[InlineKeyboardButton(get_text("back_btn", lang), callback_data="main_menu")]])
def generate_vmess_link(inbound_data: dict, client_config: dict) -> str:
    ss=json.loads(inbound_data.get("streamSettings","{}")); c={"v":"2","ps":client_config.get("email",""),"add":SERVER_ADDRESS,"port":inbound_data.get("port",""),"id":client_config.get("id",""),"scy":"auto","net":ss.get("network","ws"),"type":"none","tls":ss.get("security","none")}
    if c["net"]=="ws": ws=ss.get("wsSettings",{}); c["path"]=ws.get("path","/")[0] if isinstance(ws.get("path"),list) else ws.get("path","/"); c["host"]=ws.get("headers",{}).get("Host",SERVER_ADDRESS)
    if c["tls"]=="tls": tls=ss.get("tlsSettings",{}); c["host"]=tls.get("serverName",c.get("host",SERVER_ADDRESS)); c["sni"]=tls.get("serverName",c.get("host",SERVER_ADDRESS))
    return"vmess://"+base64.b64encode(json.dumps(c,separators=(',',':')).encode()).decode()

# --- Handlers Utama ---
api = ThreeXUIApi(THREE_XUI_PANEL_URL, THREE_XUI_USERNAME, THREE_XUI_PASSWORD)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_html(get_text("welcome", lang).format(user_mention=update.effective_user.mention_html()), reply_markup=build_main_menu(lang))
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); lang = context.user_data.get('lang', 'en')
    await q.edit_message_text(get_text("main_menu_text", lang), reply_markup=build_main_menu(lang))
async def account_type_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); lang = context.user_data.get('lang', 'en')
    await q.edit_message_text(get_text("select_account_type", lang), reply_markup=build_account_type_menu(lang))
async def list_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); lang=context.user_data.get('lang','en'); id=int(q.data.split("_")[-1]); name=next((n for n,i in INBOUND_MAPPING.items() if i==id),"")
    await q.edit_message_text(get_text("loading_list",lang).format(name=name),parse_mode=ParseMode.HTML)
    try:
        inbound=await api.get_inbound_by_id(id)
        if not inbound or not inbound.get("clientStats"): await q.edit_message_text(get_text("no_users",lang).format(name=name),parse_mode=ParseMode.HTML,reply_markup=build_account_management_menu(lang)); return
        await q.delete_message(); await context.bot.send_message(q.message.chat_id, get_text("user_list_header",lang).format(name=name), parse_mode=ParseMode.HTML)
        s=json.loads(inbound["settings"]); c_map={c["email"]:c for c in s.get("clients",[])}
        for stat in inbound["clientStats"]:
            email=stat.get('email','N/A'); conf=c_map.get(email)
            if not conf: continue
            exp=get_text("unlimited",lang)
            if stat.get('expiryTime',0)>0: exp=datetime.fromtimestamp(stat['expiryTime']/1000).strftime('%Y-%m-%d')
            txt=f"----------------------------------------\n👤 {get_text('remark',lang)} <code>{email}</code>\n🆔 {get_text('stat_id',lang)} <code>{stat.get('id','N/A')}</code>\n🔑 {get_text('uuid',lang)} <code>{conf.get('id','N/A')}</code>\n🗓️ {get_text('expired',lang)} {exp}\n----------------------------------------"
            await context.bot.send_message(q.message.chat_id,txt,parse_mode=ParseMode.HTML)
        await context.bot.send_message(q.message.chat_id,get_text("choose_other_menu",lang),reply_markup=build_account_management_menu(lang))
    except Exception as e: logger.error(f"Gagal list_users: {e}",exc_info=True); await context.bot.send_message(q.message.chat_id,f"Error: {e}",reply_markup=build_account_management_menu(lang))
async def language_menu_handler(update:Update, context:ContextTypes.DEFAULT_TYPE): q=update.callback_query; await q.answer(); lang=context.user_data.get('lang','en'); await q.edit_message_text("Please select language:", reply_markup=build_lang_menu(lang))
async def set_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); lang = q.data.split("_")[-1]
    context.user_data['lang'] = lang
    await q.edit_message_text(get_text("welcome", lang).format(user_mention=update.effective_user.mention_html()), parse_mode=ParseMode.HTML, reply_markup=build_main_menu(lang))

# --- Alur Buat & Hapus Akun ---
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); lang=context.user_data.get('lang','en')
    btns=[[InlineKeyboardButton(n,callback_data=f"c_{i}")for n,i in INBOUND_MAPPING.items()],[InlineKeyboardButton(get_text("back_btn",lang),callback_data="cancel")]]
    await q.edit_message_text(get_text("create_choose_type",lang),reply_markup=InlineKeyboardMarkup(btns)); return SELECT_TYPE_CREATE
async def create_get_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); lang=context.user_data.get('lang','en')
    id=int(q.data.split("_")[-1]); context.user_data["inbound_id"]=id
    name=next((n for n,i in INBOUND_MAPPING.items() if i==id),"")
    await q.edit_message_text(get_text("create_details_prompt",lang).format(name=name),parse_mode=ParseMode.HTML); return GET_DETAILS_CREATE
async def create_process_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang=context.user_data.get('lang','en'); id=context.user_data.get("inbound_id")
    if not id: return ConversationHandler.END
    try:
        remark,gb,hari = update.message.text.split()
        msg=await update.message.reply_text(get_text("creating_account",lang).format(remark=remark),parse_mode=ParseMode.HTML)
        new_uuid=await api.add_client(id,remark,int(gb),int(hari))
        inbound=await api.get_inbound_by_id(id); s=json.loads(inbound["settings"])
        conf=next((c for c in s.get("clients",[])if c.get("id")==new_uuid),None)
        stat=next((s for s in inbound.get("clientStats",[])if s.get("email")==remark),None)
        if not conf or not stat: raise Exception("Gagal mengambil detail akun baru.")
        exp=get_text("unlimited",lang)
        if stat.get('expiryTime',0)>0: exp=datetime.fromtimestamp(stat['expiryTime']/1000).strftime('%Y-%m-%d')
        link=generate_vmess_link(inbound,conf)
        txt=f"<b>{get_text('create_success_header',lang)}</b>\n----------------------------------------\n👤 {get_text('remark',lang)} <code>{remark}</code>\n🆔 {get_text('stat_id',lang)} <code>{stat.get('id','N/A')}</code>\n🔑 {get_text('uuid',lang)} <code>{new_uuid}</code>\n🗓️ {get_text('expired',lang)} {exp}\n----------------------------------------\n🔗 <b>URI:</b>\n<code>{link}</code>"
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"Salin URI 📋",callback_data="copy_action")]])
        await msg.edit_text(txt,parse_mode=ParseMode.HTML,reply_markup=kb)
    except Exception as e: await msg.edit_text(get_text("create_failed",lang).format(e=e),reply_markup=build_main_menu(lang))
    context.user_data.clear(); return ConversationHandler.END
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); lang=context.user_data.get('lang','en')
    await q.edit_message_text(get_text("delete_prompt",lang)); return GET_ID_DELETE
async def delete_process_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang=context.user_data.get('lang','en'); user_id=update.message.text.strip()
    msg=await update.message.reply_text(get_text("deleting_account",lang).format(user_id=user_id),parse_mode=ParseMode.HTML)
    try:
        await api.delete_client(user_id)
        await msg.edit_text(get_text("delete_success",lang).format(user_id=user_id),parse_mode=ParseMode.HTML,reply_markup=build_main_menu(lang))
    except Exception as e: await msg.edit_text(get_text("delete_failed",lang).format(e=e),reply_markup=build_main_menu(lang))
    return ConversationHandler.END
async def copy_instruction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; lang=context.user_data.get('lang','en')
    await q.answer(get_text("copy_tip",lang),show_alert=True)
async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; lang=context.user_data.get('lang','en')
    msg=get_text("action_cancelled",lang)
    if q: await q.answer(); await q.edit_message_text(msg,reply_markup=build_main_menu(lang))
    else: await update.message.reply_text(msg,reply_markup=build_main_menu(lang))
    context.user_data.clear(); return ConversationHandler.END

def main():
    app=Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    c_conv=ConversationHandler(entry_points=[CallbackQueryHandler(create_start,"^create_start$")],states={SELECT_TYPE_CREATE:[CallbackQueryHandler(create_get_details,"^c_")],GET_DETAILS_CREATE:[MessageHandler(filters.TEXT&~filters.COMMAND,create_process_details)]},fallbacks=[CallbackQueryHandler(cancel_flow,"^cancel$")])
    d_conv=ConversationHandler(entry_points=[CallbackQueryHandler(delete_start,"^delete_start$")],states={GET_ID_DELETE:[MessageHandler(filters.TEXT&~filters.COMMAND,delete_process_id)]},fallbacks=[CallbackQueryHandler(cancel_flow,"^cancel$")])
    app.add_handler(CommandHandler("start",start));app.add_handler(c_conv);app.add_handler(d_conv)
    app.add_handler(CallbackQueryHandler(main_menu_handler,"^main_menu$"))
    app.add_handler(CallbackQueryHandler(language_menu_handler,"^menu_lang$"))
    app.add_handler(CallbackQueryHandler(set_language_handler,"^set_lang_"))
    app.add_handler(CallbackQueryHandler(account_type_menu_handler,"^menu_akun_select$"))
    app.add_handler(CallbackQueryHandler(list_users_handler,"^list_users_"))
    app.add_handler(CallbackQueryHandler(account_type_menu_handler,"^back_to_account_management$"))
    app.add_handler(CallbackQueryHandler(copy_instruction_handler,"^copy_action$"))
    app.run_polling()

if __name__=="__main__":
    main()
