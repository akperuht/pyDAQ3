# -*- coding: utf-8 -*-
"""
Python module for instrument control

Currently consists of:
- class for digital control of "pynskäbox"
- Helper function visa_resources that lists all available VISA resources
- class SR810_30_lockin for SR810/SR830 lock-in amplifier control with pyVISA
- wrapper to keithley 2450 source meter via pymeasure.instruments module
- class PN300 for controlling Digimess PN300 programmable power supply
- class to control Anritsu 68367C synthesized signal generator


@author: Aki Ruhtinas, aki.ruhtinas@gmail.com
"""
import numpy as np
import pyvisa as visa
import nidaqmx
import time
import re
import datetime
from nidaqmx.stream_writers import DigitalSingleChannelWriter
from pymeasure.instruments.keithley import Keithley2450
from pymeasure.instruments.keithley import Keithley6221
from pymeasure.instruments.srs import SR860
import yaml
import warnings

def visa_resources():
    '''
    Helper function to list all available VISA resources

    Returns
    -------
    res_list : string
        List of available resource names
    '''
    res_m=visa.ResourceManager()
    print('=======================================')
    print('Available resources:')
    res_list=res_m.list_resources()
    for ri in res_list:
        print(ri)
    print('=======================================')
    return res_list

'''
=========================================================================================================================
        Pynskäbox
=========================================================================================================================
'''

