import yt_dlp
import os

# 📁 Pasta de downloads
PASTA_DOWNLOAD = "downloads"
os.makedirs(PASTA_DOWNLOAD, exist_ok=True)

# ⚙️ Configuração
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': f'{PASTA_DOWNLOAD}/%(title)s.%(ext)s',
    'quiet': False,

    # 🎧 Converter para MP3
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

def eh_url(texto):
    """
    Verifica se o input é uma URL
    """
    return texto.startswith("http://") or texto.startswith("https://")


def baixar(input_usuario):
    """
    Função principal:
    - Se for URL → baixa direto
    - Se for texto → busca no YouTube
    """
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        if eh_url(input_usuario):
            print(f"\n📥 Detectado URL: {input_usuario}")

            # Baixa direto (vídeo ou playlist)
            ydl.download([input_usuario])

        else:
            print(f"\n🔎 Buscando: {input_usuario}")

            # Busca automática
            info = ydl.extract_info(f"ytsearch1:{input_usuario}", download=True)

            # Trata resultado
            if 'entries' in info:
                video = info['entries'][0]
            else:
                video = info

            print(f"✅ Baixado: {video['title']}")


# 🚀 Loop contínuo (estilo controle remoto)
if __name__ == "__main__":
    while True:
        entrada = input("\n🎵 Nome ou URL (ou 'sair'): ")

        if entrada.lower() == "sair":
            print("👋 Encerrando...")
            break

        if entrada.strip():
            baixar(entrada)