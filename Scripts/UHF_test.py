from zhinst.qcodes import UHFLI
from zhinst.qcodes import ZISession
import matplotlib.pyplot as plt
from scipy.signal import resample,decimate,savgol_filter
import numpy as np
import time
#from qcodes.instrument_drivers.bluefors.BlueForsBFTC import BlueForsBFTC
# Connect to UHF
#uhfli = UHFLI("dev2288", "localhost", name="lockin", allow_version_mismatch=True)   # py zhinst (26.4) newer than LabOne server (24.10)
session = ZISession('localhost', allow_version_mismatch=True)
device = session.connect_device("dev2288")
import pandas as pd

MEAS_LENGTH = 1e6
MEAS_TIME = 16
OUT_MIXER_CHANNEL = 3 #UHFLI: 3, HF2LI: 6, MFLI: 1
with device.set_transaction():
    for i in range(0,2):    
        device.sigins[i].imp50(0) # Set to megaohm impedance
        device.sigins[i].ac(0) # Set to DC coupling
        device.sigins[i].diff(0) # Turn off differential input
    #device.oscs[0].freq(10e6) # UHFLI: 10.0e6
    device.demods[OUT_MIXER_CHANNEL].oscselect(0)

# Configure the scope
with device.set_transaction():
    device.scopes[0].length(MEAS_LENGTH)
    device.scopes[0].channel(3)
    for i in range(0,2):
        device.scopes[0].channels[i].bwlimit(1)
        device.scopes[0].channels[i].inputselect(i)
    device.scopes[0].time(MEAS_TIME)
    device.scopes[0].single(True)
    device.scopes[0].segments.enable(False)

# Set range of signal inputs
device.sigins[0].range(3.0)
device.sigins[1].range(3.0)

# Initialize scope module
scope_module = session.modules.scope
scope_module.mode(0) # acquire continuously until stopped

# Subscribe to scope node data
wave_node = device.scopes[0].wave
scope_module.subscribe(wave_node)

def get_scope_records(scope_module):
    scope_module.execute()
    device.scopes[0].enable(True)
    session.sync()
    start = time.time()
    timeout = MEAS_TIME*3 # [s]
    records = scope_module.records()
    progress = scope_module.progress()
    while scope_module.progress() < 1:
        time.sleep(0.1)
    device.scopes[0].enable(False)
    # Read out the scope data from the module.
    data = scope_module.read()[wave_node][0]
    # Stop the module; to use it again we need to call execute().
    scope_module.finish()
    return data


data = get_scope_records(scope_module)
clockbase = device.clockbase()

print(f'Total number of {data[0]["totalsamples"]} collected')

def to_timestamp(record):
    totalsamples = record[0]["totalsamples"]
    dt = record[0]["dt"]
    timestamp = record[0]["timestamp"]
    triggertimestamp = record[0]["triggertimestamp"]
    t = np.arange(-totalsamples, 0) * dt + (
        timestamp - triggertimestamp
    ) / float(clockbase)
    return 1e6 * t

t = to_timestamp(data)

xs = data[0]['channelscaling'][0]
ys = data[0]['channelscaling'][1]

Gv = 100
Gi = 1e-4

i = data[0]["wave"][0, :]*xs*Gi
v = data[0]["wave"][1, :]*ys/Gv

#df = pd.DataFrame({'Current(A)':i,'Voltage(V)':v})
#df.to_csv(f"B2-9-14_OPTONANO_IVC_13mK_Gv{Gv}_Gi{Gi}_UHF_run18_slow.csv", index=False)


plt.figure()
plt.plot(t,i,'k-')
plt.show()

plt.figure()
plt.plot(t,v,'b-')
plt.show()

plt.figure()
plt.plot(v,i,'r-')
plt.show()