class pynskabox():
    '''
    Class for controlling pynskäbox outputs
    Corresponds to following wiring:
        DIO 0 -> LOADREG pin
        DIO 1 -> RESET pin
        DIO 2 -> SDI (Serial data in) pin
        DIO 3 -> CLOCK pin
        
    Pynskäbox contains two DAC7615 cards, and outputs can be programmed using timing chart
    reported in manual. NOTE: this class is constructed for pynskäbox where input bits need to be inverted
    when compared to manual.

    For different control bits change get_control_bits() function
    
    '''
    def __init__(self):
        '''
        Creates new pynskabox resource
        '''
        self.portname='Dev1/port0'
        # Digital write delays in seconds
        self.res_delay=0
        self.loadreg_delay=0
        self.data_delay=0
        self.clk_HIGH_delay=0
        self.clk_LOW_delay=0
        # Initialize communication array to FALSE
        self.msg=np.array([False,False,False,False,False,False,False,False])
                    
    def scan(self,port,step_delay, array):
        '''
        

        Parameters
        ----------
        port : int
            Port which output is scanned
        step_delay : float
            time delay for each step
        array : array (int)
            points to scan
        Returns
        -------
        None.

        '''
        for step_i in array:
            # Change pynska output
            self.write_dac(port,step_i)
            # delay for each iteration
            time.sleep(step_delay)
            
    def reset(self):
        '''
        Hard reset of all pynskäbox outputs
        Writes HIGH to RES pin
        '''
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(self.portname)
            writer=DigitalSingleChannelWriter(task.out_stream)
            
            writer.write_one_sample_multi_line(np.array([False,True,False,False,False,False,False,False]))
            time.sleep(self.res_delay)
            writer.write_one_sample_multi_line(np.array([False,False,False,False,False,False,False,False]))
            
    def write_dac(self,output,value):
        '''
        Writes value to desired output.
        Takes ~9ms to complete, limited by nidaqmx library. Settling time for pynskäbox voltage output 
        to be below 1 mV for full scale (0,4095) step is 1.5 ms, and thus any settling time above this value is good.
        
        
        NOTE: Each nidaqmx write takes approximately 200-500 us to finish, and thus here is no
        extra time delay between write commands. If this full-speed write does not work,
        it may be usefull to set time delays larger than 0
        
        Parameters
        ----------
        output : int or str
            Output where value is written
        value : int
            12bit value between 0 and 4095 corresponding to a desired voltage output
        Returns
        -------
        None.
        '''
        # Ensure that communication array is in default state
        self.msg=np.array([False for xi in range(0,8)])
        # Create boolean array from 12 bit voltage value and append control bits
        data_in=[bool(value & (1<<n)) for n in range(12)]
        # Get control bits of the desired output and add bits to data array
        control_arr=self.get_control_bits(output)
        for i in range(0,4):
            data_in.append(control_arr[3-i])
        data_in.reverse()
        data_in=np.array(data_in)
        # Load data to DAC 
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(self.portname)
            writer=DigitalSingleChannelWriter(task.out_stream)
            # load data array to DAC via SDI pin
            for d in data_in:
                # Put CLK to HIGH and update
                self.msg[3]=True
                writer.write_one_sample_multi_line(self.msg)
                # Wait for the data delay
                time.sleep(self.data_delay)
                # Put data value to SDI pin
                self.msg[2]=d
                # update changes
                writer.write_one_sample_multi_line(self.msg)
                # Wait for clock, data_delay+clk_delay > 50ns
                #time.sleep(self.clk_HIGH_delay)
                # Put CLK to LOW and update values to register
                self.msg[3]=False
                writer.write_one_sample_multi_line(self.msg)
                # Wait for clock, clock LOW time min. 30 ns
                #time.sleep(self.clk_LOW_delay)
            # Put LOADREG to HIGH and update
            self.msg[0]=True
            writer.write_one_sample_multi_line(self.msg)
            # Wait for LOADREG (min. 45 ns)
            #time.sleep(self.loadreg_delay)
            #Put LOADREG back to LOW
            self.msg[0]=False
            writer.write_one_sample_multi_line(self.msg)
            
            
    def set_voltage(self,output,voltage):
        '''
        Function that directly sets given voltage to DAC output

        Parameters
        ----------
        output : int or str
            Output where voltage is set
        voltage : float
            Voltage value that is set to the given output type
        Returns
        -------
        None.

        '''
        self.write_dac(output,self.voltage_to_int(voltage))
        
            
    @staticmethod        
    def voltage_to_int(V,Vmin=-1,Vmax=1,nsteps=4095):
        '''
        Function to calculate integer value of the given voltage

        Parameters
        ----------
        V : float
            Voltage value, unit V.
        Vmin : float, optional
            Minimum voltage allowed. The default is -1.
        Vmax : float, optional
            Maximum voltage allowed. The default is 1.
        nsteps : int, optional
            ADC resolution. The default is 4096.

        Returns
        -------
        TYPE
            DESCRIPTION.

        '''
        # Calculate corresponding value on a given scale and round up to nearest integer
        ilist=np.rint((V-Vmin)/(abs(Vmax-Vmin))*nsteps)
        # Convert to integer list and limit to allowed values
        return np.clip([int(xi) for xi in ilist], 0, nsteps)
    
    
    
    @staticmethod    
    def get_control_bits(output):
        '''
        Returns control bits for desired output

        Parameters
        ----------
        output : int or string
            Index or name of the desired output, as presented below:
                
                Index    OUTPUT           A1 A0 S1 S0    
                ==========================================
                0   |  DAC1          |   0  1  1  0     |
                ==========================================
                1   |  DAC2          |   0  0  1  0     |
                ==========================================
                2   |  RF1 offset    |   1  1  1  0     |
                ==========================================
                3   |  RF2 offset    |   1  0  1  0     |
                ==========================================
                4   |  RF1 GAIN      |   1  1  1  1     |
                ==========================================
                5   |  RF2 GAIN      |   1  0  1  1     |
                ==========================================
                6   |  RF1 CROSSGAIN |   0  0  1  1     |
                ==========================================
                7   |  RF2 CROSSGAIN |   0  1  1  1     |
                ==========================================

        Returns
        -------
        list
            boolean list of corresponding control bits

        '''
        
        if output==0 or output=='DAC 1':
            return [False,True,True,False]
        if output==1 or output=='DAC 2':
            return [False,False,True,False]
        if output==2 or output=='RF1 OFFSET':
            return [True,True,True,False]
        if output==3 or output=='RF2 OFFSET':
            return [True,False,True,False]
        if output==4 or output=='RF1 GAIN':
            return [True,True,True,True]
        if output==5 or output=='RF2 GAIN':
            return [True,False,True,True]
        if output==7 or output=='RF1 CROSSGAIN':
            return [False,False,True,True]
        if output==8 or output=='RF2 CROSSGAIN':
            return [False,True,True,True]



'''
=========================================================================================================================
 Stanford Research Systems lock-in amplifier models SR810 and SR830
=========================================================================================================================
'''

class SR810_30_lockin():
    '''
    Class for controlling Stanford Research Systems lock-in amplifier models SR810 and SR830
    '''
    
    def __init__(self,gpib_id, instr_number):
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

        self.filter_slope_options=['6 dB/oct','12 dB/oct','18 dB/oct','24 dB/oct']
        
        self.expand_list=[0,10,100]
        
        self.disp1_list=['X','R','X Noise','Aux In 1','Aux In 2']
        self.sr830_disp2_list=['Y','Phase','Y Noise','Aux In 3','Aux In 4']
        self.disp1_ratio_list=['None','Aux In 1','Aux In 2']
        self.sr830_disp2_ratio_list=['None','Aux In 3','Aux In 4']
        
        self.input_config_list=['A','A-B','I(1 Mohm)','I(100 Mohm)']
        
        self.notch_list=['Out','Line In', '2x Line in','Both In']
        
        self.ref_slope_list=['Sine','TTL Rising','TTL Falling']
        
        self.phase_shift=0
        
        self.instr_num=instr_number
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Lock-in amplifier online. device ID:',self.instr_id)
        
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
        print('================================================================')
        print('Lock-in amplifier ',str(self.instr_num),':')
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
        
        
    def set_tau_slope(self, tau,slope):
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
            
            
            
            
            
