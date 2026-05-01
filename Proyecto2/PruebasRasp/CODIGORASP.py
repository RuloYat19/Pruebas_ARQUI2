import board
import busio
from adafruit_pn532.i2c import PN532_I2C
from RPLCD.i2c import CharLCD
import RPi.GPIO as GPIO
import os
import time
import threading
import json
import uuid
import paho.mqtt.client as mqtt
from datetime import datetime

MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.18")
MQTT_PORT = 1883
TOPIC_PREFIX = "/parkguard"
MQTT_CLIENT_ID = f"raspberry_parkguard_{uuid.uuid4().hex[:8]}"
MQTT_CONNECT_RETRIES = 5
MQTT_RETRY_DELAY_SECONDS = 3
LCD_COLS = 16
LCD_ROWS = 2
LCD_CHARMAP = "A00"
LCD_MIN_UPDATE_INTERVAL = 0.12
I2C_LOCK_TIMEOUT_SECONDS = 0.5
PN532_I2C_ADDRESS = 0x24

# Configurar pines
GPIO.setmode(GPIO.BCM)
GPIO.setup(13, GPIO.OUT)
GPIO.setup(18, GPIO.OUT)
GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(0,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(5,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(26, GPIO.OUT)
GPIO.setup(12, GPIO.OUT)

LEDS_PARQUEO = [17, 27, 22, 10, 11]
for led in LEDS_PARQUEO:
    GPIO.setup(led, GPIO.OUT)
    GPIO.output(led, GPIO.LOW)

SENSORES_PARQUEO = [23, 24, 25, 8, 7]
SENSORES_INVERTIDOS = [23, 24]

for pin in SENSORES_PARQUEO:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

servo_entrada = GPIO.PWM(13, 50)
servo_salida  = GPIO.PWM(18, 50)
ventilador    = GPIO.PWM(12, 1000)
servo_entrada.start(0)
servo_salida.start(0)
ventilador.start(0)

talanquera_abierta = False
alerta_gas         = False
estado_anterior    = [None] * 5
espacios_habilitados = [True] * 5
lcd_lock           = threading.Lock()
pantalla           = None  # variable global del LCD
mqtt_client        = None
mqtt_connected     = False
mqtt_lock          = threading.Lock()
registration_mode  = False
registration_waiting_result = False
registration_cooldown_until = 0.0
gate_open_warning_until = 0.0
lcd_reconnect_in_progress = False
last_lcd_lines = ("", "")
last_lcd_update = 0.0
lcd_error_count = 0
lcd_max_errors = 3

def buzzer_dos_pitidos():
    # Dos pitidos cortos cuando la tarjeta no tiene saldo
    if alerta_gas:
        return
    for _ in range(2):
        GPIO.output(26, GPIO.HIGH)
        time.sleep(0.12)
        GPIO.output(26, GPIO.LOW)
        time.sleep(0.12)

def buzzer_un_pitido():
    # Pitido corto cuando la tarjeta es aceptada
    if alerta_gas:
        return
    GPIO.output(26, GPIO.HIGH)
    time.sleep(0.12)
    GPIO.output(26, GPIO.LOW)

def hora():
    return datetime.now().strftime("%H:%M:%S")

def mover_servo(servo, grados):
    ciclo = 2 + (grados / 18)
    servo.ChangeDutyCycle(ciclo)
    time.sleep(0.5)
    servo.ChangeDutyCycle(0)

def init_lcd():
    for direccion in [0x27, 0x26]:
        try:
            lcd = CharLCD(
                'PCF8574',
                direccion,
                cols=LCD_COLS,
                rows=LCD_ROWS,
                charmap=LCD_CHARMAP,
                auto_linebreaks=False,
            )
            print(f"[{hora()}] LCD encontrado en {hex(direccion)}")
            return lcd
        except Exception as e:
            print(f"[{hora()}] No encontrado en {hex(direccion)}: {e}")
    print(f"[{hora()}] ⚠️ LCD no encontrado, reintentando en 3s...")
    return None

def init_pn532():
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        lock_start = time.time()
        while not i2c.try_lock():
            if time.time() - lock_start > I2C_LOCK_TIMEOUT_SECONDS:
                print(f"[{hora()}] Timeout tomando lock de I2C para PN532")
                return None
            time.sleep(0.01)

        try:
            direcciones = i2c.scan()
        finally:
            i2c.unlock()

        if PN532_I2C_ADDRESS not in direcciones:
            print(
                f"[{hora()}] PN532 no detectado en I2C "
                f"(esperado {hex(PN532_I2C_ADDRESS)}, encontrados {[hex(d) for d in direcciones]})"
            )
            return None

        pn532 = PN532_I2C(i2c, debug=False)
        pn532.SAM_configuration()
        return pn532
    except Exception as e:
        print(f"Error PN532: {e}")
        return None

def reiniciar_lcd():
    global pantalla, last_lcd_lines, last_lcd_update
    pantalla = init_lcd()
    if pantalla is not None:
        last_lcd_lines = ("", "")
        last_lcd_update = 0.0
        print(f"[{hora()}] ✅ LCD listo")

def hilo_reconexion_lcd():
    global pantalla, lcd_reconnect_in_progress
    while pantalla is None:
        reiniciar_lcd()
        if pantalla is None:
            time.sleep(3)
    lcd_reconnect_in_progress = False

def iniciar_reconexion_lcd():
    global lcd_reconnect_in_progress
    if lcd_reconnect_in_progress:
        return
    lcd_reconnect_in_progress = True
    threading.Thread(target=hilo_reconexion_lcd, daemon=True).start()

def _normalizar_linea_lcd(texto):
    limpio = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in str(texto))
    return limpio[:LCD_COLS].ljust(LCD_COLS)

def escribir_lcd(linea1, linea2="", force=False):
    global pantalla, last_lcd_lines, last_lcd_update, lcd_error_count
    if pantalla is None:
        iniciar_reconexion_lcd()
        return

    l1 = _normalizar_linea_lcd(linea1)
    l2 = _normalizar_linea_lcd(linea2)

    if not force and (l1, l2) == last_lcd_lines:
        return

    elapsed = time.time() - last_lcd_update
    if elapsed < LCD_MIN_UPDATE_INTERVAL:
        time.sleep(LCD_MIN_UPDATE_INTERVAL - elapsed)

    escritura_exitosa = False
    try:
        if lcd_lock.acquire(timeout=0.5):
            try:
                pantalla.cursor_pos = (0, 0)
                pantalla.write_string(l1)
                pantalla.cursor_pos = (1, 0)
                pantalla.write_string(l2)
                last_lcd_lines = (l1, l2)
                last_lcd_update = time.time()
                lcd_error_count = 0
                escritura_exitosa = True
            finally:
                lcd_lock.release()
        else:
            print(f"[{hora()}] WARNING: Lock LCD timeout (posible deadlock)")
            pantalla = None
            lcd_error_count += 1
    except Exception as e:
        print(f"[{hora()}] Error LCD: {e}")
        lcd_error_count += 1
        pantalla = None

    if lcd_error_count >= lcd_max_errors:
        print(f"[{hora()}] WARNING: Demasiados errores LCD ({lcd_error_count}), forzando reconexion...")
        lcd_error_count = 0
        iniciar_reconexion_lcd()
    elif not escritura_exitosa and pantalla is not None:
        iniciar_reconexion_lcd()

def leer_sensor(pin):
    lectura = GPIO.input(pin)
    if pin in SENSORES_INVERTIDOS:
        lectura = not lectura
    return lectura

def contar_libres():
    return sum(
        1
        for i, pin in enumerate(SENSORES_PARQUEO)
        if espacios_habilitados[i] and leer_sensor(pin)
    )

def contar_habilitados():
    return sum(1 for h in espacios_habilitados if h)

def actualizar_leds():
    if alerta_gas:
        for led in LEDS_PARQUEO:
            GPIO.output(led, GPIO.HIGH)
    else:
        for i, led in enumerate(LEDS_PARQUEO):
            GPIO.output(led, GPIO.HIGH if not espacios_habilitados[i] else GPIO.LOW)

def publish_space_status(space_id, enabled):
    mqtt_publish(
        f"{TOPIC_PREFIX}/space/status",
        {
            "space_id": int(space_id),
            "enabled": bool(enabled),
            "timestamp": datetime.now().isoformat(),
            "source": "raspberry"
        },
        qos=1
    )

def actualizar_lcd():
    global pantalla
    if pantalla is None:
        iniciar_reconexion_lcd()
        return
    try:
        if alerta_gas:
            escribir_lcd("!! ALERTA GAS !!", "Evacuese ya!!")
        elif contar_libres() == 0:
            escribir_lcd("Parqueo LLENO", "No hay espacio")
        else:
            libres = contar_libres()
            habilitados = contar_habilitados()
            escribir_lcd(f"Parqueos: {libres}/{habilitados}", "Acerca tarjeta")
    except Exception as e:
        print(f"[{hora()}] Error LCD: {e} — reiniciando...")
        pantalla = None
        iniciar_reconexion_lcd()

def mqtt_publish(topic, payload, qos=1, retain=False):
    global mqtt_client, mqtt_connected
    if mqtt_client is None or not mqtt_connected:
        return
    try:
        with mqtt_lock:
            mqtt_client.publish(topic, json.dumps(payload), qos=qos, retain=retain)
    except Exception as e:
        print(f"[{hora()}] Error publicando MQTT en {topic}: {e}")

def mqtt_reason_code_value(reason_code):
    # paho-mqtt v2 can pass ReasonCode objects (not directly castable to int).
    if hasattr(reason_code, "value"):
        return reason_code.value
    if isinstance(reason_code, (int, float)):
        return int(reason_code)
    try:
        return int(reason_code)
    except Exception:
        return str(reason_code)

def publish_estado_talanquera(entrada=None, salida=None):
    if entrada is not None:
        mqtt_publish(
            f"{TOPIC_PREFIX}/actuadores/talanquera-entrada",
            {"estado": bool(entrada), "ts": datetime.now().isoformat()},
            qos=0
        )
    if salida is not None:
        mqtt_publish(
            f"{TOPIC_PREFIX}/actuadores/talanquera-salida",
            {"estado": bool(salida), "ts": datetime.now().isoformat()},
            qos=0
        )

def publish_estado_sistema(ventilador_estado=None, emergencia_estado=None):
    if ventilador_estado is not None:
        mqtt_publish(
            f"{TOPIC_PREFIX}/actuadores/ventilador",
            {"estado": bool(ventilador_estado), "ts": datetime.now().isoformat()},
            qos=0
        )
    if emergencia_estado is not None:
        mqtt_publish(
            f"{TOPIC_PREFIX}/actuadores/emergencia",
            {"estado": bool(emergencia_estado), "ts": datetime.now().isoformat()},
            qos=0
        )

def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    rc = mqtt_reason_code_value(reason_code)
    mqtt_connected = (rc == 0)
    if mqtt_connected:
        print(f"[{hora()}] ✅ MQTT conectado a {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(f"{TOPIC_PREFIX}/access/response", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/emergency/command", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/fan/control", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/exit/command", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/registration/start", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/registration/result", qos=1)
        client.subscribe(f"{TOPIC_PREFIX}/space/manage", qos=1)
        client.publish(f"{TOPIC_PREFIX}/system/raspberry/status", "online", qos=1, retain=True)
        for i, enabled in enumerate(espacios_habilitados, start=1):
            publish_space_status(i, enabled)
    else:
        print(f"[{hora()}] ❌ Error conectando MQTT (rc={rc})")

def on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    global mqtt_connected
    mqtt_connected = False
    rc = mqtt_reason_code_value(reason_code)
    print(f"[{hora()}] MQTT desconectado (rc={rc})")

def on_mqtt_message(client, userdata, msg):
    global talanquera_abierta, registration_mode, registration_waiting_result, registration_cooldown_until
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    if msg.topic.endswith("/access/response"):
        if registration_mode or time.time() < registration_cooldown_until:
            print(f"[{hora()}] Respuesta de acceso ignorada por modo registro")
            return
        granted = payload.get("granted", False)
        message = payload.get("message", "")
        deny_code = payload.get("deny_code", "")
        if granted and not alerta_gas:
            print(f"[{hora()}] ✅ Acceso aprobado por consumer")
            buzzer_un_pitido()
            escribir_lcd("Acceso OK!", "Pasando...")
            mover_servo(servo_entrada, 180)
            time.sleep(0.3)
            mover_servo(servo_entrada, 90)
            talanquera_abierta = True
            publish_estado_talanquera(entrada=True)
        else:
            print(f"[{hora()}] ⛔ Acceso denegado: {message}")
            buzzer_dos_pitidos()
            escribir_lcd("Acceso denegado", "Intente de nuevo")
            time.sleep(1.5)
            actualizar_lcd()

    elif msg.topic.endswith("/registration/start"):
        registration_mode = True
        registration_waiting_result = False
        print(f"[{hora()}] Modo lector activado para registro de tarjeta")
        escribir_lcd("Registro RFID", "Acerque tarjeta")

    elif msg.topic.endswith("/registration/result"):
        ok = bool(payload.get("ok", False))
        state = payload.get("state", "")
        message = payload.get("message", "Resultado de registro")
        registration_waiting_result = False
        if ok:
            buzzer_un_pitido()
        if ok or state == "duplicate":
            registration_mode = False
            registration_cooldown_until = time.time() + 3

        print(f"[{hora()}] Resultado registro RFID: {message}")
        escribir_lcd("Registro RFID", message[:16])

        time.sleep(1.2)
        if not registration_mode:
            actualizar_lcd()

    elif msg.topic.endswith("/fan/control"):
        action = payload.get("action", "off")
        if action == "on":
            ventilador.ChangeDutyCycle(100)
            publish_estado_sistema(ventilador_estado=True)
            print(f"[{hora()}] Ventilador encendido por MQTT")
        else:
            ventilador.ChangeDutyCycle(0)
            publish_estado_sistema(ventilador_estado=False)
            print(f"[{hora()}] Ventilador apagado por MQTT")

    elif msg.topic.endswith("/emergency/command"):
        action = payload.get("action", "deactivate")
        if action == "activate":
            GPIO.output(26, GPIO.HIGH)
            ventilador.ChangeDutyCycle(100)
            mover_servo(servo_entrada, 90)
            mover_servo(servo_salida, 90)
            publish_estado_talanquera(entrada=True, salida=True)
            publish_estado_sistema(ventilador_estado=True, emergencia_estado=True)
            print(f"[{hora()}] Emergencia activada por MQTT")
        else:
            GPIO.output(26, GPIO.LOW)
            ventilador.ChangeDutyCycle(0)
            mover_servo(servo_entrada, 180)
            mover_servo(servo_salida, 0)
            publish_estado_talanquera(entrada=False, salida=False)
            publish_estado_sistema(ventilador_estado=False, emergencia_estado=False)
            print(f"[{hora()}] Emergencia desactivada por MQTT")

    elif msg.topic.endswith("/exit/command"):
        action = payload.get("action", "")
        if action == "open" and not alerta_gas:
            print(f"[{hora()}] Apertura de salida por MQTT")
            mover_servo(servo_salida, 90)
            publish_estado_talanquera(salida=True)

    elif msg.topic.endswith("/space/manage"):
        space_id = int(payload.get("space_id", 0))
        enabled = bool(payload.get("enabled", True))
        idx = space_id - 1
        if idx < 0 or idx >= len(espacios_habilitados):
            print(f"[{hora()}] Comando de espacio invalido: {space_id}")
            return

        espacios_habilitados[idx] = enabled
        estado_anterior[idx] = "DESHAB " if not enabled else None
        actualizar_leds()
        actualizar_lcd()
        publish_space_status(space_id, enabled)
        print(
            f"[{hora()}] Espacio {space_id} "
            f"{'habilitado' if enabled else 'deshabilitado'} por MQTT"
        )

def init_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_CLIENT_ID
    )
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=10)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.on_message = on_mqtt_message
    for intento in range(1, MQTT_CONNECT_RETRIES + 1):
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_start()
            publish_estado_talanquera(entrada=False, salida=False)
            publish_estado_sistema(ventilador_estado=False, emergencia_estado=False)
            return
        except Exception as e:
            print(
                f"[{hora()}] No se pudo conectar al broker MQTT: {e} "
                f"(intento {intento}/{MQTT_CONNECT_RETRIES})"
            )
            if intento < MQTT_CONNECT_RETRIES:
                time.sleep(MQTT_RETRY_DELAY_SECONDS)

    print(f"[{hora()}] ⚠️ MQTT no disponible, el sistema seguira sin broker")

# ─────────────────────────────────────────
# HILO 1: Sensor de gas MQ2
# ─────────────────────────────────────────
def hilo_gas():
    global alerta_gas, talanquera_abierta
    print(f"[{hora()}] Hilo gas iniciado")
    while True:
        if GPIO.input(16) == GPIO.LOW:
            if not alerta_gas:
                alerta_gas = True
                print(f"[{hora()}] ⚠️  GAS DETECTADO - ALERTA ACTIVADA")
                mqtt_publish(
                    f"{TOPIC_PREFIX}/emergency/trigger",
                    {"triggered": True, "gas_level": 100, "timestamp": datetime.now().isoformat()}
                )
                mqtt_publish(
                    f"{TOPIC_PREFIX}/status/gas",
                    {"value": 100, "timestamp": datetime.now().isoformat()},
                    qos=0
                )
                actualizar_leds()
                actualizar_lcd()
                GPIO.output(26, GPIO.HIGH)
                ventilador.ChangeDutyCycle(100)
                publish_estado_sistema(ventilador_estado=True, emergencia_estado=True)
                mover_servo(servo_entrada, 90)
                mover_servo(servo_salida, 90)
                publish_estado_talanquera(entrada=True, salida=True)
                talanquera_abierta = True
        else:
            if alerta_gas:
                alerta_gas = False
                print(f"[{hora()}] ✅ Gas despejado - Alerta desactivada")
                mqtt_publish(
                    f"{TOPIC_PREFIX}/emergency/trigger",
                    {"triggered": False, "gas_level": 0, "timestamp": datetime.now().isoformat()}
                )
                mqtt_publish(
                    f"{TOPIC_PREFIX}/status/gas",
                    {"value": 0, "timestamp": datetime.now().isoformat()},
                    qos=0
                )
                actualizar_leds()
                GPIO.output(26, GPIO.LOW)
                ventilador.ChangeDutyCycle(0)
                publish_estado_sistema(ventilador_estado=False, emergencia_estado=False)
                mover_servo(servo_entrada, 180)
                mover_servo(servo_salida, 0)
                publish_estado_talanquera(entrada=False, salida=False)
                talanquera_abierta = False
                actualizar_lcd()

        time.sleep(0.1)

# ─────────────────────────────────────────
# HILO 2: Monitoreo sensores parqueo
# ─────────────────────────────────────────
def hilo_parqueos():
    global estado_anterior
    print(f"[{hora()}] Hilo parqueos iniciado")
    while True:
        if not alerta_gas:
            hubo_cambio = False
            for i, pin in enumerate(SENSORES_PARQUEO):
                if not espacios_habilitados[i]:
                    if estado_anterior[i] != "DESHAB ":
                        estado_anterior[i] = "DESHAB "
                        hubo_cambio = True
                    continue

                estado = "LIBRE   " if leer_sensor(pin) else "OCUPADO"
                if estado != estado_anterior[i]:
                    estado_prev = estado_anterior[i]
                    estado_anterior[i] = estado
                    hubo_cambio = True
                    mqtt_publish(
                        f"{TOPIC_PREFIX}/occupancy/change",
                        {
                            "space_id": i + 1,
                            "status": "free" if estado.strip() == "LIBRE" else "occupied",
                            "previous_status": None if estado_prev is None else ("free" if estado_prev.strip() == "LIBRE" else "occupied"),
                            "timestamp": datetime.now().isoformat()
                        }
                    )

            if hubo_cambio:
                libres = contar_libres()
                habilitados = contar_habilitados()
                print(f"\n[{hora()}] ── Estado de parqueos ──")
                for i in range(5):
                    if estado_anterior[i] == "DESHAB ":
                        icono = "⚪"
                    else:
                        icono = "🟢" if estado_anterior[i] == "LIBRE   " else "🔴"
                    print(f"  Parqueo {i+1}: {icono} {estado_anterior[i]}")
                print(f"  Total libres: {libres}/{habilitados}")
                print(f"────────────────────────")

            if hubo_cambio and not talanquera_abierta:
                actualizar_lcd()

        time.sleep(0.2)

# ─────────────────────────────────────────
# HILO 3: Sensor IR talanquera entrada
# ─────────────────────────────────────────
def hilo_talanquera():
    global talanquera_abierta
    print(f"[{hora()}] Hilo talanquera entrada iniciado")
    while True:
        if talanquera_abierta and not alerta_gas:
            if GPIO.input(21) == GPIO.LOW:
                print(f"[{hora()}] Vehiculo detectado, esperando que pase...")
                escribir_lcd("Esperando...", "vehiculo...")

                while GPIO.input(21) == GPIO.LOW:
                    time.sleep(0.05)

                print(f"[{hora()}] Cerrando talanquera entrada...")
                time.sleep(0.3)
                mover_servo(servo_entrada, 180)
                publish_estado_talanquera(entrada=False)
                talanquera_abierta = False
                time.sleep(0.5)
                actualizar_lcd()

        time.sleep(0.05)

# ─────────────────────────────────────────
# HILO 4: Finales de carrera salida
# ─────────────────────────────────────────
def hilo_salida():
    print(f"[{hora()}] Hilo talanquera salida iniciado")
    while True:
        if not alerta_gas:
            if GPIO.input(5) == GPIO.LOW:
                print(f"[{hora()}] Abriendo salida...")
                mqtt_publish(
                    f"{TOPIC_PREFIX}/exit/request",
                    {"space_id": 0, "timestamp": datetime.now().isoformat()}
                )
                escribir_lcd("Salida:", "Abriendo...")
                mover_servo(servo_salida, 90)
                publish_estado_talanquera(salida=True)
                while GPIO.input(5) == GPIO.LOW:
                    time.sleep(0.05)

            if GPIO.input(0) == GPIO.LOW:
                print(f"[{hora()}] Cerrando salida...")
                escribir_lcd("Salida:", "Cerrando...")
                mover_servo(servo_salida, 0)
                publish_estado_talanquera(salida=False)
                time.sleep(0.5)
                actualizar_lcd()
                while GPIO.input(0) == GPIO.LOW:
                    time.sleep(0.05)

        time.sleep(0.05)

