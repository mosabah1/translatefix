# -*- coding: utf-8 -*-
"""
يختبر قراءة ملف الاعدادات.

الخطأ الذي وقع: محررات ويندوز تحفظ UTF-8 مع BOM، وقراءة الملف بـ utf-8
العادي تجعل configparser يفشل بـ MissingSectionHeaderError. كان الكود
يبتلع الخطأ ويعود للقيم الافتراضية بصمت - فيعدّل المستخدم اعداداته ولا
يحدث شيء ولا يعرف لماذا.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translatefix as t

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("  %-44s %s%s" % (name, "OK" if ok else "فشل", detail))


SAMPLE = """\
; تعليق في الاول
[translatefix]
hotkey = ctrl+alt+9
provider = google
lang_b = FR
timeout = 7
notify = false
"""


def load_from(raw_bytes):
    """يكتب ملف اعدادات بترميز معين ويحمّله، ثم يرجع القيم الناتجة."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "settings.ini")
    with open(path, "wb") as fh:
        fh.write(raw_bytes)
    t.settings_path = lambda: path          # نوجّه الاداة لهذا الملف
    for name, value in (("HOTKEY", "ctrl+alt+t"), ("PROVIDER", "deepl"),
                        ("LANG_B", "EN-US"), ("TIMEOUT", 12.0),
                        ("NOTIFY", True), ("FALLBACK_PROVIDER", "google")):
        setattr(t, name, value)             # نعيد الافتراضيات قبل كل حالة
    t.load_settings()
    return dict(hotkey=t.HOTKEY, provider=t.PROVIDER, lang_b=t.LANG_B,
                timeout=t.TIMEOUT, notify=t.NOTIFY, error=t.SETTINGS_ERROR)


print("1) ملف بـ UTF-8 بلا BOM\n")
r = load_from(SAMPLE.encode("utf-8"))
check("قرأ الاختصار", r["hotkey"] == "ctrl+alt+9", "  -> %r" % r["hotkey"])
check("قرأ المحرك", r["provider"] == "google", "  -> %r" % r["provider"])
check("قرأ رقما عشريا", r["timeout"] == 7.0, "  -> %r" % r["timeout"])
check("قرأ قيمة منطقية", r["notify"] is False, "  -> %r" % r["notify"])
check("بلا اخطاء", not r["error"])

print("\n2) ملف بـ UTF-8 مع BOM - هذا ما تكتبه محررات ويندوز\n")
r = load_from(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
check("قرأ الاختصار رغم BOM", r["hotkey"] == "ctrl+alt+9",
      "  -> %r" % r["hotkey"])
check("قرأ المحرك رغم BOM", r["provider"] == "google",
      "  -> %r" % r["provider"])
check("بلا اخطاء", not r["error"], "  -> %r" % r["error"])

print("\n3) ملف تالف - يجب ان يشرح السبب لا ان يصمت\n")
r = load_from("هذا ليس ملف اعدادات اصلا\n".encode("utf-8"))
check("عاد للقيم الافتراضية", r["provider"] == "deepl")
check("وسجّل سببا مفهوما", bool(r["error"]), "\n      %s" % r["error"])

print("\n4) قسم باسم خاطئ - نفس المطلوب\n")
r = load_from("[wrongname]\nprovider = google\n".encode("utf-8"))
check("عاد للقيم الافتراضية", r["provider"] == "deepl")
check("وسجّل سببا مفهوما", bool(r["error"]), "\n      %s" % r["error"])

print("\n5) تفريغ مفتاح اختياري يجب ان يعطّله لا ان يُهمَل\n")
load_from("[translatefix]\nfallback_provider =\n".encode("utf-8"))
check("القيمة الفارغة ألغت الافتراضي", t.FALLBACK_PROVIDER == "",
      "  -> %r" % t.FALLBACK_PROVIDER)
load_from("[translatefix]\nhotkey =\n".encode("utf-8"))
check("لكن الاختصار الفارغ يبقى على الافتراضي",
      t.HOTKEY == "ctrl+alt+t", "  -> %r" % t.HOTKEY)

print("\nالنتيجة:", "كل الاختبارات ناجحة" if all(results) else "فيه فشل")
sys.exit(0 if all(results) else 1)
