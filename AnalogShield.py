from __future__ import print_function, division

import numpy as np # For calculating means and standard deviations
import os.path # For saving ADC and DAC calibration
import pickle # For reading and saving calibration to a file
import serial # For communicating with the Arduino
import sys # Determine what version of Python is running
import time
import warnings

class AnalogShield(object):
    def __init__(self, address, calibration_location=None):
        """
        address: the serial port of the shield.

        calibration_location: if provided, DAC and ADC calibration
        will be loaded from and saved to this file.
        """

        self.device = serial.Serial(port=address, baudrate=2e6, timeout=0)
        time.sleep(3) # Ensure the first bytes of serial communication aren't dropped

        self.ramp = {
            "on": [False] * 4,
            "period": [100] * 4,
            "amplitude": [5] * 4,
            "offset": [0] * 4,
            "phase": [0]*4,
            "function": ["triangle"] * 4
        }

        # Error correction functions - do nothing by default
        self.adc_correct = [None] * 4
        self.dac_correct = [None] * 4

        # If provided, load the calibration from a file
        self.calibration_location = calibration_location
        if self.calibration_location is not None and os.path.exists(calibration_location):
            with open(self.calibration_location, "rb") as calibration_file:
                calibration = pickle.load(calibration_file)

                self.adc_correct = calibration["adc"]
                self.dac_correct = calibration["dac"]

        # Reset to known default state
        self.queue_off()
        self.ramp_off("all")
        self.ramp_period("all", 100)
        self.ramp_amplitude("all", 5)
        self.ramp_offset("all", 0)
        self.ramp_phase("all", 0)
        self.ramp_function("all", "triangle")

        self.analog_write("all", 0)

        # For some reason, the first three readings of the ADC
        # channels are sometimes 0x0000, 0x0000, 0x00**. After that,
        # reading acts normally. This is a temporary fix to swallow
        # those three strange values until a better solution is found.
        for channel in range(4):
            self.analog_read(channel, 5)

    def write(self, identifier, arg=0):
        """
        Write a command to the Analog Shield and return the response.

        The identifier is a two-character string (case-insensitive).
        The argument to the command must be an 16-bit unsigned integer
        (i.e. 0 <= arg <= 0xffff).  If the argument is omitted, two
        null bytes will be sent.
        """

        ## Write the command
        # Convert the command into a series of bytes
        byte_list = bytearray([ord(char) for char in identifier])
        byte_list.extend(AnalogShield.encode_num(arg))

        self.device.write(byte_list)

        ## Read the response
        # The response to a command is always terminated by a
        # semicolon, so keep polling the input buffer until we read
        # one.
        response = self.device.read()
        while True: # Keep reading until we break out of the loop
            response += self.device.read()

            if len(response) > 0:
                 # In Python 2 slicing bytes results in str, but in
                 # Python 3 it gives an int. We therefore need to
                 # check both cases to version-independently determine
                 # if the character we just read is a semicolon. 0x3b
                 # is ASCII semicolon.
                if response[-1] == ";" or response[-1] == 0x3b:
                    break

        # If Python 3 (or later), convert to a Unicode string
        if sys.version_info.major >= 3:
            response = response.decode("latin-1")

        return response[:-1] # Strip the semicolon

    def adc_calibrate(self, channel, multimeter):
        """
        There exists a linear error on each ADC channel, for some
        reason. This method determines it and saves the results to a
        compensation table (AnalogShield.adc_correct). To perform the
        calibration, connect DAC channel 0 to the ADC being
        calibrated. A multimeter with a Python interface must also be
        attached to the computer. How that multimeter works is
        irrelevant, as long as the Python interface has a method
        voltage() that returns a number.
        """

        actual_readings = []
        adc_readings = []

        # A big jump in DAC output occurs going to -5V, so give the multimeter extra time to adjust
        self.analog_write(0, -5)
        time.sleep(2)
        for v_out in range(-5, 6): # Go from -5 to 5V in 1V steps
            self.analog_write(0, v_out)

            # Collect data
            time.sleep(0.01) # Delay to let the multimeter adjust
            v_actual = multimeter.voltage()
            v_adc = np.mean(self.analog_read(channel, 500, correct=False)) # Average 500 readings to reduce noise

            # Save data
            actual_readings.append(v_actual)
            adc_readings.append(v_adc)

        # Calculate a linear regression that fits the error data
        self.adc_correct[channel] = np.poly1d(np.polyfit(adc_readings, actual_readings, 1))

        # If a calibration file was given, save the updated calibration
        if self.calibration_location is not None:
            # Read the existing calibrations, if the file exists
            if os.path.exists(self.calibration_location):
                with open(self.calibration_location, "rb") as calibration_file:
                    calibration = pickle.load(calibration_file)

            else:
                calibration = {"adc": self.adc_correct, "dac": self.dac_correct}

            # Update the calibration
            calibration["adc"][channel] = self.dac_correct[channel]

            with open(self.calibration_location, "wb") as calibration_file:
                pickle.dump(calibration, calibration_file, protocol=2) # Use a Python 2--compatible protocol

    def dac_calibrate(self, channel, multimeter):
        """
        There exists a linear error on each DAC channel, for some
        reason. This method determines it and saves the results to a
        compensation table (AnalogShield.dac_correct). To perform the
        calibration, a multimeter with a Python interface must be
        attached to the computer. How that multimeter works is
        irrelevant, as long as the Python interface has a method
        voltage() that returns a number.
        """

        input_v = [v for v in range(-5, 6)]
        dac_output = []

        # A big jump in DAC output occurs going to -5V, so give the multimeter extra time to adjust
        self.analog_write(channel, -5, correct=False)
        time.sleep(2)
        for v_out in input_v: # Go from -5 to 5V in 1V steps
            self.analog_write(channel, v_out, correct=False)

            # Collect data
            time.sleep(0.01) # Delay to let the multimeter adjust
            v_actual = multimeter.voltage()

            # Save data
            dac_output.append(v_actual)

        # Calculate a linear regression that fits the error data
        self.dac_correct[channel] = np.poly1d(np.polyfit(dac_output, input_v, 1))

        # If a calibration file was given, save the updated calibration
        if self.calibration_location is not None:
            # Read the existing calibrations, if the file exists
            if os.path.exists(self.calibration_location):
                with open(self.calibration_location, "rb") as calibration_file:
                    calibration = pickle.load(calibration_file)

            else:
                calibration = {"adc": self.adc_correct, "dac": self.dac_correct}

            # Update the calibration
            calibration["dac"][channel] = self.dac_correct[channel]

            with open(self.calibration_location, "wb") as calibration_file:
                pickle.dump(calibration, calibration_file, protocol=2) # Use a Python 2--compatible protocol

    # Ramp methods
    def ramp_running(self, channel):
        return self.ramp["on"][channel]

    def ramp_on(self, channel):
        if channel == "all":
            for c in range(4):
                self.ramp_on(c)
            return

        self.ramp["on"][channel] = True
        self.write("rc", channel)
        return self.write("r1")

    def ramp_off(self, channel):
        if channel == "all":
            for c in range(4):
                self.ramp_off(c)
            return

        self.ramp["on"][channel] = False
        self.write("rc", channel)
        return self.write("r0")

    def ramp_period(self, channel, time=None):
        """
        Set the period of the triangle wave.  Without an argument,
        return the current value.
        """

        if channel == "all":
            for c in range(4):
                self.ramp_period(c, time)
            return

        if time is None:
            return self.ramp["period"][channel]
        elif time > 0:
            self.ramp["period"][channel] = time
            self.write("rc", channel)
            return self.write("rp", time)
        else:
            raise ValueError("Period must be positive.")

    def ramp_amplitude(self, channel, amp=None):
        """
        Set the amplitude of the triangle wave (equal to
        V_max-V_average).  Without an argument, return the current
        value.
        """

        if channel == "all":
            for c in range(4):
                self.ramp_amplitude(c, amp)
            return

        if amp is None:
            return self.ramp["amplitude"][channel]
        elif 0 <= amp <= 5:
            self.ramp["amplitude"][channel] = amp
            amp_bits = AnalogShield.volts_to_bits(amp)

            self.write("rc", channel)
            return self.write("ra", amp_bits)
        else:
            raise ValueError("Amplitude must be between 0V and 5V.")

    def ramp_offset(self, channel, offset=None):
        """
        Set the offset of the triangle wave (equal to V_average-0V).
        Without an argument, return the current value.
        """

        if channel == "all":
            for c in range(4):
                self.ramp_offset(c, offset)
            return

        if offset is None:
            return self.ramp["offset"][channel]
        elif -5 <= offset <= 5:
            self.ramp["offset"][channel] = offset
            offset_bits = AnalogShield.volts_to_bits(offset)

            self.write("rc", channel)
            return self.write("ro", offset_bits)

    def ramp_phase(self, channel, phase=None):
        """
        Set the phase shift of the wave, expressed as a percentage of
        the period. Without an argument, return the current value.
        """

        if channel == "all":
            for c in range(4):
                self.ramp_phase(c, phase)
            return

        if phase is None:
            return self.ramp["phase"][channel]
        elif 0 <= phase <= 100:
            self.ramp["phase"][channel] = phase
            phase_bits = int(phase * 65535/100) # Convert from percent to bits

            self.write("rc", channel)
            return self.write("rs", phase_bits)

    def ramp_function(self, channel, function=None):
        """
        Set the function used to generate the wave. Without an
        argument, return the current value. Acceptable values:
        triangle, sin, and square.
        """

        if channel == "all":
            for c in range(4):
                self.ramp_function(c, function)
            return

        if function is None:
            return self.ramp["function"][channel]
        elif function in ("triangle", "sin", "square"):
            self.ramp["function"][channel] = function
            func_num = {"triangle":0, "sin":1, "square":2}[function]

            self.write("rc", channel)
            return self.write("rf", func_num)
        else:
            raise ValueError("Invalid ramp function: {}".format(function))

    # DAC methods
    def analog_write(self, channel, val, correct=True):
        """Set the value on one of the DACs."""

        # Apply correction function, if desired
        if correct and channel != "all":
            if self.dac_correct[channel] is not None:
                val = self.dac_correct[channel](val)

                # Make sure the corrected value stays within range
                val = max(-5, val)
                val = min(5, val)
            else:
                warnings.warn("DAC channel {} is not yet calibrated.".format(channel), RuntimeWarning, stacklevel=2)

        val_bits = AnalogShield.volts_to_bits(val)
        if isinstance(channel, str) and channel.lower() == "all":
            return self.write("va", val_bits)
        elif 0 <= channel <= 3:
            return self.write("v"+str(channel), val_bits)

    # ADC methods
    def analog_read(self, channel, samples=1, correct=True):
        """
        Read one or more values off of the ADC.

        This method returns an array of voltages.  The samples are
        taken as fast as possible, without a regular delay.
        """

        if 0 <= channel <= 3:
            # Extract values from the response
            response = self.write("A"+str(channel), samples)
            bit_vals = (int(x, 16) for x in response.split(","))

            # Convert to volts
            voltages = [AnalogShield.bits_to_volts(b) for b in bit_vals]

            # Apply correction function, if desired
            if correct:
                if self.adc_correct[channel] is not None:
                    voltages = [self.adc_correct[channel](v) for v in voltages]
                else:
                    warnings.warn("ADC channel {} is not yet calibrated.".format(channel), RuntimeWarning, stacklevel=2)

            return voltages
        else:
            raise ValueError("Invalid channel: {}".format(channel))

    # Queue methods
    def queue_on(self):
        return self.write('qm', 1)

    def queue_off(self):
        return self.write('qm', 0)

    @staticmethod
    def bits_to_volts(bits):
        """Convert a voltage as encoded by the Analog Shield into volts."""

        return 2*bits/13107 - 5

    @staticmethod
    def volts_to_bits(volts):
        """Convert volts into a 16-bit number for the Analog Shield."""

        return int((13107*volts + 65535)/2)

    @staticmethod
    def encode_num(n):
        """
        Convert a 16-bit number to two separate bytes in MSB, LSB
        order.

        How it works:

            - Input bytes: 0100 1111 0010 1011

            - MSB: shift right eight bits, discarding the rightmost
              bits

            - LSB: bitwise AND with 0000 0000 1111 1111, setting the
              leftmost byte to zero
        """

        return [n >> 8, n & 0x00ff]
