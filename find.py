import serial
import time

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


# 🔌 CONFIG
PORTA = "COM4"
BAUD = 9600


def conectar_audio():
    """
    🎧 Conecta ao áudio (compatível com várias versões do pycaw)
    """
    devices = AudioUtilities.GetSpeakers()

    # 🔧 Compatibilidade com versões diferentes
    device = getattr(devices, "_dev", None) or getattr(devices, "dev", None) or devices

    interface = device.Activate(
        IAudioEndpointVolume._iid_,
        CLSCTX_ALL,
        None
    )

    volume = cast(interface, POINTER(IAudioEndpointVolume))
    return volume

def set_volume(volume_ctrl, valor_arduino):
    """
    🎚️ Converte 0–1023 → 0.0–1.0
    """
    percentual = max(0, min(1, valor_arduino / 1023))
    volume_ctrl.SetMasterVolumeLevelScalar(percentual, None)

    print(f"🔊 Volume: {int(percentual * 100)}%")


def main():
    print("🔌 Conectando serial...")

    ser = serial.Serial(PORTA, BAUD)
    time.sleep(2)

    print("🎧 Conectando áudio...")
    volume_ctrl = conectar_audio()

    print("🚀 Rodando... (Ctrl+C para sair)\n")

    while True:
        try:
            linha = ser.readline().decode().strip()

            if not linha:
                continue

            print("📡 Recebido:", linha)

            # 🎚️ POT
            if linha.startswith("POT:"):
                valor = int(linha.split(":")[1])
                set_volume(volume_ctrl, valor)

        except Exception as e:
            print("❌ Erro:", e)


if __name__ == "__main__":
    main()