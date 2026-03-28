"""
extension_api.py
================
API exposta para extensões do Arduino Player.

Cada extensão é um arquivo .py na pasta  extensions/
que define uma subclasse de BaseExtension e exporta:

    EXTENSION = MinhaExtension

Ciclo de vida:
    on_load()    → chamado uma vez ao carregar
    on_unload()  → chamado ao desligar/hot-reload
    on_tick()    → chamado a cada ~500ms (na thread da extensão)
    on_event(evento, dados) → chamado para cada evento do app

Eventos disponíveis:
    "musica_mudou"   dados = {"nome": str, "index": int}
    "volume_mudou"   dados = {"pct": int}
    "ir_recebido"    dados = {"codigo": str, "acao": str|None}
    "serial_linha"   dados = {"linha": str}
    "play"           dados = {}
    "pause"          dados = {}
    "modo_mudou"     dados = {"modo": str}
"""

from __future__ import annotations
import threading
import time
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  AppAPI — interface que as extensões recebem
# ══════════════════════════════════════════════════════════════════════════════
class AppAPI:
    """
    Objeto passado para cada extensão com acesso controlado ao app.
    Todas as chamadas que tocam em widgets Tkinter usam .after(0, ...) 
    automaticamente para serem thread-safe.
    """

    def __init__(self, app):
        self._app = app

    # ── Player ────────────────────────────────────────────────────────────────
    def play(self):
        self._app.after(0, self._app._cmd_play)

    def pause(self):
        if self._app.modo_tipo == "local" and self._app.player:
            self._app.after(0, self._app.player.pausar)

    def proxima(self):
        self._app.after(0, self._app._cmd_proxima)

    def anterior(self):
        self._app.after(0, self._app._cmd_anterior)

    def tocar_indice(self, i: int):
        if self._app.modo_tipo == "local" and self._app.player:
            self._app.after(0, lambda: self._app.player.tocar_indice(i))

    def set_volume(self, pct: int):
        self._app.after(0, lambda p=pct: self._app._set_volume_ext(p))

    def get_volume(self) -> int:
        return self._app._get_vol_pct()

    def musica_atual(self) -> str:
        if self._app.modo_tipo == "local" and self._app.player:
            return self._app.player.musica_atual()
        return ""

    def lista_musicas(self) -> list[str]:
        if self._app.modo_tipo == "local" and self._app.player:
            return list(self._app.player.musicas)
        return []

    def modo(self) -> str:
        return self._app.modo_tipo

    # ── Serial ────────────────────────────────────────────────────────────────
    def serial_send(self, texto: str):
        """Envia linha para o Arduino."""
        ar = self._app.arduino
        if ar and ar.is_open:
            try:
                ar.write((texto + "\n").encode())
            except Exception as e:
                print(f"[ext] serial_send erro: {e}")

    def serial_readline(self) -> str | None:
        """
        Lê uma linha da serial SE disponível (não bloqueia).
        Retorna None se não há dados.
        ATENÇÃO: a thread serial principal também lê — use on_event("serial_linha")
        em vez disto quando possível.
        """
        ar = self._app.arduino
        if ar and ar.is_open and ar.in_waiting:
            try:
                return ar.readline().decode(errors="ignore").strip()
            except Exception:
                pass
        return None

    # ── UI ────────────────────────────────────────────────────────────────────
    def adicionar_widget(self, widget_fn):
        """
        Adiciona widget ao painel de extensões.
        widget_fn(parent) → tk.Widget
        Chamado na thread principal via after().
        """
        self._app.after(0, lambda: self._app._ext_manager.montar_widget(widget_fn))

    def toast(self, msg: str, cor: str = "#22c55e", duracao_ms: int = 3000):
        """Exibe mensagem temporária no rodapé do app."""
        self._app.after(0, lambda: self._app._mostrar_toast(msg, cor, duracao_ms))

    def log(self, msg: str):
        """Adiciona linha ao log do painel de extensões."""
        self._app.after(0, lambda m=msg: self._app._ext_manager.log(m))


