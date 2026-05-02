import tkinter as tk
from tkinter import ttk, messagebox
import threading
import serial
import serial.tools.list_ports
import time
import os
import sys
import json
import random
import ctypes

# ── DPI Awareness (deve vir ANTES de qualquer tk.Tk()) ──────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware v2
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from player import MusicPlayer
from ir_config import IRConfig, ACOES
from external_player import ExternalPlayer, MODOS
from extension_api import ExtensionManager
from tray import TrayManager, HAS_PYSTRAY

# ══════════════════════════════════════════
#  Caminhos dinâmicos (relativo ao app.py)
# ══════════════════════════════════════════
# Funciona independente de onde o app for movido.
# Se empacotado com PyInstaller, usa a pasta do executável.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOADS_DIR  = os.path.join(BASE_DIR, "downloads")
EXTENSIONS_DIR = os.path.join(BASE_DIR, "extensions")
CONFIG_PATH    = os.path.join(BASE_DIR, "config.json")

# Garante que as pastas existam
os.makedirs(DOWNLOADS_DIR,  exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)

# ══════════════════════════════════════════
#  Paleta
# ══════════════════════════════════════════
BG     = "#0f0f13"
BG2    = "#17171f"
BG3    = "#1e1e2a"
ACCENT = "#7c3aed"
ACC2   = "#a855f7"
GOLD   = "#f59e0b"
GREEN  = "#22c55e"
RED    = "#ef4444"
TEXT   = "#f1f0fa"
TEXT2  = "#9490b5"
BORDER = "#2e2b45"


