import numpy as np
import pyvisa
from qcodes.instrument_drivers.stanford_research import SR860
import pandas as pd
import time
import matplotlib.pyplot as plt
import yaml
from BlueForsBFTC import BlueForsBFTC

# Connect to BFTC
# Fridge (all thermometer channels are logged automatically).
bftc = BlueForsBFTC("bftc", "169.254.27.31")


# Connect to SR860
v_lockin1 = SR860("SR860", "TCPIP0::169.254.58.1::INSTR")
# Set TTl sync signal
v_lockin1.write("BLAZEX BIsync")

# Connect to SR830 1
rm = pyvisa.ResourceManager()

print(rm.list_resources())
v_lockin2 = rm.open_resource('GPIB1::13::INSTR')
print(v_lockin2.query("*IDN?"))
v_lockin2.write("*CLS")

# Connect to SR830 2
v_lockin3 = rm.open_resource('GPIB1::7::INSTR')
print(v_lockin3.query("*IDN?"))
v_lockin3.write("*CLS")

LOCKIN_AMPLITUDE = 1
LOCKIN_FREQUENCY = 18.457
LOAD_RESISTOR = 10e6 # 10 Mohm load resistor
I_EXC = LOCKIN_AMPLITUDE/LOAD_RESISTOR
v_lockin1.amplitude(LOCKIN_AMPLITUDE)
v_lockin1.frequency(LOCKIN_FREQUENCY)

Tmxc = []
v1 = []
v1_phase = []
v2 = []
v2_phase = []
v3 = []
v3_phase = []


# Set the temperature
#bftc.heater.setpoint(float(15e-3))


T_LIMIT = 0.05
# Read the start temperature
ti = bftc.mxc.temperature()

def getVT():
    t0 = time.perf_counter()
    ti = bftc.mxc.temperature()
    print(ti)
    Tmxc.append(ti)
    # Query AC voltages and currents
    v1.append(v_lockin1.R())
    v1_phase.append(v_lockin1.P())
    v2.append(float(v_lockin2.query("OUTP? 3")))
    v2_phase.append(float(v_lockin2.query("OUTP? 3")))
    v3.append(float(v_lockin3.query("OUTP? 3")))
    v3_phase.append(float(v_lockin3.query("OUTP? 3")))
    return ti


# Loop until measurement finishes
while ti>T_LIMIT:
    ti = getVT()


fname = 'B2-9_234_OPTONANO_cooldown'
#fname='testRT'


df = pd.DataFrame({'Dev 2 voltage(V)':np.array(v1),'Dev 2 phase':np.array(v1),
                  'Dev 3 voltage(V)':np.array(v2),'Dev 3 phase':np.array(v2),
                  'Dev 4 voltage(V)':np.array(v3),'Dev 4 phase':np.array(v3),
                  'Current(A)':np.ones(len(v1))*I_EXC}
                  )

df.to_csv(f'{fname}.csv', index=False)

# dump metadata to yaml file
metadata_dict = {'Cryostat':'OPTONANO',
                 'AC voltage 1':{'Lockin':'SR860'},
                 'AC voltage 2':{'Lockin':'SR830'},
                 'AC voltage 3':{'Lockin':'SR830'},
                    'Frequency':LOCKIN_FREQUENCY,
                  'Load resistor (Ohm)': LOAD_RESISTOR,
                  'Lockin amplitude (V)':LOCKIN_AMPLITUDE,

}
with open(f'{fname}.yml', 'w') as outfile:
    yaml.dump(metadata_dict, outfile, default_flow_style=False)

plt.figure()
plt.plot(v1)
plt.plot(v2)
plt.plot(v3)
plt.show()

plt.figure()
plt.plot(Tmxc,v1)
plt.plot(Tmxc,v2)
plt.plot(Tmxc,v3)
plt.show()

