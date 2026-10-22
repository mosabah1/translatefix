# -*- coding: utf-8 -*-
"""
translatefix - ترجمة النص اثناء الكتابة بضغطة اختصار.

اكتب جملة، اضغط Ctrl+Alt+T، فتُستبدل بترجمتها. الاتجاه يُكتشف تلقائيا:
العربي يُترجم الى الانجليزية والانجليزي الى العربية.

التشغيل:
    translatefix.exe                  # يعمل بالخلفية مع ايقونة بشريط المهام
    translatefix.exe --check-api      # هل المفتاح يعمل؟ وهل العربية مدعومة؟
    translatefix.exe --tr "كيف حالك"  # ترجمة من سطر الاوامر
    translatefix.exe --autostart [off]
    translatefix.exe --settings
    translatefix.exe --debug
    translatefix.exe --check

محرك الالتقاط (ارسال المفاتيح والحافظة) منقول من layoutfix بعد ان ضُبط هناك
على ثلاثة اخطاء حقيقية - انظر التعليقات في copy_selection و release_modifiers.
https://github.com/mosabah1/layoutfix
"""

import configparser
import ctypes
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg
from ctypes import wintypes

APP_NAME = "translatefix"
VERSION = "1.0.0"

# ---------------------------------------------------------------- الاعدادات --

HOTKEY = "ctrl+alt+t"      # اختصار الترجمة
PROVIDER = "deepl"         # deepl او google
FALLBACK_PROVIDER = "google"   # محرك احتياطي اذا فشل الاساسي (فارغ = معطل)
DEEPL_API_KEY = ""         # مفتاحك من deepl.com/pro-api
LANG_A = "AR"              # اللغة الاولى
LANG_B = "EN-US"           # اللغة الثانية
FORMALITY = "default"      # default / more / less  (DeepL فقط، لبعض اللغات)
TIMEOUT = 12.0             # مهلة الاتصال بالخدمة (ثانية)
FALLBACK_LINE = True       # اذا لم يكن هناك نص محدد، ترجم السطر الحالي
NOTIFY = True              # اظهر رسالة تشرح السبب عند الفشل
EMPTY_GRACE = 0.7
UNTOUCHED_GRACE = 0.4
DEBUG = False

BOOLS = ("fallback_line", "notify", "debug")
FLOATS = ("empty_grace", "untouched_grace", "timeout")
TEXTS = ("hotkey", "provider", "fallback_provider", "deepl_api_key",
         "lang_a", "lang_b", "formality")
# مفاتيح يكون الفراغ فيها قرارا لا سهوا: تفريغها يعني "عطّل هذا".
# بقية المفاتيح يبقى الافتراضي اذا فُرّغت، لان اختصارا فارغا مثلا لا معنى له.
ALLOW_EMPTY = ("deepl_api_key", "fallback_provider")


def is_frozen():
    return getattr(sys, "frozen", False)


def app_path():
    if is_frozen():
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def app_dir():
    return os.path.dirname(app_path())


def settings_path():
    portable = os.path.join(app_dir(), "settings.ini")
    if os.path.isfile(portable):
        return portable
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME, "settings.ini")


def log_path():
    return os.path.join(os.path.dirname(settings_path()), "translatefix.log")


DEFAULT_INI = """\
; اعدادات translatefix - احفظ الملف ثم اعد تشغيل الاداة ليسري التغيير

[translatefix]
; الاختصار. امثلة: ctrl+alt+t  /  ctrl+shift+t  /  f9
hotkey = ctrl+alt+t

; محرك الترجمة: deepl (يحتاج مفتاحا) او google (بلا مفتاح)
provider = deepl

; محرك احتياطي يُستخدم تلقائيا اذا فشل الاساسي - مثلا حين ينفد رصيد DeepL.
; خطة DeepL Developer تعطي رصيدا لمرة واحدة لا حصة شهرية متجددة، فحين
; ينفد تستمر الاداة بالعمل عبر هذا المحرك بدل ان تتوقف. اتركه فارغا لتعطيله.
fallback_provider = google

; مفتاحك من https://www.deepl.com/pro-api - الباقة المجانية تكفي
; احفظ هذا الملف لنفسك: المفتاح سر، ومن يملكه يستهلك حصتك
deepl_api_key =

; اللغتان اللتان نتنقل بينهما. رموز DeepL: AR, EN-US, EN-GB, FR, DE, TR ...
lang_a = AR
lang_b = EN-US

; درجة الرسمية في الترجمة (DeepL فقط، ولبعض اللغات): default / more / less
formality = default

; مهلة الاتصال بالخدمة بالثواني
timeout = 12

; اذا لم يكن هناك نص محدد، ترجم السطر من بدايته حتى المؤشر
fallback_line = true

; اظهر رسالة تشرح السبب عند الفشل
notify = true

; اكتب سجل تشخيص في translatefix.log بجانب هذا الملف
debug = false
"""