# ══════════════════════════════════════════════════════════════════════════════
#  BaseExtension — classe base que toda extensão deve herdar
# ══════════════════════════════════════════════════════════════════════════════
class BaseExtension:
    # Metadados (sobrescrever na subclasse)
    NOME        = "Extensão sem nome"
    DESCRICAO   = ""
    VERSAO      = "1.0"
    AUTOR       = ""

    def __init__(self, api: AppAPI):
        self.api = api
        self._ativo = False

    # ── Ciclo de vida (sobrescrever) ──────────────────────────────────────────
    def on_load(self):
        """Chamado uma vez ao carregar. Configure recursos aqui."""
        pass

    def on_unload(self):
        """Chamado ao desligar ou hot-reload. Libere recursos aqui."""
        pass

    def on_tick(self):
        """
        Chamado a cada ~500ms na thread da extensão.
        NÃO mexa em widgets Tkinter aqui — use self.api.toast() etc.
        """
        pass

    def on_event(self, evento: str, dados: dict):
        """
        Chamado para cada evento do app (na thread da extensão).
        eventos: musica_mudou, volume_mudou, ir_recebido,
                 serial_linha, play, pause, modo_mudou
        """
        pass

    def build_widget(self, parent: tk.Frame) -> tk.Widget | None:
        """
        Opcional: retorna um widget para o painel de extensões.
        Chamado na thread principal.
        """
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  ExtensionManager — carrega, gerencia e distribui eventos
# ══════════════════════════════════════════════════════════════════════════════
import importlib.util
import importlib
import sys
import os
import traceback

EXTENSIONS_DIR = "extensions"
WATCHDOG_TIMEOUT = 5.0   # segundos máximos para on_tick / on_event


class _ExtThread(threading.Thread):
    """Thread dedicada a uma extensão com watchdog."""

    def __init__(self, ext: BaseExtension, tick_ms: int = 500):
        super().__init__(daemon=True)
        self.ext      = ext
        self.tick_ms  = tick_ms
        self._vivo    = True
        self._fila: list[tuple[str, dict]] = []
        self._lock    = threading.Lock()

    def enqueue(self, evento: str, dados: dict):
        with self._lock:
            self._fila.append((evento, dados))

    def parar(self):
        self._vivo = False

    def _chamar_com_timeout(self, fn, *args, timeout=WATCHDOG_TIMEOUT):
        resultado = [None]
        erro      = [None]

        def _run():
            try:
                resultado[0] = fn(*args)
            except Exception as e:
                erro[0] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            print(f"[watchdog] {self.ext.NOME}.{fn.__name__} excedeu {timeout}s")
        if erro[0]:
            print(f"[{self.ext.NOME}] erro: {erro[0]}")

    def run(self):
        try:
            self._chamar_com_timeout(self.ext.on_load)
        except Exception as e:
            print(f"[{self.ext.NOME}] on_load erro: {e}")
            return

        while self._vivo:
            # Processa fila de eventos
            with self._lock:
                fila = self._fila[:]
                self._fila.clear()

            for ev, dados in fila:
                if not self._vivo:
                    break
                self._chamar_com_timeout(self.ext.on_event, ev, dados)

            # Tick
            if self._vivo:
                self._chamar_com_timeout(self.ext.on_tick)

            time.sleep(self.tick_ms / 1000)

        try:
            self._chamar_com_timeout(self.ext.on_unload)
        except Exception as e:
            print(f"[{self.ext.NOME}] on_unload erro: {e}")


