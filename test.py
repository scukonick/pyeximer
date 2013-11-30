__author__ = 'alexwinner'
from time import sleep
import signal
def handler(a,b):
    print("Catched signal")
    exit()

while True:
    sleep(3)


signal.signal(signal.SIGTERM,handler)
