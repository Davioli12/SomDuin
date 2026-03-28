"""
Extensão: Exemplo Completo
==========================
Demonstra TODOS os recursos disponíveis na API de extensões:

  ✅ on_load / on_unload / on_tick / on_event
  ✅ Todos os eventos: musica_mudou, volume_mudou, ir_recebido,
                       serial_linha, play, pause, modo_mudou
  ✅ Controle do player: play, pause, proxima, anterior, tocar_indice, set_volume
  ✅ Serial: serial_send, (leitura via on_event "serial_linha")
  ✅ UI: build_widget com botões, labels e atualização em tempo real
  ✅ toast e log
  ✅ Estado persistente entre ticks
  ✅ Watchdog: on_tick nunca bloqueia mais de 5s
"""

from extension_api import BaseExtension

NOME      = "Exemplo Completo"
DESCRICAO = "Demonstra todos os recursos da API de extensões"
VERSAO    = "1.0"
AUTOR     = "Arduino Player"

import tkinter as tk
import time
import threading


class ExemploCompleto(BaseExtension):

    NOME      = NOME
    DESCRICAO = DESCRICAO
    VERSAO    = VERSAO
    AUTOR     = AUTOR

    # ─────────────────────────────────────────────────────────────────────────
    # Ciclo de vida
    # ─────────────────────────────────────────────────────────────────────────

    def on_load(self):
        """
        Chamado UMA VEZ quando a extensão é ligada.
        Inicialize variáveis de estado aqui.
        """
        # Estado interno
        self._ticks          = 0
        self._musica_atual   = "—"
        self._volume_atual   = 0
        self._modo           = "?"
        self._ultimo_ir      = "—"
        self._linhas_serial  = 0
        self._eventos_log    = []
        self._lock           = threading.Lock()

        # Referências aos widgets (preenchidas em build_widget)
        self._lbl_tick    = None
        self._lbl_musica  = None
        self._lbl_volume  = None
        self._lbl_ir      = None
        self._lbl_serial  = None
        self._lbl_modo    = None
        self._lbl_eventos = None

        # Lê estado inicial do app
        self._musica_atual = self.api.musica_atual() or "—"
        self._volume_atual = self.api.get_volume()
        self._modo         = self.api.modo()

        self.api.log(f"[ExemploCompleto] carregada — modo={self._modo}, "
                     f"músicas={len(self.api.lista_musicas())}")
        self.api.toast("🧩 Exemplo Completo ligado!", "#a855f7")

    def on_unload(self):
        """
        Chamado quando a extensão é desligada ou recarregada.
        Libere recursos, feche arquivos, cancele timers.
        """
        self.api.log("[ExemploCompleto] descarregada")
        self.api.toast("🧩 Exemplo Completo desligado", "#9490b5", 2000)

    # ─────────────────────────────────────────────────────────────────────────
    # Tick periódico  (~500ms, thread da extensão)
    # ─────────────────────────────────────────────────────────────────────────

    def on_tick(self):
        """
        Chamado a cada ~500ms.
        NÃO toque em widgets Tkinter diretamente aqui —
        use self.api.toast(), self.api.log(), ou agende via after().
        """
        self._ticks += 1

        # Lê estado atual do app a cada tick
        musica = self.api.musica_atual()
        volume = self.api.get_volume()
        modo   = self.api.modo()

        with self._lock:
            self._musica_atual = musica or "—"
            self._volume_atual = volume
            self._modo         = modo

        # Atualiza labels do widget (thread-safe via after implícito do api)
        self._atualizar_labels()

        # A cada 20 ticks (~10s): envia ping para o Arduino
        if self._ticks % 20 == 0:
            self.api.serial_send("PING")
            self.api.log(f"[tick {self._ticks}] PING enviado ao Arduino")

        # A cada 40 ticks (~20s): mostra lista de músicas no log
        if self._ticks % 40 == 0:
            musicas = self.api.lista_musicas()
            self.api.log(f"[tick {self._ticks}] {len(musicas)} músicas na biblioteca")

    # ─────────────────────────────────────────────────────────────────────────
    # Eventos do app  (thread da extensão)
    # ─────────────────────────────────────────────────────────────────────────

    def on_event(self, evento: str, dados: dict):
        """
        Recebe TODOS os eventos emitidos pelo app.
        Também chamado na thread da extensão — não toque em Tkinter diretamente.
        """
        ts = time.strftime("%H:%M:%S")

        # ── musica_mudou ──────────────────────────────────────────────────────
        if evento == "musica_mudou":
            nome  = dados.get("nome", "?")
            index = dados.get("index", 0)
            with self._lock:
                self._musica_atual = nome
            self._registrar_evento(f"🎵 Música mudou → {nome} (#{index})")
            self.api.toast(f"🎵 {nome}", "#7c3aed", 4000)
            self.api.log(f"[{ts}] musica_mudou: {nome}")

        # ── volume_mudou ──────────────────────────────────────────────────────
        elif evento == "volume_mudou":
            pct = dados.get("pct", 0)
            with self._lock:
                self._volume_atual = pct
            self._registrar_evento(f"🔊 Volume → {pct}%")

        # ── ir_recebido ───────────────────────────────────────────────────────
        elif evento == "ir_recebido":
            codigo = dados.get("codigo", "?")
            acao   = dados.get("acao") or "sem mapeamento"
            with self._lock:
                self._ultimo_ir = f"{codigo} → {acao}"
            self._registrar_evento(f"📡 IR: {codigo} ({acao})")
            self.api.log(f"[{ts}] IR recebido: {codigo} → {acao}")

        # ── serial_linha ──────────────────────────────────────────────────────
        elif evento == "serial_linha":
            linha = dados.get("linha", "")
            with self._lock:
                self._linhas_serial += 1

            # Reage a comando personalizado do Arduino
            if linha == "PONG":
                self.api.log(f"[{ts}] Arduino respondeu PONG ✅")
                self._registrar_evento("🔌 Arduino: PONG recebido")

            elif linha.startswith("SENSOR:"):
                valor = linha.split(":", 1)[1]
                self._registrar_evento(f"📟 Sensor: {valor}")
                self.api.log(f"[{ts}] Sensor lido: {valor}")

        # ── play ──────────────────────────────────────────────────────────────
        elif evento == "play":
            self._registrar_evento("▶ Play")

        # ── pause ─────────────────────────────────────────────────────────────
        elif evento == "pause":
            self._registrar_evento("⏸ Pause")

        # ── modo_mudou ────────────────────────────────────────────────────────
        elif evento == "modo_mudou":
            modo = dados.get("modo", "?")
            with self._lock:
                self._modo = modo
            self._registrar_evento(f"🔄 Modo mudou → {modo}")

    # ─────────────────────────────────────────────────────────────────────────
    # Widget no painel de extensões
    # ─────────────────────────────────────────────────────────────────────────

    def build_widget(self, parent: tk.Frame) -> tk.Widget:
        """
        Constrói o widget exibido no painel de extensões do app.
        Chamado na thread principal — pode criar widgets Tkinter normalmente.
        """
        BG_W    = "#17171f"
        BG_CARD = "#1e1e2a"
        ACCENT  = "#7c3aed"
        ACC2    = "#a855f7"
        GREEN   = "#22c55e"
        GOLD    = "#f59e0b"
        RED     = "#ef4444"
        TEXT    = "#f1f0fa"
        TEXT2   = "#9490b5"

        outer = tk.Frame(parent, bg=BG_CARD,
                         highlightthickness=1, highlightbackground="#2e2b45")
        outer.pack(fill="x", pady=4, padx=2)

        # Título
        tk.Label(outer, text="🧩 Exemplo Completo",
                 bg=BG_CARD, fg=ACC2,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 2))

        # ── Estado em tempo real ──────────────────────────────────────────────
        info = tk.Frame(outer, bg=BG_CARD)
        info.pack(fill="x", padx=10, pady=2)

        def row(label, inicial, cor=TEXT2):
            f = tk.Frame(info, bg=BG_CARD)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=label, bg=BG_CARD, fg=TEXT2,
                     font=("Segoe UI", 8), width=14, anchor="w").pack(side="left")
            lbl = tk.Label(f, text=inicial, bg=BG_CARD, fg=cor,
                           font=("Segoe UI", 8, "bold"), anchor="w")
            lbl.pack(side="left")
            return lbl

        self._lbl_tick    = row("Ticks:",        "0",   GOLD)
        self._lbl_musica  = row("Música:",       "—",   TEXT)
        self._lbl_volume  = row("Volume:",       "—",   GREEN)
        self._lbl_modo    = row("Modo:",         "—",   ACC2)
        self._lbl_ir      = row("Último IR:",    "—",   GOLD)
        self._lbl_serial  = row("Serial rcv:",   "0",   TEXT2)

        # ── Log de eventos ───────────────────────────────────────────────────
        tk.Label(outer, text="Últimos eventos:",
                 bg=BG_CARD, fg=TEXT2,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self._lbl_eventos = tk.Label(outer, text="",
                                     bg=BG_CARD, fg="#6b7280",
                                     font=("Courier", 7),
                                     justify="left", anchor="w",
                                     wraplength=440)
        self._lbl_eventos.pack(fill="x", padx=10, pady=(0, 4))

        # ── Botões de controle ───────────────────────────────────────────────
        ctrl = tk.Frame(outer, bg=BG_CARD)
        ctrl.pack(fill="x", padx=10, pady=(2, 8))

        def btn(txt, cor, cmd):
            return tk.Button(ctrl, text=txt, bg=cor, fg=TEXT,
                             relief="flat", font=("Segoe UI", 8, "bold"),
                             padx=8, pady=3, cursor="hand2", command=cmd)

        btn("⏮", "#2e2b45", self.api.anterior).pack(side="left", padx=(0, 2))
        btn("▶/⏸", ACCENT,   self.api.play).pack(side="left", padx=(0, 2))
        btn("⏭", "#2e2b45", self.api.proxima).pack(side="left", padx=(0, 8))

        btn("🔉 -10%", "#2e2b45",
            lambda: self.api.set_volume(max(0,   self.api.get_volume() - 10))
            ).pack(side="left", padx=(0, 2))
        btn("🔊 +10%", "#2e2b45",
            lambda: self.api.set_volume(min(100, self.api.get_volume() + 10))
            ).pack(side="left", padx=(0, 8))

        btn("📡 Ping", "#1e2a1e",
            lambda: self.api.serial_send("PING")).pack(side="left", padx=(0, 2))

        btn("🎲 Aleatória", "#2a1e2a",
            self._tocar_aleatoria).pack(side="left", padx=(0, 2))

        return outer

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────────────────────────────────

    def _registrar_evento(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self._eventos_log.append(f"[{ts}] {msg}")
            if len(self._eventos_log) > 20:
                self._eventos_log = self._eventos_log[-20:]

    def _atualizar_labels(self):
        """Agenda atualização dos labels na thread principal via toast/after."""
        with self._lock:
            tick    = self._ticks
            musica  = self._musica_atual
            volume  = self._volume_atual
            modo    = self._modo
            ir      = self._ultimo_ir
            serial  = self._linhas_serial
            eventos = list(self._eventos_log[-5:])

        def _update():
            try:
                if self._lbl_tick:
                    self._lbl_tick.config(text=str(tick))
                if self._lbl_musica:
                    nome_curto = musica[:35] + "…" if len(musica) > 35 else musica
                    self._lbl_musica.config(text=nome_curto)
                if self._lbl_volume:
                    self._lbl_volume.config(text=f"{volume}%")
                if self._lbl_modo:
                    self._lbl_modo.config(text=modo)
                if self._lbl_ir:
                    self._lbl_ir.config(text=ir)
                if self._lbl_serial:
                    self._lbl_serial.config(text=str(serial))
                if self._lbl_eventos:
                    self._lbl_eventos.config(text="\n".join(eventos) or "—")
            except Exception:
                pass  # widget pode ter sido destruído

        self.api._app.after(0, _update)

    def _tocar_aleatoria(self):
        """Escolhe uma música aleatória da lista e toca."""
        import random
        musicas = self.api.lista_musicas()
        if not musicas:
            self.api.toast("❌ Sem músicas na biblioteca", "#ef4444")
            return
        idx = random.randint(0, len(musicas) - 1)
        self.api.tocar_indice(idx)
        self.api.toast(f"🎲 Aleatória: {musicas[idx][:40]}", "#7c3aed")


# Exportação obrigatória
EXTENSION = ExemploCompleto