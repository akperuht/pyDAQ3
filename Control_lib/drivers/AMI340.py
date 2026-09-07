import socket
import time
import matplotlib.pyplot as plt
import numpy as np
'''
=========================================================================================================================
 Driver for American Magnetics Inc. AMI340 superconducting magnet controller via TCP/IP
=========================================================================================================================
'''

class AMI340:
    def __init__(self, ip, port=7180):
        """Connect to AMI340 superconducting magnet controller via TCP/IP."""
        self.ip = ip
        self.port = port
        self.field_max = 7.0
        self.sock = None

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((ip, port))
            print("Superconducting magnet controller, {}, is connected".format(self.id()))
        except socket.error as e:
            raise ConnectionError("Could not connect to AMI340 at {}:{} - {}".format(ip, port, e))

    # ---------------------------
    # Helper communication methods
    # ---------------------------
    def write(self, cmd):
        """Send a command string to the instrument."""
        self.sock.sendall((cmd + '\n').encode())

    def read(self):
        """Read a response string from the instrument."""
        data = b''
        while not data.endswith(b'\n'):
            chunk = self.sock.recv(1024)
            if not chunk:
                break
            data += chunk
        return data.decode().strip()

    def query(self, cmd, fmt=None):
        """Send a query and return parsed response."""
        self.write(cmd)
        resp = self.read()
        if fmt == '%f':
            try:
                return float(resp)
            except ValueError:
                return float('nan')
        elif fmt == '%s':
            return resp
        return resp

    # ---------------------------
    # Properties
    # ---------------------------
    def id(self):
        """Instrument ID string."""
        return self.query('*IDN?', '%s')

    @property
    def field_target(self):
        return self.query('FIELD:TARG?', '%f')

    @field_target.setter
    def field_target(self, value):
        assert abs(value) <= self.field_max, (
            "Don't set target field greater than {} T".format(self.field_max)
        )
        self.write('CONF:FIELD:TARG {}'.format(value))

    @property
    def Field(self):
        return self.query('FIELD:MAG?', '%f')

    @property
    def VOLT_MAG(self):
        return self.query('VOLT:MAG?', '%f')

    @property
    def VOLT_SUPPLY(self):
        return self.query('VOLT:SUPP?', '%f')

    @property
    def VOLT_LIM(self):
        return self.query('VOLT:LIM?', '%f')

    @VOLT_LIM.setter
    def VOLT_LIM(self, value):
        self.write('CONF:VOLT:LIM {}'.format(value))

    @property
    def state(self):
        value = int(self.query('STATE?', '%f'))
        if value == 1:
            print('RAMPING to target field/current')
        elif value == 2:
            print('Holding at target field/current')
        elif value == 3:
            print('Paused')
        elif value == 7:
            print('Quench detected')
        return value

    # ---------------------------
    # Ramp rate configuration
    # ---------------------------
    def set_ramp_rate(self, rate_t_per_min, limit_t):
        """
        Configure ramp rate (Tesla/min) and limit.
        Example: set_ramp_rate(0.0005, 7.0)
        """
        self.write('CONF:DEV:MODE FIELD')         # field control mode
        self.write('CONF:FIELD:UNITS 1')          # Tesla units
        self.write('CONF:RAMP:RATE:UNITS 0')      # Tesla per minute
        self.write('CONF:RAMP:RATE:SEG 1')        # 1 segment
        self.write('CONF:RAMP:RATE:FIELD 1,{:.6f},{:.3f}'.format(rate_t_per_min, limit_t))

    def get_ramp_rate(self, seg=1):
        """Return ramp-rate configuration for segment."""
        return self.query('CONF:RAMP:RATE:FIELD? {}'.format(seg), '%s')

    # ---------------------------
    # Instrument control
    # ---------------------------
    def RAMP(self):
        """Start ramping the field and live-plot progress."""
        self.write('RAMP')

        t0 = time.time()
        times, field_vals, vsupply_vals, vmag_vals = [], [], [], []

        plt.ion()
        fig, axs = plt.subplots(3, 1, figsize=(6, 8))
        fig.suptitle("Ramp to {} T from {}".format(self.field_target, time.ctime()))

        lines = [
            axs[0].plot([], [])[0],
            axs[1].plot([], [])[0],
            axs[2].plot([], [])[0],
        ]
        axs[0].set_ylabel("B (T)")
        axs[1].set_ylabel("V_S (V)")
        axs[2].set_ylabel("V_M (V)")
        axs[2].set_xlabel("Time (s)")

        while True:
            time.sleep(0.2)
            t = time.time() - t0
            times.append(t)
            field_vals.append(self.Field)
            vsupply_vals.append(self.VOLT_SUPPLY)
            vmag_vals.append(self.VOLT_MAG)

            lines[0].set_data(times, field_vals)
            lines[1].set_data(times, vsupply_vals)
            lines[2].set_data(times, vmag_vals)

            for ax, ydata in zip(axs, [field_vals, vsupply_vals, vmag_vals]):
                ax.relim()
                ax.autoscale_view()

            plt.pause(0.05)

            if self.state == 2:  # Holding
                self.PAUSE()
                break

        plt.ioff()
        plt.show()

    def get_state(self):
        try:
            return int(float(self.query("STATE?")))
        except Exception:
            return -1

    def PAUSE(self):
        """Pause ramping."""
        self.write('PAUSE')

    def close(self):
        """Close TCP/IP connection."""
        if self.sock:
            self.sock.close()
            self.sock = None
            print("Connection closed.")

    def set_parameter(self,parameter,value):
        '''
        Function for setting the magnetic field value
        '''
        print(parameter)
        if parameter=="Magnetic field":
            print('Setting field')
            # Set field target
            value_to_set =  np.around(value,decimals=5)
            self.field_target = value_to_set
            # Ramp to target
            self.ramp_to_target()
            return value_to_set
        else:
            print(f'AMI340 ERROR:invalid parameter to set{parameter}')

    def ramp_to_target(self):
        '''
        Function to ramp the magnet to target value
        '''
        # Initiate ramping
        self.write('RAMP')
        # wait until field target is reached
        while True:
            value = self.get_state()
            if value == 1: #RAMPING to target field/current
                continue
            elif value == 2:
                break #Holding at target field/current
            elif value == 3:
                print('Paused')
            elif value == 7:
                print('Quench detected')
                raise RuntimeError("Magnet quench detected")
            else:
                continue
        print('Field ramped to the target')
        # Return the field value
        return self.query('FIELD:MAG?', '%f')

    def apply_settings(self,settingsDict):
        '''
        Function to apply settings to the device
        '''
        print('Applying settings to AMI340')
        # Set ramp rate
        if 'Ramp rate' in settingsDict:
            ramp_rate = settingsDict['Ramp rate']
            self.set_ramp_rate(ramp_rate,7.0)
            print(f'Ramp rate set to {ramp_rate}')

        # Set field target
        if 'Field target' in settingsDict:
            # Set field target
            self.field_target  = settingsDict['Field target']
            print(f'Field target set to {settingsDict['Field target']}')

        # Set ramp 
        if 'Ramp to target' in settingsDict:
            if settingsDict['Ramp to target']:
                print('Starting to ramp the field')
                val = self.ramp_to_target()
                print(f'Field ramped to {self.field_target} successfully')



