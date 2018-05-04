#include <analogShield.h>
#include <SPI.h>

const unsigned int ZERO_V = 32767;

// Queue settings
unsigned int queue = 0;
int queue_pin = 7;

// DAC values
unsigned int dac[4];

// Ramp default settings
boolean ramp_enabled[4] = {false, false, false, false};
int ramp_channel = 0;
unsigned int ramp_period[4] = {100 * 1e3, 100 * 1e3, 100 * 1e3, 100 * 1e3}; // Units: microseconds
unsigned int ramp_amplitude[4] = {ZERO_V, ZERO_V, ZERO_V, ZERO_V}; // Units: volts
unsigned int ramp_offset[4] = {ZERO_V, ZERO_V, ZERO_V, ZERO_V}; // Units volts
float ramp_phase[4] = {0, 0, 0, 0}; // Units: percent of period
unsigned int ramp_function[4] = {0, 0, 0, 0};

// Change ramp settings - returns 0 on success, -1 on error
int ramp_settings(char function, unsigned short arg) {
  if (function == '0') { // Ramp off
    ramp_enabled[ramp_channel] = false;
    analog.write(ramp_channel, ZERO_V); // Reset the channel
  } else if (function == '1') { // Ramp on
    ramp_enabled[ramp_channel] = true;
  } else if (function == 'C' || function == 'c') {
    if (arg <= 3) { // Check channel
      ramp_channel = arg;
    } else { // Invalid channel; return error status
      return -1;
    }
  } else if (function == 'P' || function == 'p') { // Set period
    ramp_period[ramp_channel] = arg * 1e3; // Convert milliseconds to microseconds
  } else if (function == 'A' || function == 'a') { // Set amplitude
    ramp_amplitude[ramp_channel] = arg-ZERO_V;
  } else if (function == 'O' || function == 'o') { // Set offset
    ramp_offset[ramp_channel] = arg;
  } else if (function == 'S' || function == 's') { // Set phase
    ramp_phase[ramp_channel] = arg * 1.0/0xffff; // Convert from bits to percentage
  } else if (function == 'F' || function == 'f') { // Set function
    ramp_function[ramp_channel] = arg;
  } else { // Unrecognized function
    return -1;
  }

  Serial.print("OK");
  return 0; // Return success status
}

// Calculate the voltage output as a function of time (microseconds)
// V(t) = amplitude * (|(t - phase shift) % period - period/2| / (period/4) - 1) + offset
long  ramp_triangle(unsigned long t, int channel) {
  return ramp_amplitude[channel] * (abs((t - (int)(ramp_phase[channel]*ramp_period[channel]))%ramp_period[channel] - ramp_period[channel]/2.0) / (ramp_period[channel]/4.0) - 1) + ramp_offset[channel];
}

// V(t) = amplitude * sin(2pi/period * (t - phase shift)) + offset
long ramp_sin(unsigned long t, int channel) {
  return ramp_amplitude[channel] * sin(TWO_PI/ramp_period[channel] * (t - ramp_phase[channel]*ramp_period[channel])) + ramp_offset[channel];
}

// V(t) = amplitude * (-1)^floor((t - phase shift) / period) + offset
long ramp_square(unsigned long t, int channel) { // TODO doesn't work
  return ramp_amplitude[channel] * pow(-1, (unsigned long)((t - ramp_phase[channel]*ramp_period[channel])/ramp_period[channel])) + ramp_offset[channel];
}

int set_dac(char channel, unsigned short val) {
  if (channel == 'A' || channel == 'a') {
    dac[0] = val;
    dac[1] = val;
    dac[2] = val;
    dac[3] = val;

    analog.write(val, val, val, val, true);
  } else if ('0' <= channel && channel <= '3') {
    dac[channel-'0'] = val;

    analog.write(channel-'0', val);
  } else {
    return -1; // Invalid channel
  }

  Serial.print("OK");
  return 0;
}

int get_adc(char channel, unsigned short arg) {
  if ('0' <= channel && channel <= '3') {
    for (int i = 0; i < arg; i++) {
      unsigned short reading = analog.read(channel-'0');

      Serial.print(reading, HEX);

      if (i != arg-1) { // Print separator if this isn't the last value
        Serial.print(',');
      }
    }
  } else {
    return -1; // Invalid channel
  }

  return 0;
}

int queue_settings(char function, unsigned short arg) {
  if (function == 'M' || function == 'm') {
    queue = arg;
  } else {
    return -1; // Invalid command
  }

  Serial.print("OK");
  return 0;
}

void setup() {
  SPI.setClockDivider(SPI_CLOCK_DIV2);
  Serial.begin(2e6);

  pinMode(queue_pin, INPUT);

  // Set all channels to 0V
  dac[0] = ZERO_V;
  dac[1] = ZERO_V;
  dac[2] = ZERO_V;
  dac[3] = ZERO_V;
  analog.write(ZERO_V, ZERO_V, ZERO_V, ZERO_V, true);
}

unsigned char cmd[4];
int bytes_read = 0;
void loop() {
  // Read more of the command, if it's available
  while (Serial.available() > 0 && bytes_read < 4) {
    cmd[bytes_read] = Serial.read();
    bytes_read++;
  }

  // If the full command has been received, process it
  if (bytes_read == 4) {
    // Wait for the queue pin to go HIGH in queue mode
    if (queue != 0) {
      while (digitalRead(queue_pin) != HIGH) {}
    }

    // Extract identifier and argument
    char ident[] = {cmd[0], cmd[1]};
    unsigned short arg = (cmd[2] << 8) + cmd[3];

    int status = 0;
    if (ident[0] == 'R' || ident[0] == 'r') {
      status = ramp_settings(ident[1], arg);
    } else if (ident[0] == 'V' || ident[0] == 'v') {
      status = set_dac(ident[1], arg);
    } else if (ident[0] == 'A' || ident[0] == 'a') {
      status = get_adc(ident[1], arg);
    } else if (ident[0] == 'Q' || ident[0] == 'q') {
      status = queue_settings(ident[1], arg);
    } else { // Unrecognized command
      Serial.print("??");
    }

    if (status != 0) { // Something went wrong
      Serial.print("??");
    }

    Serial.print(';'); // Always terminate with a semicolon
    Serial.flush();
    bytes_read = 0; // Ready to start reading another command
  }

  // Ramp
  for (int i = 0; i < 4; i++) { // For each channel
    if (ramp_enabled[i]) {
      unsigned long t = micros();

      long v; // Calculate new value
      if (ramp_function[i] == 0) {
        v = ramp_triangle(t, i);
      } else if (ramp_function[i] == 1) {
        v = ramp_sin(t, i);
      } else if (ramp_function[i] == 2) {
        v = ramp_square(t, i);
      }

      // Clip the ramp if it goes out of the voltage range
      v = constrain(v, 0, 0xffff);

      analog.write(i, v);
    }
  }
}