'''
=========================================================================================================================
                Keithley 2450 source meter
=========================================================================================================================
'''
            
class Keithley_2450(Keithley2450):
    '''
    Class to control Keithley 2450 source meter via GPIB. 
    Inherits class pymeasure.instruments.keithley.Keithley2450,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/keithley2450.html
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new Keithley_2450 class that inherits class Keithley2450 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        # Strip unnecessary '::INSTR' from the GPIB id
        # This is required by Keithley2450 class
        gpib_id = re.sub('\::INSTR$', '', gpib_id)
        # Inherit class Keithley2450
        Keithley2450.__init__(self,gpib_id)

    def init_sourceI_sensV_4(self,vlim):
        '''

        Parameters
        ----------
        vlim : float
            Voltage limit, max 210 V

        Returns
        -------
        None.

        '''
        # Check that voltage limit is within accepted range
        if abs(vlim)>210:
            vlim=210
        # Reset the device
        self.write('*RST')
        # Set to measure voltage
        self.write(r'SENS:FUNC "VOLT"')
        # Set to use 4-wire sens mode
        self.write('SENS:VOLT:RSEN ON')
        # Set voltage sensing to auto range
        self.write('SENS:VOLT:RANG:AUTO ON')
        # Source current
        self.write('SOUR:FUNC CURR')
        self.write('SOUR:VOLT:READ:BACK')
        # Set voltage limit
        self.write('SOUR:CURR:VLIM ' + str(vlim))
        # Turn output on
        self.enable_source() 
        print('SOURCE ENABLED')    
        
    def init_4wire_Resistance(self,Isource):
        '''

        Parameters
        ----------
        Isource : float
            Source current

        Returns
        -------
        None.

        '''
        # Reset the device
        self.write('*RST')
        # Set to source current
        self.write('SOUR:FUNC CURR')
        # Set source current value
        set_msg = 'SOUR:CURR ' +str(Isource)
        self.write(set_msg)   
        # Set voltage limit
        self.write('SOUR:CURR:VLIM 10')      
        # Set to use 4-wire sense mode
        self.write('SENS:VOLT:RSEN ON')
        # Set to measure voltage
        self.write(r'SENS:FUNC "VOLT"')
        # Set automatic voltage range
        self.write('SENS:VOLT:RANG:AUTO ON')
        # Set the instrument to measure resistance.
        self.write('SENSE:VOLT:UNIT OHM')
        
        # Turn output on
        self.enable_source() 
        print('SOURCE ENABLED') 

    def init_4wire_VoltageMeas(self,Isource):
        '''

        Parameters
        ----------
        Isource : float
            Source current

        Returns
        -------
        None.

        '''
        # Reset the device
        self.write('*RST')
        # Set to source current
        self.write('SOUR:FUNC CURR')
        # Set source current value
        set_msg = 'SOUR:CURR ' +str(Isource)
        self.write(set_msg)   
        # Set voltage limit
        self.write('SOUR:CURR:VLIM 10')      
        # Set to use 4-wire sense mode
        self.write('SENS:VOLT:RSEN ON')
        # Set to measure voltage
        self.write(r'SENS:FUNC "VOLT"')
        # Set automatic voltage range
        self.write('SENS:VOLT:RANG:AUTO ON')
        
        # Turn output on
        self.enable_source() 
        print('SOURCE ENABLED') 
        
        
    def init_Hall_meas(self):
        '''
        Function to initialize 4-wire Hall sensor measurements with 100 mA bias current

        Returns
        -------
        None.

        '''
        self.init_4wire_VoltageMeas(0.1)
        
      
    def init_current_sourcing(self,vlim):
        '''
        Helper function to initialize current sourcing

        Parameters
        ----------
        vlim : float
            Voltage limit, max 210 V

        Returns
        -------
        None.

        '''
        # Check that voltage limit is within accepted range
        if abs(vlim)>210:
            vlim=210
        # Reset the device
        self.write('*RST')
        # Setup current measurement
        self.measure_current()
        # Set current sensing to auto range
        self.write('SENS:CURR:RANG:AUTO ON')
        # Source current
        self.write('SOUR:FUNC CURR')
        # Set voltage limit
        self.write('SOUR:CURR:VLIM ' + str(vlim))
        # Turn output on
        self.enable_source() 
        print('SOURCE ENABLED')
        
'''
=========================================================================================================================
                Keithley 6221 AC and DC Current Source
