import AnalogShield as AS
import matplotlib.pyplot as plt
import operator
import RigolInstruments as RI
import time

a = AS.AnalogShield("/dev/analog_shield", "D784216")
meter = RI.DM3058("/dev/multimeter")

input_v = [v for v in range(-5, 6)] # Go from -5V to 5V in 10mV steps
dac = []

a.analog_write(1, -5)
time.sleep(2)

for v in input_v:
    a.analog_write(1, v)
    time.sleep(1)
    dac.append(meter.voltage())

error = map(operator.sub, dac, input_v)

plt.plot(input_v, error, ".")
plt.xlabel("Input [V]")
plt.ylabel("DAC error (DAC - input) [V]")
plt.show()
