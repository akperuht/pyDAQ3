import numpy as np
import pyvisa
from qcodes.instrument_drivers.stanford_research import SR860
import pandas as pd
import time
import matplotlib.pyplot as plt
import yaml

# Connect to SR860
v_lockin = SR860("SR860", "TCPIP0::169.254.58.1::INSTR")
# Set TTl sync signal
v_lockin.write("BLAZEX BIsync")

# Preamplifier settings
GV = 1000
GI = 1e-4

LOAD_RESISTOR = 50e3
LOCKIN_AMPLITUDE = 2

v_lockin.amplitude(LOCKIN_AMPLITUDE)

NTOT = 10000

idc = np.zeros(NTOT)*np.nan
vdc = np.zeros(NTOT)*np.nan


def getIV(i):
    # Query DC voltages straight from preamp with AUX IN
    idc[i] = v_lockin.aux_in0()*GI
    vdc[i] = v_lockin.aux_in1()/GV

fname = 'B2-9-10_IVC_scan_12mK_run1'
#fname='test'

for i in range(NTOT):
    print(f'Iteration {i}/{NTOT}')
    getIV(i)

df = pd.DataFrame({'DC current (A)':idc,'DC voltage (V)':vdc})
df.to_csv(f'{fname}.csv', index=False)

# dump metadata to yaml file
metadata_dict = {'Cryostat':'OPTONANO',
                 'DC voltage channel':{'Preamp':'SR560','Gv':GV},
                 'DC current channel':{'Preamp':'DL1212','Gv':GI},
                    'Frequency':0.01,
                  'Load resistor (Ohm)': LOAD_RESISTOR,
                  'Lockin amplitude (V)':LOCKIN_AMPLITUDE,

}
with open(f'{fname}.yml', 'w') as outfile:
    yaml.dump(metadata_dict, outfile, default_flow_style=False)


plt.figure(1)

plt.plot(vdc*1e3,idc*1e6,'b.')
plt.xlabel(r'DC voltage (mV)')
plt.ylabel(r'DC current ($\mu$A)')

plt.tight_layout()
plt.show()