=========================================================================================================================
'''
            
class Keithley_6221(Keithley6221):
    '''
    Class to control Keithley 6221 AC and DC Current Source via GPIB. 
    Inherits class pymeasure.instruments.keithley.Keithley6221,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/keithley2450.html
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new Keithley_6221 class that inherits class Keithley6221 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        # Strip unnecessary '::INSTR' from the GPIB id
        # This is required by Keithley2450 class
        gpib_id = re.sub('\::INSTR$', '', gpib_id)
        # Inherit class Keithley2450
        Keithley6221.__init__(self,gpib_id)

    def init_triax_current(self,curr,vlim):
        '''
        Function to initialize current sourcing

        Parameters
        ----------
        curr : float
            current value
        vlim : float
            compliance of current source in volts

        Returns
        -------
        None.

        '''
        if self.source_enabled:       
            # Turn output off to change settings
            self.disable_source()
        self.output_low_grounded = True
        self.source_compliance = vlim
        self.source_current = curr
        self.enable_source() 
        print('SOURCE ENABLED')

       
'''
=========================================================================================================================
                Keithley 2461 source meter
=========================================================================================================================
'''
            
class Keithley_2461():
    '''
    Class to control Keithley 2450 source meter via GPIB. 
    Inherits class pymeasure.instruments.keithley.Keithley2450,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/keithley2450.html
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new Keithley_2450 class that inherits class Keithley2450 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        
      
    def init_current_sourcing(self,vlim):
        '''
        Helper function to initialize current sourcing

        Parameters
        ----------
        vlim : float
            Voltage limit, max 210 V
        ilim : float
            Current limit
        Returns
        -------
        None.

        '''
        # Check that voltage limit is within accepted range
        if abs(vlim)>210:
            vlim=210
        # Reset the device
        self.instr_gpib.write('*RST')
        
        #self.instr_gpib.write('TRAC:MAKE "measBuffer", 10000')    
    
        # Set instrument to current sourcing
        self.instr_gpib.write('SOUR:FUNC CURR')
        # Set measure to currents
        self.instr_gpib.write('SENS:FUNC "CURR"')
        # Set number of measurements to 100
        self.instr_gpib.write(':COUNT 1')
        # Turning source read back on
        # Using source readback results in more accurate measurements, but also a reduction in measurement speed. 
        # When source readback is on, the front-panel display shows the measured source
        self.instr_gpib.write('SOUR:CURR:READ:BACK ON')
        # Setting voltage limit
        self.instr_gpib.write('SOUR:CURR:VLIM ' + str(vlim))
        # Initialize current to zero
        self.instr_gpib.write('SOUR:CURR 0')
        #Turn the output on
        self.instr_gpib.write('OUTP ON')
        print('SOURCE ENABLED')
        
    def set_current(self,curr):
        '''
        Function to set the source current

        Parameters
        ----------
        curr : float
            Source current, unit A
        Returns
        -------
        None.

        '''
        self.instr_gpib.write(f'SOUR:CURR {curr}')
        
    def measure(self):
        '''
        Function to read measured value

        Returns
        -------
        val : float
            Measured value

        '''
        val = self.instr_gpib.query_ascii_values('READ?')
        #self.instr_gpib.write('FORM:ASC:PREC 10')
        #self.instr_gpib.write('READ? "measBuffer"')
        #val = self.instr_gpib.query_ascii_values('TRAC:DATA? 1, 10, "measBuffer",SOUR')
        return val
        
'''
=========================================================================================================================
                Keithley 6221 AC and DC Current Source
=========================================================================================================================
'''
            
class Keithley_6221(Keithley6221):
    '''
    Class to control Keithley 6221 AC and DC Current Source via GPIB. 
    Inherits class pymeasure.instruments.keithley.Keithley6221,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/keithley2450.html
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new Keithley_6221 class that inherits class Keithley6221 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        # Strip unnecessary '::INSTR' from the GPIB id
        # This is required by Keithley2450 class
        gpib_id = re.sub('\::INSTR$', '', gpib_id)
        # Inherit class Keithley2450
        Keithley6221.__init__(self,gpib_id)

    def init_triax_current(self,curr,vlim):
        '''
        Function to initialize current sourcing

        Parameters
        ----------
        curr : float
            current value
        vlim : float
            compliance of current source in volts

        Returns
        -------
        None.

        '''
        if self.source_enabled:       
            # Turn output off to change settings
            self.disable_source()
        self.output_low_grounded = True
        self.source_compliance = vlim
        self.source_current = curr
        self.enable_source() 
        print('SOURCE ENABLED')

         

