"""
tray.py
=======
Gerencia o ícone na bandeja do sistema (system tray).
A janela principal fica oculta por padrão — só aparece
quando o usuário clica no ícone da bandeja.

Dependências: pip install pystray pillow
"""
import threading
import tkinter as tk

try:
    import pystray
    from pystray import MenuItem as TrayItem, Menu as TrayMenu
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    print("⚠️  pystray não instalado — pip install pystray pillow")

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _criar_icone_img(texto: str = "♪", cor_fundo="#7c3aed", cor_texto="#ffffff"):
    """Gera ícone 64×64 com nota musical."""
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Círculo de fundo
    draw.ellipse([2, 2, 62, 62], fill=cor_fundo)
    # Texto centralizado
    try:
        font = ImageFont.truetype("segoeui.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), texto, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) // 2, (64 - th) // 2 - 2), texto,
              fill=cor_texto, font=font)
    return img


class TrayManager:
    """
    Gerencia o ícone na bandeja e o estado de visibilidade da janela.
    A janela principal NUNCA aparece na barra de tarefas.
    """

    def __init__(self, app: tk.Tk, nome: str = "Arduino Player"):
        self._app    = app
        self._nome   = nome
        self._icon   = None
        self._visivel = False
        self._thread  = None

        if not HAS_PYSTRAY or not HAS_PIL:
            print("⚠️  Tray desativado — instale: pip install pystray pillow")
            return

        self._setup_janela()
        self._iniciar_tray()

    # ─────────────────────────────────────────
    # Configuração da janela principal
    # ─────────────────────────────────────────
    def _setup_janela(self):
        app = self._app

        # Remove da barra de tarefas — usa overrideredirect=False mas
        # com withdraw + wm_overrideredirect False para manter decorações
        app.withdraw()                        # começa oculta
        app.wm_attributes("-topmost", False)  # nunca fica em cima

        # Impede que fechar a janela encerre o app — vai para bandeja
        app.protocol("WM_DELETE_WINDOW", self.ocultar)

        # Aplica WS_EX_TOOLWINDOW para não aparecer na barra de tarefas
        # e WS_EX_NOACTIVATE para não roubar foco
        app.after(300, self._aplicar_estilos_win32)

    def _aplicar_estilos_win32(self):
        try:
            import ctypes

            GWL_EXSTYLE        = -20
            WS_EX_TOOLWINDOW   = 0x00000080   # não aparece na taskbar
            WS_EX_NOACTIVATE   = 0x08000000   # não rouba foco nunca
            WS_EX_APPWINDOW    = 0x00040000   # remove da taskbar

            hwnd = int(self._app.frame(), 16)
            est  = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            est  = (est | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, est)
            print("✅ WS_EX_TOOLWINDOW + WS_EX_NOACTIVATE aplicados")
        except Exception as e:
            print(f"⚠️  estilos win32: {e}")

    # ─────────────────────────────────────────
    # Tray icon
    # ─────────────────────────────────────────
    def _iniciar_tray(self):
        img  = _criar_icone_img("♪")
        menu = TrayMenu(
            TrayItem("🎧 Abrir Player",    self._toggle,        default=True),
            TrayMenu.SEPARATOR,
            TrayItem("⏮ Anterior",        self._ir_anterior),
            TrayItem("▶/⏸ Play / Pause",  self._ir_play),
            TrayItem("⏭ Próxima",         self._ir_proxima),
            TrayMenu.SEPARATOR,
            TrayItem("🔊 Volume +10%",     self._vol_up),
            TrayItem("🔉 Volume -10%",     self._vol_down),
            TrayMenu.SEPARATOR,
            TrayItem("❌ Sair",            self._sair),
        )
        self._icon = pystray.Icon(self._nome, img, self._nome, menu)

        # Roda em thread daemon — pystray tem seu próprio loop de eventos
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        print("✅ Tray icon iniciado")

    # ─────────────────────────────────────────
    # Visibilidade da janela
    # ─────────────────────────────────────────
    def mostrar(self):
        """Exibe a janela sem roubar foco."""
        def _do():
            self._app.deiconify()
            self._visivel = True
            # Mostra mas não força foco
            try:
                import ctypes
                SWP_NOACTIVATE = 0x0010
                SWP_NOMOVE     = 0x0002
                SWP_NOSIZE     = 0x0001
                SWP_NOZORDER   = 0x0004
                hwnd = int(self._app.frame(), 16)
                ctypes.windll.user32.SetWindowPos(
                    hwnd, None, 0, 0, 0, 0,
                    SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                )
            except Exception:
                pass
        self._app.after(0, _do)

    def ocultar(self):
        """Oculta a janela (vai para bandeja)."""
        def _do():
            self._app.withdraw()
            self._visivel = False
        self._app.after(0, _do)

    def _toggle(self, icon=None, item=None):
        if self._visivel:
            self.ocultar()
        else:
            self.mostrar()

    # ─────────────────────────────────────────
    # Ações do menu da bandeja
    # (chamadas pela thread do pystray — usam after() para ser seguras)
    # ─────────────────────────────────────────
    def _ir_play(self, *_):
        self._app.after(0, self._app._cmd_play)

    def _ir_proxima(self, *_):
        self._app.after(0, self._app._cmd_bg_proxima)

    def _ir_anterior(self, *_):
        self._app.after(0, self._app._cmd_bg_anterior)

    def _vol_up(self, *_):
        def _do():
            vol = self._app._get_vol_pct()
            self._app._set_volume_ext(min(100, vol + 10))
        self._app.after(0, _do)

    def _vol_down(self, *_):
        def _do():
            vol = self._app._get_vol_pct()
            self._app._set_volume_ext(max(0, vol - 10))
        self._app.after(0, _do)

    def _sair(self, *_):
        self._app.after(0, self._app._fechar)

    # ─────────────────────────────────────────
    # Atualiza tooltip do ícone
    # ─────────────────────────────────────────
    def atualizar_tooltip(self, texto: str):
        if self._icon:
            try:
                # pystray limita tooltip a 63 chars no Windows
                self._icon.title = texto[:63]
            except Exception:
                pass

    def parar(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass