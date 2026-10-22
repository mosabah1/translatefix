# -*- coding: utf-8 -*-
"""
يختبر التحوّل التلقائي للمحرك الاحتياطي.

خطة DeepL Developer تعطي رصيدا لمرة واحدة لا حصة متجددة، فحين ينفد يرد
DeepL بالرمز 456. يجب ان تستمر الاداة بالعمل عبر جوجل لا ان تتوقف.
يحتاج اتصالا بالانترنت (يستخدم جوجل فعليا كمحرك احتياطي).
"""
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translatefix as t

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("  %-46s %s%s" % (name, "OK" if ok else "فشل", detail))


REAL_HTTP = t._http_json


def fail_hosts(**codes):
    """
    نعترض على مستوى HTTP لا على مستوى دالة المزوّد، فيعمل كود المزوّد
    الحقيقي ويترجم رمز الخطأ الى رسالته - وهذا هو ما يراه المستخدم فعلا.
    """
    def fake(url, data=None, headers=None, timeout=None):
        for needle, code in codes.items():
            if needle in url:
                raise urllib.error.HTTPError(url, code, "simulated", {}, None)
        return REAL_HTTP(url, data, headers, timeout)
    return fake


t.PROVIDER = "deepl"
t.FALLBACK_PROVIDER = "google"
t.DEEPL_API_KEY = "fake-key:fx"

print("1) نفاد الرصيد (456) - يجب ان يستمر العمل عبر جوجل\n")
t._http_json = fail_hosts(deepl=456)
out, target, note = t.translate("كيف حالك اليوم")
check("رجعت ترجمة رغم فشل DeepL", bool(out.strip()), "  -> %r" % out)
check("الملاحظة تشرح السبب بلغة مفهومة",
      bool(note) and "رصيدك" in note, "\n      %s" % note)

print("\n2) مفتاح مرفوض (403) - نفس السلوك\n")
t._http_json = fail_hosts(deepl=403)
out, _, note = t.translate("Hello there")
check("رجعت ترجمة", bool(out.strip()), "  -> %r" % out)
check("الملاحظة تشير الى المفتاح", bool(note) and "المفتاح" in note,
      "\n      %s" % note)

print("\n3) الاحتياطي معطّل - يجب ان يفشل بوضوح لا ان يصمت\n")
t.FALLBACK_PROVIDER = ""
t._http_json = fail_hosts(deepl=456)
try:
    t.translate("كيف حالك")
    check("رفع خطأ", False, "  لم يرفع شيئا!")
except t.TranslateError as exc:
    check("رفع خطأ يشرح السبب", "رصيدك" in str(exc), "  -> %s" % exc)

print("\n4) فشل الاثنين - يجب ان يُبلّغ عن سبب الاساسي لا الاحتياطي\n")
t.FALLBACK_PROVIDER = "google"
t._http_json = fail_hosts(deepl=456, googleapis=500)
try:
    t.translate("كيف حالك")
    check("رفع خطأ", False)
except t.TranslateError as exc:
    check("السبب المعروض هو سبب DeepL", "رصيدك" in str(exc), "  -> %s" % exc)

t._http_json = REAL_HTTP
print("\nالنتيجة:", "كل الاختبارات ناجحة" if all(results) else "فيه فشل")
sys.exit(0 if all(results) else 1)
