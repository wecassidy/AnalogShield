This library controls a Digilent Analog Shield connected to an Arduino
from Python over serial. There are three layers to the system: the
Arduino side (which controls the Analog Shield), the Python side
(which is what is exposed to the user), and the serial protocol that
communicates between the two.

# Quick start
1. Upload `analog_shield.ino` to the Arduino
2. Determine the serial port of the Arduino
   - Check the Arduino application
   - Mac/Linux only:
   ```
   $ find /dev -name 'ttyUSB*' -o -name 'ttyACM*' -o -name 'ttyAMA*'
   ```
3. Connect the Python library to the shield:
   ```python
   >>> import AnalogShield as AS
   >>> a = AS.AnalogShield("/dev/analog_shield_port")
   ```

## Example use
```python
>>> a.ramp_on(0) # Ramp on DAC 0
>>> a.ramp_amplitude(0, 3.3) # Set the amplitude of the ramp to 3.3V
>>> a.analog_read(2, 3) # Take 3 samples of ADC 2
[0.32415, 0.314525, 0.328846]
>>> a.analog_write(3, -2) # Set DAC 3 to -2V
```

# Python
## Initialization
- Initialize serial communications
  - 2 Mbps baud rate
  - Set timeout to 0
- Pause for 3s because it fixed some bugs
- Initialize ramp with known settings
  - Enabled: no
  - Period: 100ms
  - Amplitude: 5V
  - Offset: 0V
  - Phase shift: none
  - Shape: triangle
- Load calibrations, if provided
- Turn off queue mode
- Set all DACs to 0V
- For some reason, the first readings from each ADC were sometimes
  `0x0000`, `0x0000`, `0x00**`. To fix this, take five samples on each
  channel

## DAC and ADC
### `analog_write(channel, voltage, correct=True)`: output constant voltage
This method sets the value of one of the DACs. The channel can be
specified as an integer or `"all"` to set all channels to the same
level. Voltage is expected as a float. If the optional parameter
`correct` is `True`, the method will apply the correction function
that was determined when the DAC was calibrated (see the section on
calibration for details on that process). If the DAC hasn't yet been
calibrated, a warning will be printed.

Example use:
```python
>>> a.analog_write(2, -3.5) # Set channel 2 to -3.5V
>>> a.analog_write(0, 4.1, correct=False) # Set channel 0 to 4.1V while supressing error correction
>>> a.analog_write("all", 0) # Set all channels to 0V
```

### `analog_read(channel, samples=1, correct=True)`: sample the ADC
This method takes a number of samples (default 1) as fast as possible
from the ADC, then returns them as a list of floats. As before, the
channel should be an integer. If the optional parameter `correct` is
`True` and the ADC has been calibrated, the correction function will
be applied to the measured voltages (see the section on calibration
for details on that process). If the ADC hasn't yet been calibrated, a
warning will be printed.

Since the ADC samples as fast as possible, a large number of samples
can be taken and then averaged to reduce error from a noisy
signal. The Arduino runs significantly faster than the Python code, so
taking several samples is not significantly slower than taking just
one.

Example use:
```python
>>> a.analog_read(1) # Poll channel 1 once
[1.1452345116]
>>> a.analog_read(3, 5) # Take five samples from channel 3
[-0.453614561, -0.5243512614, -0.4123516421, -0.4714526141, -0.5123161424]
```

## Ramping
The Analog Shield can output ramps on each DAC channel in
parallel. There are three available ramp shapes: triangle, sine, and
square.

### `ramp_running(channel)`: check if a ramp is currently enabled
Returns `True` if a ramp is running on the given channel. Note that a
ramp may appear not to be present if its amplitude is comparable to
the noise of the ADCs.

### `ramp_on(channel)`: enable ramping on a channel
Enables ramping on the given channel with the current settings. If the
channel is `"all"`, ramps on all channels are enabled.

### `ramp_off(channel)`: disable ramping on a channel
Disables ramping on the given channel. If the channel is `"all"`,
ramps on all channels are turned off.

## Write
- Write a command according to the serial specification (see below)
- Accepts identifier as a string and argument as an int
- Converts everything to a `bytearray` so that the code works with
  both Python 2 and 3
- Write to the serial port
- Read response
  - Read one character at a time from the serial input buffer until we
    read a semicolon
  - Version compatibility complications
    - `Serial.read()` returns a `bytes` object
    - In Python 2, `bytes` and `str` are exactly the same
      thing. `bytes is str` returns `True`. Thus, slicing a `bytes`
      object gives a `str`.
    - In Python 3, `bytes` is a distinct type from `str`. Slicing
      `bytes` gives the `int` value of the byte.
    - As a consequence, we need two separate checks to
      version-independently determine if a semicolon was read (and
      therefore the response is over). In one, check if the last
      character of the response is the string `";"`. In the other,
      check if it is the number `0x3b` (ASCII semicolon).
- If in Python 3, decode to a Unicode string
- Strip the semicolon before returning

# Arduino
Basic flow of the Arduino program:

1. Read whatever is available in the serial in buffer
2. If the command is fully received, process it
   1. Split the command into identifier (first two characters) and
      argument
   2. Convert the argument from two bytes into an unsigned short
3. Run the ramp

Each group of commands (based on first character) has its own function
that processes the specific command and the argument. They return a
status code to determine successful execution (zero for success,
nonzero for an error).

## Converting the argument
We want to go from two separate bytes (for example, `0x4f` and `0x2b`)
to one two-byte number (`0x4f2b`). To do this, shift the first byte
left eight bits and add the second byte. Here's what the process looks
like in binary:

