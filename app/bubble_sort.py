#Bubble sort benchmark
#300426 from https://blog.miguelgrinberg.com/post/benchmarking-micropython

import time
print("Bubble sort benchmark")
print("Benchmarks:")
print("Framework Laptop: 0.168s")
print("Pi Pico2W:        15.7s")
print("ESP32-S3:         19.1s")
print("ESP8266:          78.2s")


if hasattr(time, 'ticks_us'):
    def t():
        return time.ticks_us() / 1000000
else:
    def t():
        return time.time()

def fibo(n):
    if n <= 1:
        return n
    else:
        return fibo(n-1) + fibo(n-2)

fibo(30)  # warm up
s = t()
fibo(30)
e = t()
print(int((e - s) * 1000) / 1000)