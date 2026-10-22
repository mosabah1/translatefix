# translatefix

**[العربية](README.ar.md)** · English

Translate what you are typing, in place, with one shortcut.

```
كيف حالك اليوم     →   How are you today
How are you today  →   كيف حالك اليوم
```

Select text — or select nothing and it takes the current line — press
**Ctrl+Alt+T**, and the text is replaced by its translation. The direction is
detected automatically.

> Sibling of [layoutfix](https://github.com/mosabah1/layoutfix), which fixes text
> typed under the wrong keyboard layout. They are deliberately separate programs:
> layoutfix never touches the network, and this one has to.

---

## Install

1. Download `translatefix.exe` from the [latest release](../../releases/latest).
2. Put it anywhere and double-click it.
3. A tray icon appears near the clock. No installer, no Python, no API key.

To start it with Windows: right-click the tray icon → **تشغيل مع ويندوز**.

### Windows will warn you the first time

The executable is not code-signed, so SmartScreen shows **"Windows protected
your PC"** — click **More info → Run anyway**. Some antivirus engines may flag it
too: it sends keystrokes, reads the clipboard and makes network calls, which is a
keylogger's profile. The source is here, and
[building it yourself](#build-from-source) takes one command.

---

## Use

| Situation | What to press |
|---|---|
| Text is selected | **Ctrl+Alt+T** — translates the selection |
| Nothing selected | **Ctrl+Alt+T** — translates the current line up to the caret |

Works in anything that supports Ctrl+C / Ctrl+V — browsers, Word, WhatsApp,
Telegram, VS Code.

---

## Where your text goes

Read this before using it on anything sensitive.

**When you press the shortcut, the selected text leaves your computer.** It is
sent over HTTPS to the translation service you configured. There is no way around
that — it is what translation is. Concretely:

- **Default (`provider = google`)**: your text goes to Google's public translate
  endpoint. No account, no API key, nothing identifying you beyond the request
  itself. This is the same endpoint many free translation tools use; it is **not
  an official, documented API**, so Google may rate-limit or change it without
  notice.
- **`provider = deepl`**: your text goes to DeepL instead, with your API key.

**Nothing is sent unless you press the shortcut.** The tool does not hook the
keyboard, does not record what you type, and sits idle until the hotkey fires.
It writes nothing to disk unless you set `debug = true`, and even then your API
key is redacted out of the log.

**Do not use this for text you would not paste into a public translation site.**
Passwords, private keys, medical or legal material, anything under NDA. That is
not a flaw in this tool; it is true of every translator.

If that trade-off is unacceptable for your use, [layoutfix](
https://github.com/mosabah1/layoutfix) is the sibling tool that never makes a
network call at all.

---

## Settings

Right-click the tray icon → **فتح ملف الاعدادات**, or edit:

```
%APPDATA%\translatefix\settings.ini
```

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `ctrl+alt+t` | The shortcut |
| `provider` | `google` | `google` (no key) or `deepl` (needs a key) |
| `fallback_provider` | — | Used automatically if the main one fails |
| `deepl_api_key` | — | Your key from deepl.com/pro-api |
| `lang_a` / `lang_b` | `AR` / `EN-US` | The two languages to move between |
| `formality` | `default` | `default` / `more` / `less` (DeepL, some languages) |
| `timeout` | `12` | Seconds to wait for the service |
| `fallback_line` | `true` | Translate the current line when nothing is selected |
| `notify` | `true` | Explain failures in a notification instead of a beep |
| `debug` | `false` | Write `translatefix.log` next to the settings file |

Save and restart the tool to apply. If a change seems to do nothing, run
`translatefix.exe --check`: it prints the settings file it reads and says plainly
when that file could not be parsed.

**Other languages:** set `lang_a` and `lang_b` to any pair the service supports —
`FR`, `DE`, `TR`, `ES`. The direction detection assumes one of the two is Arabic;
for two non-Arabic languages it will not pick the direction correctly yet.

**Portable mode:** put a `settings.ini` next to the exe and it is used instead.

### Using DeepL

DeepL's output is often better, and it is an official, documented API rather than
a public endpoint that may change. It needs a free account, and the free tier is
a **one-time credit**, not a monthly allowance — when it runs out, translation
stops unless you pay.

That is what `fallback_provider` is for:

```ini
provider = deepl
fallback_provider = google
deepl_api_key = your-key-here:fx
```

Now DeepL is used while the credit lasts, and the tool quietly moves to Google
when it is exhausted instead of simply breaking. Check your key and remaining
quota with:

```bat
translatefix.exe --check-api
```

It also translates a sample in both directions, because DeepL's language list has
historically not matched what the API actually accepts.

---

## Troubleshooting

Failures are explained in a notification naming the program it was acting on:

| Message | Meaning |
|---|---|
| لم أتمكن من قراءة النص | The program didn't respond to Ctrl+C, or it runs elevated |
| تعذرت الترجمة | The service refused or could not be reached — the message says which |
| تحوّلت للمحرك الاحتياطي | The main service failed; the fallback translated instead |
| الحافظة مشغولة | Another program is holding the clipboard |

For more detail set `debug = true` and restart; the log lands next to the
settings file.

**If the target program runs as Administrator and translatefix doesn't**, Windows
blocks all synthetic input to it (UIPI). Run translatefix as Administrator too.

---

## Build from source

Needs Python 3.9+ on Windows. Nothing third-party to run it; PyInstaller and
Pillow only to build the executable and its icon.

```bat
pip install pyinstaller pillow
build.cmd
```

Or run it directly:

```bat
pythonw translatefix.py
```

### Tests

```bat
python test_settings.py      ; the settings file, BOM and all
python test_fallback.py      ; what happens when a service fails (needs network)
python translatefix.py --check      ; hotkey, tray icon, clipboard, Win32 structs
python translatefix.py --check-api  ; the translation service itself
```

Two bug classes are regression-tested here because both bit in practice:

1. **A settings file with a UTF-8 BOM** — which several Windows editors write by
   default — made `configparser` fail. The exception was swallowed and the
   defaults were used silently, so editing settings appeared to do nothing. Read
   as `utf-8-sig`, and the failure is now reported instead of hidden.
2. **`HTTPError` is a subclass of `URLError`.** Catching `URLError` first labels
   every server error "no internet connection", which sends the user to debug
   their network while the real problem is a rejected key or an exhausted quota.

The text-capture engine (sending keys, reading the selection through the
clipboard) is carried over from [layoutfix](
https://github.com/mosabah1/layoutfix), where three further bugs were found and
fixed. Its comments explain why each part looks the way it does — read them
before simplifying anything in `copy_selection` or `release_modifiers`.

---

## License

MIT — see [LICENSE](LICENSE).
