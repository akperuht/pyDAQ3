from pymeasure.instruments.srs import SR860
import pyvisa as visa
import logging
from pathlib import Path
import json 
import time
import numpy as np
'''
=========================================================================================================================
 Driver for Stanford Research Systems lock-in amplifier model SR860
 
Inherits class pymeasure.instruments.srs.SR860, and adds some useful functions
 
@author: Aki Ruhtinas, aki.ruhtinas@gmail.com
=========================================================================================================================
'''

class SR860(SR860):
    '''
    Class to control SRS SR860 lock-in amplifier via GPIB/ethernet. 
    Inherits class pymeasure.instruments.srs.SR860,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/srs/sr860.html
    '''
    def __init__(self,address):
        '''
        Creates new SR860_lockin class that inherits class SR860

        Parameters
        ----------
        address : string
            Address for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.rm = visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(address)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Lock-in amplifier online. device ID:',self.instr_id)

        paramsdict = None
        # load parameter file
        current_dir = Path(__file__).resolve().parent
        # This is meant to be called from main folder
        try:
            paramsfile = current_dir.parent.parent/ 'Control_lib' /'parameters'/'SR860_params.json'
            with open(paramsfile) as jf:
                paramsdict = json.load(jf)
        except:
            try:
                # fall back to own directory
                paramsfile = 'SR560_params.json'
                with open(paramsfile) as jf:
                    paramsdict = json.load(jf)
            except:
                logging.info('ERROR: Unable to find parameter file')
        self.setting_params = paramsdict['Settings']

    def apply_settings(self,settingsDict):
        '''
        Provides interface to change most of the lock-in amplifier settings. This function maybe slow, and thus
        usage of dedicated functions is encouraged for performance critical applications
        
        '''
        # Synchronous filter status setting
        if 'Synchronous filter' in settingsDict:
            self.sync = settingsDict['Synchronous filter']
            if self.sync:
                self.instr_gpib.write('SYNC 1')
            else:
                self.instr_gpib.write('SYNC 0')
                
        # Input configuration
        if 'Input configuration' in settingsDict:
            inpconf = str(settingsDict['Input configuration'])
            if inpconf == 'A':
                self.instr_gpib.write('IVMD 0')
                self.instr_gpib.write('ISRC 0')
            elif inpconf == 'A-B':
                self.instr_gpib.write('IVMD 0')
                self.instr_gpib.write('ISRC 1')
            else:
                self.instr_gpib.write('IVMD 1')

            
        # Input shield grounding
        if 'Input grounding' in settingsDict:
            if 'Float' in settingsDict['Input grounding']:
                self.instr_gpib.write('IGND 0')
            elif 'Ground' in settingsDict['Input grounding']:
                self.instr_gpib.write('IGND 1')
            else:
                print(f'Error: {settingsDict["Input grounding"]} is not a valid input shield grounding option, choose either Ground or Float')

        # Input coupling
        if 'Input coupling' in settingsDict:
            if 'AC' in settingsDict['Input coupling']:
                self.instr_gpib.write('ICPL 0')
            elif 'DC' in settingsDict   ['Input coupling']:
                self.instr_gpib.write('ICPL 1')
            else:
                print(f'Error: {settingsDict["Input coupling"]} is not a valid input coupling option, choose either DC or AC')
            
        
        # Detection harmonic
        if "Harmonic" in settingsDict:
            self.instr_gpib.write('HARM ', str(settingsDict["Harmonic"]))
            self.harm = self.instr_gpib.query('HARM?')
        
        # Time constant and slope settings       
        if 'Filter slope' in settingsDict:
            fsl = settingsDict['Filter slope']
            values = self.setting_params["Filter slope"]['values']
            self.instr_gpib.write(f'OFSL {values.index(fsl)}')

        if "Time constant" in settingsDict:
            tc = settingsDict["Time constant"]
            values = self.setting_params["Time constant"]['values']
            self.instr_gpib.write(f'OFSL {values.index(tc)}')

        # Phase shift setting
        if 'Phase' in settingsDict:
            self.instr_gpib.write('PHAS ', str(settingsDict['Phase']))
            self.phase_shift = float(self.instr_gpib.query('PHAS?')) 
            print('Phase shift set to ',str(self.phase_shift))             
        
        # Frequency and sine amplitude settings
        if 'Sine frequency' in settingsDict:
            freq = settingsDict['Sine frequency']
            self.instr_gpib.write(f'FREQINT {freq}')

        if 'Sine amplitude' in settingsDict:
            ampl = settingsDict['Sine amplitude']
            self.instr_gpib.write(f'SLVL {ampl}')
        # Setting the DC offset
        if 'DC offset' in settingsDict:
            ampl = settingsDict['DC offset']
            self.instr_gpib.write(f'SOFF {ampl}')

        # Setting the sensitivity
        if 'Sensitivity' in settingsDict:
            sens = settingsDict["Sensitivity"]
            values = self.setting_params["Sensitivity"]['values']
            self.instr_gpib.write(f'SCAL {values[::-1].index(sens)}')          
            
        print('Device settings applied successfully')

    def set_dc_offset(self,ampl):
        '''
        Method to set the DC offset
        '''
        self.instr_gpib.write(f'SOFF {ampl}')

    def read_channels(self,channels):
        '''
        Method to read channel values using OUT commands
        Warning: quite slow, using data streaming for fast capture
        '''
        available_channels = self.setting_params["Channels"]['values']
        # Initialize value array
        N_ch = len(channels)
        values = np.empty(N_ch)
        # SNAP can be used to query less than 3 channels
        if N_ch<=3:
            cmd_index = [available_channels.index(chi) for chi in channels]
            cmd_str = ','.join(map(str, cmd_index))
            values_str = self.instr_gpib.query(f"SNAP? {cmd_str}")
            values = [float(x) for x in values_str.split(',')]
        # Fall back to individual query
        else:
            for i,ch in enumerate(channels):
                if ch in available_channels:
                    values[i] = float(self.instr_gpib.query(f"OUTP? {available_channels.index(ch)}"))
                    print(f'{ch}:{values[i]}')
                    time.sleep(1e-4)
                else:
                    raise ValueError(f"Unsupported channel: {ch}")
        return values
    
    def singleNread(self,starttime,settings):
        '''
        Function to read N values from desired channels
        '''
        available_channels = self.setting_params["Channels"]['values']
        measured_channels = settings["Channels"]
        Nsamples = settings["Number of samples"]
        # Initialize arrays
        out = np.zeros((len(measured_channels), Nsamples))*np.nan
        time_arr = np.zeros(Nsamples)*np.nan
        # Collect samples in a loop
        for i in range(Nsamples):
            # Read the values from the SR830
            values = self.read_channels(measured_channels)
            out[:,i] = values
            time_arr[i] = time.perf_counter()-starttime
        return time_arr,out

    @staticmethod
    def get_capture_config(requested_channels):
        '''
        Deciding correct channels based on this:
        The CAPTURECFG i command sets the capture configuration to X (i=0), X and Y (i=1),
        R and θ (i=2) or X, Y, R and θ (i=3).
        '''
        req = set(requested_channels)
        if req <= {"X"}:
            return 0, ["X"]
        elif req <= {"X", "Y"}:
            return 1, ["X", "Y"]
        elif req <= {"R", "Theta"}:
            return 2, ["R", "Theta"]
        else:
            return 3, ["X", "Y", "R", "Theta"]

    def continuous_Nread(self,stop_event,starttime,q,settings):
        '''
        Function to read continuously data from SR830. Data is read every time 
        until stop_event is set.
        '''
        t0 = starttime
        Nsamples = settings['Number of samples']
        channels = settings['Channels']
        print(f'SR860 data acquisition started with {Nsamples} samples from channels {channels}')
        logging.info(f'Starting SR860 data acquisition with {Nsamples} samples from channels {channels}')
        try:
            while not stop_event.is_set():
                time_arr,out = self.singleNread(starttime,settings)
                q.put(np.vstack((time_arr, out)))
        finally:
            logging.info('Stopping SR860 data acquisition')


    def triggered_Nread(self,stop_event,starttime,q,settings,trigger,barrier):
        '''
        Function to read continuously data from SR860 when trigger is applied. 
        Data is read every time for trigger event until stop_event is set.
        '''
        t0 = starttime
        Nsamples = settings['Number of samples']
        channels = settings['Channels']
        print(f'SR860 data acquisition started with {Nsamples} samples from channels {channels}')
        logging.info(f'Starting SR860 data acquisition with {Nsamples} samples from channels {channels}')
        try:
            while not stop_event.is_set():
                # wait for the trigger
                trigger.wait()
                # Do the data acquisition
                time_arr,out = self.singleNread(starttime,settings)
                q.put(np.vstack((time_arr, out)))
                # Indicate that data acquisition finished to barrier
                barrier.wait()
        finally:
            logging.info('Stopping SR860 data acquisition')

    def set_parameter(self,parameter,value):
        '''
        Function to implement parameter sweeps
        '''
        if parameter=='DC offset':
            self.set_dc_offset(value)
        elif parameter=='Sine frequency':
            self.instr_gpib.write(f'FREQINT {value}')
        else:
            logging.info(f'Error: parameter {parameter} can\'t be changed')
        return value
            

def SR860_singleNreadfast(starttime,q,sr860,channels,settings):
    # Take all available channels to list
    available_channels = sr860.setting_params["Channels"]['values']

    # Select capture channels for fast capture
    sr860.instr_gpib.write(f"CAPTURECFG {sr860.get_capture_config(channels)[0]}")

    # Set capture rate (instrument-specific index/value)
    sr860.instr_gpib.write(f"CAPTURERATE {settings["Capture rate"]}")

    # Set capture length
    sr860.instr_gpib.write(f"CAPTURELEN {settings["Capture length"]}")

    # Clear previous capture
    sr860.instr_gpib.write("CAPTURESTOP")
    # Start one shot capture
    sr860.instr_gpib.write("CAPTURESTART ONE, IMM")
    # Wait until capture finishes
    while int(sr860.instr_gpib.query("CAPTURESTAT?")) & 1:
        time.sleep(1e-6)
    # Number of bytes actually captured
    nbytes = int(sr860.instr_gpib.query("CAPTUREBYTES?"))

    # Download binary float32 data
    data = sr860.instr_gpib.query_binary_values(
        "CAPTUREGET? 0,{}".format(nbytes),
        datatype='f',
        is_big_endian=False,
        container=np.array
    )
    print(data.shape())

    
if __name__ == '__main__':
    sr860 = SR860('GPIB0::10::INSTR')
    settings = {"Capture rate":20,"Capture length":2}
    starttime = time.perf_counter()
    q = None
    channels = ['Aux In 1','Aux In 1']
    print(sr860.read_channels(channels))
