This library controls a Digilent Analog Shield connected to an Arduino
from Python over serial. There are three layers to the system: the
Arduino side (which controls the Analog Shield), the Python side
(which is what is exposed to the user), and the serial protocol that
communicates between the two.

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
