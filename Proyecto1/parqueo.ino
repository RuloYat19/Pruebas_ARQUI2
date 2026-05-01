#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_PN532.h>
#include <Servo.h>

LiquidCrystal_I2C lcd(0x26, 16, 2);
Adafruit_PN532 nfc(-1, -1);
Servo servoEntrada;
Servo servoSalida;

#define MQ2_DO         2
#define BUZZER_PIN     8
#define SERVO_ENTRADA  11
#define SERVO_SALIDA   10
#define VENTILADOR_PIN 9

#define BTN_ABRIR_SALIDA  13
#define BTN_CERRAR_SALIDA 3

#define SENSOR_1        12
#define SENSOR_2        4
#define SENSOR_3        6
#define SENSOR_4        5
#define SENSOR_5        7
#define TOTAL_PARQUEOS  5

volatile bool alertaGasActiva = false;
volatile bool cambioGas       = false;

uint8_t tarjetasUID[][7] = {
  {0x82, 0xC8, 0x7B, 0x05, 0x00, 0x00, 0x00},
  {0x2A, 0x43, 0x09, 0x02, 0x00, 0x00, 0x00},
  {0xC5, 0xEA, 0xB1, 0x2B, 0x00, 0x00, 0x00},
  {0x04, 0x3F, 0x75, 0xCA, 0x52, 0x76, 0x80},
  {0x09, 0x1E, 0x1B, 0x60, 0x00, 0x00, 0x00}
};
uint8_t tarjetasLongitud[] = {4, 4, 4, 7, 4};
String usuarios[] = {
  "Alexxander IronF",
  "Platinum Trinity",
  "Revolver Ocelot",
  "Inspector Lunge",
  "Booster Gold"
};
const int totalUsuarios = sizeof(usuarios) / sizeof(usuarios[0]);

void ISR_Gas() {
  cambioGas = true;
}

int contarOcupados() {
  int ocupados = 0;
  if (digitalRead(SENSOR_1) == LOW) ocupados++;
  if (digitalRead(SENSOR_2) == LOW) ocupados++;
  if (digitalRead(SENSOR_3) == LOW) ocupados++;
  if (digitalRead(SENSOR_4) == LOW) ocupados++;
  if (digitalRead(SENSOR_5) == LOW) ocupados++;
  return ocupados;
}

void mostrarPantallaGas() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("!! ALERTA GAS !!");
  lcd.setCursor(0, 1);
  lcd.print("Evacuar zona!!");
}

void mostrarPantallaLleno() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("** LLENO **");
  lcd.setCursor(0, 1);
  lcd.print("No hay espacios");
}

void refrescarPantalla(int ocupados) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Hola!");
  lcd.setCursor(0, 1);
  lcd.print("Parqueo: ");
  lcd.print(ocupados);
  lcd.print("/");
  lcd.print(TOTAL_PARQUEOS);
}

String buscarUsuario(uint8_t* uid, uint8_t longitud) {
  for (int i = 0; i < totalUsuarios; i++) {
    if (tarjetasLongitud[i] != longitud) continue;
    bool coincide = true;
    for (int j = 0; j < longitud; j++) {
      if (tarjetasUID[i][j] != uid[j]) { coincide = false; break; }
    }
    if (coincide) return usuarios[i];
  }
  return "";
}

void setup() {
  Serial.begin(9600);

  lcd.init();
  lcd.backlight();

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  pinMode(VENTILADOR_PIN, OUTPUT);
  digitalWrite(VENTILADOR_PIN, LOW);

  pinMode(MQ2_DO, INPUT);
  attachInterrupt(digitalPinToInterrupt(MQ2_DO), ISR_Gas, CHANGE);

  pinMode(SENSOR_1, INPUT_PULLUP);
  pinMode(SENSOR_2, INPUT_PULLUP);
  pinMode(SENSOR_3, INPUT_PULLUP);
  pinMode(SENSOR_4, INPUT_PULLUP);
  pinMode(SENSOR_5, INPUT_PULLUP);

  pinMode(BTN_ABRIR_SALIDA,  INPUT_PULLUP);
  pinMode(BTN_CERRAR_SALIDA, INPUT_PULLUP);

  servoEntrada.attach(SERVO_ENTRADA);
  servoEntrada.write(180);
  Serial.println("Talanquera ENTRADA: posicion inicial (180°)");
  delay(500);

  servoSalida.attach(SERVO_SALIDA);
  servoSalida.write(180);
  Serial.println("Talanquera SALIDA: posicion inicial (180°)");
  delay(500);

  refrescarPantalla(contarOcupados());
  Serial.println("Sistema iniciado");

  nfc.begin();
  uint32_t version = nfc.getFirmwareVersion();
  if (!version) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("PN532 error");
    Serial.println("ERROR: PN532 no encontrado");
    while (1);
  }
  nfc.SAMConfig();
  Serial.println("Sistema listo");
}