SETTINGS_ERROR = ""


def _set_settings_error(msg):
    """نسجّل سبب تجاهل الاعدادات لنعرضه بدل ان يبقى المستخدم في حيرة."""
    globals()["SETTINGS_ERROR"] = msg
    _log(msg)


def load_settings():
    globals()["SETTINGS_ERROR"] = ""
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(DEFAULT_INI)
            return path
    except OSError:
        return path

    parser = configparser.ConfigParser(inline_comment_prefixes=(";",))
    try:
        # utf-8-sig لا utf-8: محررات ويندوز تضيف BOM كثيرا، وعندها يفشل
        # configparser بـ MissingSectionHeaderError فتُهمل اعداداتك بصمت.
        parser.read(path, encoding="utf-8-sig")
    except (configparser.Error, OSError) as exc:
        _set_settings_error("تعذّرت قراءة ملف الاعدادات: %s" % exc)
        return path
    if not parser.has_section(APP_NAME):
        _set_settings_error("لا يوجد قسم [%s] في ملف الاعدادات." % APP_NAME)
        return path

    g = globals()
    for key in TEXTS:
        if parser.has_option(APP_NAME, key):
            value = parser.get(APP_NAME, key).strip()
            if value or key in ALLOW_EMPTY:
                g[key.upper()] = value
    for key in BOOLS:
        if parser.has_option(APP_NAME, key):
            try:
                g[key.upper()] = parser.getboolean(APP_NAME, key)
            except ValueError:
                pass
    for key in FLOATS:
        if parser.has_option(APP_NAME, key):
            try:
                g[key.upper()] = parser.getfloat(APP_NAME, key)
            except ValueError:
                pass
    return path


def _redact(text):
    """لا نكتب المفتاح في السجل ابدا."""
    if DEEPL_API_KEY and DEEPL_API_KEY in text:
        return text.replace(DEEPL_API_KEY, "<المفتاح>")
    return text


def _log(msg):
    if not DEBUG:
        return
    try:
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (time.strftime("%H:%M:%S"), _redact(str(msg))))
    except Exception:
        pass


# ============================================================== الترجمة =====

class TranslateError(Exception):
    """خطأ نعرف سببه ونريد عرضه للمستخدم كما هو."""


def _is_arabic(ch):
    o = ord(ch)
    return 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFEFF


def pick_target(text):
    """
    يختار لغة الهدف: اذا كان النص بلغة LANG_A نترجم الى LANG_B والعكس.
    المقارنة بالجذر فقط حتى يتطابق AR مع ar و EN-US مع en.
    """
    root_a = LANG_A.split("-")[0].upper()
    looks_arabic = sum(1 for c in text if _is_arabic(c)) > 0
    source_is_a = looks_arabic if root_a == "AR" else not looks_arabic
    return LANG_B if source_is_a else LANG_A


def _http_json(url, data=None, headers=None, timeout=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


DEEPL_ERRORS = {
    403: "المفتاح مرفوض. تأكد من deepl_api_key في ملف الاعدادات.",
    429: "طلبات كثيرة بسرعة. انتظر لحظة ثم أعد المحاولة.",
    456: "نفد رصيدك في DeepL.",
    400: "طلب غير مقبول - غالبا رمز لغة غير مدعوم في باقتك.",
    503: "خدمة DeepL مشغولة الآن. أعد المحاولة بعد قليل.",
}


def deepl_endpoint(path="/v2/translate"):
    """مفاتيح الباقة المجانية تنتهي بـ :fx وتستخدم نطاقا مختلفا."""
    host = "api-free.deepl.com" if DEEPL_API_KEY.endswith(":fx") \
        else "api.deepl.com"
    return "https://%s%s" % (host, path)


def translate_deepl(text, target):
    if not DEEPL_API_KEY:
        raise TranslateError(
            "لا يوجد مفتاح DeepL. ضع المفتاح في ملف الاعدادات، أو غيّر "
            "provider الى google ليعمل بلا مفتاح.")
    payload = {"text": [text], "target_lang": target}
    if FORMALITY and FORMALITY != "default":
        payload["formality"] = FORMALITY
    body = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": "DeepL-Auth-Key " + DEEPL_API_KEY,
               "Content-Type": "application/json",
               "User-Agent": "%s/%s" % (APP_NAME, VERSION)}
    try:
        data = _http_json(deepl_endpoint(), body, headers)
    except urllib.error.HTTPError as exc:
        raise TranslateError(DEEPL_ERRORS.get(
            exc.code, "رفض DeepL الطلب (رمز %s)." % exc.code))
    items = data.get("translations") or []
    if not items:
        raise TranslateError("ردّ DeepL بلا ترجمة.")
    return items[0].get("text", "")


def translate_google(text, target):
    """
    منفذ جوجل العام غير الرسمي - بلا مفتاح. يُستخدم هنا كبديل اذا لم تكن
    لديك باقة DeepL. ليس مضمون الاستمرار، فلا تبنِ عليه خدمة عامة.
    """
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": "auto",
        "tl": target.split("-")[0].lower(), "dt": "t", "q": text})
    url = "https://translate.googleapis.com/translate_a/single?" + params
    try:
        data = _http_json(url, headers={"User-Agent": "Mozilla/5.0"})
    except urllib.error.HTTPError as exc:
        raise TranslateError("رفضت جوجل الطلب (رمز %s)." % exc.code)
    if not data or not isinstance(data, list) or not data[0]:
        raise TranslateError("ردّ جوجل بشكل غير متوقع.")
    return "".join(part[0] for part in data[0] if part and part[0])


def _translate_once(text, target, provider):
    _log("ترجمة الى %s عبر %s (%d حرف)" % (target, provider, len(text)))
    try:
        out = translate_google(text, target) if provider == "google" \
            else translate_deepl(text, target)
    except TranslateError:
        raise
    except urllib.error.HTTPError as exc:
        # قبل URLError: HTTPError وريث له، والا وُسم خطأ الخادم بأنه
        # انقطاع انترنت - وهي رسالة تضلّل المستخدم تماما.
        raise TranslateError("رفضت الخدمة الطلب (رمز %s)." % exc.code)
    except urllib.error.URLError as exc:
        raise TranslateError("تعذر الاتصال بالانترنت: %s" % exc.reason)
    except TimeoutError:
        raise TranslateError("انتهت مهلة الاتصال (%.0f ثانية)." % TIMEOUT)
    except Exception as exc:                      # noqa: BLE001
        raise TranslateError("خطأ غير متوقع: %s" % exc)
    if not out.strip():
        raise TranslateError("رجعت الترجمة فارغة.")
    return out


def translate(text, target=None):
    """
    يرجع (الترجمة، لغة الهدف، ملاحظة الاحتياطي).
    الملاحظة None في الحالة العادية، والا فهي نص يشرح لماذا تحوّلنا.
    """
    target = target or pick_target(text)
    primary = (PROVIDER or "deepl").strip().lower()
    fallback = (FALLBACK_PROVIDER or "").strip().lower()
    try:
        return _translate_once(text, target, primary), target, None
    except TranslateError as first:
        if not fallback or fallback == primary:
            raise
        _log("فشل %s (%s) - نجرب %s" % (primary, first, fallback))
        try:
            out = _translate_once(text, target, fallback)
        except TranslateError:
            raise first          # نبلّغ عن سبب الاخفاق الاصلي لا الاحتياطي
        return out, target, "%s تعذّر (%s) فتُرجمت عبر %s." % (
            primary, first, fallback)


