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

# Connect to SR830
rm = pyvisa.ResourceManager()
i_lockin = rm.open_resource('GPIB1::7::INSTR')
print(i_lockin.query("*IDN?"))
i_lockin.write("*CLS")

# Preamplifier settings
GV = 1000
GI = 1e-4

# Scan settings
NRAMP = 2000
LOAD_RESISTOR = 50e3
LOCKIN_AMPLITUDE = 0.005
MAX_DC = 3
MIN_DC = -3

dc_offset_list = np.concatenate((np.linspace(0,MIN_DC,NRAMP),np.linspace(MIN_DC,MAX_DC,2*NRAMP),np.linspace(MAX_DC,0,NRAMP)))
#dc_offset_list = (np.linspace(0,MIN_DC,NRAMP))
idc_list = dc_offset_list/LOAD_RESISTOR
v_lockin.amplitude(LOCKIN_AMPLITUDE)

NTOT = len(dc_offset_list)

idc = np.zeros(len(dc_offset_list))*np.nan
vdc = np.zeros(len(dc_offset_list))*np.nan

vac = np.zeros(len(dc_offset_list))*np.nan
dvphase = np.zeros(len(dc_offset_list))*np.nan
iac = np.zeros(len(dc_offset_list))*np.nan
diphase = np.zeros(len(dc_offset_list))*np.nan

def getIV(i):
    # Query DC voltages straight from preamp with AUX IN
    idc[i] = v_lockin.aux_in0()*GI
    vdc[i] = v_lockin.aux_in1()/GV
    # Query AC voltages and currents
    vac[i] = v_lockin.R()/GV
    dvphase[i] = v_lockin.P()
    iac[i] = float(i_lockin.query("OUTP? 3"))*GI
    diphase[i] = float(i_lockin.query("OUTP? 4"))


# Scan offsets
for i,vi in enumerate(dc_offset_list):
    v_lockin.sine_outdc(vi)
    #print(f'Setting DC offset to {vi:.5f}')
    print(f'Iteration {i+1}/{NTOT}')
    #time.sleep(0.1)
    getIV(i)

fname = 'B2-9-14_OPTONANO_dIdV_13mK'
#fname='test'


df = pd.DataFrame({'DC current (A)':idc,'DC voltage (V)':vdc,'AC current(A)':iac,'AC voltage(V)':vac,'Voltage phase':dvphase,'Current phase':diphase})
df.to_csv(f'{fname}.csv', index=False)

# dump metadata to yaml file
metadata_dict = {'Cryostat':'OPTONANO',
                 'AC voltage channel':{'Lockin':'SR860','Preamp':'SR560','Gv':GV},
                 'AC current channel':{'Lockin':'SR830','Preamp':'DL1212','Gv':GI},
                 'DC voltage channel':{'Preamp':'SR560','Gv':GV},
                 'DC current channel':{'Preamp':'DL1212','Gv':GI},
                    'Frequency':377.976,
                  'Load resistor (Ohm)': LOAD_RESISTOR,
                  'Lockin amplitude (V)':LOCKIN_AMPLITUDE,
                  'Max DC offset (V)':MAX_DC,
                  'Min DC offset (V)':MIN_DC,
                  'Ramp points':2*NRAMP,

}
with open(f'{fname}.yml', 'w') as outfile:
    yaml.dump(metadata_dict, outfile, default_flow_style=False)


fig, ax = plt.subplots((2))

ax[0].plot(vdc*1e3,idc*1e6,'b.')
ax[0].set_xlabel(r'DC voltage (mV)')
ax[0].set_ylabel(r'DC current ($\mu$A)')

ax[1].plot(idc*1e6,vac/iac,'b.')
ax[1].set_xlabel(r'DC current ($\mu$A)')
ax[1].set_ylabel(r'dV/dI($\Omega$)')

plt.tight_layout()
plt.show()