class ExtensionManager:
    def __init__(self, app, widget_parent: tk.Frame):
        self._app     = app
        self._parent  = widget_parent   # frame onde widgets de ext são montados
        self._loaded: dict[str, tuple[BaseExtension, _ExtThread]] = {}
        self._api     = AppAPI(app)
        self._log_lines: list[str] = []
        self._lbl_log: tk.Label | None = None

        os.makedirs(EXTENSIONS_DIR, exist_ok=True)

    # ── Descoberta ────────────────────────────────────────────────────────────
    def descobrir(self) -> list[dict]:
        """Retorna lista de {arquivo, nome, descricao, versao, carregado}"""
        result = []
        for f in sorted(os.listdir(EXTENSIONS_DIR)):
            if not f.endswith(".py") or f.startswith("_"):
                continue
            info = self._ler_metadados(f)
            info["carregado"] = f in self._loaded
            result.append(info)
        return result

    def _ler_metadados(self, arquivo: str) -> dict:
        """Lê NOME/DESCRICAO/VERSAO/AUTOR sem importar o módulo."""
        path = os.path.join(EXTENSIONS_DIR, arquivo)
        meta = {"arquivo": arquivo, "nome": arquivo, "descricao": "", "versao": "?", "autor": ""}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for linha in f:
                    linha = linha.strip()
                    for campo in ("NOME", "DESCRICAO", "VERSAO", "AUTOR"):
                        if linha.startswith(f"{campo}"):
                            val = linha.split("=", 1)[-1].strip().strip('"\'')
                            meta[campo.lower()] = val
        except Exception:
            pass
        return meta

    # ── Carregar / descarregar ────────────────────────────────────────────────
    def carregar(self, arquivo: str) -> bool:
        if arquivo in self._loaded:
            print(f"[ext] {arquivo} já carregado")
            return True
        try:
            path   = os.path.join(EXTENSIONS_DIR, arquivo)
            spec   = importlib.util.spec_from_file_location(arquivo[:-3], path)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)

            cls = getattr(modulo, "EXTENSION", None)
            if cls is None:
                print(f"[ext] {arquivo} não exporta EXTENSION")
                return False

            ext    = cls(self._api)
            thread = _ExtThread(ext)
            thread.start()

            self._loaded[arquivo] = (ext, thread)
            self.log(f"✅ {ext.NOME} carregada")

            # Monta widget se disponível
            self._app.after(0, lambda e=ext: self._montar_widget_ext(e))
            return True

        except Exception as e:
            traceback.print_exc()
            self.log(f"❌ Erro ao carregar {arquivo}: {e}")
            return False

    def descarregar(self, arquivo: str):
        if arquivo not in self._loaded:
            return
        ext, thread = self._loaded.pop(arquivo)
        thread.parar()
        self.log(f"🔴 {ext.NOME} descarregada")

    def hot_reload(self, arquivo: str):
        """Descarrega e recarrega sem reiniciar o app."""
        self.descarregar(arquivo)
        time.sleep(0.2)
        self.carregar(arquivo)

    def descarregar_todas(self):
        for arq in list(self._loaded):
            self.descarregar(arq)

    # ── Eventos ───────────────────────────────────────────────────────────────
    def emitir(self, evento: str, dados: dict = {}):
        """Distribui evento para todas as extensões carregadas."""
        for ext, thread in self._loaded.values():
            thread.enqueue(evento, dados)

    # ── Widgets ───────────────────────────────────────────────────────────────
    def _montar_widget_ext(self, ext: BaseExtension):
        try:
            w = ext.build_widget(self._parent)
            if w:
                w.pack(fill="x", pady=2)
        except Exception as e:
            print(f"[ext] build_widget erro: {e}")

    def montar_widget(self, widget_fn):
        try:
            w = widget_fn(self._parent)
            if w:
                w.pack(fill="x", pady=2)
        except Exception as e:
            print(f"[ext] montar_widget erro: {e}")

    # ── Log ───────────────────────────────────────────────────────────────────
    def log(self, msg: str):
        ts  = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self._log_lines.append(line)
        if len(self._log_lines) > 200:
            self._log_lines = self._log_lines[-200:]
        if self._lbl_log:
            try:
                self._lbl_log.config(text="\n".join(self._log_lines[-6:]))
            except Exception:
                pass
        print(f"[ext] {line}")

    def set_log_widget(self, w: tk.Label):
        self._lbl_log = w