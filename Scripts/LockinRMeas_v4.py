# -*- coding: utf-8 -*-
"""
Class to test python data acquisition system

WARNING: still under heavy development

@author: akperuht
"""
# Import python module folder
import sys
sys.path.append(r'C:\Users\akperuht\Nextcloud\Private\Python')
#sys.path.append(r'C:\Users\akperuht\Nextcloud2\Python')

from pymodules.realTimeGraph_v6 import realTimeGraph
from pymodules.NiDAQmx_control import *
from pymodules.instrument_control import *
from pymodules.thermometer_calib import *
import uuid
from scipy.signal import *

from PyQt5 import QtWidgets
import matplotlib.pyplot as plt
import numpy as np
import time
import multiprocessing as mp
import traceback
import h5py
import signal


class lockinRMeas():
    '''
    Class to test python measurement environment functionalities
    '''
    def __init__(self):
        self.channels=["Dev1/ai0","Dev1/ai1","Dev1/ai2"]  # Channels to read
        self.Nsamples = 1000 # Number of samples per each point
        self.sample_rate = 5e4 # DAQ card sampling rate
        self.settling_time = 15e-3 # Settling time after param setting
        self.wait_time = 10e-3 # Wait 10 ms between runs
        
        self.sens_change_wait = 100e-3 # Waiting time after lock-in sensitivity hase changed
        
        self.closeAtExit = False
        self.exit  = False
                
        self.N = 0 # Number of collected datapoints
        self.pathname = ""
        self.filename = "temp.txt"
        
        self.therm_calib_name = "Dipstick"
        
        # Thermometer calibration
        self.therm_multiplier = 1000
        self.Rtemp_ch = 0
        
        # Instrument GPIB interface addresses
        self.Vlockin_address = 'GPIB0::7::INSTR'
        self.Ilockin_address = 'GPIB0::8::INSTR'
        
        # Lock in amplifier settings
        self.lockin_freq = 18.457   # Sine output frequency
        self.lockin_ampl = 0.1      # Sine output amplitude in volts   
        self.Ilockin_ch = 1
        self.Vlockin_ch = 2
        self.autosens = False
        
        self.plot_labels = ['Time(s)','Rtherm ','Current(A) ','Voltage(V) ',
                    'Resistance(Ohm)','Temperature(K)']
        self.plot_Vunit_multip = 1 # Unit volts
        self.plot_Iunit_multip = 1 # Unit amperes
        
        # Preamplifier settings
        self.Gi = 1e-4
        self.Gv = 100
                
        # Set up queues for communication
        self.q1 = mp.Queue() # Queue for data communication
        self.q2 = mp.Queue() # Dictionary queue for metadata
        self.q3 = mp.Queue() # Queue for data logging
        self.qin = mp.Queue() # Queue to get data from UI
        
        self.start = False
        self.uuid = uuid.uuid4()
        self.fname = None
        self.lockin1_online = False
        self.lockin2_online = False
        
    def startPlotting(self,Nchannel):
        '''
        Function to start plotting

        Parameters
        ----------
        Nchannel : int
            Number of data channels

        Returns
        -------
        None.

        '''
        # Start plotting application
        app = QtWidgets.QApplication(sys.argv)
        main = realTimeGraph()
        # Initialize UI
        main.init_UI(Nchannel=Nchannel+1,labels = self.plot_labels ,filepath = self.defaultpathname, Nsamples = self.Nsamples, SampleRate = self.sample_rate)
        # Pass data queue to UI
        main.setDataQueue(self.q1,self.q2, self.qin)
        
        # Run the UI
        main.Run()
        main.show()
        sys.exit(app.exec_())
     
    def getInstruments(self):
        '''
        Function to get all available and supported instruments to a dictionary

        Returns
        -------
        instruments : dictionary
            dicationary containing aall available instruments:
                keys:
                    'pynska'   Pynskäbox
                    'keithley' Keithley 2450 Source meter
                    'Ilockin'  Oxford Instruments lock-in amplifier SR810/SR830
                    'Vlockin'  Oxford Instruments lock-in amplifier SR810/SR830

        '''
        s= "=" * 60
        print(s)
        print('Setting up the instruments')
        # Pynskabox
        instruments={}
                  
        # Oxford 1
        try:
            print(s)
            print('Connecting to Oxford Instruments lock-in amplifier SR810/SR830 1')
            instruments['Ilockin'] = SR810_30_lockin(self.Ilockin_address,0)
            self.lockin1_online = True
            print('Connected')
        except:
            instruments['Ilockin'] = None
            print('ERROR: Not able to connect to lock-in amplifier 1')
            
        # Oxford 2
        try:
            print(s)
            print('Connecting to Oxford Instruments lock-in amplifier SR810/SR830 2')
            instruments['Vlockin'] = SR810_30_lockin(self.Vlockin_address,1)
            self.lockin2_online = True
            print('Connected')
        except Exception as e:
            print(e)
            instruments['Vlockin'] = None
            print('ERROR: Not able to connect to lock-in amplifier 2')
        print(s)
        return instruments
            
        
    def readData(self):
        '''
        Read data from the DAQ card

        Parameters
        ----------
        q1 : multiprocessing.queue
            queue to pass the data 
        q2 : multiprocessing.queue
            dictionary queue to pass the metadata
        Ndata : int
            maximum number of collected datapoints

        Returns
        -------
        None.

        '''
        while not self.start:
            self.processIncomingData()              
        # Get available instruments
        instruments = self.getInstruments()
        # Wait until both lockins are connected
        t1 = time.perf_counter()
        while self.lockin1_online*self.lockin2_online!=1:                
            instruments = self.getInstruments()
            tloop = time.perf_counter()-t1
            if tloop>5:
                print(str(tloop)+" s")
                print('TIMEOUT: Not able to connect to lock-in amplifiers')
                break
                self.start = False          
                
        # Set lock-in amplifier settings
        instruments['Ilockin'].standard_settings()
        instruments['Vlockin'].standard_settings()
        
        instruments['Ilockin'].set_ref_source('internal')            
        instruments['Ilockin'].set_freq_ampl(self.lockin_freq,self.lockin_ampl)
        instruments['Vlockin'].set_ref_source('external')
        
        # Export lock-in amplifier settings
        instruments['Vlockin'].export_settings(self.pathname + self.filename + "_settings_Vlockin.yml")
        instruments['Ilockin'].export_settings(self.pathname + self.filename + "_settings_Ilockin.yml")
        
        # Wait one second before starting measurement
        time.sleep(1)
        
        # Get starting time for measurement
        starttime=time.perf_counter()
        # Initialize arrays for data collection
        self.out = np.empty(shape=(len(self.channels),self.Nsamples))
        data = []
        self.N = 0
        # Initialize DAQ control class
        self.daq = DAQcontrol(self.channels)
        iter_time = 1
        # Data acquisition and control loop
        while True:
            # Handle communication to main UI
            self.processIncomingData()
            while not self.start:
                self.processIncomingData()
            # Get timestamp
            t1=time.perf_counter()
            timestamp = t1-starttime
            # Collect data from DAQ card
            self.daq.request_data(self.out,self.sample_rate,self.Nsamples)          
            # Get temperature
            Rtemp = np.average(self.out[self.Rtemp_ch])
            # Calculate temperature
            T=0
            if self.therm_calib_name == "Dipstick_old":
                T = calibration_dipstick(Rtemp,self.therm_multiplier)
            elif self.therm_calib_name == "Dipstick":
                T = calibration_dipstick_new(Rtemp,self.therm_multiplier)
            elif self.therm_calib_name == "Kanada_old":
                T = calibration_Kanada(Rtemp,self.therm_multiplier)
            elif self.therm_calib_name == "Kanada":
                T = calibration_Kanada_lowtemp_2022(Rtemp,self.therm_multiplier)
            elif self.therm_calib_name == "Ling":
                T = calibration_Ling(Rtemp,self.therm_multiplier)
            else:
                T = calibration_dipstick_new(Rtemp,self.therm_multiplier)	



            # Calculate current in amperes
            Ilockin = np.average(self.out[self.Ilockin_ch])
            I = (Ilockin*self.Gi*instruments['Ilockin'].get_sens_voltage(instruments['Ilockin'].sens))/10.0
            # Calculate voltage in volts
            Vlockin = np.average(self.out[self.Vlockin_ch])
            V = ((Vlockin/self.Gv)*instruments['Vlockin'].get_sens_voltage(instruments['Vlockin'].sens))/10.0
            # Calculate measured resistance in ohms
            R = V/I
            # Adjust voltage lock-in amplifier sensitivities if autosens is on
            if self.autosens:
                if Vlockin > 9.9:
                    instruments['Vlockin'].set_sens('up')
                    # Wait voltage to settle
                    time.sleep(self.sens_change_wait)
                    print('Lock-in amplifier 2: sensitivity to ',instruments['Vlockin'].sens)
                if Vlockin < 2.0:
                    # Get lock-in amplifier sensitivity voltage
                    vsens_val = instruments['Vlockin'].get_sens_voltage(instruments['Vlockin'].sens)
                    # Lower sensitivity only to certain limit
                    if vsens_val > 5e-5:
                        # Set sensitivity down
                        instruments['Vlockin'].set_sens('down')
                        # Wait voltage to settle
                        time.sleep(self.sens_change_wait)
                        print('Lock-in amplifier 2: sensitivity to ',instruments['Vlockin'].sens)
					
            # Add values to data array
            datalabels=['#','Time(s) ','R_thermometer ','Current(A) ','Voltage(V) ',
                        'Resistance(Ohm)','Temperature(K)','Raw current ','Raw voltage']
            
            data=[t1-starttime]
            # Put all of the data to data array
            for di in [Rtemp, I, V, R, T, Ilockin, Vlockin]:
                data.append(di)
            # Transfer data to queue and select what to plot
            self.q1.put([timestamp,Rtemp, I*self.plot_Iunit_multip, V*self.plot_Vunit_multip, R,T])
            # Write data to a file
            if self.N == 0:
                self.dataLogger('# UUID '+str(self.uuid),spaces = False)
                # Write down datalabels for first iteration
                self.dataLogger(datalabels)
            self.dataLogger(data)
            # Construct metadata queue
            self.q2.put({"Npoints" : self.N, 
                         "Temperature": T, 
                         "Freq": str(np.around(1/iter_time,decimals=2))+" Hz",
                         })
            # Time between iterations
            time.sleep(self.wait_time)
            # Calculate iteration time
            t2 = time.perf_counter()
            iter_time = abs(t1-t2)
            self.N+=1
            
        # close plotting window at exit
        if self.closeAtExit:
            self.exit = True
            self.q1.put('Exit')
        sys.exit()
         
    def processIncomingData(self):
        '''
        Method to process data sent by UI
        Changes Gv, Gi and Rtherm_multip when these are changed in UI

        Returns
        -------
        None.

        '''
        # Read if values are changed in UI
        while not self.qin.empty():
            # Extract data from queue
            measParamDict = self.qin.get_nowait()
            print('===========================================================')
            if 'Gv' in measParamDict:
                self.Gv = float(measParamDict['Gv'])
                print('Preamplifier gain changed: Gv = ' + str(self.Gv))
            if 'Gi' in measParamDict:
                self.Gi = float(measParamDict['Gi'])
                print('Preamplifier gain changed: Gi = ' + str(self.Gi))
            if 'Rtherm_multip' in measParamDict:
                self.therm_multiplier = float(measParamDict['Rtherm_multip'])
                print('Resistance bridge multiplier changed: Multiplier = ' + str(self.therm_multiplier))
            if 'start' in measParamDict:
                self.start = True
            if 'stop' in measParamDict:
                self.start = False
            if 'autosens' in measParamDict:
                self.autosens = measParamDict['autosens']
                
            # Get thermometer calibration from GUI
            if 'ThermCalibName' in measParamDict:
                self.therm_calib_name = str(measParamDict['ThermCalibName'])
                
                
            # Get filename from GUI
            if 'fname' in measParamDict:
                self.fname = str(measParamDict['fname'])
                print(self.fname)
            
            # Change sample rate on the fly
            if 'SampleRate' in measParamDict:
                self.sample_rate = int(measParamDict['SampleRate'])
                print('Sample rate: ' + str(self.sample_rate))
                
            # Change samples/point on the fly
            if 'Nsamples' in measParamDict:
                self.Nsamples = int(measParamDict['Nsamples'])
                # Update data array length accordingly
                self.out = np.empty(shape=(len(self.channels),self.Nsamples))
                print('Samples/point: ' + str(self.Nsamples))
                
            print('===========================================================')
        
    def dataLogger(self,data,spaces = True):
        '''
        Function for data logging and communication to external plotting UI

        Returns
        -------
        None.

        '''
        # write data to file
        #self.fname = self.defaultpathname+"\\"+self.filename
        with open(self.fname,'a+') as f:
            if spaces:
                f.write(" ".join(str(item) for item in data))
                f.write("\n")
            else:
                f.write(data)
                f.write("\n")
                
    
    def Exit(self):
        '''
        Exit system

        Returns
        -------
        None.

        '''
        sys.exit()
        
    def Run(self):
        '''
        Run the measurement 

        Returns
        -------
        None.

        '''
        # Start data reading and logging in different threads
        worker = mp.Process(target = self.readData)
        worker.start()
        # Start data plotting GUI
        self.startPlotting(len(self.channels))    

if __name__ == '__main__':
        meas = lockinRMeas()
        
        meas.Vlockin_address = 'GPIB0::8::INSTR'
        meas.Ilockin_address = 'GPIB0::7::INSTR'
        
        meas.therm_calib_name = "Dipstick"
        meas.Nsamples = 4000
        meas.sample_rate = 5e4
        meas.settling_time = 10e-3
        meas.defaultpathname = r"C:\Users\akperuht\Nextcloud\Private\Experiments\NbTiN HIM samples\T5\Measurements\Dipstick\R(T)\\"
        meas.filename = r'testing.data'
        meas.Gi = 1e-4
        meas.Gv = 100
        meas.therm_multiplier = 1000
        meas.channels=["Dev1/ai0","Dev1/ai1","Dev1/ai2"]
        worker = mp.Process(target = meas.readData)
        worker.start()
        # Start data plotting GUI
        meas.startPlotting(5)
        

         
    
    
    
    
    
    
    