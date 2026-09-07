import pyvisa as visa
import re
from time import perf_counter
import numpy as np
import logging
import warnings

'''
=========================================================================================================================
                Driver for Picowatt AVS-47
@author: Aki Ruhtinas, aki.ruhtinas@gmail.com
=========================================================================================================================
'''
class AVS47():
    '''
    Class to control Picowatt AVS-47 Resistance bridge via GPIB
    '''
    def __init__(self,gpib_id):
        '''
        Creates new AVS47 class

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        Returns
        -------
        None.

        '''
        self.gpib_id = re.sub('::INSTR$', '', gpib_id)
        self.rm = visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Picowatt AVS-47 resistance bridge online:',self.instr_id)
        
        self.range = 1
        # Available range options
        self.range_options = [0,2,20,200,2000,20e3,200e3,2e6]
        
        self.exc = 1
        # Available exctiation options
        self.exc_options = [0,3,10,30,100,300,1000,3000]
        
        self.input_options = ['Zero','Measure','Calibrate']

    def apply_settings(self,settingsDict):
        '''
        Method to apply settings to the device from dictionary

        Parameters
        ----------
        settingsDict : dict
            dictionary containing setting type as a key and corresponding value

        Returns
        -------
        None.

        '''
        # Make sure that device is in remote mode
        self.enable_remote()
        # Process all settings that are in settingsDict
        # Excitation
        if 'Excitation' in settingsDict:
            self.set_exc(settingsDict['Excitation'])
        # Range
        if 'Range' in settingsDict:
            self.set_range(settingsDict['Range'])
        # Input
        if 'Input' in settingsDict:
            if settingsDict['Input'] == 'Zero':
                self.to_GND()
            elif settingsDict['Input'] == 'Calibrate':
                self.to_100_ohm_ref()
            elif settingsDict['Input'] == 'Measure':
                self.measure()
            else:
                print('ERROR:Unknown input type')
            # Finally check that correct input is applied
            self.get_input()
        # Channel
        if 'Channel' in settingsDict:
            self.set_channel(settingsDict['Channel'])
        
        
        
        
    def write(self,msg):
        '''
        Wrapper for writing messages to instruments

        Parameters
        ----------
        msg : string
            GPIB command

        Returns
        -------
        None.

        '''
        self.instr_gpib.write(msg)
        
        
        
    def query(self,msg):
        '''
        Wrapper for queries to instruments

        Parameters
        ----------
        msg : string
            GPIB command

        Returns
        -------
        string
            Instruments response to query

        '''
        return self.instr_gpib.query(msg)
    
    def get_input(self):
        '''
        Queries input type 

        Returns
        -------
        None.

        '''
        inp = int(self.instr_gpib.query('INP ?')[3:5])
        print(f'Input:{self.input_options[inp]}')
        
    
    def to_GND(self):
        '''
        Connects the bridge input to ground. Use
        this position for determining any possible offset.

        Returns
        -------
        TYPE
            DESCRIPTION.

        '''
        self.instr_gpib.write('INP 0')

    def measure(self):
        '''
        Enables the actual measurement. The sensor
        channel is determined by the MUX setting

        Returns
        -------
        TYPE
            DESCRIPTION.

        '''
        self.instr_gpib.write('INP 1')
    
    def to_100_ohm_ref(self):
        '''
        Connects the bridge to an internal 100Ω
        precision reference. Use this position for calibrating the scale factor.

        Returns
        -------
        None.

        '''
        self.instr_gpib.write('INP 1')

    def set_range(self,rang):
        '''
        Select the measurement range and queries that change is successfull.
        
        Do not use range 0, because this prevents the
        AVS-47B from stabilizing. (This setting means
        that no range is connected. The AVS-47B powers
        on with RAN 0, so that it could not heat the sensor
        before the proper range and excitation have been
        selected).

        Parameters
        ----------
        rang : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        '''
        i = -1
        if isinstance(rang, int) and 0<rang<8:
            i = rang
        else:
            try:
                i = int(self.range_options.index(rang))
            except:
                print('ERROR:Invalid range')
        # Set the range
        if i>=0:
            self.instr_gpib.write('RAN '+ str(i))
            # Check the range
            print(f'Range: {self.range_options[self.get_range()]}')
    
    def get_range(self):
        '''
        Queries what range is in use

        Returns
        -------
        rang : int
            Measurement range in use

        '''
        rang = self.instr_gpib.query('RAN ?')
        self.range = rang
        return int(rang[3:5])
    
    def set_exc(self,exc):
        '''
        Select the measurement excitation and queries that change is successfull.

        Parameters
        ----------
        exc : string or int
            Desired excitation

        Returns
        -------
        None.

        '''
        if isinstance(exc, int) and 0<exc<8:
            i = exc
            self.instr_gpib.write('EXC '+ str(i))
        else:
            try:
                i = str(self.exc_options.index(exc))
                self.instr_gpib.write('EXC '+ str(i))
            except:
                warnings.warn('Invalid excitation')
        print(f'Excitation: {self.exc_options[self.get_exc()]}')
    
    def get_exc(self):
        '''
        Queries what excitation is in use

        Returns
        -------
        rang : int
            Measurement range in use

        '''
        exc = self.instr_gpib.query('EXC ?')
        self.exc = exc
        return int(exc[3:5])
    
    def set_channel(self,ch):
        '''
        Sets measurement channel

        Parameters
        ----------
        ch : int
            Channel number

        Returns
        -------
        None.

        '''
        if isinstance(ch, int) and 0<=ch<8:
            self.instr_gpib.write('MUX '+ str(ch))

        else:
            print('ERROR:Invalid channel')
        print(f'Channel: {self.get_channel()}')
            
    def get_channel(self):
        '''
        Gets measurement channel number

        Returns
        -------
        ch : int
            Channel number
        '''
        ch = self.instr_gpib.query('MUX ?')
        self.ch = ch
        return ch
   
    def enable_remote(self):
        '''
        Enable remote control

        Returns
        -------
        None.

        '''
        self.instr_gpib.write('REM 1')
        if self.instr_gpib.query('REM ?') == '1':
            print('Remote enabled')
        
    def disable_remote(self):
        '''
        Disable remote control

        Returns
        -------
        None.

        '''
        self.instr_gpib.write('REM 0')
        if self.instr_gpib.query('REM ?') == '0':
            print('Remote disabled')

    def singleNread(self,starttime,settings):
        '''
        Function to read N values from desired channels
        '''
        Nsamples = settings["Number of samples"]
        # Initialize arrays
        out = np.zeros((1, Nsamples))*np.nan
        time_arr = np.zeros(Nsamples)*np.nan
        # Collect samples in a loop
        for i in range(Nsamples):
            # Read the values from the AVS-47
            self.write("ADC")
            # Read the value
            value = float(self.query("RES?").split('  ')[1])
            out[:,i] = value
            time_arr[i] = perf_counter()-starttime
        return time_arr,out

    def continuous_Nread(self,stop_event,starttime,q,settings):
        '''
        Function to read continuously data from AVS-47. Data is read every time 
        until stop_event is set. N=1 best of read speed issues
        '''
        try:
            Nsamples = settings["Number of samples"]
        except:
            Nsamples = 1
        t0 = perf_counter()
        try:
            while not stop_event.is_set():
                time_arr,out = self.singleNread(starttime,settings)
                q.put(np.vstack((time_arr, out)))
        finally:
            logging.info('Stopping AVS-47 data acquisition')

    def triggered_Nread(self,stop_event,trigger,starttime,q,settings):
        print('TODO:implementation')