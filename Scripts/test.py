import numpy as np
import pyvisa
rm = pyvisa.ResourceManager()
rs = rm.list_resources()
print(rs)

#dev = rm.open_resource('GPIB0::10::INSTR')
#print(dev.query("*IDN?"))
print(np.around(0.00007775687,decimals=4))
'''
for rsi in rs:
    try:
        dev = rm.open_resource('TCPIP0::192.168.150.26::inst0::INSTR',)
        print(dev.query("*IDN?"))
        print('rsi')
    except:
        continue
        
'''