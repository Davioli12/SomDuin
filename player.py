import pygame
import os
import random
import json
import time
from collections import defaultdict

# Evento customizado que o pygame dispara quando a música termina
_MUSIC_END = pygame.USEREVENT + 1


class MusicPlayer:
    def __init__(self, pasta="downloads", config_path="config.json"):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        pygame.init()  # necessário para o sistema de eventos

        # Registra evento de fim de música — pygame chama isso sozinho
        pygame.mixer.music.set_endevent(_MUSIC_END)

        self.pasta        = pasta
        self.config_path  = config_path
        self.musicas      = self.carregar_musicas()
        self.index        = 0
        self.volume       = 0.5
        self.velocidade   = 1.0
        self.modo_shuffle = False
        self.fila_shuffle: list[int] = []
        self.autoplay     = True
        self.autopass     = True

        # Rastreamento de posição
        self._inicio_toque = 0.0
        self._pos_pausada  = 0.0
        self._pausado      = False

        # Histórico separado de "o que o usuário ouviu" —
        # NÃO misturado com as estatísticas de contagem
        # Cada entrada é o index que estava tocando ANTES de avançar.
        # Assim anterior() sempre sabe para onde voltar.
        self._historico_nav: list[int] = []   # navegação (para anterior())
        self._em_transicao  = False            # evita duplo-avanço no autopass

        # Duração em cache (carregada sob demanda)
        self._duracao_cache: dict[str, float] = {}

        # Estatísticas
        self.contagem: defaultdict[str, int] = defaultdict(int)

        pygame.mixer.music.set_volume(self.volume)
        self._carregar_estatisticas()

        if self.autoplay and self.musicas:
            self._tocar_interno()

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

    def reiniciar_audio(self):
        """
        Reinicia o sistema de áudio (pygame.mixer).
        Útil quando troca dispositivo de som (fone, caixa, etc).
        """

        try:
            # salva estado atual
            pos = self.posicao_seg()   # posição atual da música
            vol = self.volume          # volume atual
            tocando = self.esta_tocando()
            pausado = self.esta_pausado()

            # para tudo e fecha o mixer
            pygame.mixer.music.stop()
            pygame.mixer.quit()

            # reinicia o mixer (padrão)
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

            # IMPORTANTE: precisa registrar de novo o evento de fim de música
            pygame.mixer.music.set_endevent(_MUSIC_END)

            # restaura volume
            pygame.mixer.music.set_volume(vol)

            # recarrega música atual
            if self.musicas:
                caminho = os.path.join(self.pasta, self.musicas[self.index])
                pygame.mixer.music.load(caminho)
                pygame.mixer.music.play()

                # tenta voltar pra posição anterior
                try:
                    pygame.mixer.music.set_pos(pos)
                except:
                    pass

                # restaura estado play/pause
                if pausado:
                    pygame.mixer.music.pause()
                    self._pausado = True
                    self._pos_pausada = pos
                else:
                    self._pausado = False
                    self._inicio_toque = time.time()

            print("🔊 Áudio reconectado com sucesso")

        except Exception as e:
            print(f"Erro ao reiniciar áudio: {e}")

    # ─────────────────────────────────────────
    # ▶️ Controles internos (sem mexer no histórico de nav)
    # ─────────────────────────────────────────
    def _tocar_interno(self):
        """
        Carrega e toca self.index.
        NÃO toca no histórico de navegação — isso é responsabilidade
        de proxima() / anterior() / tocar_indice().
        """
        if not self.musicas:
            return False
        caminho = os.path.join(self.pasta, self.musicas[self.index])
        try:
            pygame.mixer.music.load(caminho)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"Erro ao tocar {caminho}: {e}")
            return False

        self._inicio_toque  = time.time()
        self._pos_pausada   = 0.0
        self._pausado       = False
        self._em_transicao  = False

        # Registra nas estatísticas de contagem
        nome = self.musicas[self.index]
        self.contagem[nome] += 1
        if len(list(self.contagem)) > 0:
            self._salvar_estatisticas()

        print(f"▶️  [{self.index}] {self.musicas[self.index]}")
        return True

    # ─────────────────────────────────────────
    # 🎮 API pública de controle
    # ─────────────────────────────────────────
    def tocar(self):
        """Toca a música no index atual (sem alterar histórico)."""
        return self._tocar_interno()

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
        """Toggle play/pause."""
        if self._pausado:
            self.retomar()
        elif pygame.mixer.music.get_busy():
            self.pausar()
        else:
            self._tocar_interno()

    def proxima(self):
        """Avança para próxima música, salvando a atual no histórico de nav."""
        if not self.musicas:
            return
        # Salva posição atual para o anterior() poder voltar
        self._historico_nav.append(self.index)
        if len(self._historico_nav) > 200:
            self._historico_nav = self._historico_nav[-200:]

        if self.modo_shuffle:
            self.index = self._proximo_shuffle()
        else:
            self.index = (self.index + 1) % len(self.musicas)
        self._tocar_interno()

    def anterior(self):
        """
        Volta para a música anterior no histórico de navegação.
        Se menos de 3s tocaram, volta para o início da atual primeiro.
        Se não há histórico, vai para index-1.
        """
        if not self.musicas:
            return

        pos_atual = self.posicao_seg()

        # Se tocou mais de 3s: volta ao início da música atual
        if pos_atual > 3.0:
            self._pos_pausada  = 0.0
            self._inicio_toque = time.time()
            pygame.mixer.music.rewind()
            return

        # Senão: volta para a música anterior no histórico
        if self._historico_nav:
            self.index = self._historico_nav.pop()
        else:
            # Sem histórico: vai para index-1
            self.index = (self.index - 1) % len(self.musicas)

        self._tocar_interno()

    def tocar_indice(self, indice: int):
        if 0 <= indice < len(self.musicas):
            # Salva atual no histórico antes de pular
            self._historico_nav.append(self.index)
            if len(self._historico_nav) > 200:
                self._historico_nav = self._historico_nav[-200:]
            self.index = indice
            self._tocar_interno()

    def seek(self, segundos: float):
        try:
            pygame.mixer.music.set_pos(segundos)
            self._pos_pausada  = segundos
            self._inicio_toque = time.time()
        except Exception:
            pass

    # ─────────────────────────────────────────
    # ⏱️ Estado / Posição / Fim de música
    # ─────────────────────────────────────────
    def esta_tocando(self) -> bool:
        return pygame.mixer.music.get_busy() and not self._pausado

    def esta_pausado(self) -> bool:
        return self._pausado

    def posicao_seg(self) -> float:
        if self._pausado:
            return self._pos_pausada
        if pygame.mixer.music.get_busy():
            return self._pos_pausada + (time.time() - self._inicio_toque)
        return 0.0

    def duracao_seg(self) -> float:
        if not self.musicas:
            return 0.0
        nome = self.musicas[self.index]
        if nome in self._duracao_cache:
            return self._duracao_cache[nome]
        try:
            sound = pygame.mixer.Sound(os.path.join(self.pasta, nome))
            dur   = sound.get_length()
            del sound
        except Exception:
            dur = 0.0
        self._duracao_cache[nome] = dur
        return dur

    def progresso_pct(self) -> float:
        dur = self.duracao_seg()
        return min(1.0, self.posicao_seg() / dur) if dur > 0 else 0.0

    def checar_fim(self) -> bool:
        """
        Verifica se o evento de fim de música foi disparado pelo pygame.
        Deve ser chamado periodicamente pelo loop da UI (no after()).
        Retorna True UMA VEZ quando a música terminou — depois reseta.
        Usa o sistema de eventos do pygame para detecção precisa.
        """
        if self._pausado or self._em_transicao:
            return False
        # Consome eventos pendentes do pygame sem bloquear
        for event in pygame.event.get(_MUSIC_END):
            if event.type == _MUSIC_END:
                self._em_transicao = True   # bloqueia dupla-detecção
                return True
        return False

    # ─────────────────────────────────────────
    # 🏎️ Velocidade
    # ─────────────────────────────────────────
    def set_velocidade(self, v: float):
        v = max(0.5, min(2.0, round(v, 2)))
        self.velocidade = v
        nova_freq = int(44100 * v)
        pos = self.posicao_seg()
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        pygame.mixer.init(frequency=nova_freq, size=-16, channels=2, buffer=2048)
        pygame.mixer.music.set_endevent(_MUSIC_END)   # re-registra após reinit
        pygame.mixer.music.set_volume(self.volume)
        if self.musicas:
            caminho = os.path.join(self.pasta, self.musicas[self.index])
            pygame.mixer.music.load(caminho)
            pygame.mixer.music.play()
            try:
                pygame.mixer.music.set_pos(pos)
            except Exception:
                pass
            self._inicio_toque = time.time()
            self._pos_pausada  = pos
            self._pausado      = False
            self._em_transicao = False

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

    def _proximo_shuffle(self) -> int:
        if not self.fila_shuffle:
            self._gerar_fila_shuffle()
        try:
            pos = self.fila_shuffle.index(self.index)
        except ValueError:
            pos = -1
        return self.fila_shuffle[(pos + 1) % len(self.fila_shuffle)]

    # ─────────────────────────────────────────
    # ⭐ Recomendações / Favoritas
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
    # 📊 Estatísticas / Config
    # ─────────────────────────────────────────
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
    # 🎚️ Volume / Info
    # ─────────────────────────────────────────
    def set_volume(self, valor: float):
        self.volume = max(0.0, min(1.0, valor if valor <= 1 else valor / 1023))
        pygame.mixer.music.set_volume(self.volume)

    def get_volume_pct(self) -> int:
        return int(self.volume * 100)

    def musica_atual(self) -> str:
        if not self.musicas:
            return "Nenhuma música"
        return os.path.splitext(self.musicas[self.index])[0]

    def listar_musicas(self):
        return self.musicas

    def total_musicas(self) -> int:
        return len(self.musicas)

    def destruir(self):
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass