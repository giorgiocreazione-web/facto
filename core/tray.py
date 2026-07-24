#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — «sempre acceso», OPT-IN (decisione Gio 23 lug: icona vicino
all'orologio + opt-in).

  facto tray on       attiva l'avvio al login e (Windows) accende SUBITO
                      l'icona vicino all'orologio
  facto tray off      spegne tutto (autostart via; l'icona muore al Quit)
  facto tray status   cosa è attivo, dove, con quale comando
  facto tray-run      il processo del tray (lo lancia l'autostart, non l'umano)

Windows: icona di sistema VERA in stdlib pura (ctypes + Shell_NotifyIcon):
  doppio click = apre la dashboard nel browser · tasto destro = menu
  (Open dashboard / Quit). Il server web gira in un thread dello stesso
  processo: un solo processo, niente orfani.
macOS / Linux (v1, scelta ratificata): NIENTE icona — l'autostart accende il
  server al login e la dashboard è sempre raggiungibile; l'icona nativa lì
  richiederebbe dipendenze e Facto resta stdlib pura.

Zero dipendenze, come tutto il resto del motore.
"""
import json
import os
import subprocess
import sys

WIN = os.name == "nt"
MAC = sys.platform == "darwin"
LANG = ((os.environ.get("FACTO_LANG") or os.environ.get("REGISTRO_LANG") or "en").strip().lower()[:2])


def T(en, it):
    return it if LANG == "it" else en


# ----------------------------------------------------------------- percorsi
def _porta(root):
    """La porta della dashboard dal config del progetto (default 8780)."""
    try:
        with open(os.path.join(root, "facto.config.json"), encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
        return int(cfg.get("dashboard", {}).get("port", 8780))
    except Exception:
        return 8780


def _pythonw():
    """Su Windows: il python SENZA console accanto a quello attivo (se c'è)."""
    if not WIN:
        return sys.executable
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.isfile(cand) else sys.executable


def _comando_tray(root):
    """La riga che l'autostart lancia: `<python(w)> -m facto tray-run --root <proj>`.
    -m facto: non dipende dal PATH dell'ambiente di login (più fragile del nostro)."""
    return [_pythonw(), "-m", "facto", "tray-run", "--root", root]


# ------------------------------------------------------- autostart per OS
def _win_run_key(set_to=None, delete=False):
    """Legge/scrive/cancella il valore 'Facto' nella chiave Run dell'utente."""
    import winreg
    K = r"Software\Microsoft\Windows\CurrentVersion\Run"
    # CreateKeyEx, non OpenKey: la chiave Run NON esiste su tutti i profili
    # (utenti nuovi, account di servizio, runner headless) e OpenKey esploderebbe
    # con FileNotFoundError. CreateKeyEx la apre se c'è, la crea se manca — ed è
    # la chiave standard dell'utente, non una scrittura invasiva.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, K, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
        if delete:
            try:
                winreg.DeleteValue(k, "Facto")
                return True
            except FileNotFoundError:
                return False
        if set_to is not None:
            winreg.SetValueEx(k, "Facto", 0, winreg.REG_SZ, set_to)
            return True
        try:
            return winreg.QueryValueEx(k, "Facto")[0]
        except FileNotFoundError:
            return None


def _mac_plist_path():
    return os.path.expanduser("~/Library/LaunchAgents/com.facto.tray.plist")


def _linux_desktop_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", "facto.desktop")


def _start_menu_url(root, crea=True):
    """Windows: «Facto Dashboard» nel menu START — un .url con la nostra icona.
    Doppio click = dashboard nel browser (col tray attivo il server c'è sempre).
    Stdlib pura: è un file di testo, niente COM, niente exe."""
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "Microsoft", "Windows", "Start Menu", "Programs")
    p = os.path.join(base, "Facto Dashboard.url")
    if not crea:
        if os.path.isfile(p):
            os.remove(p)
        return p
    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facto.ico")
    os.makedirs(base, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("[InternetShortcut]\n"
                 f"URL=http://127.0.0.1:{_porta(root)}/\n"
                 f"IconFile={ico}\nIconIndex=0\n")
    return p


def autostart_on(root):
    cmd = _comando_tray(root)
    if WIN:
        _win_run_key(set_to=subprocess.list2cmdline(cmd))
        try:
            _start_menu_url(root, crea=True)
        except OSError:
            pass
        return T(f"login autostart ON (registry Run key, user scope) + Start menu entry",
                 f"avvio al login ON (chiave Run del registro, solo utente) + voce nel menu Start")
    if MAC:
        import plistlib
        p = _mac_plist_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            plistlib.dump({"Label": "com.facto.tray", "ProgramArguments": cmd,
                           "RunAtLoad": True, "WorkingDirectory": root}, fh)
        return T(f"login autostart ON ({p})", f"avvio al login ON ({p})")
    p = _linux_desktop_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("[Desktop Entry]\nType=Application\nName=Facto\n"
                 f"Exec={' '.join(cmd)}\nX-GNOME-Autostart-enabled=true\n")
    return T(f"login autostart ON ({p})", f"avvio al login ON ({p})")


def autostart_off():
    if WIN:
        c = _win_run_key(delete=True)
        try:
            _start_menu_url("", crea=False)
        except OSError:
            pass
        return T("login autostart OFF", "avvio al login OFF") if c else \
            T("autostart was not set", "l'avvio al login non era attivo")
    p = _mac_plist_path() if MAC else _linux_desktop_path()
    if os.path.isfile(p):
        os.remove(p)
        return T("login autostart OFF", "avvio al login OFF")
    return T("autostart was not set", "l'avvio al login non era attivo")


def autostart_status():
    if WIN:
        v = _win_run_key()
        return v if isinstance(v, str) else None
    p = _mac_plist_path() if MAC else _linux_desktop_path()
    return p if os.path.isfile(p) else None


# ------------------------------------------------------------ comandi CLI
def cmd_tray(argv, root):
    """facto tray on|off|status [--no-launch]"""
    az = next((a for a in argv if not a.startswith("-")), "status")
    if az == "on":
        print("  [ OK ] " + autostart_on(root))
        if WIN and "--no-launch" not in argv:
            # accendi l'icona SUBITO (processo staccato: sopravvive al terminale)
            try:
                subprocess.Popen(_comando_tray(root),
                                 creationflags=subprocess.DETACHED_PROCESS
                                 | subprocess.CREATE_NEW_PROCESS_GROUP,
                                 close_fds=True)
                print("  [ OK ] " + T("tray icon starting — look next to the clock",
                                      "icona in avvio — guarda vicino all'orologio"))
            except Exception as e:
                print("  [WARN] " + T(f"could not start the tray now ({e}); it will start at next login",
                                      f"non riesco ad avviare il tray ora ({e}); partirà al prossimo login"))
        elif not WIN:
            print("  " + T("(no native icon on this OS in v1 — the dashboard server will run at login;",
                           "(niente icona nativa su questo OS nella v1 — il server dashboard parte al login;"))
            print("  " + T(" open it anytime at http://127.0.0.1:%d/)" % _porta(root),
                           " aprila quando vuoi su http://127.0.0.1:%d/)" % _porta(root)))
        return 0
    if az == "off":
        print("  [ OK ] " + autostart_off())
        if WIN:
            print("  " + T("(if the icon is running now, right-click it → Quit)",
                           "(se l'icona è accesa adesso: tasto destro → Quit)"))
        return 0
    v = autostart_status()
    if v:
        print("  [ ON ] " + T(f"autostart: {v}", f"avvio al login: {v}"))
    else:
        print("  [ OFF] " + T("autostart not set — `facto tray on` to enable",
                              "avvio al login non attivo — `facto tray on` per attivarlo"))
    return 0


# ------------------------------------------------ il processo tray (Windows)
def _serve_in_thread(root, porta):
    """La dashboard nello stesso processo del tray: un solo processo, zero orfani."""
    import threading
    os.chdir(root)                        # il config discovery parte da qui
    try:
        from . import dashboard_server as ds
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dashboard_server as ds
    srv = ds._ServerSenzaDNS(("127.0.0.1", porta), ds.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def tray_run(argv):
    """Processo dell'icona (lanciato dall'autostart o da `tray on`)."""
    root = os.getcwd()
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    porta = _porta(root)
    url = f"http://127.0.0.1:{porta}/"
    if not WIN:
        # v1 non-Windows: solo il server, in foreground (lo gestisce il login manager)
        srv = _serve_in_thread(root, porta)
        import time
        print(f"facto dashboard · {url}")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            srv.shutdown()
        return 0

    # ---------------- Windows: icona vera vicino all'orologio (ctypes puro)
    import ctypes
    from ctypes import wintypes
    import webbrowser
    u32, s32, k32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32

    # DPI-awareness: senza, su schermi scalati (125/150%) i menu del processo
    # vengono upscalati come bitmap -> testo sfocato/illeggibile.
    try:
        u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PerMonitorV2
    except Exception:
        try:
            u32.SetProcessDPIAware()
        except Exception:
            pass

    # FIRME ESPLICITE: su x64 senza restype/argtypes gli HANDLE vengono troncati
    # a 32 bit (int di default) -> menu/finestre corrotti (voci illeggibili).
    HMENU, HWND2 = wintypes.HMENU, wintypes.HWND
    u32.CreatePopupMenu.restype = HMENU
    u32.AppendMenuW.restype = wintypes.BOOL
    u32.AppendMenuW.argtypes = [HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    u32.TrackPopupMenu.restype = ctypes.c_int      # con TPM_RETURNCMD ritorna l'ID scelto
    u32.TrackPopupMenu.argtypes = [HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, HWND2, ctypes.c_void_p]
    u32.DestroyMenu.argtypes = [HMENU]
    u32.InsertMenuItemW.restype = wintypes.BOOL
    u32.InsertMenuItemW.argtypes = [HMENU, wintypes.UINT, wintypes.BOOL, ctypes.c_void_p]
    u32.SetMenuDefaultItem.argtypes = [HMENU, wintypes.UINT, wintypes.UINT]
    u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    u32.SetForegroundWindow.argtypes = [HWND2]
    u32.CreateWindowExW.restype = HWND2
    u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, HWND2, ctypes.c_void_p, wintypes.HINSTANCE,
                                    ctypes.c_void_p]
    u32.DestroyWindow.argtypes = [HWND2]
    u32.LoadImageW.restype = wintypes.HANDLE
    u32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u32.LoadIconW.restype = wintypes.HICON
    u32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]   # 32512 = IDI_APPLICATION
    k32.GetModuleHandleW.restype = wintypes.HINSTANCE
    k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    # LA firma che mancava (causa vera dei menu vuoti): senza argtypes, un lParam
    # che porta un PUNTATORE (64 bit) veniva costretto in un int a 32 bit ->
    # OverflowError a ogni messaggio di sistema -> rendering morto a meta'.
    u32.DefWindowProcW.restype = ctypes.c_longlong
    u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]

    try:
        _serve_in_thread(root, porta)
    except OSError:
        pass                              # porta già occupata: un server c'è già, bene così

    WM_APP_TRAY = 0x8000 + 1
    WM_DESTROY, WM_COMMAND = 0x0002, 0x0111
    WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0203, 0x0205
    ID_OPEN, ID_QUIT = 1, 2

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                    ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD)]

    def _icona():
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facto.ico")
        if os.path.isfile(p):
            h = u32.LoadImageW(None, p, 1, 0, 0, 0x00000010 | 0x00000040)  # ICON, LOADFROMFILE|DEFAULTSIZE
            if h:
                return h
        return u32.LoadIconW(None, 32512)                                   # IDI_APPLICATION

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
    nid = NOTIFYICONDATAW()

    # ---------- menu BRAND (disegnato da noi: immune ai temi rotti, estetica Facto)
    # GDI: firme COMPLETE, restype E argtypes — su x64 ogni handle lasciato al
    # default c_int (32 bit) e' una bomba (visto stasera: 3 sintomi diversi,
    # una sola malattia). Qui non resta nulla di inferito.
    g32 = ctypes.windll.gdi32
    HDC_, HB_, HF_, HGDI = wintypes.HDC, wintypes.HBRUSH, wintypes.HFONT, wintypes.HGDIOBJ
    g32.CreateSolidBrush.restype = HB_
    g32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    g32.CreateFontW.restype = HF_
    g32.CreateFontW.argtypes = [ctypes.c_int] * 11 + [wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]
    g32.SelectObject.restype = HGDI
    g32.SelectObject.argtypes = [HDC_, HGDI]
    g32.DeleteObject.restype = wintypes.BOOL
    g32.DeleteObject.argtypes = [HGDI]
    g32.SetTextColor.restype = wintypes.COLORREF
    g32.SetTextColor.argtypes = [HDC_, wintypes.COLORREF]
    g32.SetBkMode.restype = ctypes.c_int
    g32.SetBkMode.argtypes = [HDC_, ctypes.c_int]
    u32.DrawTextW.restype = ctypes.c_int
    u32.DrawTextW.argtypes = [HDC_, wintypes.LPCWSTR, ctypes.c_int,
                              ctypes.POINTER(wintypes.RECT), wintypes.UINT]
    u32.FillRect.restype = ctypes.c_int
    u32.FillRect.argtypes = [HDC_, ctypes.POINTER(wintypes.RECT), HB_]
    u32.FrameRect.restype = ctypes.c_int
    u32.FrameRect.argtypes = [HDC_, ctypes.POINTER(wintypes.RECT), HB_]
    u32.GetClientRect.restype = wintypes.BOOL
    u32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u32.InvalidateRect.restype = wintypes.BOOL
    u32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.SetFocus.restype = wintypes.HWND
    u32.SetFocus.argtypes = [wintypes.HWND]
    u32.GetDpiForWindow.restype = wintypes.UINT
    u32.GetDpiForWindow.argtypes = [wintypes.HWND]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL),
                    ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                    ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    u32.BeginPaint.restype = HDC_                     # l'HDC 64-bit: il colpevole di stasera
    u32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    u32.EndPaint.restype = wintypes.BOOL
    u32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]

    u32.LoadCursorW.restype = wintypes.HANDLE
    u32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    hwnd_main = [None]                                # la principale, per il Quit dal menu

    VOCI = ["Open dashboard", "Quit Facto"]
    # COLORREF = 0x00BBGGRR — la palette della dashboard
    C_SFONDO, C_BORDO = 0x160E0A, 0x4A3622            # notte + hairline
    C_HOVER, C_TESTO, C_TESTO_HOVER = 0x402C1A, 0xE7DCD6, 0xFFD646
    mstato = {"hwnd": None, "hover": -1, "font": None, "riga_h": 34, "pad": 6}

    def _menu_riga(lp):
        y = (lp >> 16) & 0xFFFF
        r = (y - mstato["pad"]) // mstato["riga_h"]
        return r if 0 <= r < len(VOCI) else -1

    def menu_proc(mh, msg, wp, lp):
        WM_PAINT, WM_MOUSEMOVE, WM_LBUTTONUP = 0x000F, 0x0200, 0x0202
        WM_ACTIVATE, WM_KILLFOCUS = 0x0006, 0x0008
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = u32.BeginPaint(mh, ctypes.byref(ps))
            rc = wintypes.RECT()
            u32.GetClientRect(mh, ctypes.byref(rc))
            b = g32.CreateSolidBrush(C_SFONDO)
            u32.FillRect(hdc, ctypes.byref(rc), b); g32.DeleteObject(b)
            b = g32.CreateSolidBrush(C_BORDO)
            u32.FrameRect(hdc, ctypes.byref(rc), b); g32.DeleteObject(b)
            g32.SetBkMode(hdc, 1)                      # TRANSPARENT
            old = g32.SelectObject(hdc, mstato["font"])
            for i, testo in enumerate(VOCI):
                r = wintypes.RECT(rc.left + 1, mstato["pad"] + i * mstato["riga_h"],
                                  rc.right - 1, mstato["pad"] + (i + 1) * mstato["riga_h"])
                if i == mstato["hover"]:
                    hb = g32.CreateSolidBrush(C_HOVER)
                    u32.FillRect(hdc, ctypes.byref(r), hb); g32.DeleteObject(hb)
                g32.SetTextColor(hdc, C_TESTO_HOVER if i == mstato["hover"] else C_TESTO)
                r.left += 14
                u32.DrawTextW(hdc, testo, -1, ctypes.byref(r), 0x20 | 0x4)  # VCENTER|SINGLELINE
            g32.SelectObject(hdc, old)
            u32.EndPaint(mh, ctypes.byref(ps))
            return 0
        if msg == WM_MOUSEMOVE:
            r = _menu_riga(lp)
            if r != mstato["hover"]:
                mstato["hover"] = r
                u32.InvalidateRect(mh, None, True)
            return 0
        if msg == WM_LBUTTONUP:
            r = _menu_riga(lp)
            u32.DestroyWindow(mh)
            if r == 0:
                webbrowser.open(url)
            elif r == 1:
                u32.DestroyWindow(hwnd_main[0])       # spegne icona + processo
            return 0
        if msg == WM_KILLFOCUS or (msg == WM_ACTIVATE and (wp & 0xFFFF) == 0):
            u32.DestroyWindow(mh)                     # click fuori: si chiude
            return 0
        return u32.DefWindowProcW(mh, msg, wp, lp)

    menu_cb = WNDPROC(menu_proc)                      # riferimento VIVO (niente GC)
    mwc = None                                        # classe registrata al primo uso

    def apri_menu_brand(owner):
        nonlocal mwc
        try:
            dpi = u32.GetDpiForWindow(owner) or 96
        except Exception:
            dpi = 96
        sc = dpi / 96.0
        mstato["riga_h"] = int(34 * sc); mstato["pad"] = int(6 * sc)
        if mstato["font"] is None:
            mstato["font"] = g32.CreateFontW(-int(14 * sc), 0, 0, 0, 400, 0, 0, 0,
                                             0, 0, 0, 5, 0, "Segoe UI")   # 5=CLEARTYPE
        if mwc is None:
            mwc = WNDCLASSW()
            mwc.lpfnWndProc = menu_cb
            mwc.hInstance = k32.GetModuleHandleW(None)
            mwc.lpszClassName = "FactoMenuWnd"
            mwc.hCursor = u32.LoadCursorW(None, 32512)
            u32.RegisterClassW(ctypes.byref(mwc))
        W, H = int(190 * sc), mstato["pad"] * 2 + mstato["riga_h"] * len(VOCI)
        pt = wintypes.POINT(); u32.GetCursorPos(ctypes.byref(pt))
        mstato["hover"] = -1
        mh = u32.CreateWindowExW(0x0008 | 0x0080, "FactoMenuWnd", "", 0x80000000,
                                 pt.x - W + 8, pt.y - H - 4, W, H,
                                 owner, None, mwc.hInstance, None)   # TOPMOST|TOOLWINDOW · POPUP
        mstato["hwnd"] = mh
        u32.ShowWindow(mh, 5)
        u32.SetForegroundWindow(mh)
        u32.SetFocus(mh)

    def wnd_proc(hwnd, msg, wp, lp):
        if msg == WM_APP_TRAY:
            ev = lp & 0xFFFF
            if ev == WM_LBUTTONDBLCLK:
                webbrowser.open(url)
            elif ev == WM_RBUTTONUP:
                # menu DISEGNATO DA NOI: niente TrackPopupMenu — sul campo esistono
                # sistemi (visto il 23 lug) dove i menu Win32 classici renderizzano
                # il testo invisibile. Il nostro popup e' immune E nel brand.
                apri_menu_brand(hwnd)
            return 0
        if msg == WM_DESTROY:
            s32.Shell_NotifyIconW(2, ctypes.byref(nid))      # NIM_DELETE
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    proc = WNDPROC(wnd_proc)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = k32.GetModuleHandleW(None)
    wc.lpszClassName = "FactoTrayWnd"
    u32.RegisterClassW(ctypes.byref(wc))
    hwnd = u32.CreateWindowExW(0, wc.lpszClassName, "Facto", 0, 0, 0, 0, 0,
                               None, None, wc.hInstance, None)
    hwnd_main[0] = hwnd

    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = 0x1 | 0x2 | 0x4                              # MESSAGE | ICON | TIP
    nid.uCallbackMessage = WM_APP_TRAY
    nid.hIcon = _icona()
    nid.szTip = f"Facto — {url}"
    s32.Shell_NotifyIconW(0, ctypes.byref(nid))               # NIM_ADD

    msg = wintypes.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))
    return 0
