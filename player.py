import pygame
import os
import random
import json
import time
from collections import defaultdict


class MusicPlayer:
    def __init__(self, pasta="downloads", config_path="config.json"):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

        self.pasta       = pasta
        self.config_path = config_path
        self.musicas     = self.carregar_musicas()
        self.index       = 0
        self.volume      = 0.5
        self.velocidade  = 1.0          # 0.5 – 2.0
        self.modo_shuffle = False
        self.fila_shuffle = []
        self.autoplay    = True         # inicia tocando
        self.autopass    = True         # avança ao acabar

        # Rastreamento de posição
        self._inicio_toque  = 0.0      # time.time() quando play() foi chamado
        self._pos_pausada   = 0.0      # acumulado em segundos antes da pausa
        self._pausado       = False
        self._duracao_cache: dict[str, float] = {}  # nome → segundos

        # Histórico / estatísticas
        self.historico: list[int]         = []
        self.contagem: defaultdict[str, int] = defaultdict(int)
        self.ultima_tocada = None

        pygame.mixer.music.set_volume(self.volume)
        self._carregar_estatisticas()

        if self.autoplay and self.musicas:
            self.tocar()

    # ─────────────────────────────────────────
    # 📂 Carregamento
    # ─────────────────────────────────────────
    def carregar_musicas(self):
        if not os.path.exists(self.pasta):
            os.makedirs(self.pasta, exist_ok=True)
            return []
        return sorted([
            f for f in os.listdir(self.pasta)
            if f.lower().endswith((".mp3", ".wav", ".ogg", ".flac"))
        ])

    def recarregar(self):
        self.musicas = self.carregar_musicas()
        if self.modo_shuffle:
            self._gerar_fila_shuffle()

    # ─────────────────────────────────────────
    # ▶️ Controles
    # ─────────────────────────────────────────
    def tocar(self):
        if not self.musicas:
            return False
        caminho = os.path.join(self.pasta, self.musicas[self.index])
        pygame.mixer.music.load(caminho)
        pygame.mixer.music.play()
        self._inicio_toque = time.time()
        self._pos_pausada  = 0.0
        self._pausado      = False
        self._registrar_reproducao(self.index)
        print(f"▶️ {self.musicas[self.index]}")
        return True

    def pausar(self):
        if not self._pausado and pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self._pos_pausada += time.time() - self._inicio_toque
            self._pausado = True

    def retomar(self):
        if self._pausado:
            pygame.mixer.music.unpause()
            self._inicio_toque = time.time()
            self._pausado = False

    def continuar(self):
        """Toggle pause/retomar"""
        if self._pausado:
            self.retomar()
        elif pygame.mixer.music.get_busy():
            self.pausar()
        else:
            self.tocar()

    def esta_tocando(self) -> bool:
        return pygame.mixer.music.get_busy() and not self._pausado

    def esta_pausado(self) -> bool:
        return self._pausado

    def proxima(self):
        if not self.musicas:
            return
        self.index = self._proximo_shuffle() if self.modo_shuffle \
                     else (self.index + 1) % len(self.musicas)
        self.tocar()

    def anterior(self):
        if not self.musicas:
            return
        if len(self.historico) > 1:
            self.historico.pop()
            self.index = self.historico[-1]
        else:
            self.index = (self.index - 1) % len(self.musicas)
        self.tocar()

    def tocar_indice(self, indice: int):
        if 0 <= indice < len(self.musicas):
            self.index = indice
            self.tocar()

    def seek(self, segundos: float):
        """Pula para posição em segundos."""
        try:
            pygame.mixer.music.set_pos(segundos)
            self._pos_pausada  = segundos
            self._inicio_toque = time.time()
        except Exception:
            pass

    # ─────────────────────────────────────────
    # ⏱️ Posição / Duração
    # ─────────────────────────────────────────
    def posicao_seg(self) -> float:
        """Retorna posição atual em segundos."""
        if self._pausado:
            return self._pos_pausada
        if pygame.mixer.music.get_busy():
            return self._pos_pausada + (time.time() - self._inicio_toque)
        return 0.0

    def duracao_seg(self) -> float:
        """Duração da música atual em segundos (com cache)."""
        if not self.musicas:
            return 0.0
        nome = self.musicas[self.index]
        if nome in self._duracao_cache:
            return self._duracao_cache[nome]
        try:
            sound = pygame.mixer.Sound(os.path.join(self.pasta, nome))
            dur = sound.get_length()
            del sound
        except Exception:
            dur = 0.0
        self._duracao_cache[nome] = dur
        return dur

    def progresso_pct(self) -> float:
        """0.0 – 1.0"""
        dur = self.duracao_seg()
        if dur <= 0:
            return 0.0
        return min(1.0, self.posicao_seg() / dur)

    def terminou(self) -> bool:
        """True se a música acabou (não está tocando nem pausada)."""
        return (not pygame.mixer.music.get_busy()) and (not self._pausado) \
               and self._pos_pausada > 0

    # ─────────────────────────────────────────
    # 🏎️ Velocidade
    # ─────────────────────────────────────────
    def set_velocidade(self, v: float):
        """
        pygame não suporta pitch-shift nativo.
        Implementamos via reinicialização do mixer com taxa de sample diferente.
        v: 0.5 (metade) a 2.0 (dobro).
        """
        v = max(0.5, min(2.0, round(v, 2)))
        self.velocidade = v
        freq_base = 44100
        nova_freq = int(freq_base * v)
        pos = self.posicao_seg()
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        pygame.mixer.init(frequency=nova_freq, size=-16, channels=2, buffer=2048)
        pygame.mixer.music.set_volume(self.volume)
        if self.musicas:
            caminho = os.path.join(self.pasta, self.musicas[self.index])
            pygame.mixer.music.load(caminho)
            pygame.mixer.music.play()
            # Tenta continuar de onde parou
            try:
                pygame.mixer.music.set_pos(pos)
            except Exception:
                pass
            self._inicio_toque = time.time()
            self._pos_pausada  = pos
            self._pausado      = False

    # ─────────────────────────────────────────
    # 🔀 Shuffle
    # ─────────────────────────────────────────
    def toggle_shuffle(self):
        self.modo_shuffle = not self.modo_shuffle
        if self.modo_shuffle:
            self._gerar_fila_shuffle()
        return self.modo_shuffle

    def _gerar_fila_shuffle(self):
        indices = list(range(len(self.musicas)))
        if self.index in indices:
            indices.remove(self.index)
        random.shuffle(indices)
        self.fila_shuffle = [self.index] + indices

    def _proximo_shuffle(self):
        if not self.fila_shuffle:
            self._gerar_fila_shuffle()
        pos = self.fila_shuffle.index(self.index) \
              if self.index in self.fila_shuffle else -1
        return self.fila_shuffle[(pos + 1) % len(self.fila_shuffle)]

    # ─────────────────────────────────────────
    # ⭐ Recomendações
    # ─────────────────────────────────────────
    def recomendadas(self, n=5):
        if not self.musicas:
            return []
        mx = max(self.contagem.values()) if self.contagem else 1
        scores = []
        for i, nome in enumerate(self.musicas):
            c  = self.contagem.get(nome, 0)
            sf = (c / mx) * 0.5 + (1.0 if c == 0 else 0.1 / (c + 1)) * 0.5
            if i == self.index:
                sf *= 0.1
            scores.append((i, sf))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scores[:n]]

    def favoritas(self, n=5):
        if not self.musicas:
            return []
        pares = sorted(
            [(i, self.contagem.get(nome, 0)) for i, nome in enumerate(self.musicas)],
            key=lambda x: x[1], reverse=True
        )
        return [i for i, c in pares[:n] if c > 0]

    def nao_ouvidas(self):
        return [i for i, nome in enumerate(self.musicas)
                if self.contagem.get(nome, 0) == 0]

    # ─────────────────────────────────────────
    # 📊 Estatísticas
    # ─────────────────────────────────────────
    def _registrar_reproducao(self, i: int):
        nome = self.musicas[i]
        self.contagem[nome] += 1
        self.historico.append(i)
        if len(self.historico) > 100:
            self.historico = self.historico[-100:]
        self.ultima_tocada = i
        self._salvar_estatisticas()

    def _salvar_estatisticas(self):
        try:
            dados = self._carregar_config()
            dados["estatisticas"] = {
                k.encode("utf-8", errors="replace").decode("utf-8"): v
                for k, v in self.contagem.items()
            }
            tmp = self.config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=True)
            os.replace(tmp, self.config_path)
        except Exception as e:
            print(f"Erro ao salvar estatísticas: {e}")

    def _carregar_estatisticas(self):
        dados = self._carregar_config()
        self.contagem = defaultdict(int, dados.get("estatisticas", {}))

    def _carregar_config(self) -> dict:
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8", errors="replace") as f:
                conteudo = f.read().strip()
            return json.loads(conteudo) if conteudo else {}
        except json.JSONDecodeError as e:
            print(f"⚠️  config.json corrompido: {e}")
            bak = self.config_path + ".bak"
            try:
                os.replace(self.config_path, bak)
            except OSError:
                pass
            return {}
        except OSError:
            return {}

    # ─────────────────────────────────────────
    # 🎚️ Volume
    # ─────────────────────────────────────────
    def set_volume(self, valor: float):
        self.volume = max(0.0, min(1.0, valor if valor <= 1 else valor / 1023))
        pygame.mixer.music.set_volume(self.volume)

    def get_volume_pct(self) -> int:
        return int(self.volume * 100)

    # ─────────────────────────────────────────
    # ℹ️ Info
    # ─────────────────────────────────────────
    def musica_atual(self) -> str:
        if not self.musicas:
            return "Nenhuma música"
        return os.path.splitext(self.musicas[self.index])[0]

    def listar_musicas(self):
        return self.musicas

    def total_musicas(self) -> int:
        return len(self.musicas)

    def destruir(self):
        """Chama antes de fechar o app para liberar o mixer."""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass