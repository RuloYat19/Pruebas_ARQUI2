import board
import busio
from adafruit_pn532.i2c import PN532_I2C
from RPLCD.i2c import CharLCD
import time

# Inicializar LCD
lcd = CharLCD('PCF8574', 0x27)  

# Inicializar PN532
i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, debug=False)
pn532.SAM_configuration()

lcd.clear()
lcd.write_string("Listo!")
lcd.crlf()
lcd.write_string("Acerca tarjeta")

print("Esperando tarjeta RFID...")

while True:
    uid = pn532.read_passive_target(timeout=0.5)
    
    if uid is not None:
        uid_str = [hex(i) for i in uid]
        print(f"Tarjeta detectada: {uid_str}")
        
        lcd.clear()
        lcd.write_string("Tarjeta detectada")
        lcd.crlf()
        lcd.write_string(str(uid_str))
        
        time.sleep(2)
        
        lcd.clear()
        lcd.write_string("Listo!")
        lcd.crlf()
        lcd.write_string("Acerca tarjeta")