'''
=========================================================================================================================
                Digimess PN300
=========================================================================================================================
'''
class PN300():
    '''
    Class to control Digimess PN300 programmable power supply via GPIB. 
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new PN300 class

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        # Strip unnecessary '::INSTR' from the GPIB id
        # This is required by Keithley2450 class
        self.gpib_id = re.sub('\::INSTR$', '', gpib_id)
        self.instr_num=instr_number
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('PN300 power supply online. device ID:',self.instr_id)
        
        # Attributes
        # Which source is selected
        self.source = ''
        # Whether source is current sourcing (CC) or voltage sourcing (CV)
        self.source_type = ''
        # Operation mode of the source
        self.oper_mode = ''
        
        self.voltage = 0
        self.current = 0
        self.setV = 0
        self.setI = 0
        
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
 
    def reset(self):
        '''
        Method for resetting the power supply

        Returns
        -------
        None.

        '''
        self.write('*RST')    

    def set_source(self,source):
        '''
        Method for selecting active source

        Parameters
        ----------
        source : string
            String describing what source to activate:
            'A' for source A and 'B' for source B

        Returns
        -------
        None.

        '''
        if source == 'A':
            self.write('SEL_A')
        elif source == 'B':
            self.write('SEL_B')
        else:
            print('ERROR: Unknown source')
            
    def get_source(self):
        '''
        Method for detecting which source is active

        Returns
        -------
        None.

        '''
        response  = self.query('SEL?')
        
        if 'SEL_A' in response:
            self.source = 'A'
            print('Source A selected')
        elif 'SEL_B' in response:
            self.source = 'B'
            print('Source B selected')
        else:
            print('ERROR')
        
    def enable_output(self):
        '''
        Method for setting output on

        Returns
        -------
        None.

        '''
        self.write('OUT_ON')
        state = self.query('OUT?')
        if 'OUT_ON' in state:
            print('OUTPUT ON')
        else:
            print('ERROR: output not enabled')
  

    def disable_output(self):
        '''
        Method for setting output off

        Returns
        -------
        None.

        '''
        self.write('OUT_OFF')
        state = self.query('OUT?')
        if 'OUT_OFF' in state:
            print('OUTPUT OFF')
        else:
            print('ERROR: output not enabled')
            
    def set_operating_mode(self, mode):
        '''
        Method for setting operating mode for outputs A and B

        Parameters
        ----------
        mode : string
            Independent (or ind) - setting of the operating mode INDEPEND (Independent Mode) 
            Tracking (or trac) - setting of the operating mode A-B TRAC (Tracking Mode) 
            Parallel (or par) - setting of the operating mode A-B PAR (Parallel Mode) 

        Returns
        -------
        None.

        '''
        modes_dict = {'independent':'OPER_IND',
                       'ind': 'OPER_IND',
                       'tracking':'OPER_TRAC',
                       'trac':'OPER_TRAC',
                       'parallel':'OPER_PAR',
                       'par':'OPER_PAR',
                       }
        self.write(modes_dict[mode.lower()])
        self.get_operating_mode()
            
        
    def get_operating_mode(self):
        '''
        Method for quering operating mode of the power supply

        Returns
        -------
        None.

        '''
        response = self.query('OPER?')   
        if 'IND' in response:
            print('Operation mode set to independent')
            self.mode = 'independent'
        elif 'TRAC' in response:
            print('Operation mode set to tracking')
            self.mode = 'tracking'
        elif 'PAR' in response:
            print('Operation mode set to parallel')
            self.mode = 'parallel'
        else:
            print('ERROR')   
        
    
    def current_sourcing(self):
        '''
        Set the source working off as a constant current source 

        Returns
        -------
        None.

        '''
        self.write('CONT_CC')   
        self.get_source_type()
                   
    def voltage_sourcing(self):
        '''
        Set the source working off as a constant voltage source 

        Returns
        -------
        None.

        '''
        self.write('CONT_CV')
        self.get_source_type()
                   
    def get_source_type(self):
        '''
        Function to get sourcing type and change class attributes accordingly

        Returns
        -------
        None.

        '''
        st = self.query('CONT?') 
        if 'CC' in st:
            self.source_type  ='CC'
            print('Power supply is working off as a constant current source')
        elif 'CV' in st:
            self.source_type  ='CV'
            print('Power supply is working off as a constant voltage source')    
        else:
            print('ERROR')
            
    def set_voltage(self,value,**kwargs):
        '''   
        Method for setting voltage of the source

        Parameters
        ----------
        value :float
            set voltage in volts
        Returns
        -------
        None.

        '''
        printallowed = True
        if 'printing' in kwargs:
            printallowed = kwargs['printing']
        msg = 'VSET ' + str(value)
        self.write(msg)
        if printallowed:
            self.values()
        
    def set_current(self,value,**kwargs):
        '''           
        Method for setting current of the source
        
        Parameters
        ----------
        value : float
            Current setting in amperes
            a) from Ø.ØØ1 to 2.3ØØ for the operating mode INDEPEND and A-B TRAC
            b) from Ø.3ØØ to 4.6ØØ for the operating mode A-B PAR.

        Returns
        -------
        None.

        '''
        printallowed = True
        if 'printing' in kwargs:
            printallowed = kwargs['printing']
        msg = 'ISET ' + str(value)
        self.write(msg)   
        if printallowed:
            self.values()
        
    def values(self):
        '''
        Method for extracting values of the setpoints

        Returns
        -------
        None.

        '''
        self.setV = float(self.query('VSET?')[2:-1])
        self.setI = float(self.query('ISET?')[2:-1])
        self.meas_voltage()
        self.meas_current()
        
        if self.setV >=1: 
            print('Voltage setpoint: '+str(self.setV) + ' V')
        else:
            print('Voltage setpoint: '+str(self.setV*1e3) + ' mV')
        if self.voltage >=1: 
            print('Measured voltage: '+str(self.voltage) + ' V')
        else:
            print('Measured voltage: '+str(self.voltage*1e3) + ' mV')
        if self.setI >=1: 
            print('Current setpoint: '+str(self.setI) + ' A')
        else:
            print('Current setpoint: '+str(self.setI*1e3) + ' mA')
        if self.voltage >=1: 
            print('Measured current: '+str(self.current) + ' V')
        else:
            print('Measured current: '+str(self.current*1e3) + ' mA')
        
    def meas_voltage(self):
        '''
        Measures voltage in volts and updates attributes

        Returns
        -------
        V : float
            voltage of the source, unit volt

        '''
        meas = self.query('VOUT?')
        V = float(meas[2:-1])
        self.voltage = V
        return V
        
    def meas_current(self):
        '''
        Measures current in amperes and updates attributes

        Returns
        -------
        I : float
            current of the source, unit ampere

        '''
        meas = self.query('IOUT?')
        I = float(meas[2:-1])
        self.current = I
        return I
    
    
    def set_protection(self,prtype):
        '''
        Method for selecting what protection setting to use

        Parameters
        ----------
        prtype : string
            'lim' - setting of the protective function LIMITING
            'cut' - setting of the protective function CUT-OUT

        Returns
        -------
        None.

        '''
        
        prot_dict = {'lim': 'PROT_LIM', 'cut': 'PROT_CUT'}
        # Set the protection type
        self.write(prot_dict[prtype].lower())
                
        
    def get_protection(self):
        '''
        Get protection mode of the instrument

        Returns
        -------
        None.

        '''
        response = self.query('PROT?')
        if 'LIM' in response:
            print('Protection: LIMITING')
        elif 'CUT' in response:
            print('Protection: CUT-OUT')
        else:
            print('ERROR')

        
        
    def init_current_sourcing(self, curr,vlim,source):
        '''
        Method to initiate current sourcing for a given source.
        Works in independent mode, protection is

        Parameters
        ----------
        curr : float
            Source current
        vlim : float
            voltage limit
        source : string
            source ('A' or 'B')

        Returns
        -------
        None.

        '''
        self.set_source(source)
        self.set_protection('lim')
        self.set_operating_mode('ind')
        self.current_sourcing()
        self.set_voltage(vlim)
        self.set_current(curr)
        self.enable_output()
  



'''
=========================================================================================================================
                Picowatt AVS-47