void loop() {

  // ── 1. PROCESAR EVENTO DE ISR (máxima prioridad) ──────────────────
  if (cambioGas) {
    cambioGas = false;

    bool gasDetectado = (digitalRead(MQ2_DO) == LOW);

    if (gasDetectado) {
      alertaGasActiva = true;
      digitalWrite(BUZZER_PIN, HIGH);
      digitalWrite(VENTILADOR_PIN, HIGH);
      Serial.println("Ventilador: ON");

      servoEntrada.write(90);
      Serial.println("Talanquera ENTRADA: abierta por gas (90°)");
      delay(500);
      servoSalida.write(90);
      Serial.println("Talanquera SALIDA: abierta por gas (90°)");

      mostrarPantallaGas();
      Serial.println("ALERTA GAS!");
    } else {
      alertaGasActiva = false;
      digitalWrite(BUZZER_PIN, LOW);
      digitalWrite(VENTILADOR_PIN, LOW);
      Serial.println("Ventilador: OFF");

      servoEntrada.write(180);
      Serial.println("Talanquera ENTRADA: cerrada (180°)");
      delay(500);
      servoSalida.write(180);
      Serial.println("Talanquera SALIDA: cerrada (180°)");

      Serial.println("Gas normalizado");
      refrescarPantalla(contarOcupados());
    }
  }

  if (alertaGasActiva) {
    return;
  }

  // ── 2. BOTONES SALIDA ─────────────────────────────────────────────
  if (digitalRead(BTN_ABRIR_SALIDA) == LOW) {
    servoSalida.write(90);
    Serial.println("Talanquera SALIDA: abierta por boton (90°)");
    delay(300);  // antirebote
  }

  if (digitalRead(BTN_CERRAR_SALIDA) == LOW) {
    servoSalida.write(180);
    Serial.println("Talanquera SALIDA: cerrada por boton (180°)");
    delay(300);  // antirebote
  }

  // ── 3. ESTADO DEL PARQUEO ─────────────────────────────────────────
  static int ocupadosAnterior = -1;
  int ocupadosActual = contarOcupados();

  if (ocupadosActual != ocupadosAnterior) {
    ocupadosAnterior = ocupadosActual;
    Serial.print("Parqueo: ");
    Serial.print(ocupadosActual);
    Serial.print("/");
    Serial.println(TOTAL_PARQUEOS);
    Serial.print("Sensor 1 (pin 12): "); Serial.println(digitalRead(SENSOR_1) == LOW ? "OCUPADO" : "libre");
    Serial.print("Sensor 2 (pin 4):  "); Serial.println(digitalRead(SENSOR_2) == LOW ? "OCUPADO" : "libre");
    Serial.print("Sensor 3 (pin 6):  "); Serial.println(digitalRead(SENSOR_3) == LOW ? "OCUPADO" : "libre");
    Serial.print("Sensor 4 (pin 5):  "); Serial.println(digitalRead(SENSOR_4) == LOW ? "OCUPADO" : "libre");
    Serial.print("Sensor 5 (pin 7):  "); Serial.println(digitalRead(SENSOR_5) == LOW ? "OCUPADO" : "libre");

    if (ocupadosActual >= TOTAL_PARQUEOS) {
      mostrarPantallaLleno();
    } else {
      refrescarPantalla(ocupadosActual);
    }
  }

  if (ocupadosActual >= TOTAL_PARQUEOS) {
    return;
  }

  // ── 4. LECTURA DE TARJETAS ────────────────────────────────────────
  uint8_t uid[7];
  uint8_t uidLength;

  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {

    Serial.println("---------------------------");
    Serial.println("Tarjeta detectada!");
    Serial.print("ID: ");
    for (int i = 0; i < uidLength; i++) {
      if (uid[i] < 0x10) Serial.print("0");
      Serial.print(uid[i], HEX);
      Serial.print(" ");
    }
    Serial.println();

    String nombre = buscarUsuario(uid, uidLength);
    lcd.clear();

    if (nombre != "") {
      lcd.setCursor(0, 0);
      lcd.print("Bienvenido!");
      lcd.setCursor(0, 1);
      lcd.print(nombre);
      Serial.print("Acceso concedido: ");
      Serial.println(nombre);

      servoEntrada.write(90);
      Serial.println("Talanquera ENTRADA: abierta (90°)");
    } else {
      lcd.setCursor(0, 0);
      lcd.print("Acceso denegado");
      lcd.setCursor(0, 1);
      lcd.print("No registrado");
      Serial.println("Acceso denegado");
    }

    Serial.println("---------------------------");
    delay(3000);
    servoEntrada.write(180);
    Serial.println("Talanquera ENTRADA: cerrada (180°)");
    refrescarPantalla(ocupadosActual);
  }
}