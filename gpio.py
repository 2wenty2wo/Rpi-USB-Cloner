import RPi.GPIO as GPIO

PIN_A = 5
PIN_B = 6
PIN_L = 27
PIN_R = 23
PIN_U = 17
PIN_D = 22
PIN_C = 4

PINS = (PIN_A, PIN_B, PIN_L, PIN_R, PIN_U, PIN_D, PIN_C)


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def read_button(pin):
    return GPIO.input(pin)


def read_buttons(pins):
    return {pin: read_button(pin) for pin in pins}


def is_pressed(pin):
    return read_button(pin) == GPIO.LOW


def cleanup():
    GPIO.cleanup()


setup_gpio()
