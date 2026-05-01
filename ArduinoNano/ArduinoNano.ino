#include <IRremote.hpp>
#include <LiquidCrystal.h>
#include <Keypad.h>

// RS, E, D4, D5, D6, D7
LiquidCrystal lcd(7, 8, 9, 10, 11, 12);

// ── PINOS
#define PIN_POT        A0
#define PIN_IR         2
#define PIN_BTN_PLAY   3
#define PIN_BTN_AVANCE 4
#define PIN_BTN_BACK   5

// ── ESTADOS
int lastBtn1 = HIGH;
int lastBtn2 = HIGH;
int lastBtn3 = HIGH;

int lastPot = -1;
String ultimoBotao = "-";
String ultimoIR = "-";

// Teclado 4 X 3
const byte LINHAS = 4;
const byte COLUNAS = 3;

char teclas[LINHAS][COLUNAS] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};

byte pinosLinhas[LINHAS] = {9, 8, 7, 6};
byte pinosColunas[COLUNAS] = {12, 11, 10};

Keypad keypad = Keypad(makeKeymap(teclas), pinosLinhas, pinosColunas, LINHAS, COLUNAS);

void setup() {
  Serial.begin(9600);

  pinMode(PIN_BTN_PLAY, INPUT_PULLUP);
  pinMode(PIN_BTN_AVANCE, INPUT_PULLUP);
  pinMode(PIN_BTN_BACK, INPUT_PULLUP);

  IrReceiver.begin(PIN_IR, ENABLE_LED_FEEDBACK);

  lcd.begin(16, 2);

  lcd.setCursor(0, 0);
  lcd.print("Iniciando...");
  delay(1000);
  lcd.clear();
}

void loop() {

  // 🎚️ POT
  int pot = analogRead(PIN_POT);

  if (abs(pot - lastPot) > 10) {
    Serial.print("POT:");
    Serial.println(pot);

    lastPot = pot;

    lcd.setCursor(0, 0);
    lcd.print("VOL:");
    lcd.print(pot);
    lcd.print("     ");
  }

  // 🔘 PLAY
  int b1 = digitalRead(PIN_BTN_PLAY);
  if (b1 == LOW && lastBtn1 == HIGH) {
    Serial.println("BUTTON1:1");

    ultimoBotao = "PLAY";
  }
  lastBtn1 = b1;

  // 🔘 NEXT
  int b2 = digitalRead(PIN_BTN_AVANCE);
  if (b2 == LOW && lastBtn2 == HIGH) {
    Serial.println("BUTTON2:1");

    ultimoBotao = "NEXT";
  }
  lastBtn2 = b2;

  // 🔘 BACK
  int b3 = digitalRead(PIN_BTN_BACK);
  if (b3 == LOW && lastBtn3 == HIGH) {
    Serial.println("BUTTON3:1");

    ultimoBotao = "BACK";
  }
  lastBtn3 = b3;

  // Atualiza botão na tela
  lcd.setCursor(9, 0);
  lcd.print("BTN:");
  lcd.print(ultimoBotao);
  lcd.print(" ");

  // 📡 IR
  if (IrReceiver.decode()) {

    unsigned long codigo = IrReceiver.decodedIRData.decodedRawData;

    Serial.print("IR:");
    Serial.println(codigo, HEX);

    ultimoIR = String(codigo, HEX);

    lcd.setCursor(0, 1);
    lcd.print("IR:");
    lcd.print(ultimoIR);
    lcd.print("     ");

    IrReceiver.resume();
  }

  // KeyPad
  char tecla = keypad.getKey();

  if (tecla) {
    Serial.print("KEY:");
    Serial.println(tecla);
  }

  delay(20);
}