=========================================================================================================================
'''
class AVS47():
    '''
    Class to control Picowatt AVS-47 Resistance bridge via GPIB
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new AVS47 class

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.gpib_id = re.sub('::INSTR$', '', gpib_id)
        self.instr_num = instr_number
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




'''
=========================================================================================================================
                ANRITSU 68367C
=========================================================================================================================
'''
class Anritsu68367C():
    '''
    Class to control ANRITSU 68367C Synthesized Signal Generator via GPIB. 
    '''
    def __init__(self,gpib_id, instr_number):
        '''
        Creates new Anritsu class

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.gpib_id = re.sub('::INSTR$', '', gpib_id)
        self.instr_num=instr_number
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Anritsu signal generator online. device ID:',self.instr_id)
        
        # Attributes
        self.frequency = 0
        self.power = 0
        self.ch_no = 1
        self.freq_unit = 'GHz'
        
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
    
    
    def disableRF(self):
        '''
        Disables RF output

        Returns
        -------
        None.

        '''
        self.instr_gpib.write('RF0')
        
        
    def enableRF(self):
        '''
        Enables RF output

        Returns
        -------
        None.

        '''
        self.instr_gpib.write('RF1')
        
 
    def set_power(self,power):
        '''
        Set RF output power for L1

        Parameters
        ----------
        power : float
            RF output power in dbm

        Returns
        -------
        None.

        '''
        msg = 'L'+str(self.ch_no)+' '+str(power)+' DM'
        self.instr_gpib.write(msg)
        
    
    def set_freq(self,freq):
        '''
        Set RF output frequency for F1
        Parameters
        ----------
        freq : float
            Frequency value, default unit GHz

        Returns
        -------
        None.

        '''
        unit = ' GH'
        if self.freq_unit.lower() == 'ghz':
            unit = ' GH'
        elif self.freq_unit.lower() == 'mhz':
            unit = ' MH'
        elif self.freq_unit.lower() == 'khz':
            unit = ' KH'
        else:
            unit = ' GH'
        
        msg = 'CF' + str(self.ch_no) + ' ' + str(freq) + unit
        self.instr_gpib.write(msg)

    

class SR860_lockin(SR860):
    '''
    Class to control SRS SR860 lock-in amplifier via GPIB/ethernet. 
    Inherits class pymeasure.instruments.srs.SR860,
    and adds some useful functions 
    
    Documentation for the pymeasure part can be found from:
    https://pymeasure.readthedocs.io/en/latest/api/instruments/srs/sr860.html
    '''
    def __init__(self,address):
        '''
        Creates new Keithley_2450 class that inherits class Keithley2450 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.rm=visa.ResourceManager()
        # Create new GPIB resource
        self.instr_gpib = self.rm.open_resource(gpib_id)
        # check resource id
        self.instr_id = self.instr_gpib.query("*IDN?")
        print('Lock-in amplifier online. device ID:',self.instr_id)




