# oled-i2c-test.py
# SSD1306 128x32 OLED test. SDA=GPIO6, SCL=GPIO7.
from machine import SoftI2C, Pin
import ssd1306

i2c = SoftI2C(scl=Pin(7), sda=Pin(6), freq=400000)

print('OLED I2C test: 129x32 display')
    
devices = i2c.scan()
if not devices:
    print('No I2C devices found')
    print('Check wiring: SDA=GPIO6, SCL=GPIO7')
else:
    print('I2C devices:', [hex(d) for d in devices])

    oled = ssd1306.SSD1306_I2C(128, 32, i2c)

    oled.fill(0)
    oled.text('Cyberdreck', 0, 0)
    oled.text('OLED test OK', 0, 12)
    oled.text('SDA=6 SCL=7', 0, 24)
    oled.show()

    print('OLED initialised, display updated')