```
Input bytes: 0100 1111, 0010 1011

Step 1: 0100 1111 << 8 = 0100 1111 0000 0000
Step 2: 0100 1111 0000 0000 + 0010 1011 = 0100 1111 0010 1011
```

## Ramping
Each ramp shape is defined as a function of time since the Arduino
started executing (in microseconds to be as correct as possible). This
has a few consequences:

- Ramps with the same period are in phase
- It's very easy to add another ramp shape, simply define another ramp
  function
- There will be a discontinuity when the microseconds counter rolls
  over (approximately 70 minutes after the program starts)

The ramping code works by calculating the voltage at the current time
using the ramp function, then clipping if it goes out of range.

These are the functions that define the various ramps:
- Triangle: `V(t) = amplitude * (|(t - phase shift) % period -
  period/2| / (period/4) - 1) + offset`
- Sine: `V(t) = amplitude * sin(2π/period * (t - phase shift)) +
  offset`
- Square: `V(t) = amplitude * (-1)^floor((t - phase shift) / period) +
  offset`

# Serial protocol
The protocol works on a command-response basis: the Python side sends
a command, then blocks until the Arduino finishes executing the
command and returns a response.

The format of the command is simple: each command is exactly four
bytes in length. The first two bytes are the identifier of the
command, which consists of two ASCII characters. Commands are
case-insensitive, so the commands `RO`, `Ro`, `rO`, and `ro` are all
equivalent. The next two bytes consist of the argument. How it is
formatted is specific to each command. It may be interpreted as a
16-bit integer, it may be ignored, or it may be used another way
entirely. Commands which have similar functions are grouped by having
the same first character. Voltages are always communicated using the
bit format used by the Analog Shield library (i.e. `0x0000` corresponds
to -5V and `0xffff` corresponds to 5V).

The response is an arbitrary number of ASCII characters terminated by
a semicolon (`;`, ASCII `0x3b`). If the command completes successfully
with no other response required, it will return "OK;". If an error
occurs at any time, whether in parsing or executing the command, the
response will be "??;".

The serial protocol operates at a baud rate of 2 Mbps to reduce
communication latency.

## Command list
### Ramp settings
Each channel can output a ramp in parallel. The ramp period,
amplitude, offset, phase shift, and waveform are all individually
configurable.

Default settings:

- Ramp off
- Period: 100 milliseconds
- Amplitude: 0V
- Offset: 0V
- Phase shift: none
- Function: triangle

| Command        | Identifier | Argument                                                        | Function                                                                                                                                                                                             |
|----------------|------------|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Channel select | `rc`       | Channel number                                                  | Choose the channel which future `r*` commands will adjust.                                                                                                                                           |
| Ramp on        | `r1`       | Ignored                                                         | Enable ramping on the currently selected channel.                                                                                                                                                    |
| Ramp off       | `r0`       | Ignored                                                         | Disable ramping on the currently selected channel.                                                                                                                                                   |
| Period         | `rp`       | Period in milliseconds                                          | Set the period of the ramp function. The argument is interpreted as a two-byte unsigned integer, so the range of possible values is 1ms to 65.535s in 1ms increments (0.015Hz to 1kHz).              |
| Amplitude      | `ra`       | Voltage in Analog Shield format (`0x0000` = -5V, `0xffff` = 5V) | Set the amplitude of the ramp function (amplitude is V<sub>average</sub> to V<sub>max</sub>, not V<sub>pp</sub>). If the ramp goes out of the range of the DACs (±5V), the waveform will be clipped. |
| Offset         | `ro`       | Voltage in Analog Shield format (`0x0000` = -5V, `0xffff` = 5V) | Set the offset of the ramp function (V<sub>average</sub>). If the ramp goes out of the range of the DACs (±5V), the waveform will be clipped.                                                        |
| Phase shift    | `rs`       | Percentage of a period (`0x0000` = 0%, `0xffff` = 100%)         | Set the phase shift of the ramp function relative to the period. For example, a 25% phase shift on a 50ms period results in a 12.5ms phase shift.                                                    |
| Function       | `rf`       | 0: triangle; 1: sine; 2: square                                 | Set the waveform of the ramp.                                                                                                                                                                        |

### DAC output

| Command        | Identifier                  | Argument                                                        | Function                                                                                                                         |
|----------------|-----------------------------|-----------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| Single channel | `vN` (N is the DAC channel) | Voltage in Analog Shield format (`0x0000` = -5V, `0xffff` = 5V) | Set a single DAC to output constantly at a given level. If there is a ramp running on that channel, the ramp will be turned off. |
| All channels   | `va`                        | Voltage in Analog Shield format (`0x0000` = -5V, `0xffff` = 5V) | Set all DACs to output constantly at the given level.                                                                            |

### ADC input

| Command      | Identifier                  | Argument          | Function                                                                                                                                                      |
|--------------|-----------------------------|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Read voltage | `aN` (N is the ADC channel) | Number of samples | Sample an ADC n times as quickly as possible. Returns all the readings as a series of comma-separated hex numbers (the voltages in Analog Shield format). |

### Queue mode
Queue mode enables more accurate timing of commands. Instead of
executing commands immediately when it receives them, queue mode
stores commands in the serial input buffer and waits until the queue
pin (pin 7) is brought high to execute.

| Command           | Identifier | Argument      | Function                      |
|-------------------|------------|---------------|-------------------------------|
| Toggle queue mode | `qm`       | 0: off; 1: on | Enable or disable queue mode. |