# ─────────────────────────────────────────
# HILO PRINCIPAL: Lector RFID
# ─────────────────────────────────────────
def main():
    global talanquera_abierta, pantalla, registration_mode, registration_waiting_result, registration_cooldown_until, gate_open_warning_until

    # Iniciar LCD sin bloquear el arranque del sistema
    reiniciar_lcd()
    if pantalla is None:
        iniciar_reconexion_lcd()
    pn532 = init_pn532()
    init_mqtt()
    actualizar_lcd()

    t1 = threading.Thread(target=hilo_gas,        daemon=True)
    t2 = threading.Thread(target=hilo_parqueos,   daemon=True)
    t3 = threading.Thread(target=hilo_talanquera, daemon=True)
    t4 = threading.Thread(target=hilo_salida,     daemon=True)
    t1.start()
    t2.start()
    t3.start()
    t4.start()

    print(f"[{hora()}] Sistema iniciado - Esperando tarjeta RFID...")
    print("────────────────────────────────────────────")

    try:
        while True:
            if alerta_gas:
                time.sleep(0.1)
                continue

            if registration_mode:
                if pn532 is None:
                    print(f"[{hora()}] Reconectando PN532 para registro...")
                    time.sleep(1)
                    pn532 = init_pn532()
                    continue

                if registration_waiting_result:
                    time.sleep(0.1)
                    continue

                try:
                    uid = pn532.read_passive_target(timeout=0.5)
                except Exception as e:
                    print(f"[{hora()}] Error leyendo tarjeta en modo registro: {e}")
                    pn532 = None
                    continue

                if uid is not None:
                    rfid = "".join([format(i, "02X") for i in uid])
                    print(f"[{hora()}] Tarjeta detectada para registro: {rfid}")
                    mqtt_publish(
                        f"{TOPIC_PREFIX}/registration/card_scanned",
                        {
                            "rfid": rfid,
                            "timestamp": datetime.now().isoformat(),
                            "source": "raspberry"
                        }
                    )
                    registration_waiting_result = True
                    escribir_lcd("Validando", "registro...")
                time.sleep(0.1)
                continue

            if contar_libres() == 0:
                time.sleep(0.1)
                continue

            if time.time() < registration_cooldown_until:
                time.sleep(0.1)
                continue

            if pn532 is None:
                print(f"[{hora()}] Reconectando PN532...")
                time.sleep(1)
                pn532 = init_pn532()
                continue

            if talanquera_abierta:
                try:
                    uid = pn532.read_passive_target(timeout=0.2)
                except Exception as e:
                    print(f"[{hora()}] Error leyendo tarjeta con talanquera abierta: {e}")
                    pn532 = None
                    continue

                if uid is not None and time.time() >= gate_open_warning_until:
                    print(f"[{hora()}] ⚠️ Tarjeta detectada con talanquera arriba, acceso ignorado")
                    buzzer_dos_pitidos()
                    gate_open_warning_until = time.time() + 2.0

                time.sleep(0.1)
                continue

            try:
                uid = pn532.read_passive_target(timeout=0.5)
            except Exception as e:
                print(f"[{hora()}] Error leyendo tarjeta: {e}")
                pn532 = None
                continue

            if uid is not None:
                uid_str = [hex(i) for i in uid]
                print(f"\n[{hora()}] ✅ Tarjeta detectada: {uid_str}")
                rfid = "".join([format(i, "02X") for i in uid])
                mqtt_publish(
                    f"{TOPIC_PREFIX}/access/request",
                    {
                        "rfid": rfid,
                        "space_available": contar_libres() > 0 and contar_habilitados() > 0,
                        "timestamp": datetime.now().isoformat(),
                        "source": "raspberry"
                    }
                )
                escribir_lcd("Validando...", "Espere")
                time.sleep(1.0)

    except KeyboardInterrupt:
        print(f"\n[{hora()}] Saliendo...")
        if mqtt_client is not None:
            try:
                mqtt_client.publish(f"{TOPIC_PREFIX}/system/raspberry/status", "offline", qos=1, retain=True)
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except Exception:
                pass
        mover_servo(servo_entrada, 180)
        mover_servo(servo_salida, 0)
        publish_estado_talanquera(entrada=False, salida=False)
        GPIO.output(26, GPIO.LOW)
        ventilador.ChangeDutyCycle(0)
        publish_estado_sistema(ventilador_estado=False, emergencia_estado=False)
        for led in LEDS_PARQUEO:
            GPIO.output(led, GPIO.LOW)
        servo_entrada.stop()
        servo_salida.stop()
        ventilador.stop()
        GPIO.cleanup()
        try:
            pantalla.clear()
        except:
            pass

main()