def check_api():
    """هل المفتاح يعمل؟ وهل اللغتان المختارتان مدعومتان فعلا؟"""
    provider = (PROVIDER or "deepl").strip().lower()
    if SETTINGS_ERROR:
        print("تنبيه    :", SETTINGS_ERROR)
        print("           (تُستخدم القيم الافتراضية - اعداداتك مهملة)\n")
    print("المحرك   :", provider)
    print("الاحتياطي:", FALLBACK_PROVIDER or "معطّل")
    if provider == "google":
        out, target, _ = translate("مرحبا بك", LANG_B)
        print("تجربة    : 'مرحبا بك' -> %r  (%s)" % (out, target))
        return 0

    if not DEEPL_API_KEY:
        print("المفتاح  : غير مضبوط")
        print("\nضع مفتاحك في:", settings_path())
        return 1
    print("المفتاح  : %s...%s  (%s)"
          % (DEEPL_API_KEY[:5], DEEPL_API_KEY[-3:],
             "باقة مجانية" if DEEPL_API_KEY.endswith(":fx") else "باقة مدفوعة"))

    headers = {"Authorization": "DeepL-Auth-Key " + DEEPL_API_KEY,
               "User-Agent": "%s/%s" % (APP_NAME, VERSION)}
    try:
        usage = _http_json(deepl_endpoint("/v2/usage"), headers=headers)
        used, limit = usage.get("character_count"), usage.get("character_limit")
        if used is not None and limit:
            print("الاستهلاك: %s من %s حرف (%.1f%%)"
                  % (f"{used:,}", f"{limit:,}", 100.0 * used / limit))
    except urllib.error.HTTPError as exc:
        print("فشل التحقق من المفتاح:",
              DEEPL_ERRORS.get(exc.code, "رمز %s" % exc.code))
        return 1
    except Exception as exc:                      # noqa: BLE001
        print("تعذر الوصول الى DeepL:", exc)
        return 1

    # هل العربية مدعومة فعلا في هذه الباقة؟ الاختبار الوحيد الحاسم هو الترجمة.
    # نتجاوز المحرك الاحتياطي عمدا هنا: لو تحوّلنا الى جوجل عند فشل DeepL
    # لظهر الفحص ناجحا بينما DeepL لا يدعم اللغة - وهذا بالضبط ما نفحصه.
    print()
    ok = True
    for sample, target in (("مرحبا بك", LANG_B), ("Hello there", LANG_A)):
        try:
            out = _translate_once(sample, target, "deepl")
            print("  %-14r -> %-8s %r" % (sample, target, out))
        except TranslateError as exc:
            print("  %-14r -> %-8s فشل: %s" % (sample, target, exc))
            ok = False
    print("\nالنتيجة:", "اللغتان مدعومتان" if ok else "لغة غير مدعومة - "
          "جرّب provider = google في ملف الاعدادات")
    return 0 if ok else 1


# ==========================================================  Win32 plumbing ==
# منقول من layoutfix بعد ان ضُبط هناك. لا تبسّط هذا الجزء قبل قراءة تعليقاته.

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

WM_DESTROY, WM_CLOSE, WM_HOTKEY = 0x0002, 0x0010, 0x0312
WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0205, 0x0203
WM_TRAY = 0x8001

CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 1, 2, 4, 8, 0x4000
HOTKEY_ID = 0xA721

VK_SHIFT, VK_CTRL, VK_ALT = 0x10, 0x11, 0x12
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_HOME, VK_END = 0x24, 0x23
VK_C, VK_V = 0x43, 0x56

VK_NAMES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
            "shift": MOD_SHIFT, "win": MOD_WIN}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                ("d3", wintypes.WORD), ("d4", ctypes.c_byte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                ("hBalloonIcon", wintypes.HICON)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
user32.SetClipboardData.restype = ctypes.c_void_p
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.LoadIconW.argtypes = (wintypes.HINSTANCE, ctypes.c_void_p)
user32.LoadIconW.restype = wintypes.HICON
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
user32.CreateWindowExW.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD))
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD))
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    n = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if n != len(inputs):
        _log("SendInput حُجب: %d من %d" % (n, len(inputs)))
    return n


EXTENDED_VKS = frozenset([0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
                          0x2D, 0x2E, 0x5B, 0x5C])


def _k(vk, up=False):
    # Chrome وتطبيقات Electron تتجاهل الاحداث التي تصل بـ scan code صفر
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0x0002 if up else 0
    if vk in EXTENDED_VKS:
        flags |= 0x0001
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0,
                        dwExtraInfo=0)
    return i


