"""
external_player.py
Controla Spotify / YouTube Music / YouTube via teclas de mídia.
Volume controlado via pycaw (compatível com Python 3.13+).

pip install pyautogui pygetwindow pycaw
"""
import time
import threading
import subprocess

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


# ══════════════════════════════════════════════════════════════════════════════
#  Core Audio via pycaw — compatível com Python 3.13+
# ══════════════════════════════════════════════════════════════════════════════
HAS_CORE_AUDIO = False
_volume_ctrl   = None

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    def _connect_audio():
        """
        Conecta ao dispositivo de áudio padrão.
        Usa getattr para compatibilidade com múltiplas versões do pycaw.
        """
        devices = AudioUtilities.GetSpeakers()
        # pycaw < 0.0.9  → devices é IMMDevice direto
        # pycaw >= 0.0.9 → devices tem ._dev ou .dev
        device = getattr(devices, "_dev", None) \
              or getattr(devices, "dev",  None) \
              or devices
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    _volume_ctrl   = _connect_audio()
    HAS_CORE_AUDIO = True
    _vol_test = int(_volume_ctrl.GetMasterVolumeLevelScalar() * 100)
    print(f"✅ Core Audio OK — volume: {_vol_test}%")

except Exception as _e:
    print(f"⚠️  pycaw indisponível ({_e})")
    print("   Instale: pip install pycaw")
    def _connect_audio(): return None


# ── Thread-local: COM é apartment-threaded ────────────────────────────────────
_tlocal = threading.local()

def _get_ctrl():
    """Retorna IAudioEndpointVolume válido para a thread atual."""
    if not HAS_CORE_AUDIO:
        return None
    if not getattr(_tlocal, "ctrl", None):
        try:
            _tlocal.ctrl = _connect_audio()
        except Exception as e:
            print(f"⚠️  audio thread-local: {e}")
            _tlocal.ctrl = None
    return _tlocal.ctrl


# ── API pública ───────────────────────────────────────────────────────────────
def _sys_get_volume() -> int:
    """Retorna volume atual do dispositivo padrão (0–100), ou -1 se indisponível."""
    ctrl = _get_ctrl()
    if ctrl:
        try:
            return int(ctrl.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            pass
    return -1


def _sys_set_volume(pct: int):
    """Define volume do dispositivo padrão (0–100)."""
    pct = max(0, min(100, int(pct)))
    ctrl = _get_ctrl()
    if ctrl:
        try:
            ctrl.SetMasterVolumeLevelScalar(pct / 100.0, None)
        except Exception as e:
            print(f"Erro set_volume: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  Modos suportados
# ══════════════════════════════════════════════════════════════════════════════
MODOS = {
    "spotify":  {"nome": "Spotify",       "icone": "🟢", "janela": "Spotify"},
    "ytmusic":  {"nome": "YouTube Music", "icone": "🔴", "janela": "YouTube Music"},
    "youtube":  {"nome": "YouTube",       "icone": "▶️",  "janela": "YouTube"},
}


def _dependencias_ok() -> tuple[bool, str]:
    f = []
    if not HAS_PYAUTOGUI:   f.append("pyautogui")
    if not HAS_PYGETWINDOW: f.append("pygetwindow")
    return (False, f"pip install {' '.join(f)}") if f else (True, "")


def _media_key(key: str):
    if HAS_PYAUTOGUI:
        try:
            pyautogui.press(key)
        except Exception as e:
            print(f"Erro tecla {key}: {e}")


def _foco_janela(modo: str) -> bool:
    if not HAS_PYGETWINDOW:
        return False
    alvo = MODOS.get(modo, {}).get("janela", "")
    try:
        ws = gw.getWindowsWithTitle(alvo)
        if ws:
            w = ws[0]
            if w.isMinimized:
                w.restore()
            w.activate()
            time.sleep(0.12)
            return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  ExternalPlayer
# ══════════════════════════════════════════════════════════════════════════════
class ExternalPlayer:
    def __init__(self, modo: str = "spotify"):
        self.modo     = modo
        self._info    = MODOS.get(modo, MODOS["spotify"])
        self._tocando = True
        vol = _sys_get_volume()
        self._volume_atual = vol if vol >= 0 else 50

    @property
    def nome(self):  return self._info["nome"]

    @property
    def icone(self): return self._info["icone"]

    def dependencias_ok(self):     return _dependencias_ok()
    def tem_controle_volume(self): return HAS_CORE_AUDIO

    def _cmd(self, key: str):
        threading.Thread(
            target=lambda: (_foco_janela(self.modo), _media_key(key)),
            daemon=True
        ).start()

    def continuar(self):
        self._tocando = not self._tocando
        self._cmd("playpause")

    def pausar(self):
        if self._tocando:
            self._tocando = False
            self._cmd("playpause")

    def proxima(self):  self._cmd("nexttrack")
    def anterior(self): self._cmd("prevtrack")

    def set_volume(self, pct: int):
        _sys_set_volume(pct)
        self._volume_atual = max(0, min(100, int(pct)))

    def get_volume_pct(self) -> int:
        real = _sys_get_volume()
        if real >= 0:
            self._volume_atual = real
        return self._volume_atual

    def musica_atual(self) -> str:
        src = "Core Audio" if HAS_CORE_AUDIO else "sem controle de volume"
        return f"{self.icone} {self.nome}  [{src}]"

    def esta_tocando(self) -> bool:
        return self._tocando

    def abrir_app(self):
        cmds = {
            "spotify":  ["spotify"],
            "ytmusic":  ["start", "https://music.youtube.com"],
            "youtube":  ["start", "https://www.youtube.com"],
        }
        cmd = cmds.get(self.modo)
        if not cmd: return
        try:
            subprocess.Popen(cmd) if self.modo == "spotify" \
                else subprocess.Popen(cmd, shell=True)
        except Exception as e:
            print(f"Erro ao abrir {self.nome}: {e}")