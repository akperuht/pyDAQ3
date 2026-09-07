import pyvisa as visa
import numpy as np
import time
import yaml
import datetime
from time import perf_counter
import logging
'''
=========================================================================================================================
 Driver for Stanford Research Systems lock-in amplifier models SR810 and SR830
 
@author: Aki Ruhtinas, aki.ruhtinas@gmail.com
=========================================================================================================================
'''

class SR830():
    '''
    Class for controlling Stanford Research Systems lock-in amplifier models SR810 and SR830
    '''
    
    def __init__(self,gpib_id):
        '''
        Creates new SR830 or SR810 resource

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument

        Returns
        -------
        None.

        '''
        
        
        '''
        Options available at SR810/SR830 lock in amplifiers
        '''
        self.time_const_options=['10 us','30 us','100 us','300 us','1 ms','3 ms', '10 ms', 
                 '30 ms', '100 ms', '300 ms','1 s','3 s','10 s','30 s','100 s'
                 '300 s', '1 ks', '3 ks','10 ks','30 ks']

        self.reserve_mode_options=['High Reserve','Normal', 'Low Noise']

        self.sens_options=['2 nV/fA','5 nV/fA','10 nV/fA','20 nV/fA','50 nV/fA','100 nV/fA',
              '200 nV/fA','500 nV/fA','1 uV/pA','2 uV/pA','5 uV/pA','10 uV/pA','20 uV/pA',
              '50 uV/pA','100 uV/pA','200 uV/pA','500 uV/pA ','1 mV/nA','2 mV/nA','5 mV/nA',
              '10 mV/nA','20 mV/nA','50 mV/nA','100 mV/nA','200 mV/nA','500 mV/nA','1 V/uA',]

        self.filter_slope_options = ['6 dB/oct','12 dB/oct','18 dB/oct','24 dB/oct']
        
        self.expand_list=[0,10,100]
        
        self.disp1_list=['X','R','X Noise','Aux In 1','Aux In 2']
        self.sr830_disp2_list=['Y','Phase','Y Noise','Aux In 3','Aux In 4']
        self.disp1_ratio_list=['None','Aux In 1','Aux In 2']
        self.sr830_disp2_ratio_list=['None','Aux In 3','Aux In 4']
        
        self.input_config_list = ['A','A-B','I(1 Mohm)','I(100 Mohm)']
        
        self.notch_list=['Out','Line In', '2x Line in','Both In']
        
        self.ref_slope_list=['Sine','TTL Rising','TTL Falling']
        
        self.phase_shift=0
        
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Lock-in amplifier online. device ID:',self.instr_id)

        self.instr_gpib.timeout = 5000
        
        # Initialize attributes
        self.frequency=19.127
        self.sine_ampl=0.1
        self.harm=1
        self.ref_slope=0
        self.tau='300 ms'
        self.slope=''
        self.internal=True
        self.rmod='Normal'
        self.sens='1 mV/nA'
        self.sync=True
        self.input_config='A'
        self.shield_gnd=1
        self.input_coupling=0
        self.notch=0
        
        # Offset attributes
        self.x_offset = None
        self.y_offset = None
        self.r_offset = None
        # Expand attributes
        self.x_expand = None
        self.y_expand = None
        self.r_expand = None
        # Display and output attributes
        self.ch1_disp = None
        self.ch1_ratio = None
        self.ch1_output = None       
        self.ch2_disp = None
        self.ch2_ratio = None
        self.ch2_output = None
        
        # create dictionaries to store the settings
        self.settingsDict={}
        self.oexp_dict={}
        self.disp_dict={}
        
        
        # Read current settings of the device
        self.read_settings()

    def read_output(self,value_to_read):
        '''
        Queries output of the lock-in amplifier

        Parameters
        ----------
        value_to_read : string
            String describing desired output value to read.
            Supported outputs: X,Y,R,Phase
            
        Returns
        -------
        float
            Requested output value, returned as ASCII floating point numbers 
            with units of Volts or degrees.
        '''
      
        if 'X' in value_to_read:
            return float(self.instr_gpib.query('OUTP? 1'))
        elif 'Y' in value_to_read:
            return float(self.instr_gpib.query('OUTP? 2'))
        elif 'R' in value_to_read:
            return float(self.instr_gpib.query('OUTP? 3'))
        elif any(item in ['Phase','phase','ph','P'] for item in value_to_read):
            return float(self.instr_gpib.query('OUTP? 4'))
        else:
            print('Output type not recognized')

    def set_ref_source(self, ref_type):
        '''
        Sets the reference source for SR810/SR830 lock-in amplifiers

        Parameters
        ----------
        ref_type : string
           Reference source, either "internal" or "external"
        Returns
        -------
        None.

        '''        
        # Set reference sources and check that reference sources are set correc
        try:
            if ref_type=="internal":
                self.instr_gpib.write('FMOD ',str(1))
                self.internal=True
            else:
                self.instr_gpib.write('FMOD ',str(0))
                self.internal=False
            mode=self.instr_gpib.query('FMOD?')
            if '1' in mode and ref_type=='internal':
                print('   Reference source set to internal')
            elif '0' in mode and ref_type=='external':
                print('   Reference source set to external')
            else:
                print('Error occurred when setting the reference source')
        except Exception as e:
            print(e)
            
    def get_ref_source(self):
        '''
        Queries type of reference source and updates class attributes accordingly

        Returns
        -------
        None.

        '''
        mode=self.instr_gpib.query('FMOD?')
        if '1' in mode:
            self.internal=True
        elif '0' in mode:
            self.internal=False
        else:
            print('Error occurred: unknown reference setting')
        
        
    def set_tau_slope(self, tau, slope):
        '''
        Sets time constant and filter slope setting for the instrument

        Parameters
        ----------
        tau : string
            Time constant
        slope : string
            Filter slope

        Returns
        -------
        None.

        '''
        # Set time constants and slope of lock-in amplifiers
        try:
            self.instr_gpib.write('OFLT ',str(self.time_const_options.index(tau)))
            self.instr_gpib.write('OFSL ',str(self.filter_slope_options.index(slope)))  
            self.get_tau_slope()
            if self.tau!=tau or self.slope!=slope:
                print('Error: unable to set time constant or filter slope settings')
        except Exception as e:
            print(e)
            
            
    def get_tau_slope(self):
        '''
        Queries time constant and filter slope settings and updates attributes accordingly

        Returns
        -------
        string
            Time constant
        string
            Filter slope, '6 dB/oct', '12 dB/oct', '18 dB/oct' or '24 dB/oct'
        '''
        self.tau=self.time_const_options[int(self.instr_gpib.query('OFLT?'))]
        self.slope=self.filter_slope_options[int(self.instr_gpib.query('OFSL?'))]
        return self.tau,self.slope
        
        
    def set_freq_ampl(self, freq, ampl):
        '''
        Sets sine output frequency and amplitude

        Parameters
        ----------
        freq : float
            Sine output frequency in Hz
        ampl: float
            Sine output amplitude in volts
        Returns
        -------
        None.

        '''
        try:
            self.instr_gpib.write('FREQ ',str(freq))
            self.instr_gpib.write('SLVL ', str(ampl))
            self.get_freq_ampl()
        except Exception as e:
            print(e)
            
    def get_freq_ampl(self):
        '''
        Queries frequency and amplitude of the lock-in amplifier and updates
        corresponding attributes

        Returns
        -------
        float
            Frequency of the lock in amplifier, unit Hz
        float
            Amplitude, unit V

        '''
        self.frequency=float(self.instr_gpib.query('FREQ?').strip())
        self.sine_ampl=float(self.instr_gpib.query('SLVL?').strip())
        return self.frequency,self.sine_ampl
        
        
    def set_display_output(self,**kwargs):
        '''
        Parameters
        ----------
        **kwargs : 

        For SR810 only CH1 options are available
            
        CH1display      CH2display
        0 X             0 Y
        1 R             1 theta
        2 X Noise       2 Y Noise
        3 Aux In 1      3 Aux In 3
        4 Aux In 2      4 Aux In 4

        CH1ratio        CH2ratio
        0 none          0 none
        1 Aux In 1      1 Aux In 3
        2 Aux In 2      2 Aux In 4

        CH1output       CH2output
        0 CH1 Display   0 CH2 Display
        1 X             1 Y
        
        Returns
        -------
        None.

        '''
        # read possible new values from kwargs
        if 'CH1display' in kwargs:
            self.ch1_disp=kwargs['CH1display']
        if 'CH1ratio' in kwargs:
            self.ch1_ratio=kwargs['CH1ratio']
        if 'CH1output' in kwargs:
            self.ch1_output=kwargs['CH1output']        
        if 'CH2display' in kwargs:
            if 'SR830' not in self.instr_id:
                print('Error: device has only one output channel')
            else:
                self.ch2_disp=kwargs['CH2display']
        if 'CH2ratio' in kwargs:
            if 'SR830' not in self.instr_id:
                print('Error: device has only one output channel')
            else:
                self.ch2_ratio=kwargs['CH2ratio']
        if 'CH2output' in kwargs:
            if 'SR830' not in self.instr_id:
                print('Error: device has only one output channel')
            else:
                self.ch2_output=kwargs['CH2output']    
            
        if 'SR830' in self.instr_id:
            self.instr_gpib.write('DDEF 1,'+str(self.ch1_disp)+','+str(self.ch1_ratio))
            self.instr_gpib.write('DDEF 2,'+str(self.ch2_disp)+','+str(self.ch2_ratio))
            # Set front panel output source
            self.instr_gpib.write('FPOP 1,'+str(self.ch1_output))
            self.instr_gpib.write('FPOP 2,'+str(self.ch2_output))
        else:
            # Set front panel output source
            self.instr_gpib.write('DDEF '+str(self.ch1_disp)+','+str(self.ch1_ratio))
            # Set front panel output source
            self.instr_gpib.write('FPOP '+str(self.ch1_output))
        
    def get_display_output(self):
        '''
        Queries display settings and updates corresponding attributes

        Returns
        -------
        list
            List of integers corresponding to current display and output settings
            SR830:[CH1 Display, CH1 Ratio, CH2 Display, CH2 Ratio, CH1 Output, CH2 Output]
            SR810: [CH1 Display, CH1 Ratio, CH1 Output]

        '''
        if 'SR830' in self.instr_id:
            # Read display settings
            self.ch1_disp, self.ch1_ratio = np.array(self.instr_gpib.query('DDEF? 1').split(',')).astype(int)
            self.ch2_disp, self.ch2_ratio = np.array(self.instr_gpib.query('DDEF? 2').split(',')).astype(int)
            # Read front panel output values
            self.ch1_output = int(self.instr_gpib.query('FPOP? 1'))
            self.ch2_output = int(self.instr_gpib.query('FPOP? 2'))
            # Return settings
            return [self.ch1_disp, self.ch1_ratio,self.ch2_disp, 
                   self.ch2_ratio,self.ch1_output,self.ch2_output]
        else:
            # Read display settings
            self.ch1_disp, self.ch1_ratio = np.array(self.instr_gpib.query('DDEF?').split(',')).astype(int)
            # Read front panel output values
            self.ch1_output = int(self.instr_gpib.query('FPOP?'))
            # Return settings
            return [self.ch1_disp, self.ch1_ratio,self.ch1_output]
            
        
    def set_offset(self, data, offset):
        '''
        Sets offsets for data

        Parameters
        ----------
        dataline : string
             Target data for offset setting, either X, Y or R
        offset : float
            Offset in percent, (-105.00 ≤ offset ≤ 105.00)

        Returns
        -------
        None.

        '''
        if data=='X':
            self.x_offset=offset
            self.instr_gpib.write('OEXP 1,'+str(offset)+','+
                                  str(self.expand_list.index(self.x_expand)))
        if data=='Y':
            self.y_offset=offset
            self.instr_gpib.write('OEXP 2,'+str(offset)+','+
                                  str(self.expand_list.index(self.y_expand)))
        if data=='R':
            self.r_offset=offset
            self.instr_gpib.write('OEXP 3,'+str(offset)+','+
                                  str(self.expand_list.index(self.r_expand)))
            
            
            
    def set_expand(self,data,expand):
        '''
        Sets expand values for data

        Parameters
        ----------
        data : string
            Target data for expand setting, either X, Y or R
        expand : int
            Possible expand values: 0,10,100
        Returns
        -------
        None.

        '''
        if data=='X':
            self.x_expand=expand
            self.instr_gpib.write('OEXP 1,'+str(self.x_offset)+','+
                                  str(self.expand_list.index(expand)))
        if data=='Y':
            self.y_expand=expand
            self.instr_gpib.write('OEXP 2,'+str(self.y_offset)+','+
                                  str(self.expand_list.index(expand)))
        if data=='R':
            self.r_expand=expand
            self.instr_gpib.write('OEXP 3,'+str(self.r_offset)+','+
                                  str(self.expand_list.index(expand)))
            
    def get_oexp(self):
        '''
        Reads current data offset and expand settings and updates attributes

        Returns
        -------
        list
            list that contains offset and expand values for X,Y and R.
            List is of the form 
            [Offset X, Expand X, Offset Y, Expand Y, Offset R, Expand R]
        '''
        # X
        oexp_data_x=self.instr_gpib.query('OEXP? 1').split(',')
        self.x_offset=float(oexp_data_x[0])
        self.x_expand=self.expand_list[int(oexp_data_x[1])]
        # Y
        oexp_data_y=self.instr_gpib.query('OEXP? 2').split(',')
        self.y_offset=float(oexp_data_y[0])
        self.y_expand=self.expand_list[int(oexp_data_y[1])]
        # R
        oexp_data_r=self.instr_gpib.query('OEXP? 3').split(',')
        self.r_offset=float(oexp_data_r[0])
        self.r_expand=self.expand_list[int(oexp_data_r[1])]
        
        return [self.x_offset, self.x_expand,
                self.y_offset, self.y_expand,
                self.r_offset, self.r_expand]
        

    def adjust_settings(self,**kwargs):
        '''
        Provides interface to change most of the lock-in amplifier settings. This function maybe slow, and thus
        usage of dedicated functions is encouraged for performance critical applications
        
        Parameters
        ----------
        **kwargs : 
            shield_ground:  Sets the input shield grounding, 'Float' or 'Ground'.
            sync:  Sets the synchronous filter status, True or False
            rmod:  Sets the reserve mode. Selects 
                            'High Reserve', 
                            'Normal' or 
                            'Low Noise'.
            notch = i : Sets the input line notch filter status. Selects 
                            Out or no filters (i=0), 
                            Line notch in (i=1), 
                            2xLine notch in (i=2) or 
                            Both notch filters in (i=3).
            input_coupling: Sets the input coupling, 'ac' or 'dc'
            input_config = i : Sets input configuration. The parameter is an integer 
                            A(i=0), A-B (i=1), I (1 MΩ) (i=2) or I (100 MΩ) (i=3).
            harm = i: Sets detection harmonic. This parameter is an integer from 1 to 19999
            ref_slope = i: Selects sine zero crossing (i=0), TTL rising edge (i=1), or TTL falling edge (i=2)
            tau:  Sets the time constant.
            slope: Sets the low pass filter slope
            phase: Sets the phase shift
            freq: Sets sine output frequency in Hz
            ampl: Sets sine output amplitude in volts
        Returns
        -------
        None.

        '''
        # Reserve mode setting
        if 'rmod' in kwargs:
            if kwargs['rmod'] not in self.reserve_mode_options:
                print('Error when setting reserve mode')
            else:
                self.rmod=self.reserve_mode_options[int(self.instr_gpib.query("RMOD?").strip())]
                self.instr_gpib.write('RMOD ',str(self.reserve_mode_options.index(self.rmod)))
        # Synchronous filter status setting
        if 'sync' in kwargs:
            self.sync=kwargs['sync']
            if self.sync:
                self.instr_gpib.write('SYNC 1')
            else:
                self.instr_gpib.write('SYNC 0')
                
        # Input configuration
        if 'input_config' in kwargs:
            self.instr_gpib.write('ISRC ',str(kwargs['input_config']))
            self.input_config=self.input_config_list[int(self.instr_gpib.query('ISRC?'))]     
            
        # Input shield grounding
        if 'shield_ground' in kwargs:
            if 'float' in kwargs['shield_ground'].lower():
                self.instr_gpib.write('IGND 0')
            elif 'ground' in kwargs['shield_ground'].lower():
                self.instr_gpib.write('IGND 1')
            else:
                print('Wrong type of input shield grounding, choose either Ground or Float')
            # Read values
            if int(self.instr_gpib.query('IGND?'))==0: 
                self.shield_gnd='Float'
            else:
                self.shield_gnd='Ground'

        # Input coupling
        if 'input_coupling' in kwargs:
            if 'ac' in kwargs['input_coupling'].lower():
                self.instr_gpib.write('ICPL 0')
            elif 'dc' in kwargs['input_coupling'].lower():
                self.instr_gpib.write('ICPL 1')
            else:
                print('Error: wrong type of input coupling, choose either DC or AC')
            # Read values
            if int(self.instr_gpib.query('ICPL?'))==0:
                self.input_coupling='AC'
            else:
                self.input_coupling='DC'
            
        # Line notch filter setting
        if 'notch' in kwargs:
            self.instr_gpib.write('ILIN ', str(kwargs['notch']))
            self.notch=int(self.instr_gpib.query('ILIN?'))
        
        # Detection harmonic
        if 'harm' in kwargs:
            self.instr_gpib.write('HARM ', str(kwargs['harm']))
            self.harm=self.instr_gpib.query('HARM?')
        
        # External reference slope
        if 'ref_slope' in kwargs: 
            self.instr_gpib.write('RSLP ', str(kwargs['ref_slope']))
            self.ref_slope=int(self.instr_gpib.query('RSLP?'))            
            
        # Time constant and slope settings       
        if 'tau' in kwargs:
            self.set_tau_slope(kwargs['tau'], self.slope)
        elif 'slope' in kwargs:
            self.set_tau_slope(self.tau, kwargs['slope'])
        else:
            # update settings with possibly changed attributes
            self.set_tau_slope(self.tau, self.slope)
        # Update display and output settings with current attributes
        self.set_display_output()
        
        # Phase shift setting
        if 'phase' in kwargs:
            self.instr_gpib.write('PHAS ', str(kwargs['phase']))
            self.phase_shift=float(self.instr_gpib.query('PHAS?')) 
            print('Phase shift set to ',str(self.phase_shift))             
        
        # Frequency and sine amplitude settings
        if 'freq' in kwargs:
            self.set_freq_ampl(kwargs['freq'],self.sine_ampl)
        elif 'ampl' in kwargs:
            self.set_freq_ampl(self.frequency , kwargs['ampl'])  
        else:
            # update frequency using current attributes
            self.set_freq_ampl(self.frequency,self.sine_ampl)
            
        
    def apply_settings(self,settingsDict):
        '''
        Provides interface to change most of the lock-in amplifier settings. This function maybe slow, and thus
        usage of dedicated functions is encouraged for performance critical applications
        
        Parameters
        ----------
        settingsDict : dict
            Dictionary containing the settings to be adjusted.
            shield_ground:  Sets the input shield grounding, 'Float' or 'Ground'.
            sync:  Sets the synchronous filter status, True or False
            rmod:  Sets the reserve mode. Selects 
                            'High Reserve', 
                            'Normal' or 
                            'Low Noise'.
            notch = i : Sets the input line notch filter status. Selects 
                            Out or no filters (i=0), 
                            Line notch in (i=1), 
                            2xLine notch in (i=2) or 
                            Both notch filters in (i=3).
            input_coupling: Sets the input coupling, 'ac' or 'dc'
            input_config = i : Sets input configuration. The parameter is an integer 
                            A(i=0), A-B (i=1), I (1 MΩ) (i=2) or I (100 MΩ) (i=3).
            harm = i: Sets detection harmonic. This parameter is an integer from 1 to 19999
            ref_slope = i: Selects sine zero crossing (i=0), TTL rising edge (i=1), or TTL falling edge (i=2)
            tau:  Sets the time constant.
            slope: Sets the low pass filter slope
            phase: Sets the phase shift
            freq: Sets sine output frequency in Hz
            ampl: Sets sine output amplitude in volts
        Returns
        -------
        None.

        '''
        # Reserve mode setting
        if 'Reserve mode' in settingsDict:
            if settingsDict['Reserve mode'] not in self.reserve_mode_options:
                print('Error when setting reserve mode')
            else:
                self.rmod=self.reserve_mode_options[int(self.instr_gpib.query("RMOD?").strip())]
                self.instr_gpib.write('RMOD ',str(self.reserve_mode_options.index(self.rmod)))
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
            self.instr_gpib.write('ISRC ',self.input_config_list.index(inpconf))
            self.input_config = self.input_config_list[int(self.instr_gpib.query('ISRC?'))]     
            
        # Input shield grounding
        if 'Input grounding' in settingsDict:
            if 'Float' in settingsDict['Input grounding']:
                self.instr_gpib.write('IGND 0')
            elif 'Ground' in settingsDict['Input grounding']:
                self.instr_gpib.write('IGND 1')
            else:
                print(f'Error: {settingsDict["Input grounding"]} is not a valid input shield grounding option, choose either Ground or Float')
            # Read values
            if int(self.instr_gpib.query('IGND?'))==0: 
                self.shield_gnd='Float'
            else:
                self.shield_gnd='Ground'

        # Input coupling
        if 'Input coupling' in settingsDict:
            if 'AC' in settingsDict['Input coupling']:
                self.instr_gpib.write('ICPL 0')
            elif 'DC' in settingsDict   ['Input coupling']:
                self.instr_gpib.write('ICPL 1')
            else:
                print(f'Error: {settingsDict["Input coupling"]} is not a valid input coupling option, choose either DC or AC')
            # Read values
            if int(self.instr_gpib.query('ICPL?'))==0:
                self.input_coupling='AC'
            else:
                self.input_coupling='DC'
            
        # Line notch filter setting
        if 'Line filter' in settingsDict:
            ntch = str(settingsDict['Line filter'])
            self.instr_gpib.write('ILIN ', self.notch_list.index(ntch))
            self.notch = int(self.instr_gpib.query('ILIN?'))
        
        # Detection harmonic
        if "Harmonic" in settingsDict:
            self.instr_gpib.write('HARM ', str(settingsDict["Harmonic"]))
            self.harm=self.instr_gpib.query('HARM?')
        
        # External reference slope
        if 'ref_slope' in settingsDict: 
            self.instr_gpib.write('RSLP ', str(settingsDict['ref_slope']))
            self.ref_slope=int(self.instr_gpib.query('RSLP?'))            
            
        # Time constant and slope settings       
        if 'Filter slope' in settingsDict:
            self.set_tau_slope(self.tau, settingsDict['Filter slope'])
        if "Time constant" in settingsDict:
            self.set_tau_slope(settingsDict["Time constant"], self.slope)
            
        # Update display and output settings with current attributes
        self.set_display_output()
        
        # Phase shift setting
        if 'Phase' in settingsDict:
            self.instr_gpib.write('PHAS ', str(settingsDict['Phase']))
            self.phase_shift=float(self.instr_gpib.query('PHAS?')) 
            print('Phase shift set to ',str(self.phase_shift))             
        
        # Frequency and sine amplitude settings
        if 'Sine frequency' in settingsDict:
            self.set_freq_ampl(settingsDict['Sine frequency'],self.sine_ampl)
        if 'Sine amplitude' in settingsDict:
            self.set_freq_ampl(self.frequency , settingsDict['Sine amplitude'])
            
        # Setting the sensitivity
        if 'Sensitivity' in settingsDict:
            self.set_sens(settingsDict['Sensitivity'])
            
        print('Device settings applied successfully')
        
        
    def read_channels(self,channels=['R']):
        '''
        Reads current output values of the lock-in amplifier

        Returns
        -------
        list
            List containing current output values of the lock-in amplifier.
            List is of the form [X,Y,R,Phase,AUX1,AUX2,AUX3,AUX4].
        '''
        out = np.ones(len(channels))*np.nan
        for chi in channels:
            '''
            Available channels:
                "X",
                "Y",
                "R",
                "Theta",
                "Aux In 1",
                "Aux In 2",
                "Aux In 3",
                "Aux In 4"
            '''
            if chi=='X':
                out[channels.index(chi)] = self.instr_gpib.query("OUTP? 1")
            elif chi=='Y':
                out[channels.index(chi)] = self.instr_gpib.query("OUTP? 2")
            elif chi=='R':
                out[channels.index(chi)] = self.instr_gpib.query("OUTP? 3")
            elif chi=='Theta': 
                out[channels.index(chi)] = self.instr_gpib.query("OUTP? 4")
            elif chi=='Aux In 1':
                out[channels.index(chi)] = self.instr_gpib.query("OAUX? 1")
            elif chi=='Aux In 2':
                out[channels.index(chi)] = self.instr_gpib.query("OAUX? 2")
            elif chi=='Aux In 3':
                out[channels.index(chi)] = self.instr_gpib.query("OAUX? 3")
            elif chi=='Aux In 4':
                out[channels.index(chi)] = self.instr_gpib.query("OAUX? 4")
            else:
                print('Error: channel not recognized')
        return out
        
    @staticmethod
    def get_sens_voltage(sens):
        '''
        Transforms sensitivity string to proper voltage
        '''
        sens=sens.strip()
        sens_volt=0
        if 'nV/fA' in sens:
            sens_volt=float(sens.strip('nV/fA'))*1e-9
        if 'uV/pA' in sens:
            sens_volt=float(sens.strip('uV/pA'))*1e-6
        if 'mV/nA' in sens:
            sens_volt=float(sens.strip('mV/nA'))*1e-3
        if 'V/uA' in sens:
            sens_volt=float(sens.strip('V/uA'))           
        return sens_volt    
    
    
    def set_sens(self, sens):
        '''
        Sets and queries the sensitivity

        Parameters
        ----------
        sens : string
            Desired sensitivity setting. Either exact setting that is wanted or alternatively
                'up' raises sensitivity one level up and 
                'down' lowers sensitivity one level down. Sensitivity options stored in
                'sens_options' attribute.
        Returns
        -------
        float
            Voltage sensitivity, unit mV

        '''
        # Check for raising/lowering commands
        if sens=='up':
            self.instr_gpib.write('SENS '+str(self.sens_options.index(self.sens)+1))
            self.sens=self.sens_options[int(self.instr_gpib.query('SENS?'))]
        elif sens=='down':
            self.instr_gpib.write('SENS '+str(self.sens_options.index(self.sens)-1))
            self.sens=self.sens_options[int(self.instr_gpib.query('SENS?'))]
        # Apply desired sensitivity setting
        else:
            try:
                self.instr_gpib.write('SENS '+str(self.sens_options.index(sens)))
                self.sens=self.sens_options[int(self.instr_gpib.query('SENS?'))]
            except Exception as e:
                print(e)
        return self.get_sens_voltage(self.sens)*1e3
    
    
    def standard_settings(self):
        '''
        Sets lock-in amplifier to default settings

        Returns
        -------
        None.

        '''
        self.set_tau_slope('100 ms' ,'18 dB/oct')
        self.adjust_settings(input_coupling = 'ac',
                                               input_config = 'A',
                                               sync = True,
                                               shield_ground = 'float',
                                               rmod = 'Normal',
                                               harm = 1,
                                               notch = 0,
                                               ref_slope = 0)
        
        self.set_display_output(CH1display=1, # Set output to R
                                CH1ratio=0, 
                                CH1output=0)
        # Set offsets to zero
        self.set_offset('R', 0)
        self.set_expand('R',0)
        self.set_offset('Y', 0)
        self.set_expand('Y',0)
        self.set_offset('X', 0)
        self.set_expand('X',0)
        print('Lock-in amplifier set to standard settings:')
        self.print_settings()
    
    def get_sens(self):
        '''
        Queries sensitivity of the lock-in amplifier and 
        updates corresponding attribute accordingly

        Returns
        -------
        float
            voltage sensitivity, unit mV

        '''
        self.sens=self.sens_options[int(self.instr_gpib.query('SENS?'))]
        return self.get_sens_voltage(self.sens)*1e3
            
    
    def read_settings(self):
        '''
        Reads current device settings and updates attributes

        Returns
        -------
        None.

        '''
        self.get_sens()
        self.get_freq_ampl()
        self.get_tau_slope()
        self.get_ref_source()
        self.get_display_output()
        self.get_oexp()
        
        # Additional settings to read
        # Reserve mode
        self.rmod=self.reserve_mode_options[int(self.instr_gpib.query("RMOD?").strip())]
        # Sync filter
        self.sync=bool(self.instr_gpib.query('SYNC?'))
        # Input configuration
        self.input_config=self.input_config_list[int(self.instr_gpib.query('ISRC?'))]
        # Input shield grounding
        if int(self.instr_gpib.query('IGND?'))==0: 
            self.shield_gnd='Float'
        else:
            self.shield_gnd='Ground'
        # Input coupling
        if int(self.instr_gpib.query('ICPL?'))==0:
            self.input_coupling='AC'
        else:
            self.input_coupling='DC'
            
        # Notch filter
        self.notch=int(self.instr_gpib.query('ILIN?'))
        # Detection harmonic
        self.harm=int(self.instr_gpib.query('HARM?'))
        # External reference slope
        self.ref_slope=int(self.instr_gpib.query('RSLP?'))  
        # phase shift
        self.phase_shift=float(self.instr_gpib.query('PHAS?')) 
        
       

    def print_settings(self):
        '''
        Prints current state of the lock-in amplifier

        Returns
        -------
        None.

        '''
        self.read_settings()
        print('===========================================================')
        print('Device information')
        print('===========================================================')
        print('Device type: Lock-in amplifier')
        print('Device ID:',self.instr_id)
        print('===========================================================')
        print('General settings:')
        if self.internal:
            print('Reference source: Internal')
        else:
            print('Reference source: External')
        print('External reference slope: ',self.ref_slope_list[int(self.ref_slope)])
        print('Lock-in frequency: ',self.frequency,' Hz')
        print('Sine output amplitude: ',self.sine_ampl,' V')
        print('Sensitivity: ',self.sens)
        
        print('Phase shift: ',str(self.phase_shift)) 
        
        print('Time constant: ',self.tau)
        print('Slope: ',self.slope)
        print('Reserve mode: ',self.rmod)
        print('Detection harmonic: ', self.harm)
        if self.sync:
            print('Synchronous filter enabled')
        else:
            print('Synchronous filter disabled')
        print('Input configuration: ',self.input_config)
        print('Input shield grounding: ',self.shield_gnd)
        print('Input coupling: ',self.input_coupling)
        print('Line Notch Filter: ', self.notch_list[int(self.instr_gpib.query('ILIN?'))])
        
        print('===========================')
        print('Offset and expand settings:')
        print('X offset: ',self.x_offset,' %')
        print('Y offset: ',self.y_offset,' %')
        print('R offset: ',self.r_offset,' %')
        print('X expand: ',self.x_expand)
        print('Y expand: ',self.y_expand)
        print('R expand: ',self.r_expand)
        print('===========================')
        print('Display and output options:')
        
        # Print display and output settings
        if 'SR830' in self.instr_id:
            print('Channel 1 display: ',self.disp1_list[self.ch1_disp])
            print('Channel 2 display: ',self.sr830_disp2_list[self.ch2_disp])
            print('Channel 1 ratio: ',self.disp1_ratio_list[self.ch1_ratio])
            print('Channel 2 ratio: ',self.sr830_disp2_ratio_list[self.ch2_ratio])
            if self.ch1_output==0:
                print('Channel 1 output: display')
            else:
                print('Channel 1 output: X')
            if self.ch2_output==0:
                print('Channel 2 output: display')
            else:
                print('Channel 2 output: Y')
        else:
            print('Channel 1 display: ',self.disp1_list[self.ch1_disp])
            print('Channel 1 ratio: ',self.disp1_ratio_list[self.ch1_ratio])
            if self.ch1_output==0:
                print('Channel 1 output: display')
            else:
                print('Channel 1 output: X')
        print('===========================')




        
    def load_settings(self,settingsfile):
        # open YAML file containing lock in amplifier settings
        with open(settingsfile,'r') as file:
            # Load setting dictionary from YAML file
            settings_dict = yaml.load(file, Loader=yaml.FullLoader)
        
        self.set_ref_source(settings_dict['Reference source'].lower())
        self.set_tau_slope(settings_dict['Time constant'],settings_dict['Slope'])

    def createSettingsDict(self):
        '''
        Function to generate settings dictionary

        Returns
        -------
        None.

        '''
        if 'SR830' in self.instr_id:
            self.settingsDict['Device'] = 'Standford Research Systems SR830 lock-in amplifier'
        elif 'SR810' in self.instr_id:
            self.settingsDict['Device'] = 'Standford Research Systems SR810 lock-in amplifier'
        self.settingsDict['Timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.internal:
            self.settingsDict['Reference source'] = 'Internal'
        else:
            self.settingsDict['Reference source'] = 'External'
        self.settingsDict['External reference slope'] = str(self.ref_slope)
        self.settingsDict['Lock-in frequency'] = str(self.frequency)
        self.settingsDict['Sine output amplitude'] = str(self.sine_ampl)
        self.settingsDict['Sensitivity'] = str(self.sens)
        
        self.settingsDict['Phase shift'] = str(self.phase_shift)
        
        self.settingsDict['Time constant'] = str(self.tau)
        self.settingsDict['Slope'] = str(self.slope)
        self.settingsDict['Reserve mode'] = str(self.rmod)
        self.settingsDict['Detection harmonic'] = str(self.harm)
        if self.sync:
            self.settingsDict['Synchronous filter'] = 'Enabled'
        else:
            self.settingsDict['Synchronous filter'] = 'Disabled'
        self.settingsDict['Input configuration'] = str(self.input_config)
        self.settingsDict['Input shield grounding'] = str(self.shield_gnd)
        self.settingsDict['Input coupling'] = str(self.input_coupling)
        self.settingsDict['Line Notch Filter'] = self.notch_list[self.notch]
            
        # offset and expand settings    
        self.oexp_dict['X offset'] = str(self.x_offset) + ' % '
        self.oexp_dict['Y offset'] = str(self.y_offset) + ' % '
        self.oexp_dict['R offset'] = str(self.r_offset) + ' % '
        self.oexp_dict['X expand'] = str(self.x_expand)
        self.oexp_dict['Y expand'] = str(self.y_expand)
        self.oexp_dict['R expand'] = str(self.r_expand)

        self.settingsDict['Offset and expand settings'] = self.oexp_dict     
        
        # Display and output settings          
        if 'SR830' in self.instr_id:
            self.disp_dict['Channel 1 display'] = self.disp1_list[self.ch1_disp]
            self.disp_dict['Channel 2 display'] = self.sr830_disp2_list[self.ch2_disp]
            self.disp_dict['Channel 1 ratio'] = self.disp1_ratio_list[self.ch1_ratio]
            self.disp_dict['Channel 2 ratio'] = self.sr830_disp2_ratio_list[self.ch2_ratio]
            if self.ch1_output==0:
                self.disp_dict['Channel 1 output'] = 'display'
            else:
                self.disp_dict['Channel 1 output'] = 'X'
            if self.ch2_output==0:
                self.disp_dict['Channel 2 output'] = 'display'
            else:
                self.disp_dict['Channel 2 output'] = 'Y'
        else:
            self.disp_dict['Channel 1 display'] = self.disp1_list[self.ch1_disp]
            self.disp_dict['Channel 1 ratio'] = self.disp1_ratio_list[self.ch1_ratio]
            if self.ch1_output==0:
                self.disp_dict['Channel 1 output'] = 'display'
            else:
                self.disp_dict['Channel 1 output'] = 'X'

        self.settingsDict['Display and output options'] = self.disp_dict
        
        
    def export_settings(self,settingsfile):
        '''
        Function that exports current settings to YAML file

        Parameters
        ----------
        settingsfile : string
        
            file where settings are written

        Returns
        -------
        None.

        '''
        self.read_settings()
        self.createSettingsDict()
        with open(settingsfile, 'w') as sfile:
            documents = yaml.dump(self.settingsDict, sfile)
                
    def auto_adjust(self, adj_type):
        '''
        Performs automatic adjustment depending on  adjustment type. 

        Parameters
        ----------
        adj_type : string
            'gain', performs Auto Gain function
            'phase', performs Auto Phase function
            'reserve', performs Auto Reserve function
        Returns
        -------
        None.

        '''
        timeout=5
        if adj_type=='gain':
            self.instr_gpib.write('AGAN')
            print(self.instr_gpib.query('*STB? 1').strip())
            t1=time.perf_counter()
            while int(self.instr_gpib.query('*STB? 1').strip()) != 0:
                      time.sleep(0.1)
                      if abs(time.perf_counter()-t1)>timeout:
                          print('Autogain error: timeout')
                          break
            self.sens=self.sens_options[int(self.instr_gpib.query('SENS?'))]
        if adj_type=='phase':
            self.instr_gpib.write('APHS')
        if adj_type=='reserve':
            self.instr_gpib.write('ARSV')

    def continuous_Nread(self,stop_event,starttime,q,settings):
        '''
        Function to read continuously data from SR830. Data is read every time 
        until stop_event is set.
        '''
        t0 = starttime
        Nsamples = settings['Number of samples']
        channels = settings['Channels']
        print(f'SR830 data acquisition started with {Nsamples} samples from channels {channels}')
        logging.info(f'Starting SR830 data acquisition with {Nsamples} samples from channels {channels}')
        out = np.zeros((len(channels), Nsamples))*np.nan
        time_arr = np.zeros(Nsamples)*np.nan
        try:
            while not stop_event.is_set():
                # Collect samples in a loop
                for i in range(Nsamples):
                    # Read the values from the SR830
                    try:
                        values = self.read_channels(channels)
                        out[:,i] = values
                        time_arr[i] = perf_counter()-t0
                    except:
                        continue        
                # Put values to queue
                q.put(np.vstack((time_arr, out)))
        finally:
            logging.info('Stopping SR830 data acquisition')

    def triggered_Nread(self,stop_event,starttime,q,settings,trigger,barrier):
        '''
        Function to read continuously data from SR830 when trigger is applied. 
        Data is read every time for trigger event until stop_event is set.
        '''
        t0 = starttime
        Nsamples = settings['Number of samples']
        channels = settings['Channels']
        print(f'SR830 data acquisition started with {Nsamples} samples from channels {channels}')
        logging.info(f'Starting SR830 data acquisition with {Nsamples} samples from channels {channels}')
        out = np.zeros((len(channels), Nsamples))*np.nan
        time_arr = np.zeros(Nsamples)*np.nan
        try:
            while not stop_event.is_set():
                # wait for the trigger
                trigger.wait()
                # Collect samples in a loop
                for i in range(Nsamples):
                    # Read the values from the SR830
                    try:
                        values = self.read_channels(channels)
                        out[:,i] = values
                        time_arr[i] = perf_counter()-t0
                    except:
                        continue   
                # Put values to queue
                q.put(np.vstack((time_arr, out)))
                # Indicate that data acquisition finished to barrier
                barrier.wait()
        finally:
            logging.info('Stopping SR830 data acquisition')
            
            
            
            