import json
import os

# Ações disponíveis e suas descrições
ACOES = {
    "PLAY_PAUSE": "▶/⏸  Play / Pausar",
    "NEXT":       "⏭   Próxima música",
    "PREV":       "⏮   Música anterior",
    "VOL_UP":     "🔊  Volume +",
    "VOL_DOWN":   "🔉  Volume -",
    "SHUFFLE":    "🔀  Toggle Aleatório",
    "RECOMENDA":  "⭐  Tocar Recomendada",
}

# Mapeamento padrão (código IR → ação)
MAPEAMENTO_PADRAO = {
    "PLAY":  "PLAY_PAUSE",
    "PAUSE": "PLAY_PAUSE",
    "NEXT":  "NEXT",
    "PREV":  "PREV",
    "VOL+":  "VOL_UP",
    "VOL-":  "VOL_DOWN",
}


class IRConfig:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.mapeamento = {}
        self.carregar()

    # ─────────────────────────────────────────
    # 🔒 JSON seguro (leitura/escrita atômica)
    # ─────────────────────────────────────────

    def _ler_json_seguro(self):
        """Lê o JSON ignorando bytes inválidos — nunca lança exceção de encoding."""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8", errors="replace") as f:
                conteudo = f.read().strip()
            if not conteudo:
                return {}
            return json.loads(conteudo)
        except json.JSONDecodeError as e:
            print(f"⚠️  config.json corrompido — recriando. ({e})")
            bak = self.config_path + ".bak"
            try:
                os.replace(self.config_path, bak)
                print(f"   Backup salvo em: {bak}")
            except OSError:
                pass
            return {}
        except OSError as e:
            print(f"⚠️  Erro ao ler config.json: {e}")
            return {}

    def _salvar_json_seguro(self, dados: dict) -> bool:
        """Escreve o JSON de forma atômica usando arquivo temporário."""
        tmp = self.config_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=True)  # ASCII-safe: evita encoding misto
            os.replace(tmp, self.config_path)  # rename atômico no SO
            return True
        except OSError as e:
            print(f"Erro ao salvar config: {e}")
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    # ─────────────────────────────────────────
    # 📥 Carregar / 💾 Salvar
    # ─────────────────────────────────────────

    def carregar(self):
        """Carrega mapeamento do arquivo de configuração."""
        dados = self._ler_json_seguro()
        self.mapeamento = dados.get("ir_mapping", MAPEAMENTO_PADRAO.copy())

    def salvar(self) -> bool:
        """Salva apenas a chave ir_mapping, preservando o resto do config.json."""
        dados = self._ler_json_seguro()
        dados["ir_mapping"] = self.mapeamento
        return self._salvar_json_seguro(dados)

    # ─────────────────────────────────────────
    # 🔧 Operações
    # ─────────────────────────────────────────

    def mapear(self, codigo_ir: str, acao: str) -> bool:
        """Associa um código IR a uma ação."""
        if acao not in ACOES:
            return False
        self.mapeamento[codigo_ir.upper()] = acao
        return self.salvar()

    def remover(self, codigo_ir: str) -> bool:
        """Remove mapeamento de um código IR."""
        codigo = codigo_ir.upper()
        if codigo in self.mapeamento:
            del self.mapeamento[codigo]
            return self.salvar()
        return False

    def resolver(self, codigo_ir: str):
        """Retorna a ação para um código IR, ou None."""
        return self.mapeamento.get(codigo_ir.upper())

    def resetar(self):
        """Volta ao mapeamento padrão."""
        self.mapeamento = MAPEAMENTO_PADRAO.copy()
        self.salvar()

    def listar(self):
        """Retorna lista de (codigo_ir, acao, descricao_acao) ordenada."""
        return sorted(
            [(c, a, ACOES.get(a, a)) for c, a in self.mapeamento.items()],
            key=lambda x: x[0]
        )

    def acoes_disponiveis(self):
        return ACOES