'''
=========================================================================================================================
                Basel SP1004
=========================================================================================================================
'''

class Basel_SP1004():
    def __init__(self):
        '''
        Creates 

        Parameters
        ----------
        gpib_id : string
            GPIB adress for given instrument
        instr_number : int
            Number of the instrument for future referencing
        Returns
        -------
        None.

        '''
        self.gain = 1000 # Amplifier gain in Hertz
        self.cutoff = 100 # Amplifier LP-filter cutoff in Hertz
        # Pin mapping between amplifier input TTL control pins
        self.pinmap = {'pin1':1,
                       'pin2':2,
                       'pin3':3,
                       'pin4':4,
                       'pin6':6,
                       'pin7':7,
                       'pin8':8,
                       'pin9':9,
                       }
        # Initialize control pins to zero
        self.pin1 = 0
        self.pin2 = 0
        self.pin3 = 0
        self.pin4 = 0
        self.pin6 = 0
        self.pin8 = 0
     
        # Logic table for control gain
        #               pin3 pin1
        self.gainlogic = ((1,0),    #10000
                          (0,0),    #1000
                          (0,1))    #100
        self.gainlist = (10000,1000,100)
        self.gainpinlist = (self.pin3,self.pin1)
        
        
        # Logic table for control LP filter cutoff
        #                   pin8 pin6 pin4 pin2      
        self.filterlogic = ((1,0,0,0),  #1MHz
                            (0,1,1,1),  #300 kHz
                            (0,1,1,0),  #100 kHz
                            (0,1,0,1),  #30 kHz
                            (0,1,0,0),  #10 kHz
                            (0,0,1,1),  #3 kHz
                            (0,0,1,0),  #1 kHz
                            (0,0,0,1),  #300 Hz
                            (0,0,0,0),  #100 Hz
                            )
        self.cutofflist = ('1MHz',
                           '300 kHz',
                           '100 kHz',
                           '30 kHz',
                           '10 kHz',
                           '3 kHz',
                           '1 kHz',
                           '300 Hz',
                           '100 Hz'
                           )
        self.cutoffpinlist = (self.pin8,self.pin6,self.pin4,self.pin2)
        
        
        
    def set_gain(self,gain):
        '''
        Method for setting amplifier gain

        Parameters
        ----------
        gain : int
            Amplifier gain value.

        Returns
        -------
        None.

        '''
        pinstate = self.gainlogic[self.gainlist.index(gain)]
        self.pin3 = pinstate[0]
        self.pin1 = pinstate[1]
        self.write_pins()

    def set_cutoff(self,cutoff):
        '''
        Method for setting amplifier LP filter cutoff

        Parameters
        ----------
        cutoff : string
            Amplifier LP filter cutoff.

        Returns
        -------
        None.

        '''
        pinstate = self.filterlogic[self.cutofflist.index(cutoff)]
        self.pin2 = pinstate[0]
        self.pin4 = pinstate[1]
        self.pin6 = pinstate[2]
        self.pin8 = pinstate[3]
        self.write_pins()
        
    def write_pins(self):
        print('MAKE THIS WORK')
        
    
