import AnalogShield as AS
import matplotlib.pyplot as plt
import numpy as np
import operator
import RigolInstruments as RI
import time

a = AS.AnalogShield("/dev/analog_shield", "D784216")

a.adc_calibrate(0, "/dev/multimeter")

# Connect to the multimeter
multimeter = RI.DM3058("/dev/multimeter")

actual_readings = []
adc_readings = []

# A big jump in DAC output occurs going to -5V, so give the multimeter extra time to adjust
a.analog_write(0, -5)
time.sleep(2)
for v_out in range(-5, 6): # Go from -5 to 5V in 1V steps
    a.analog_write(0, v_out)

    # Collect data
    time.sleep(0.01) # Delay to let the multimeter adjust
    v_actual = multimeter.voltage()
    v_adc = np.mean(a.analog_read(0, 500, correct=False)) # Average 500 readings to reduce noise

    # Save data
    actual_readings.append(v_actual)
    adc_readings.append(v_adc)

error = map(operator.sub, adc_readings, actual_readings)

plt.plot(actual_readings, error, ".")
plt.title("ADC error - without calibration")
plt.xlabel("Input [V]")
plt.ylabel("Error (ADC - input) [V]")
plt.savefig("adc_error.png")
