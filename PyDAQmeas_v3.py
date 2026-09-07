# -*- coding: utf-8 -*-
"""
Python data acquisition code with UI

Collects, plots and logs data from chosen analog channels

Warning: still under development

@author: Aki Ruhtinas, aki.ruhtinas@gmail.com
"""
import sys

from UI.pyDAQ_UI_v3 import realTimeGraph
from Control_lib.DAQ_lib import DAQ
# Import all instruments individually. Enables to define precise drivers to be used
from Control_lib.drivers.BlueforsController import BFcontinuous_MXC_read,BFtrigger_MXC_read

import DeviceManager
from DataProcess import DataProcess
from DataLogger import DataLogger
import nidaqmx
from nidaqmx.constants import AcquisitionType ,LoggingMode, LoggingOperation, WaitMode
from nidaqmx.stream_readers import AnalogMultiChannelReader
import Control_lib.thermometer_calib_LTL as tc
import uuid
from scipy.signal import *
from PySide6 import QtWidgets
import numpy as np
import multiprocessing as mp
import threading as th
import traceback
import warnings
import logging
import pandas as pd
import time

class pyDAQmeas():
    '''
    Class for data acquisition
    '''
    def __init__(self):
        self.channels=["Channel 1","Channel 2","Channel 3"]  # Channels to read
        self.Nsamples = 1000 # Number of samples per each point
        self.sample_rate = 5e4 # DAQ card sampling rate
        self.settling_time = 15e-3 # Settling time after param setting
        self.wait_time = 10e-3 # Wait 10 ms between runs
        
        self.memory_limit = 1000000
        
        self.N_logging = 100
        
        self.sens_change_wait = 100e-3 # Waiting time after lock-in sensitivity hase changed
        
        self.closeAtExit = False
        self.exit  = False
                
        self.N = 0 # Number of collected datapoints
        self.pathname = ""
        self.filename = "temp.txt"
        
        self.therm_calib_name = 'None'
        
        self.chunk_averaging = True
        self.rawdataout = True
        
        self.uuid = uuid.uuid4()
                        
        # Thermometer calibration
        self.therm_multiplier = 1000
        self.thermCh = 0

        self.plot_labels = ['Channel ' + str(i-1) for i in range(20)]
        self.plot_labels[0] = '#Time(s)'
        self.plot_Vunit_multip = 1 # Unit volts
        self.plot_Iunit_multip = 1 # Unit amperes
        
        # Preamplifier settings
        self.Gi = 1e-4
        self.Gv = 100
                
        # Set up queues for communication
        self.q00 = mp.Queue() # Queue for DAQ raw data
        self.q01 = mp.Queue() # Queue for DAQ raw data
        self.q02 = mp.Queue() # Queue for DAQ raw data
        self.q03 = mp.Queue() # Queue for DAQ raw data
        self.q04 = mp.Queue() # Queue for DAQ raw data

        self.data_queues = [self.q00,self.q01,self.q02,self.q03,self.q04]

        self.q10 = mp.Queue() # Queue for parameter sweep raw data
        self.q11 = mp.Queue() # Queue for parameter sweep raw data
        self.q12 = mp.Queue() # Queue for parameter sweep raw data

        self.param_sweep_queues = [self.q10,self.q11,self.q12]

        self.q1 = mp.Queue() # Queue for data communication
        self.q2 = mp.Queue() # Dictionary queue for metadata
        self.q3 = mp.Queue() # Queue for data logging
        self.qin = mp.Queue() # Queue to get data from UI
        self.qr = mp.Queue() # Queue for communicating channel multipliers to measurement thread
        
        self.start = False
        
        self.stop_event = mp.Event()
        
        self.fname = None
        
        self.setup_data_collection = True
        
        self.daq_device_name = 'Dev1'
        
        self.DAQrange = [-10,10]
        
        self.settingDict = {}
        self.devicelist = {}

        self.DAQinterfaces = {}
        self.DAQsettingDict = {}

        self.N_param_sweeps = 0
        self.paramSweepSettingDict = {}
        self.param_sweep_devices = {}

        # Start message handling
        worker = mp.Process(target = self.messageHandling,args=(self.stop_event,))
        worker.start()
        
        
        
    def startPlotting(self):
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
        # Forces fusion style for the app
        app.setStyle("fusion")
        main = realTimeGraph()
        # Get available channels 
        self.available_channels = getChannelNames(self.daq_device_name)
        # Initialize UI
        main.init_UI(filepath = self.defaultpathname, 
                     Nsamples = self.Nsamples, 
                     SampleRate = self.sample_rate,
                     available_channels = self.available_channels,
                     memory_limit = self.memory_limit,
                     rawdataout = self.rawdataout
                     )
        
        # Pass data queue to UI
        main.setDataQueue(self.q1,self.q2, self.qin)
        
        # Run the UI
        main.Run()
        main.show()
        sys.exit(app.exec())
        
        
    def messageHandling(self,stop_event):
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
        # Process messages continuously
        print('Message handling started')
        while True:
            # Handle communication to main UI
            self.processIncomingMessages(stop_event)
        sys.exit()
        
        
    def processIncomingMessages(self,stop_event):
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
            #print('===========================================================')
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
                self.newstart = True
                # Clear the stop event 
                stop_event.clear()
                self.startEvent(stop_event)
                
            if 'stop' in measParamDict:
                self.start = False
                print('Stop event set')
                # Set stop event flag
                stop_event.set()
                
            # Get thermometer calibration from GUI
            if 'ThermCalibName' in measParamDict:
                print(f'Calibration changed to {self.therm_calib_name}')
                self.therm_calib_name = str(measParamDict['ThermCalibName'])
                
            if 'ThermCh' in measParamDict:
                self.thermCh = measParamDict['ThermCh']
                print(f'Thermometer channel changed to {self.thermCh}')
                
            # Get filename from GUI
            if 'fname' in measParamDict:
                self.fname = str(measParamDict['fname'])
                print(self.fname)
            
            # Change sample rate on the fly
            if 'SampleRate' in measParamDict:
                self.sample_rate = int(measParamDict['SampleRate'])
                print('Sample rate: ' + str(self.sample_rate))

            # Change amount of points collected before written into file
            if 'Nlogging' in measParamDict:
                self.N_logging = int(measParamDict['Nlogging'])
                print('Sample rate: ' + str(self.N_logging))

            if 'measChannels' in measParamDict:
                # Read channels from dictionary
                self.channels = measParamDict['measChannels']
                # Initialize multipliers
                self.multips = np.ones(len(self.channels)+1)
                # Setup flag to update data collection
                self.setup_data_collection =True
                
            if 'datalabels' in measParamDict:
                # Setup channel names
                self.plot_labels = measParamDict['datalabels']
                
            # Check thermometer calibration name
            if 'ThermCalibName' in measParamDict:
                self.therm_calib_name = measParamDict['ThermCalibName']
                
            # Change samples/point on the fly
            if 'Nsamples' in measParamDict:
                self.Nsamples = int(measParamDict['Nsamples'])
                # Update data array length accordingly
                self.out = np.empty(shape=(len(self.channels),self.Nsamples))
                print('Samples/point: ' + str(self.Nsamples))
            
            if 'SettingDict' in measParamDict:
                # Get parameters from input dictionary
                setdict = measParamDict['SettingDict']
                setting_chi = setdict['Settings']
                multip_chi = setdict['Multiplier']
                chi = setdict['Channel']
                # Parse parameters to settingDict
                self.settingDict[chi] = {'Multiplier' : multip_chi,'Settings' : setting_chi}
                # Handle parameter change
                self.handleSettingDictChange(chi)

            if 'DAQSettingDict' in measParamDict:
                # Get parameters from input dictionary
                setdict = measParamDict['DAQSettingDict']
                setting_daqchi = setdict['Settings']
                chi = setdict['Channel']
                # Parse parameters to settingDict
                self.DAQsettingDict[chi] = {'Settings' : setting_daqchi}
                # Handle parameter change
                self.handleDAQSettingDictChange(chi)

            if 'DAQinterfaces' in measParamDict:
                # Get DAQ interfaces from input dictionary
                self.DAQ_interfaces = measParamDict['DAQinterfaces']

            if 'paramSweepSettingDict' in measParamDict:
                # Get parameters from input dictionary
                setdict = measParamDict['paramSweepSettingDict']
                setting_paramsweep = setdict['Settings']
                chi = setdict['Channel']
                # Parse parameters to settingDict
                self.paramSweepSettingDict[chi] = {'Settings' : setting_paramsweep}
                chi = measParamDict['paramSweepSettingDict']['Channel']
                self.param_sweep_devices = measParamDict['param_sweep_devices']
                self.handleparamSweepSetting(chi)

            # Get UUID for the measurement
            if 'UUID' in measParamDict:
                self.uuid = measParamDict['UUID']

    def handleDAQSettingDictChange(self,channel):
        '''
        Method to handle event when DAQ settings are changed

        Parameters
        ----------
        channel : str
            DAQ whose settings has been modified

        Returns
        -------
        None.

        '''       
        # Communicate device settings to the device
        self.connectAndApplySettings(self.DAQsettingDict,channel)


    def handleparamSweepSetting(self,channel):
        '''
        Method to update parameter sweep settings to the device
        '''
        # Update number of parameter sweeps
        self.N_param_sweeps = len(self.param_sweep_devices)
        # Apply settings to the device
        self.connectAndApplySettings(self.paramSweepSettingDict,channel)

    def handleSettingDictChange(self,channel):
        '''
        Method to handle event when channel settings are changed

        Parameters
        ----------
        channel : str
            Channel whose settings has been modified

        Returns
        -------
        None.

        '''
        self.multips = []
        # Iterate through the channels and extract channel multipliers
        for chi in self.channels:
            try:
                multip_chi = self.settingDict[chi]['Multiplier']
            except:
                multip_chi = 1
            self.multips.append(multip_chi)
        # Communicate channel multiplier to measurement thread
        self.qr.put(self.multips)
        
        # Communicate device settings to the device
        if self.settingDict[channel]['Settings']['Remote']:
            self.connectAndApplySettings(self.settingDict,channel)


    def connectAndApplySettings(self,settingsdict,channel):
        '''
        Method to connect to the device and apply settings
        '''
        # Check device name and connection type
        dev_name = settingsdict[channel]['Settings']['Device']
        if dev_name=='BF':
            return
        print(f'Device name: {dev_name}')
        conn_type = settingsdict[channel]['Settings']['Connection type']
        print(f'Connection type: {conn_type}')
        # Read device address based on connection type
        if conn_type == 'GPIB':
            device_address = settingsdict[channel]['Settings']['GPIB channel']
        elif conn_type.startswith('IP'):
            if conn_type == 'IPv4 Address':
                device_address = settingsdict[channel]['Settings']['IPv4 Address']
            elif conn_type == 'IPv6 Address':
                device_address = settingsdict[channel]['Settings']['IPv6 Address']
        else:
            warnings.warn('Unknown connection type')
            return
        # Check if device address already exists and it is assigned to wanted device
        if device_address in self.devicelist and self.devicelist[device_address]['Name'] == dev_name:
            # Apply settings to the device
            self.devicelist[device_address]['Device'].apply_settings(settingsdict[channel]['Settings'])
        # Device does not exist, so initialize new one
        else:
            # Add device using DeviceManager
            DeviceManager.add_device(
                self.devicelist,
                dev_name,
                device_address,
                settingsdict[channel]["Settings"],
            )
            try:
                # Apply settings
                self.devicelist[device_address]['Device'].apply_settings(settingsdict[channel]['Settings'])   
                logging.info(f'Device {dev_name} settings updated succesfully')
            except Exception as e:
                print(e)
                logging.info(f'Error occured while updating settings to {dev_name}')

    def startEvent(self,stop_event):
        '''
        Handles event when measurement is started

        Returns
        -------
        None.

        '''
        # Start data collection
        with open(self.fname,'a+') as f:
            # Write down unique identifier
            f.write('# UUID: '+str(self.uuid))
            f.write("\n")
            # Write column labels
            for pi in self.plot_labels[:len(self.channels)+1]:
                f.write(pi + " ")
            # Write raw data labels if necessary
            if self.rawdataout:
                for chi in self.channels:
                    f.write(chi + " ")
            f.write("\n")

        # Initialize triggers and barriers for use in triggered data collection
        trigger_event = mp.Event()
        try:
            barrier = mp.Barrier(len(self.DAQ_interfaces)+1) # +1 for the main process
        except:
            logging.info('No DAQ interfaces')
            self.start = False
            # Set stop event flag
            stop_event.set()
            return

        # Log same start time for all processes for syncing
        starttime = time.perf_counter()

        # Initialize queues to be used in data collection
        self.used_queues = {}

        # Start data collection
        self.startDataCollection(starttime,stop_event,trigger_event,barrier)
        print('Data logging started')

        # Update parameter sweep of queues
        for i,di in enumerate(self.paramSweepSettingDict.values()):
            # Initialize queue for parameter sweep data
            qi = self.param_sweep_queues[i]
            self.used_queues[i+len(self.DAQ_interfaces.keys())] = qi

        # Start processing thread
        try:
            # Create a dictionary to pass to the processing function
            processdict = {
                'multips': self.multips,
                'rawdataout': self.rawdataout,
                'thermCh': self.thermCh,
                'therm_calib_name': self.therm_calib_name,
                'chunk_averaging': self.chunk_averaging,
                'DAQsettingDict': self.DAQsettingDict,
                'paramSweepDict': self.paramSweepSettingDict,
                'N_logging': self.N_logging
            }

            # Create DataProcess class
            pd = DataProcess(stop_event,self.used_queues,self.q1,self.q3,self.qr,processdict)
            
            # Start the processing in a separate process
            proData = mp.Process(target = pd.process, args = ())
            proData.start()
            print('Data processing started')
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while starting data processing: {e}")

        # Data logging thread
        logData = mp.Process(target = DataLogger,args = (stop_event,self.q3,self.fname))
        logData.start()
        print('Data writing to file started')

        time.sleep(10) # wait 10 seconds before start of scanning
        #TODO: make this to wait actual time

        # Start parameter sweeps if needed
        if len(self.param_sweep_devices)>0:
            self.startParamSweeps(starttime,stop_event,trigger_event,barrier)

    def startParamSweeps(self,starttime,stop_event,trigger_event,barrier):
        '''
        Method to start parameter sweeps
        '''
        paramdicts = []
        # Set up the parameter sweeps
        print('Setting up the parameter sweep')
        for i,di in enumerate(self.paramSweepSettingDict.values()):
            # Initialize queue for parameter sweep data
            qi = self.used_queues[i+len(self.DAQ_interfaces.keys())] 
            # Parameter to sweep
            param_name = di['Settings']['Parameter to sweep']
            # Set up parameter scan loop
            si = di['Settings']
            scan_start = si["Scan start"]
            scan_stop = si["Scan stop"]
            Npoints = si["Points to scan"]
            sett_time = si["Settling time"]
            loopi = np.linspace(scan_start,scan_stop,Npoints)
            # Add loop and settling time to the lists

            # Check device name and connection type
            dev_name = si['Device']
            #print(f'Device name: {dev_name}')
            conn_type = si['Connection type']
            #print(f'Connection type: {conn_type}')
            # Read device address based on connection type
            if conn_type == 'GPIB':
                device_address = si['GPIB channel']
            elif conn_type.startswith('IP'):
                if conn_type == 'IPv4 Address':
                    device_address = si['IPv4 Address']
                elif conn_type == 'IPv6 Address':
                    device_address = si['IPv6 Address']
            else:
                warnings.warn('Unknown connection type')
                return
            # Check if device address already exists and it is assigned to wanted device
            if device_address in self.devicelist and self.devicelist[device_address]['Name'] == dev_name:
                # Add to parameter sweep device list
                dev = self.devicelist[device_address]['Device']
            else:
                logging.info(f'Device {dev_name} not found for parameter sweep. Please check the device connection.')

            paramdicts.append({'loopi':loopi,
                                'param_name':param_name,
                              'sett_time':sett_time,
                              'trigger_event':trigger_event,
                              'barrier':barrier,
                              'device':dev,
                              'qi':qi,
                              'starttime':starttime,
                              'stop_event':stop_event})
        print('Starting parameter sweep')
        self.nested_iteration(paramdicts)
        # Stop the data acquisition
        stop_event.set()

        # Start the thread for the nested iteration for parameter sweeps
        try:
            psthread = th.Thread(target = self.nested_iteration,args = (paramdicts,))
            psthread.start()
        except Exception as e:
            print(f"Error occurred while setting up parameter sweep: {i}")

    # Make a function that operates every sweep step
    def set_device_param(self,value, paramdict):
        '''
        Function to be operated at scan point
        '''
        param_name = paramdict['param_name']
        stop_event = paramdict['stop_event']
        device = paramdict['device']
        sett_time = paramdict['sett_time']
        trigger_event = paramdict['trigger_event']
        barrier = paramdict['barrier']
        print(f'Setting {param_name} to {value}')
        if stop_event.is_set():
            return
        # Set the parameter on the device
        setvalue = device.set_parameter(param_name,value)
        # Wait for settling time
        time.sleep(sett_time)
        # Trigger the data acquisition 
        trigger_event.set()
        # Wait for data acquisition to be finished
        barrier.wait()
        # Clear the trigger
        trigger_event.clear()
        print('Parameter set')
        return setvalue

    def nested_iteration(self,paramdicts,out_arrs = None, level=0):
        '''
        Function to iterate trough N number of parameter sweeps
        '''
        stop_event = paramdicts[level]['stop_event']
        starttime = paramdicts[level]['starttime']

        if out_arrs is None:
            out_arrs = np.empty(len(paramdicts), dtype=object)
            for i in range(len(paramdicts)):
                out_arrs[i] = np.array([[time.perf_counter()-starttime],[np.nan]])
        # Check for stop_event
        if stop_event.is_set():
            return
        # iterate though nested loop level
        try:
            for value in paramdicts[level]['loopi']:
                # Check for the stop event
                if stop_event.is_set():
                    return
                setvalue= self.set_device_param(value,paramdicts[level])
                # Log the change in the parameter sweep
                out_arrs[level] = np.array([[time.perf_counter()-starttime],[setvalue]])
                # Put current values to queue
                for i,pi in enumerate(paramdicts):
                    qii = pi['qi']
                    qii.put(out_arrs[i])
                if level + 1 < len(paramdicts):
                    # Do nested iteration
                    self.nested_iteration(paramdicts,out_arrs, level + 1)
                    # Put current values to queue
                    for i,pi in enumerate(paramdicts):
                        qii = pi['qi']
                        qii.put(out_arrs[i])
                    # Check again for the stop event
                    if stop_event.is_set():
                        return
        except Exception as e:
            print(traceback.print_exc())
            logging.info(f'Parameter sweep failed:{e}')

    def startDataCollection(self,starttime,stop_event,trigger_event,barrier):
        '''
        Method to start data collection from the DAQ interfaces

        Parameters
        ----------
        stop_event : multiprocessing.Event
            Event to signal stopping of data collection.
        trigger_event : multiprocessing.Event
            Event to signal triggering of data collection.
        barrier : multiprocessing.Barrier
            Barrier for synchronizing processes.

        Returns
        -------
        None.

        '''
        # initialize DAQ control class
        daq = DAQ()
        for daqch,daqi in zip(self.DAQ_interfaces.keys(), self.DAQ_interfaces.values()):
            print(f'Setting up DAQ interface {daqch} of type {daqi}')
            qi = self.data_queues[daqch]
            settings = self.DAQsettingDict[daqch]['Settings']
            mi = None
            # Moku GO
            if daqi == 'Moku Go':
                try:
                    mi = mp.Thread(target = daq.MokuGo_continuous_Nread,
                                    args = (stop_event,starttime,qi,settings))
                except Exception as e:
                    print(f"Error occurred while initializing Moku Go: {e}")
                try:
                    mi.start()
                except Exception as e:
                    print(f"Error occurred while starting Moku Go process: {e}")
            # Ni DAQ acquisition
            elif daqi == 'NI DAQ':
                mi = mp.Thread(target = daq.NiDAQmx_continous_Nread,args = (stop_event,starttime,qi,settings))
                mi.start()
            # Bluefors data acquisition
            elif daqi == 'BF':
                if settings['Acquisition mode'] == 'Continuous':
                    # use threading as instrument needs to be passed to the process and it is not picklable
                    try:
                        ti = mp.Process(target = BFcontinuous_MXC_read,args = (stop_event,starttime,qi))
                    except Exception as e:
                        print(f"Error occurred while initializing Bluefors API: {e}")
                    try:
                        ti.start()
                    except Exception as e:
                        print(f"Error occurred while starting Bluefors API: {e}")
                elif settings['Acquisition mode'] == 'Trigger':
                    # use threading as instrument needs to be passed to the process and it is not picklable
                    try:
                        ti = mp.Process(target = BFtrigger_MXC_read,args = (stop_event,starttime,qi,
                                                                                    trigger_event,
                                                                                    barrier))
                    except Exception as e:
                        print(f"Error occurred while initializing Bluefors API: {e}")
                    try:
                        ti.start()
                    except Exception as e:
                        print(f"Error occurred while starting Bluefors API: {e}")
            # Using device read functions with GPIB devices
            else:
                conn_type = settings['Connection type']
                print(f'Connection type: {conn_type}')
                # Read device address based on connection type
                if conn_type == 'GPIB':
                    device_address = settings['GPIB channel']
                elif conn_type.startswith('IP'):
                    if conn_type == 'IPv4 Address':
                        device_address = settings['IPv4 Address']
                    elif conn_type == 'IPv6 Address':
                        device_address = settings['IPv6 Address']
                else:
                    warnings.warn('Unknown connection type')
                    return
                # Check if device address already exists and it is assigned to wanted device
                if device_address in self.devicelist and self.devicelist[device_address]['Name'] == daqi:
                    device = self.devicelist[device_address]['Device']
                    # use threading as instrument needs to be passed to the process and it is not picklable
                    try:
                        if settings['Acquisition mode'] == 'Continuous':
                            print(f'Starting continuous acquisition with {daqi}')
                            ti = th.Thread(target = device.continuous_Nread,args = (stop_event,
                                                                                    starttime,
                                                                                    qi,
                                                                                    settings))
                        elif settings['Acquisition mode'] == 'Trigger':
                            print(f'Starting triggered acquisition {daqi}')
                            ti = th.Thread(target = device.triggered_Nread,args = (stop_event,
                                                                                   starttime,
                                                                                   qi,
                                                                                   settings,
                                                                                   trigger_event,
                                                                                   barrier))
                        else: 
                            ti = th.Thread(target = device.continuous_Nread,args = (stop_event,starttime,qi,settings))
                    except Exception as e:
                        print(f"Error occurred while initializing {daqi}: {e}")
                    try:
                        ti.start()
                    except Exception as e:
                        print(f"Error occurred while starting process: {e}")
                else:
                    print(f"{daqi} not found for GPIB channel {device_address}. Please check the device connection.")

            # Add thread and queue to the list of used threads and queues
            self.used_queues[daqch] = qi
        print(f"Number of used DAQ queues: {len(self.used_queues)}")


    def Exit(self):
        '''
        Exit system

        Returns
        -------
        None.

        '''
        sys.exit()
        


        