def tap(vk, *mods):
    """كل ضغطة على حدة مع فاصل زمني - الدفعة الواحدة تتجاهلها برامج كثيرة."""
    for m in mods:
        _send(_k(m))
        time.sleep(0.012)
    _send(_k(vk))
    time.sleep(0.012)
    _send(_k(vk, True))
    time.sleep(0.012)
    for m in reversed(mods):
        _send(_k(m, True))
        time.sleep(0.008)


MOD_KEYS = (VK_CTRL, VK_ALT, VK_SHIFT, VK_LWIN, VK_RWIN)


def held_modifiers():
    return [vk for vk in MOD_KEYS if user32.GetAsyncKeyState(vk) & 0x8000]


def release_modifiers(timeout=1.2):
    """
    ننتظر رفع يدك فعليا عن Ctrl+Alt قبل ارسال Ctrl+C. بدون ذلك يستقبل
    البرنامج Ctrl+Alt+C. ارسال keyup صناعي لا يغيّر حالة المفتاح الفيزيائي.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not held_modifiers():
            time.sleep(0.02)
            return True
        time.sleep(0.015)
    stuck = held_modifiers()
    if stuck:
        _send(*[_k(vk, True) for vk in stuck])
        time.sleep(0.04)
    return False


def _open_clipboard(tries=10):
    for _ in range(tries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def clip_get():
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    if not _open_clipboard():
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def clip_set(text):
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        if text is None:
            return True
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            return False
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, buf, size)
        kernel32.GlobalUnlock(h)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        user32.CloseClipboard()


SENTINEL = "​⁠translatefix⁠​"


def copy_selection(timeout=1.5):
    """
    نضع علامة فريدة قبل Ctrl+C: ان بقيت فلا شيء نُسخ، ويستحيل ان نرجع
    محتوى حافظة قديما. رقم التسلسل وحده لا يكفي لانه يرتفع عند
    EmptyClipboard اي قبل كتابة النص.
    """
    started = time.time()
    if not clip_set(SENTINEL):
        _log("تعذر وضع العلامة - برنامج آخر يمسك الحافظة")
    seq0 = user32.GetClipboardSequenceNumber()
    tap(VK_C, VK_CTRL)

    touched_at = None
    while time.time() - started < timeout:
        time.sleep(0.025)
        now = time.time()
        got = clip_get()
        if got and got != SENTINEL:
            return got
        if user32.GetClipboardSequenceNumber() != seq0:
            if touched_at is None:
                touched_at = now
            elif now - touched_at > EMPTY_GRACE:
                return ""
        elif now - started > UNTOUCHED_GRACE:
            _log("العلامة باقية - البرنامج لم يستجب لـ Ctrl+C")
            return ""
    return ""


def foreground_app():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "?"
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = "?"
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = buf.value.rsplit("\\", 1)[-1]
        kernel32.CloseHandle(h)
    return name


_nid = None
_wndproc_ref = None
_busy = threading.Lock()


def notify(title, msg, beep=0x30):
    _log("%s - %s" % (title, msg))
    user32.MessageBeep(beep)
    if not (NOTIFY and _nid is not None):
        return
    _nid.uFlags = 0x10
    _nid.szInfoTitle = title[:62]
    _nid.szInfo = msg[:250]
    _nid.dwInfoFlags = 0x01
    shell32.Shell_NotifyIconW(1, ctypes.byref(_nid))
    _nid.uFlags = 0x01 | 0x02 | 0x04


# ------------------------------------------------------------- الفعل الرئيسي --

def do_translate():
    """
    يعمل في خيط منفصل: نداء الشبكة قد يستغرق ثواني، ولا نريد تجميد
    حلقة الرسائل فتبدو الاداة معلّقة ولا تستجيب ايقونتها.
    """
    if not _busy.acquire(blocking=False):
        notify(APP_NAME, "هناك ترجمة جارية. انتظر لحظة.", beep=0x40)
        return
    try:
        app = foreground_app()
        _log("--- الاختصار في: %s" % app)
        release_modifiers()
        saved = clip_get()
        try:
            text = copy_selection()
            if not text and FALLBACK_LINE:
                tap(VK_HOME, VK_SHIFT)
                time.sleep(0.06)
                text = copy_selection()
            if not text.strip():
                notify("لم أتمكن من قراءة النص",
                       "%s لم يستجب لـ Ctrl+C. حدّد النص يدوياً ثم أعد "
                       "المحاولة." % app)
                return
            try:
                out, target, note = translate(text)
            except TranslateError as exc:
                notify("تعذرت الترجمة", str(exc))
                return
            if note:
                notify("تحوّلت للمحرك الاحتياطي", note, beep=0x40)
            if out.strip() == text.strip():
                notify("لا تغيير", "رجعت الترجمة مطابقة للنص الأصلي.",
                       beep=0x40)
                return
            if not clip_set(out):
                notify("الحافظة مشغولة", "أعد المحاولة بعد لحظة.")
                return
            time.sleep(0.04)
            tap(VK_V, VK_CTRL)
            time.sleep(0.22)
            _log("تُرجم الى %s: %r" % (target, out[:60]))
        finally:
            if clip_get() != saved:
                clip_set(saved)
    finally:
        _busy.release()


# -------------------------------------------------------- النافذة والايقونة --

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    exe = app_path()
    if is_frozen():
        return '"%s"' % exe
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    return '"%s" "%s"' % (pyw, exe)


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enable):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        _log("تعذر تعديل الاقلاع: %s" % exc)
        return False


def open_settings_file():
    path = load_settings()
    try:
        os.startfile(path)
    except OSError:
        user32.MessageBoxW(None, "ملف الاعدادات:\n%s" % path, APP_NAME, 0x40)


def parse_hotkey(spec):
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    mods, vk = MOD_NOREPEAT, None
    for p in parts:
        if p in VK_NAMES:
            mods |= VK_NAMES[p]
        elif len(p) == 1:
            vk = ord(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x70 + int(p[1:]) - 1
        elif p == "space":
            vk = 0x20
        elif p in ("pause", "break"):
            vk = 0x13
        elif p in ("insert", "ins"):
            vk = 0x2D
    if vk is None:
        raise SystemExit("اختصار غير صالح: %s" % spec)
    return mods, vk


MF_SEPARATOR, MF_CHECKED = 0x0800, 0x0008
ID_RUN, ID_QUIT, ID_AUTOSTART, ID_SETTINGS, ID_ABOUT = 1, 2, 3, 4, 5


def show_menu(hwnd):
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, 0, ID_RUN, "ترجم الآن  (%s)" % HOTKEY.upper())
    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(menu, MF_CHECKED if autostart_enabled() else 0,
                       ID_AUTOSTART, "تشغيل مع ويندوز")
    user32.AppendMenuW(menu, 0, ID_SETTINGS, "فتح ملف الاعدادات")
    user32.AppendMenuW(menu, 0, ID_ABOUT, "عن الاداة")
    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(menu, 0, ID_QUIT, "ايقاف الاداة")

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, hwnd, None)
    user32.DestroyMenu(menu)

    if cmd == ID_RUN:
        threading.Thread(target=do_translate, daemon=True).start()
    elif cmd == ID_AUTOSTART:
        wanted = not autostart_enabled()
        if set_autostart(wanted):
            notify(APP_NAME, "ستعمل الاداة تلقائيا مع ويندوز." if wanted
                   else "لن تعمل الاداة تلقائيا مع ويندوز.", beep=0x40)
    elif cmd == ID_SETTINGS:
        open_settings_file()
    elif cmd == ID_ABOUT:
        user32.MessageBoxW(
            None,
            "%s %s\n\nيترجم النص المحدد بضغطة اختصار.\n\n"
            "الاختصار  : %s\nالمحرك    : %s\nاللغتان   : %s <-> %s\n"
            "الاعدادات : %s\n\nرخصة MIT."
            % (APP_NAME, VERSION, HOTKEY.upper(), PROVIDER, LANG_A, LANG_B,
               settings_path()),
            "عن %s" % APP_NAME, 0x40)
    elif cmd == ID_QUIT:
        user32.DestroyWindow(hwnd)


def wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAY:
        if (lparam & 0xFFFF) in (WM_RBUTTONUP, WM_LBUTTONDBLCLK):
            show_menu(hwnd)
        return 0
    if msg in (WM_CLOSE, WM_DESTROY):
        if _nid is not None:
            shell32.Shell_NotifyIconW(2, ctypes.byref(_nid))
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def run_daemon(check_only=False):
    global _wndproc_ref, _nid

    kernel32.CreateMutexW(None, True, "translatefix_single_instance")
    if ctypes.get_last_error() == 183:
        if check_only:
            print("الاداة تعمل بالفعل (نسخة واحدة فقط مسموحة).")
        return

    hinst = kernel32.GetModuleHandleW(None)
    _wndproc_ref = WNDPROC(wndproc)
    cls = WNDCLASSEXW()
    cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
    cls.lpfnWndProc = _wndproc_ref
    cls.hInstance = hinst
    cls.lpszClassName = "TranslateFixWnd"
    if not user32.RegisterClassExW(ctypes.byref(cls)):
        raise ctypes.WinError(ctypes.get_last_error())

    hwnd = user32.CreateWindowExW(0, "TranslateFixWnd", APP_NAME, 0,
                                  0, 0, 0, 0, None, None, hinst, None)
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())

    mods, vk = parse_hotkey(HOTKEY)
    if not user32.RegisterHotKey(hwnd, HOTKEY_ID, mods, vk):
        user32.MessageBoxW(
            None, "تعذر تسجيل الاختصار %s - ربما يستخدمه برنامج آخر.\n"
            "غيّر hotkey في:\n%s" % (HOTKEY.upper(), settings_path()),
            APP_NAME, 0x10)
        return

    _nid = NOTIFYICONDATAW()
    _nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    _nid.hWnd = hwnd
    _nid.uID = 1
    _nid.uFlags = 0x01 | 0x02 | 0x04
    _nid.uCallbackMessage = WM_TRAY
    _nid.hIcon = user32.LoadIconW(None, 32516)
    _nid.szTip = "%s - %s للترجمة" % (APP_NAME, HOTKEY.upper())
    shell32.Shell_NotifyIconW(0, ctypes.byref(_nid))

    if SETTINGS_ERROR:
        notify("ملف الاعدادات مُهمَل",
               "%s\nتعمل الاداة بالقيم الافتراضية." % SETTINGS_ERROR)

    if check_only:
        print("حجم INPUT:", ctypes.sizeof(INPUT), "(المتوقع 40)")
        saved = clip_get()
        probe = "translatefix-probe"
        clip_set(probe)
        got = clip_get()
        clip_set(saved)
        print("الحافظة:", "OK" if got == probe else "فشل")
        print("النافذة والاختصار والايقونة: OK (%s)" % HOTKEY.upper())
        print("البرنامج في المقدمة:", foreground_app())
        shell32.Shell_NotifyIconW(2, ctypes.byref(_nid))
        user32.UnregisterHotKey(hwnd, HOTKEY_ID)
        user32.DestroyWindow(hwnd)
        return

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            threading.Thread(target=do_translate, daemon=True).start()
            continue
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    user32.UnregisterHotKey(hwnd, HOTKEY_ID)


def attach_console():
    if not is_frozen():
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        if kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8",
                              errors="replace", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8",
                              errors="replace", buffering=1)
    except Exception:
        pass


def main():
    args = sys.argv[1:]
    if args:
        attach_console()
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0] in ("-v", "--version"):
        print("%s %s" % (APP_NAME, VERSION))
        return 0

    path = load_settings()

    if args and args[0] == "--settings":
        print(path)
        return 0
    if args and args[0] == "--check-api":
        return check_api()
    if args and args[0] in ("--tr", "--translate"):
        text = " ".join(args[1:])
        try:
            out, target, note = translate(text)
        except TranslateError as exc:
            print("فشل:", exc, file=sys.stderr)
            return 1
        print(out)
        if note:
            print("تنبيه:", note, file=sys.stderr)
        print("(-> %s)" % target, file=sys.stderr)
        return 0
    if args and args[0] == "--autostart":
        on = len(args) < 2 or args[1] not in ("off", "0", "false")
        ok = set_autostart(on)
        print("الاقلاع التلقائي:", "مفعّل" if on else "متوقف")
        return 0 if ok else 1
    if args and args[0] == "--debug":
        globals()["DEBUG"] = True
        _log("=== بدأ التشغيل بوضع التشخيص (%s %s) ===" % (APP_NAME, VERSION))
    if args and args[0] == "--check":
        print("ملف الاعدادات:", path)
        run_daemon(check_only=True)
        return 0

    run_daemon()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
