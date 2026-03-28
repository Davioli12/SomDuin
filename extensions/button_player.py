from extension_api import BaseExtension

NOME = "Buttons Player"
VERSAO = "1.0"
DESCRICAO = "Toca/pausa a música com botões físicos (via serial)"
AUTOR = "Davi de Oliveira Santos"

class Buttons(BaseExtension):
    def on_load(self):
        self.api.log("Olá!")
    
    def on_event(self, evento, dados):
        if evento == "serial_linha":
            
            BUTTONS = dados["linha"]

            if BUTTONS == "BUTTON1:1":
                self.api.log("Botão 1 pressionado!")
                self.api.toast("🎵 Play música")
                self.api.play()
            elif BUTTONS == "BUTTON2:1":
                self.api.log("Botão 2 pressionado!")
                self.api.toast("🎵 Próxima música")
                self.api.proxima()
            elif BUTTONS == "BUTTON3:1":
                self.api.log("Botão 3 pressionado!")
                self.api.toast("🎵 Música anterior")
                self.api.anterior()


EXTENSION = Buttons