def testfunction(Nchannels,Nsamples):
    '''
    Function to test data aquisition system

    Parameters
    ----------
    Nchannels : int
        Number of measurement channels in use.
    Nsamples : int
        Number of samples.

    Returns
    -------
    out
        output array with random numbers

    '''
    return np.random.rand(Nchannels,Nsamples)

def getChannelNames(name):
    '''
    Function to generate channel names for testing

    Parameters
    ----------
    name : TYPE
        DESCRIPTION.

    Returns
    -------
    list
        DESCRIPTION.

    '''
    return ["Dev1/ai0","Dev1/ai1","Dev1/ai2","Dev1/ai3","Dev1/ai4","Dev1/ai5","Dev1/ai6","Dev1/ai7"]
        
if __name__ == '__main__':
        # Initialize class
        meas = pyDAQmeas()
        # Device name, change if needed
        #meas.daq_device_name = 'Dev1'
        meas.daq_device_name = 'Dev1'
        meas.daq_device_name = 'MokuGo'
        meas.moku_go_ip = '[fe80::7269:79ff:feb9:7b5c]'
        
        meas.testmode = False

        # Settling time, 10e-3 is good starting point
        meas.settling_time = 10e-3
        meas.N_logging = 10
        meas.memory_limit = 1000000
        
        meas.disable_plotting = False
        
        meas.chunk_averaging = True
        meas.rawdataout = True
        
        meas.stop_event = mp.Event()
        
        # Default values for different variables
        # All of these can be changed from the GUI
        meas.therm_calib_name = "None"
        meas.Nsamples = 5000
        meas.sample_rate = 5e4
        meas.defaultpathname = r""
        meas.filename = r'testing.data'
        meas.therm_multiplier = 1000
        #meas.channels=["Dev1/ai0","Dev1/ai1","Dev1/ai2"]
        meas.channels=["time","ch1","ch2"]
        
        # Start data plotting GUI
        gui_process = mp.Process(target = meas.startPlotting)
        gui_process.start()
        

         
    
    
    
    
    
    
    