# ══════════════════════════════════════════
#  Layout responsivo — helper
# ══════════════════════════════════════════
def _geometry_responsiva(win: tk.Tk | tk.Toplevel,
                          frac_w=0.30, frac_h=0.78,
                          min_w=480, min_h=600):
    """
    Dimensiona e centraliza uma janela proporcionalmente à tela.
    Respeita o DPI real após SetProcessDpiAwareness.
    """
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    w  = max(min_w, int(sw * frac_w))
    h  = max(min_h, int(sh * frac_h))
    x  = (sw - w) // 2
    y  = (sh - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.minsize(min_w, min_h)
    return w, h


# ──────────────────────────────────────────
def _fmt_seg(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


def detectar_arduino():
    for p in serial.tools.list_ports.comports():
        if any(k in p.description.lower()
               for k in ("arduino", "ch340", "usb serial", "ch341")):
            print(f"✅ Arduino: {p.device}")
            return p.device
    portas = list(serial.tools.list_ports.comports())
    return portas[0].device if portas else None


def _ler_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8", errors="replace") as f:
            return json.loads(f.read().strip() or "{}")
    except Exception:
        return {}


def _salvar_config(dados: dict):
    tmp = CONFIG_PATH + ".tmp"
    try:
        base = _ler_config()
        base.update(dados)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(base, f, indent=2, ensure_ascii=True)
        os.replace(tmp, CONFIG_PATH)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")


def _aplicar_noactivate_hwnd(hwnd: int):
    """Aplica WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW num HWND."""
    try:
        GWL_EXSTYLE      = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW  = 0x00040000
        est = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        est = (est | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, est)
    except Exception as e:
        print(f"⚠️  noactivate: {e}")


# ══════════════════════════════════════════
#  Tela de seleção de modo
# ══════════════════════════════════════════
class TelaModo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎧 Arduino Player")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.resultado = None
        _geometry_responsiva(self, frac_w=0.28, frac_h=0.52, min_w=440, min_h=400)
        self._build()

    def _build(self):
        
        tk.Label(self, text="🎧 Arduino Player",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack(pady=(30, 4))
        tk.Label(self, text="Como você quer ouvir música hoje?",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 10)).pack(pady=(0, 20))

        self._card("💾", "Músicas locais",
                   f"Toca arquivos MP3/WAV da pasta  {DOWNLOADS_DIR}",
                   ACCENT, lambda: self._escolher("local", None))

        tk.Label(self, text="── ou controle um app externo ──",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 8)).pack(pady=(12, 8))

        row = tk.Frame(self, bg=BG)
        row.pack()
        for chave, info in MODOS.items():
            self._mini(row, info["icone"], info["nome"], chave)

        tk.Label(self, text="Modo externo: envia teclas de mídia para o app aberto",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 7)).pack(pady=(10, 0))

        # Info da pasta base
        tk.Label(self, text=f"📁 Base: {BASE_DIR}",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 6)).pack(pady=(4, 0))

    def _card(self, icone, titulo, desc, cor, cmd):
        
        f = tk.Frame(self, bg=BG3, cursor="hand2",
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="x", padx=40, pady=2)
        inner = tk.Frame(f, bg=BG3)
        inner.pack(padx=16, pady=12, fill="x")
        tk.Label(inner, text=f"{icone}  {titulo}", bg=BG3, fg=cor,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(inner, text=desc, bg=BG3, fg=TEXT2,
                 font=("Segoe UI", 7),
                 wraplength=380).pack(anchor="w", pady=(2, 0))
        for w in [f, inner] + list(inner.winfo_children()):
            w.bind("<Button-1>", lambda e, c=cmd: c())

    def _mini(self, parent, icone, nome, chave):
        
        f = tk.Frame(parent, bg=BG3, cursor="hand2",
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(side="left", padx=6, ipadx=12, ipady=8)
        tk.Label(f, text=icone, bg=BG3, fg=TEXT,
                 font=("Segoe UI", 16)).pack()
        tk.Label(f, text=nome, bg=BG3, fg=TEXT2,
                 font=("Segoe UI", 8)).pack()
        for w in [f] + list(f.winfo_children()):
            w.bind("<Button-1>", lambda e, k=chave: self._escolher("externo", k))

    def _escolher(self, tipo, chave):
        self.resultado = (tipo, chave)
        self.destroy()


# ══════════════════════════════════════════
#  Janela Config IR
# ══════════════════════════════════════════
class JanelaIR(tk.Toplevel):
    def __init__(self, parent, ir_config):
        super().__init__(parent)
        self.ir_config = ir_config
        self.parent    = parent
        self.title("⚙️ Configurar Controle IR")
        self.configure(bg=BG)
        self.resizable(True, True)
        _geometry_responsiva(self, frac_w=0.32, frac_h=0.55, min_w=500, min_h=440)
        self._build()
        self._refresh()

    def _build(self):
        
        tk.Label(self, text="🎮 Mapeamento de Teclas IR",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(16, 4))
        tk.Label(self, text="Associe cada código IR a uma ação do player",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 9)).pack(pady=(0, 10))

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=16)

        fl = tk.Frame(main, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        fl.pack(fill="both", expand=True)

        cols = ("Código IR", "Ação", "Descrição")
        self.tree = ttk.Treeview(fl, columns=cols, show="headings",
                                 selectmode="browse", height=8)
        for c, w in zip(cols, (130, 130, 220)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")

        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Treeview", background=BG3, foreground=TEXT,
                     fieldbackground=BG3, rowheight=26,
                     font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background=BG2, foreground=ACC2,
                     font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", ACCENT)])

        sb = ttk.Scrollbar(fl, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        form = tk.Frame(main, bg=BG, pady=10)
        form.pack(fill="x")

        tk.Label(form, text="Código IR:", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=4)
        self.entry_cod = tk.Entry(form, bg=BG3, fg=TEXT, insertbackground=TEXT,
                                  relief="flat", font=("Segoe UI", 10),
                                  highlightthickness=1, highlightbackground=BORDER,
                                  width=18)
        self.entry_cod.grid(row=0, column=1, padx=8, sticky="w")
        self.btn_cap = tk.Button(form, text="📡 Capturar",
                                 bg=BG3, fg=ACC2, relief="flat",
                                 font=("Segoe UI", 9), cursor="hand2",
                                 command=self._capturar)
        self.btn_cap.grid(row=0, column=2, padx=4)

        tk.Label(form, text="Ação:", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=4)
        self.combo = ttk.Combobox(form, state="readonly",
                                  font=("Segoe UI", 9), width=26)
        self.combo["values"] = [f"{k}  —  {v}" for k, v in ACOES.items()]
        self.combo.current(0)
        self.combo.grid(row=1, column=1, padx=8, columnspan=2, sticky="w")

        btns = tk.Frame(main, bg=BG)
        btns.pack(fill="x", pady=(4, 12))
        self._btn(btns, "➕ Adicionar", ACCENT, self._adicionar).pack(side="left", padx=(0, 6))
        self._btn(btns, "🗑 Remover",   RED,    self._remover).pack(side="left", padx=(0, 6))
        self._btn(btns, "🔄 Resetar",  BG3,    self._resetar).pack(side="left")

        self.lbl_st = tk.Label(main, text="", bg=BG, fg=GREEN,
                               font=("Segoe UI", 9))
        self.lbl_st.pack()

    def _btn(self, p, t, c, cmd):
        
        return tk.Button(p, text=t, bg=c, fg=TEXT, relief="flat",
                         font=("Segoe UI", 9, "bold"),
                         padx=12, pady=5,
                         cursor="hand2", activebackground=ACC2, command=cmd)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for cod, acao, desc in self.ir_config.listar():
            self.tree.insert("", "end", values=(cod, acao, desc))

    def _adicionar(self):
        cod = self.entry_cod.get().strip().upper()
        if not cod:
            return self._st("⚠️ Digite um código IR", RED)
        acao = self.combo.get().split("  —  ")[0].strip()
        if self.ir_config.mapear(cod, acao):
            self._refresh()
            self.entry_cod.delete(0, "end")
            self._st(f"✅ {cod} → {acao} salvo!", GREEN)

    def _remover(self):
        sel = self.tree.selection()
        if not sel:
            return self._st("⚠️ Selecione um item", RED)
        if self.ir_config.remover(str(self.tree.item(sel[0])["values"][0])):
            self._refresh()
            self._st("🗑 Removido", TEXT2)

    def _resetar(self):
        if messagebox.askyesno("Resetar", "Voltar ao mapeamento padrão?", parent=self):
            self.ir_config.resetar()
            self._refresh()
            self._st("🔄 Resetado para padrão", GOLD)

    def _capturar(self):
        if not getattr(self.parent, "arduino", None):
            return self._st("❌ Arduino não conectado", RED)
        self.parent.capturar_proximo_ir(self._receber)
        self.btn_cap.config(text="⏳ Aguardando...", state="disabled")
        self._st("📡 Pressione uma tecla...", GOLD)

    def _receber(self, cod):
        self.entry_cod.delete(0, "end")
        self.entry_cod.insert(0, cod)
        self.btn_cap.config(text="📡 Capturar", state="normal")
        self._st(f"✅ Capturado: {cod}", GREEN)

    def _st(self, msg, cor=GREEN):
        self.lbl_st.config(text=msg, fg=cor)
        self.after(4000, lambda: self.lbl_st.config(text=""))


# ══════════════════════════════════════════
#  Janela de extensões
# ══════════════════════════════════════════
class JanelExtensoes(tk.Toplevel):
    def __init__(self, parent, manager):
        super().__init__(parent)
        self.manager = manager
        self.parent  = parent
        self.title("🧩 Extensões")
        self.configure(bg=BG)
        self.resizable(True, True)
        _geometry_responsiva(self, frac_w=0.38, frac_h=0.60, min_w=520, min_h=480)
        self._build()
        self._refresh()

    def _build(self):
        
        tk.Label(self, text="🧩 Extensões instaladas",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(16, 2))
        tk.Label(self, text=f"Pasta: {EXTENSIONS_DIR}",
                 bg=BG, fg=TEXT2,
                 font=("Segoe UI", 7)).pack(pady=(0, 10))

        lf = tk.Frame(self, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="both", expand=True, padx=16)

        cols = ("Arquivo", "Nome", "Versão", "Status")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings",
                                 selectmode="browse", height=10)
        for c, w in zip(cols, (140, 160, 60, 80)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")

        st = ttk.Style()
        st.configure("Treeview", background=BG3, foreground=TEXT,
                     fieldbackground=BG3, rowheight=26,
                     font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background=BG2, foreground=ACC2,
                     font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", ACCENT)])

        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btns = tk.Frame(self, bg=BG, pady=8)
        btns.pack(fill="x", padx=16)
        for txt, cor, cmd in [
            ("✅ Ligar",       GREEN, self._ligar),
            ("🔴 Desligar",   RED,   self._desligar),
            ("🔄 Hot-reload", GOLD,  self._reload),
        ]:
            tk.Button(btns, text=txt, bg=cor, fg=TEXT, relief="flat",
                      font=("Segoe UI", 9, "bold"),
                      padx=10, pady=5,
                      cursor="hand2", command=cmd).pack(side="left", padx=(0, 4))
        tk.Button(btns, text="🔃 Atualizar", bg=BG3, fg=TEXT2, relief="flat",
                  font=("Segoe UI", 9),
                  padx=10, pady=5,
                  cursor="hand2", command=self._refresh).pack(side="right")

        log_f = tk.Frame(self, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
        log_f.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(log_f, text="Log:", bg=BG2, fg=TEXT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=6, pady=(4, 0))
        self._log_lbl = tk.Label(log_f, text="", bg=BG2, fg=GREEN,
                                 font=("Courier", 7),
                                 justify="left", anchor="w", wraplength=520)
        self._log_lbl.pack(fill="x", padx=6, pady=(0, 6))
        self.manager.set_log_widget(self._log_lbl)
        self._loop_log()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for info in self.manager.descobrir():
            status = "✅ ON" if info["carregado"] else "⭕ OFF"
            self.tree.insert("", "end", iid=info["arquivo"],
                             values=(info["arquivo"], info["nome"],
                                     info["versao"], status))

    def _selecionado(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _ligar(self):
        arq = self._selecionado()
        if arq:
            self.manager.carregar(arq)
            self.parent._salvar_extensoes_ativas()
            self._refresh()

    def _desligar(self):
        arq = self._selecionado()
        if arq:
            self.manager.descarregar(arq)
            self.parent._salvar_extensoes_ativas()
            self._refresh()

    def _reload(self):
        arq = self._selecionado()
        if arq:
            self.manager.hot_reload(arq)
            self.parent._salvar_extensoes_ativas()
            self._refresh()

    def _loop_log(self):
        if not self.winfo_exists():
            return
        try:
            self._log_lbl.config(text="\n".join(self.manager._log_lines[-8:]))
        except Exception:
            pass
        self.after(800, self._loop_log)


# ══════════════════════════════════════════
#  App principal
# ══════════════════════════════════════════
class App(tk.Tk):
    def __init__(self, modo: str, chave_ext: str | None):
        super().__init__()

        self.modo_tipo   = modo
        self.chave_ext   = chave_ext
        self.ir_config   = IRConfig(CONFIG_PATH)
        self._captura_cb = None
        self._vivo       = True
        self._ir_ativo   = False

        cfg  = _ler_config()
        pref = cfg.get("preferencias", {})

        # ── Player ──────────────────────────────
        if modo == "local":
            self.player = MusicPlayer(DOWNLOADS_DIR, CONFIG_PATH)
            self.player.autoplay   = pref.get("autoplay", True)
            self.player.autopass   = pref.get("autopass", True)
            self.player.velocidade = pref.get("velocidade", 1.0)
            self.ext = None
            if not self.player.autoplay:
                self.player.pausar()
        else:
            self.player = None
            self.ext    = ExternalPlayer(chave_ext)
            ok, msg = self.ext.dependencias_ok()
            if not ok:
                messagebox.showwarning("Dependência faltando",
                    f"Instale:\n\n  {msg}")
            elif not self.ext.tem_controle_volume():
                messagebox.showinfo("Volume",
                    "pycaw não encontrado.\nInstale: pip install pycaw")

        # ── Arduino ─────────────────────────────
        self.porta   = detectar_arduino()
        self.arduino = None
        self._conectar_arduino()

        # ── Janela ──────────────────────────────
        titulo = "🎧 Arduino Player"
        if modo == "externo":
            titulo += f"  [{self.ext.nome}]"
        self.title(titulo)
        self.configure(bg=BG)
        self.resizable(True, True)
        _geometry_responsiva(self, frac_w=0.30, frac_h=0.80, min_w=480, min_h=600)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        # Estado lista
        self._lista_cache: list[str] = []
        self._indices_lista: list[int] = []
        self._tab_ativa = tk.StringVar(value="playlist")

        self._build_ui()

        # ── Extensões ───────────────────────────
        self._ext_manager = ExtensionManager(self, self._ext_widget_frame,
                                             ext_dir=EXTENSIONS_DIR)
        self._ext_manager.set_log_widget(self._ext_log_lbl)
        self._carregar_extensoes_salvas()

        self.after(250, self._aplicar_noactivate)
        self.after(500, self._loop_ui)

        # ── Tray ────────────────────────────────
        self._tray = TrayManager(self, "Arduino Player")
        self.after(2000, self._atualizar_tray)

        if self.arduino:
            threading.Thread(target=self._loop_serial, daemon=True).start()

    # ─────────────────────────────────────────
    # 🔌 Arduino
    # ─────────────────────────────────────────
    def _conectar_arduino(self):
        if not self.porta:
            return
        try:
            self.arduino = serial.Serial(self.porta, 9600, timeout=0.1)
            time.sleep(2)
            print(f"✅ Serial: {self.porta}")
        except Exception as e:
            print(f"Erro serial: {e}")
            self.arduino = None

    def capturar_proximo_ir(self, cb):
        self._captura_cb = cb

    # ─────────────────────────────────────────
    # 🏗️ UI
    # ─────────────────────────────────────────
    def _build_ui(self):
        

        # ── Header ──────────────────────────────
        hdr = tk.Frame(self, bg=BG2, pady=10)
        hdr.pack(fill="x")

        badge_txt = "💾 Local" if self.modo_tipo == "local" \
                    else f"{self.ext.icone} {self.ext.nome}"
        badge_cor = ACCENT if self.modo_tipo == "local" else GREEN

        tk.Label(hdr, text="🎧 Arduino Player",
                 bg=BG2, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack()

        row = tk.Frame(hdr, bg=BG2)
        row.pack(pady=(3, 0))
        tk.Label(row, text=badge_txt, bg=badge_cor, fg=TEXT,
                 font=("Segoe UI", 8, "bold"),
                 padx=8, pady=2).pack(side="left")
        porta_cor = GREEN if self.arduino else RED
        tk.Label(row, text=f"  •  {self.porta or 'sem Arduino'}",
                 bg=BG2, fg=porta_cor,
                 font=("Segoe UI", 8)).pack(side="left", padx=4)
        tk.Button(row, text="↩ Trocar modo",
                  bg=BG3, fg=TEXT2, relief="flat",
                  font=("Segoe UI", 7),
                  cursor="hand2", command=self._trocar_modo).pack(side="left", padx=6)

        # ── Card música ──────────────────────────
        card = tk.Frame(self, bg=BG3, padx=20, pady=12,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=16, pady=(10, 0))
        self.lbl_musica = tk.Label(card, text="Carregando...",
                                   bg=BG3, fg=TEXT,
                                   font=("Segoe UI", 11, "bold"),
                                   wraplength=460, justify="center")
        self.lbl_musica.pack()
        self.lbl_info = tk.Label(card, text="", bg=BG3, fg=TEXT2,
                                 font=("Segoe UI", 8))
        self.lbl_info.pack(pady=(2, 0))

        # ── Barra de progresso (modo local) ──────
        if self.modo_tipo == "local":
            pf = tk.Frame(self, bg=BG, padx=16)
            pf.pack(fill="x", pady=(8, 0))
            tr = tk.Frame(pf, bg=BG)
            tr.pack(fill="x")
            self.lbl_pos = tk.Label(tr, text="0:00", bg=BG, fg=TEXT2,
                                    font=("Segoe UI", 8))
            self.lbl_pos.pack(side="left")
            self.lbl_dur = tk.Label(tr, text="0:00", bg=BG, fg=TEXT2,
                                    font=("Segoe UI", 8))
            self.lbl_dur.pack(side="right")
            self.canvas_prog = tk.Canvas(pf, height=6, bg=BG3,
                                         highlightthickness=0, cursor="hand2")
            self.canvas_prog.pack(fill="x", pady=(4, 0))
            self.canvas_prog.bind("<Button-1>", self._seek_click)
            self._barra_w = 0

        # ── Volume ───────────────────────────────
        vf = tk.Frame(self, bg=BG, padx=16, pady=4)
        vf.pack(fill="x")
        tk.Label(vf, text="🔉", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 11)).pack(side="left")
        self.lbl_volume = tk.Label(vf, text="...", bg=BG, fg=ACC2,
                                   font=("Segoe UI", 9, "bold"), width=5)
        self.slider_vol = ttk.Scale(vf, from_=0, to=100, orient="horizontal",
                                    command=self._on_slider_vol)
        ttk.Style().configure("TScale", background=BG)
        vol_ini = self.ext.get_volume_pct() if self.modo_tipo == "externo" \
                  else (self.player.get_volume_pct() if self.player else 50)
        self.slider_vol.set(vol_ini)
        self.slider_vol.pack(side="left", fill="x", expand=True, padx=8)
        tk.Label(vf, text="🔊", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 11)).pack(side="left")
        self.lbl_volume.pack(side="left", padx=(6, 0))

        # ── Controles ────────────────────────────
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(pady=6)
        self._cbtn(ctrl, "⏮", self._cmd_anterior).pack(side="left", padx=5)
        self._cbtn(ctrl, "▶/⏸", self._cmd_play,
                   large=True, cor=ACCENT).pack(side="left", padx=5)
        self._cbtn(ctrl, "⏭", self._cmd_proxima).pack(side="left", padx=5)

        # ── Extra ────────────────────────────────
        ex = tk.Frame(self, bg=BG)
        ex.pack(pady=3)
        self.btn_shuffle = tk.Button(ex, text="🔀 Aleatório",
                                     bg=BG3, fg=TEXT2, relief="flat",
                                     font=("Segoe UI", 9),
                                     padx=10, pady=4,
                                     cursor="hand2", command=self._toggle_shuffle)
        self.btn_shuffle.pack(side="left", padx=4)
        if self.modo_tipo != "local":
            self.btn_shuffle.config(state="disabled", fg=BORDER)
        tk.Button(ex, text="⚙️ Config IR",
                  bg=BG3, fg=TEXT2, relief="flat",
                  font=("Segoe UI", 9),
                  padx=10, pady=4, cursor="hand2",
                  command=lambda: JanelaIR(self, self.ir_config)).pack(side="left", padx=4)

        # ── Config ───────────────────────────────
        self._build_painel_config()

        # ── Conteúdo principal ───────────────────
        if self.modo_tipo == "local":
            self._build_tabs()
        else:
            self._build_info_externo()

        # ── Extensões ────────────────────────────
        self._ext_widget_frame = tk.Frame(self, bg=BG)
        self._ext_log_lbl = tk.Label(self, text="", bg=BG, fg=TEXT2,
                                     font=("Courier", 7))
        self._build_painel_extensoes()

        # ── Toast ────────────────────────────────
        self._toast_lbl = tk.Label(self, text="", bg=BG, fg=GREEN,
                                   font=("Segoe UI", 8), pady=2)
        self._toast_lbl.pack(fill="x", padx=16, pady=(0, 4))

    def _cbtn(self, p, txt, cmd, large=False, cor=BG3):
        
        return tk.Button(p, text=txt, bg=cor, fg=TEXT, relief="flat",
                         font=("Segoe UI", (13 if large else 11), "bold"),
                         padx=(14 if large else 10), pady=7,
                         cursor="hand2", activebackground=ACC2, command=cmd)

    # ── Painel config ─────────────────────────
    def _build_painel_config(self):
        cfg = _ler_config().get("preferencias", {})

        pf = tk.Frame(self, bg=BG2, padx=16, pady=8,
                      highlightthickness=1, highlightbackground=BORDER)
        pf.pack(fill="x", padx=16, pady=(6, 2))

        tk.Label(pf, text="⚙️ Configurações", bg=BG2, fg=TEXT2,
                 font=("Segoe UI", 8, "bold")).grid(
                 row=0, column=0, columnspan=7, sticky="w", pady=(0, 6))

        self.var_autoplay = tk.BooleanVar(value=cfg.get("autoplay", True))
        tk.Checkbutton(pf, text="▶ Autoplay", variable=self.var_autoplay,
                       bg=BG2, fg=TEXT, selectcolor=BG3,
                       activebackground=BG2, activeforeground=TEXT,
                       font=("Segoe UI", 9),
                       command=self._salvar_prefs).grid(row=1, column=0, sticky="w",
                                                        padx=(0, 12))

        self.var_autopass = tk.BooleanVar(value=cfg.get("autopass", True))
        tk.Checkbutton(pf, text="⏭ Autopass", variable=self.var_autopass,
                       bg=BG2, fg=TEXT, selectcolor=BG3,
                       activebackground=BG2, activeforeground=TEXT,
                       font=("Segoe UI", 9),
                       command=self._salvar_prefs).grid(row=1, column=1, sticky="w",
                                                        padx=(0, 16))

        tk.Label(pf, text="🏎 Vel:", bg=BG2, fg=TEXT2,
                 font=("Segoe UI", 9)).grid(row=1, column=2,
                                                    sticky="e", padx=(0, 4))
        self.lbl_vel = tk.Label(pf, text=f"{cfg.get('velocidade', 1.0):.2f}x",
                                bg=BG2, fg=GOLD,
                                font=("Segoe UI", 9, "bold"), width=5)
        self.slider_vel = ttk.Scale(pf, from_=0.5, to=2.0, orient="horizontal",
                                    length=110, command=self._on_slider_vel)
        self.slider_vel.set(cfg.get("velocidade", 1.0))
        self.slider_vel.grid(row=1, column=3, padx=4)
        self.lbl_vel.grid(row=1, column=4, padx=(4, 0))
        tk.Button(pf, text="1×", bg=BG3, fg=TEXT2, relief="flat",
                  font=("Segoe UI", 8), padx=4, pady=2, cursor="hand2",
                  command=self._reset_vel).grid(row=1, column=5, padx=(4, 0))

        # Info pasta
        tk.Label(pf, text=f"📁 {BASE_DIR}", bg=BG2, fg=TEXT2,
                 font=("Segoe UI", 6)).grid(row=2, column=0, columnspan=6,
                                                    sticky="w", pady=(6, 0))

        if self.modo_tipo != "local":
            self.slider_vel.config(state="disabled")
            self.btn_shuffle.config(state="disabled")

    def _on_slider_vel(self, val):
        v = round(float(val), 2)
        self.lbl_vel.config(text=f"{v:.2f}x")
        if self.modo_tipo == "local":
            self.player.set_velocidade(v)
        self._salvar_prefs()

    def _reset_vel(self):
        self.slider_vel.set(1.0)

    def _salvar_prefs(self):
        _salvar_config({"preferencias": {
            "autoplay":   self.var_autoplay.get(),
            "autopass":   self.var_autopass.get(),
            "velocidade": round(float(self.slider_vel.get()), 2),
        }})
        if self.modo_tipo == "local":
            self.player.autoplay = self.var_autoplay.get()
            self.player.autopass = self.var_autopass.get()

    # ── Progresso ────────────────────────────
    def _atualizar_progresso(self):
        if self.modo_tipo != "local" or not self.player.musicas:
            return
        pos = self.player.posicao_seg()
        dur = self.player.duracao_seg()
        self.lbl_pos.config(text=_fmt_seg(pos))
        self.lbl_dur.config(text=_fmt_seg(dur))
        w = self.canvas_prog.winfo_width()
        if w < 2:
            return
        self._barra_w = w
        self.canvas_prog.delete("all")
        self.canvas_prog.create_rectangle(0, 1, w, 5, fill=BG3, outline="")
        pct = self.player.progresso_pct()
        px  = int(pct * w)
        if px > 0:
            self.canvas_prog.create_rectangle(0, 1, px, 5, fill=ACCENT, outline="")
        r = max(4, int(5 * self._s))
        self.canvas_prog.create_oval(px - r, 0, px + r, int(6*self._s),
                                     fill=ACC2, outline="")

    def _seek_click(self, event):
        if self.modo_tipo != "local" or self._barra_w == 0:
            return
        self.player.seek((event.x / self._barra_w) * self.player.duracao_seg())

    # ── Tabs ─────────────────────────────────
    def _build_tabs(self):
        tf = tk.Frame(self, bg=BG, padx=16)
        tf.pack(fill="both", expand=True, pady=(6, 0))

        hd = tk.Frame(tf, bg=BG)
        hd.pack(fill="x")
        tabs = [("playlist", "🎵 Playlist"),
                ("recomendadas", "⭐ Recomendadas"),
                ("favoritas", "❤️ Favoritas")]
        self._tab_btns = {}
        for chave, label in tabs:
            b = tk.Button(hd, text=label,
                          bg=ACCENT if chave == "playlist" else BG3,
                          fg=TEXT   if chave == "playlist" else TEXT2,
                          relief="flat", font=("Segoe UI", 9),
                          padx=11, pady=4, cursor="hand2",
                          command=lambda k=chave: self._trocar_tab(k))
            b.pack(side="left", padx=(0, 3))
            self._tab_btns[chave] = b

        bf = tk.Frame(tf, bg=BG)
        bf.pack(fill="x", pady=(5, 2))
        tk.Label(bf, text="🔍", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 10)).pack(side="left")
        self.entry_busca = tk.Entry(bf, bg=BG3, fg=TEXT,
                                    insertbackground=TEXT, relief="flat",
                                    font=("Segoe UI", 9),
                                    highlightthickness=1, highlightbackground=BORDER)
        self.entry_busca.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.entry_busca.bind("<KeyRelease>",
                              lambda e: self._sincronizar_lista(forcar=True))

        lf = tk.Frame(tf, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="both", expand=True, pady=(2, 8))
        self.listbox = tk.Listbox(lf, bg=BG3, fg=TEXT,
                                  selectbackground=ACCENT, activestyle="none",
                                  font=("Segoe UI", 9),
                                  relief="flat", bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", self._duplo_clique)
        self._sincronizar_lista(forcar=True)

    def _build_info_externo(self):
        
        f = tk.Frame(self, bg=BG3, padx=24, pady=20,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        tk.Label(f, text=f"{self.ext.icone}  {self.ext.nome}",
                 bg=BG3, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))
        for linha in ["Os botões enviam teclas de mídia",
                      f"para o app {self.ext.nome} aberto no PC.", "",
                      "▸  Abra o app antes de usar",
                      "▸  Volume usa Core Audio do sistema"]:
            tk.Label(f, text=linha, bg=BG3,
                     fg=TEXT if linha.startswith("▸") else TEXT2,
                     font=("Segoe UI", 9)).pack(anchor="w")
        tk.Button(f, text=f"🚀 Abrir {self.ext.nome}",
                  bg=ACCENT, fg=TEXT, relief="flat",
                  font=("Segoe UI", 10, "bold"),
                  padx=16, pady=8, cursor="hand2",
                  command=self.ext.abrir_app).pack(pady=(16, 0))

    # ── Lista ─────────────────────────────────
    def _linhas_lista(self):
        tab   = self._tab_ativa.get()
        busca = self.entry_busca.get().lower().strip() \
                if hasattr(self, "entry_busca") else ""
        if tab == "playlist":
            base = [i for i in range(len(self.player.musicas))
                    if not busca or busca in self.player.musicas[i].lower()]
            linhas = []
            for rank, i in enumerate(base):
                nome = os.path.splitext(self.player.musicas[i])[0]
                pref = "▶ " if i == self.player.index else "   "
                linhas.append(f"{pref}{rank+1:02d}. {nome}")
            return linhas, base
        elif tab == "recomendadas":
            idxs = self.player.recomendadas(15)
            linhas = []
            for rank, i in enumerate(idxs, 1):
                nome  = os.path.splitext(self.player.musicas[i])[0]
                count = self.player.contagem.get(self.player.musicas[i], 0)
                linhas.append(
                    f"  {rank:02d}. {nome}  "
                    f"[{'🆕' if count == 0 else f'{count}x'}]")
            return linhas, idxs
        else:
            idxs = self.player.favoritas(15)
            linhas = [
                f"  {r:02d}. {os.path.splitext(self.player.musicas[i])[0]}"
                f"  [{self.player.contagem.get(self.player.musicas[i], 0)}x]"
                for r, i in enumerate(idxs, 1)
            ]
            return linhas or ["   Nenhuma música ouvida ainda"], idxs

    def _sincronizar_lista(self, forcar=False):
        if self.modo_tipo != "local":
            return
        novas, indices = self._linhas_lista()
        self._indices_lista = indices
        if not forcar and novas == self._lista_cache:
            return
        yv  = self.listbox.yview()
        sel = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for i, linha in enumerate(novas):
            self.listbox.insert("end", linha)
            if indices and i < len(indices) and indices[i] == self.player.index:
                self.listbox.itemconfig(i, fg=ACC2)
        self.listbox.yview_moveto(yv[0])
        if sel and sel[0] < len(novas):
            self.listbox.selection_set(sel[0])
        self._lista_cache = novas

    def _trocar_tab(self, tab):
        self._tab_ativa.set(tab)
        for k, b in self._tab_btns.items():
            b.config(bg=ACCENT if k == tab else BG3,
                     fg=TEXT   if k == tab else TEXT2)
        self._lista_cache = []
        self._sincronizar_lista(forcar=True)

    def _duplo_clique(self, _):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self._indices_lista):
            self.player.tocar_indice(self._indices_lista[sel[0]])
            self._trocar_tab("playlist")

    # ── Extensões painel ──────────────────────
    def _build_painel_extensoes(self):
        outer = tk.Frame(self, bg=BG, padx=16)
        outer.pack(fill="x", pady=(4, 0))

        hdr = tk.Frame(outer, bg=BG2, highlightthickness=1,
                       highlightbackground=BORDER)
        hdr.pack(fill="x")

        self._ext_aberto = tk.BooleanVar(value=False)
        body = tk.Frame(outer, bg=BG3, highlightthickness=1,
                        highlightbackground=BORDER)

        self._ext_widget_frame = tk.Frame(body, bg=BG3)
        self._ext_widget_frame.pack(fill="x", padx=8, pady=4)
        self._ext_log_lbl = tk.Label(body, text="", bg=BG3, fg=TEXT2,
                                     font=("Courier", 7),
                                     justify="left", anchor="w",
                                     wraplength=470)
        self._ext_log_lbl.pack(fill="x", padx=8, pady=(0, 6))

        def toggle():
            if self._ext_aberto.get():
                body.pack_forget()
                self._ext_aberto.set(False)
                btn_t.config(text="▶ Extensões")
            else:
                body.pack(fill="both")
                self._ext_aberto.set(True)
                btn_t.config(text="▼ Extensões")

        btn_t = tk.Button(hdr, text="▶ Extensões", bg=BG2, fg=TEXT2,
                          relief="flat", font=("Segoe UI", 8, "bold"),
                          padx=10, pady=4,
                          cursor="hand2", command=toggle)
        btn_t.pack(side="left")
        tk.Button(hdr, text="⚙ Gerenciar", bg=BG2, fg=ACC2, relief="flat",
                  font=("Segoe UI", 8), cursor="hand2",
                  command=self._abrir_painel_extensoes).pack(side="right", padx=6)

    def _abrir_painel_extensoes(self):
        JanelExtensoes(self, self._ext_manager)

    def _carregar_extensoes_salvas(self):
        for arq in _ler_config().get("extensoes_ativas", []):
            if os.path.exists(os.path.join(EXTENSIONS_DIR, arq)):
                self._ext_manager.carregar(arq)

    def _salvar_extensoes_ativas(self):
        _salvar_config({"extensoes_ativas":
                        list(self._ext_manager._loaded.keys())})

    # ── Toast ─────────────────────────────────
    def _mostrar_toast(self, msg: str, cor: str = "#22c55e", ms: int = 3000):
        if not self._vivo:
            return
        try:
            self._toast_lbl.config(text=msg, fg=cor)
            if hasattr(self, "_toast_after"):
                try:
                    self.after_cancel(self._toast_after)
                except Exception:
                    pass
            self._toast_after = self.after(
                ms, lambda: self._toast_lbl.config(text=""))
        except Exception:
            pass

    # ─────────────────────────────────────────
    # 🔄 Loop UI
    # ─────────────────────────────────────────
    def _loop_ui(self):
        if not self._vivo:
            return
        if self.modo_tipo == "local":
            p = self.player
            self.lbl_musica.config(text=f"🎵 {p.musica_atual()}")
            estado = ("⏸ Pausado" if p.esta_pausado()
                      else "▶ Tocando" if p.esta_tocando()
                      else "⏹ Parado")
            self.lbl_info.config(
                text=f"{p.total_musicas()} músicas  •  {estado}  •  "
                     f"{'🔀' if p.modo_shuffle else '🔢'}  •  {p.velocidade:.2f}x"
            )
            self._atualizar_progresso()
            self._sincronizar_lista()
            if p.autopass and p.checar_fim():
                p.proxima()
            if not hasattr(self, "_ultimo_index"):
                self._ultimo_index = -1
            if p.musicas and p.index != self._ultimo_index:
                self._ultimo_index = p.index
                if hasattr(self, "_ext_manager"):
                    self._ext_manager.emitir("musica_mudou",
                        {"nome": p.musica_atual(), "index": p.index})
        else:
            self.lbl_musica.config(text=self.ext.musica_atual())
            vol_real = self.ext.get_volume_pct()
            src = "Core Audio" if self.ext.tem_controle_volume() else "sem vol"
            self.lbl_info.config(text=f"Modo externo  •  🔊 {vol_real}%  •  {src}")
            try:
                self.slider_vol.set(vol_real)
                self.lbl_volume.config(text=f"{vol_real}%")
            except tk.TclError:
                pass
        self.after(500, self._loop_ui)

    # ─────────────────────────────────────────
    # 🎚️ Volume
    # ─────────────────────────────────────────
    def _on_slider_vol(self, val):
        if not self._vivo:
            return
        pct = int(float(val))
        self.lbl_volume.config(text=f"{pct}%")
        if self.modo_tipo == "local":
            self.player.set_volume(pct / 100)
        else:
            self.ext.set_volume(pct)

    def _set_volume_ext(self, pct: int):
        if not self._vivo:
            return
        try:
            if self.modo_tipo == "local":
                self.player.set_volume(pct / 100)
            else:
                self.ext.set_volume(pct)
            self.slider_vol.set(pct)
            self.lbl_volume.config(text=f"{pct}%")
        except tk.TclError:
            pass

    def _get_vol_pct(self) -> int:
        if self.modo_tipo == "local":
            return self.player.get_volume_pct()
        return self.ext.get_volume_pct()

    # ─────────────────────────────────────────
    # 🎮 Comandos
    # ─────────────────────────────────────────
    def _cmd_play(self):
        (self.player if self.modo_tipo == "local" else self.ext).continuar()

    def _cmd_proxima(self):
        (self.player if self.modo_tipo == "local" else self.ext).proxima()

    def _cmd_anterior(self):
        (self.player if self.modo_tipo == "local" else self.ext).anterior()

    def _toggle_shuffle(self):
        if self.modo_tipo != "local":
            return
        ativo = self.player.toggle_shuffle()
        self.btn_shuffle.config(
            bg=ACCENT if ativo else BG3,
            fg=TEXT   if ativo else TEXT2,
            text="🔀 Aleatório ON" if ativo else "🔀 Aleatório")

    def _tocar_recomendada(self):
        if self.modo_tipo != "local":
            return
        idxs = self.player.recomendadas(5)
        if idxs:
            self.player.tocar_indice(random.choice(idxs))

    # ─────────────────────────────────────────
    # 🏷️ Tray
    # ─────────────────────────────────────────
    def _atualizar_tray(self):
        if not self._vivo:
            return
        if hasattr(self, "_tray") and self._tray:
            if self.modo_tipo == "local" and self.player:
                txt = f"🎵 {self.player.musica_atual()}"
            elif self.ext:
                txt = f"{self.ext.icone} {self.ext.nome}"
            else:
                txt = "Arduino Player"
            self._tray.atualizar_tooltip(txt)
        self.after(2000, self._atualizar_tray)

    def _cmd_bg_proxima(self):
        self._cmd_bg(self._cmd_proxima)

    def _cmd_bg_anterior(self):
        self._cmd_bg(self._cmd_anterior)

    # ─────────────────────────────────────────
    # 🪟 Win32 / NOACTIVATE
    # ─────────────────────────────────────────
    def _aplicar_noactivate(self):
        try:
            hwnd = int(self.frame(), 16)
            _aplicar_noactivate_hwnd(hwnd)
            print("✅ WS_EX_NOACTIVATE aplicado")
        except Exception as e:
            print(f"⚠️  noactivate: {e}")

    def _cmd_bg(self, fn):
        def _run():
            if not self._vivo:
                return
            try:
                hwnd = int(self.frame(), 16)
                ctypes.windll.user32.SetWindowPos(
                    hwnd, None, 0, 0, 0, 0,
                    0x0010 | 0x0002 | 0x0001 | 0x0004  # NOACTIVATE|NOMOVE|NOSIZE|NOZORDER
                )
            except Exception:
                pass
            try:
                fn()
            except Exception as e:
                print(f"[cmd_bg] {e}")
        self.after(0, _run)

    # ─────────────────────────────────────────
    # 📡 IR
    # ─────────────────────────────────────────
    def _processar_ir(self, cod):
        if not self._vivo:
            return
        acao = self.ir_config.resolver(cod)
        if not acao:
            return
        threading.Thread(target=self._executar_acao_ir,
                         args=(acao,), daemon=True).start()

    def _executar_acao_ir(self, acao: str):
        if not self._vivo:
            return
        if acao == "PLAY_PAUSE":
            if self.modo_tipo == "local" and self.player:
                self._cmd_bg(self.player.continuar)
            elif self.ext:
                self.ext.continuar()
        elif acao == "NEXT":
            if self.modo_tipo == "local" and self.player:
                self._cmd_bg(self.player.proxima)
            elif self.ext:
                self.ext.proxima()
        elif acao == "PREV":
            if self.modo_tipo == "local" and self.player:
                self._cmd_bg(self.player.anterior)
            elif self.ext:
                self.ext.anterior()
        elif acao == "SHUFFLE":
            if self.modo_tipo == "local" and self.player:
                def _do():
                    ativo = self.player.toggle_shuffle()
                    self._atualizar_btn_shuffle(ativo)
                self._cmd_bg(_do)
        elif acao == "RECOMENDA":
            if self.modo_tipo == "local" and self.player:
                def _do():
                    idxs = self.player.recomendadas(5)
                    if idxs:
                        self.player.tocar_indice(random.choice(idxs))
                self._cmd_bg(_do)
        elif acao == "VOL_UP":
            novo = min(100, self._get_vol_pct() + 10)
            if self.modo_tipo == "local" and self.player:
                self._cmd_bg(lambda v=novo: (self.player.set_volume(v/100),
                                              self._atualizar_slider_silencioso(v)))
            elif self.ext:
                self.ext.set_volume(novo)
                self._cmd_bg(lambda v=novo: self._atualizar_slider_silencioso(v))
        elif acao == "VOL_DOWN":
            novo = max(0, self._get_vol_pct() - 10)
            if self.modo_tipo == "local" and self.player:
                self._cmd_bg(lambda v=novo: (self.player.set_volume(v/100),
                                              self._atualizar_slider_silencioso(v)))
            elif self.ext:
                self.ext.set_volume(novo)
                self._cmd_bg(lambda v=novo: self._atualizar_slider_silencioso(v))

    def _atualizar_btn_shuffle(self, ativo: bool):
        if not self._vivo:
            return
        try:
            self.btn_shuffle.config(
                bg=ACCENT if ativo else BG3,
                fg=TEXT   if ativo else TEXT2,
                text="🔀 Aleatório ON" if ativo else "🔀 Aleatório")
        except tk.TclError:
            pass

    def _atualizar_slider_silencioso(self, pct: int):
        if not self._vivo:
            return
        try:
            self.slider_vol.set(pct)
            self.lbl_volume.config(text=f"{pct}%")
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    # 🔌 Serial
    # ─────────────────────────────────────────
    def _loop_serial(self):
        while self._vivo:
            try:
                if self.arduino and self.arduino.in_waiting:
                    linha = self.arduino.readline().decode(errors="ignore").strip()
                    print("Arduino:", linha)
                    if hasattr(self, "_ext_manager"):
                        self._ext_manager.emitir("serial_linha", {"linha": linha})
                    if linha.startswith("POT:"):
                        val = int(linha.split(":")[1])
                        pct = int((val / 1023) * 100)
                        self.after(0, lambda p=pct: self._set_volume_ext(p))
                        if hasattr(self, "_ext_manager"):
                            self._ext_manager.emitir("volume_mudou", {"pct": pct})
                    elif linha.startswith("IR:"):
                        cod = linha.split(":", 1)[1].strip()
                        if self._captura_cb:
                            cb = self._captura_cb
                            self._captura_cb = None
                            self.after(0, lambda c=cod: cb(c))
                        else:
                            acao = self.ir_config.resolver(cod)
                            if hasattr(self, "_ext_manager"):
                                self._ext_manager.emitir("ir_recebido",
                                    {"codigo": cod, "acao": acao})
                            self.after(0, lambda c=cod: self._processar_ir(c))
                time.sleep(0.02)
            except Exception as e:
                if self._vivo:
                    print("Erro serial:", e)
                break

    # ─────────────────────────────────────────
    # ↩ Fechar / Trocar
    # ─────────────────────────────────────────
    def _trocar_modo(self):
        if hasattr(self, "_tray"):
            self._tray.parar()
        self._fechar(reiniciar=True)

    def _fechar(self, reiniciar=False):
        self._vivo = False
        if hasattr(self, "_tray"):
            self._tray.parar()
        if hasattr(self, "_ext_manager"):
            self._ext_manager.descarregar_todas()
        if self.modo_tipo == "local" and self.player:
            self.player.destruir()
        if self.arduino:
            try:
                self.arduino.close()
            except Exception:
                pass
        self.destroy()
        if reiniciar:
            main()


# ══════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════
def main():
    seletor = TelaModo()
    seletor.mainloop()
    if seletor.resultado is None:
        return
    tipo, chave = seletor.resultado
    App(tipo, chave).mainloop()


if __name__ == "__main__":
    main()