# 🎧 SomDuin

Controle suas músicas usando um Arduino + Controle IR de forma simples, rápida e personalizável.

O **SomDuin** integra Python com Arduino para criar um controlador multimídia físico capaz de:

* controlar músicas,
* ajustar volume,
* trocar faixas,
* usar modo aleatório,
* integrar com Spotify,
* carregar extensões dinâmicas,
* e muito mais.

---

# ✨ Recursos

## 🎵 Controle de Música

* Play / Pause
* Próxima música
* Música anterior
* Controle de volume
* Modo aleatório (Shuffle)
* Sistema de favoritos
* Recomendações automáticas

---

## 📡 Controle IR

Compatível com:

* controles infravermelho comuns,
* receptores IR para Arduino,
* mapeamento personalizado de botões.

O sistema permite:

* capturar códigos IR automaticamente,
* configurar ações,
* salvar perfis de controle.

---

## 🔌 Integração com Arduino

Comunicação Serial em tempo real usando:

* Arduino Nano
* Arduino Uno
* CH340 / CH341
* USB Serial

Detecção automática da porta COM.

---

## 🖥️ Interface Moderna

* Interface feita em Tkinter
* Tema escuro moderno
* Compatível com Full HD e 4K
* Escala automática de DPI
* Layout responsivo

---

## 🧩 Sistema de Extensões

O projeto possui suporte a:

* extensões externas,
* hot reload,
* widgets personalizados,
* eventos do player,
* API para automações.

As extensões são carregadas dinamicamente sem precisar recompilar o app.

---

# 📂 Estrutura do Projeto

```text
SomDuin/
│
├── app.py
├── player.py
├── extension_api.py
├── ir_config.py
├── extensions/
├── downloads/
├── config.json
└── favoritas.txt
```

---

# ⚙️ Requisitos

* Python 3.13+
* Arduino IDE
* Arduino Nano/Uno
* Controle IR
* Receptor IR

---

# 📦 Instalação

## 1. Clone o projeto

```bash
git clone https://github.com/davioli12/SomDuin.git
cd SomDuin
```

---

## 2. Instale as dependências

```bash
pip install -r requirements.txt
```

---

## 3. Execute

```bash
python app.py
```

---

# 🔨 Gerando Executável

O projeto suporta build via PyInstaller.

```bash
python3.13 -m PyInstaller --onedir --windowed app.py
```

---

# 🎮 Controles IR

As ações disponíveis incluem:

* PLAY_PAUSE
* NEXT
* PREV
* VOL_UP
* VOL_DOWN
* SHUFFLE
* RECOMENDA

Todos os botões podem ser personalizados pela interface.

---

# 🧠 Sistema de Extensões

Cada extensão é um arquivo Python dentro de:

```text
extensions/
```

Exportando:

```python
EXTENSION = MinhaExtensao
```

Eventos disponíveis:

* musica_mudou
* volume_mudou
* ir_recebido
* serial_linha
* play
* pause
* modo_mudou

---

# 🚀 Roadmap

* [ ] Marketplace de extensões
* [ ] Overlay in-game
* [ ] API WebSocket
* [ ] Sistema de temas
* [ ] Aplicativo Android
* [ ] Atualizador automático

---

# ❤️ Objetivo do Projeto

O SomDuin foi criado para unir:

* automação,
* hardware,
* Python,
* Arduino,
* multimídia,
* e personalização.

Tudo em um projeto open-source simples e expansível.

---

# 📜 Licença

Projeto open-source para fins educacionais e pessoais.