def get_instruments(**kwargs):
    '''
    Function to get all available and supported instruments to a dictionary

    Parameters
    ----------
    **kwargs : 
        pynska(boolean): Truth value to indicate whether to connect to pynska box or not
        keithley(string): GPIB address of Keithley 2450 source meter
        lockin1(string): GPIB address of lock-in amplifier 1 (SR810/SR830)
        lockin2(string): GPIB address of lock-in amplifier 1 (SR810/SR830)

    Returns
    -------
    instruments : dictionary
        dictionary containing aall available instruments:
            keys:
                'pynska'   Pynskäbox
                'keithley' Keithley 2450 Source meter
                'lockin1'  Stanford Measurement Systems lock-in amplifier SR810/SR830
                'lockin2'  Stanford Measurement Systems lock-in amplifier SR810/SR830

    '''
    s= "=" * 60
    print(s)
    print('Setting up the instruments')
    # Pynskabox
    instruments={}
    try:
        if 'pynska' in kwargs:
            if kwargs['pynska']:
                print(s)
                print('Connecting to pynskabox')
                instruments['pynska'] = pynskabox()
                print('Connected')
    except:
        instruments['pynska'] = None
        print('ERROR: Not able to connect to pynskabox')
            
    # Keithley
    try:
        if 'keithley' in kwargs:
            print(s)
            print('Connecting to Keithley 2450 source meter')
            instruments['keithley'] = Keithley_2450(kwargs['keithley'],1)
            print('Connected')
    except:
        instruments['keithley'] = None
        print('ERROR: Not able to connect to Keithley 2450')
            
    # Stanford 1
    try:
        if 'lockin1' in kwargs:
            print(s)
            print('Connecting to Stanford Measurement Systems lock-in amplifier SR810/SR830 1')
            instruments['lockin1'] = SR810_30_lockin(kwargs['lockin1'],0)
            print('Connected')
    except:
        instruments['lockin1'] = None
        print('ERROR: Not able to connect to lock-in amplifier 1')
            
    # Stanford 2
    try:
        if 'lockin2' in kwargs:
            print(s)
            print('Connecting to Stanford Measurement Systems lock-in amplifier SR810/SR830 1')
            instruments['lockin2'] = SR810_30_lockin(kwargs['lockin2'],0)
            print('Connected')
    except:
        instruments['lockin2'] = None
        print('ERROR: Not able to connect to lock-in amplifier 2')
    # PN300
    try:
        if 'PN300' in kwargs:
            print(s)
            print('Connecting to Digimess PN300 power supply')
            instruments['PN300'] = PN300(kwargs['PN300'],0)
            print('Connected')
    except:
        instruments['PN300'] = None
        print('ERROR: Not able to connect to PN300')
        
    # Anritsu
    try:
        if 'Anritsu68367C' in kwargs:
            print(s)
            print('Connecting to Anritsu 68367C Synthesized signal generator')
            instruments['Anritsu68367C'] = Anritsu68367C(kwargs['Anritsu68367C'],0)
            print('Connected')
    except:
        instruments['Anritsu68367C'] = None
        print('ERROR: Not able to connect to Anritsu 68367C')
    print(s)
    return instruments  

 
'''
=========================================================================================================================
                Main
=========================================================================================================================
'''

if __name__ == '__main__':
    
    #pynska = pynskabox()
    
    
    basel = Basel_SP1004()
    basel.set_gain(10000)
    print(basel.pin1,basel.pin3)
    basel.set_cutoff('30 kHz')
    print(basel.pin2,basel.pin4,basel.pin6,basel.pin8)

    '''
    keithley=Keithley_2450('GPIB0::18',1)
    keithley.init_current_sourcing(100):
    keithley.source_current = 0.01
    '''
    '''
    l1=SR810_30_lockin('GPIB0::7::INSTR',0)
    l2=SR810_30_lockin('GPIB0::8::INSTR',1)
    

    #lokkari.adjust_settings(ref_slope=0,harm=1)
    #l1.print_settings()
    #l1.createSettingsDict()
    #l1.export_settings('D:\DATA\Aki\lokkari1_settings.yaml')
    #l2.export_settings('D:\DATA\Aki\lokkari1_settings.yaml')
    '''