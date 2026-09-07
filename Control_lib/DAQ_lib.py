# -*- coding: utf-8 -*-
"""
Created on Thu Jun 18 13:52:32 2026

@author: ruhtina1
"""

import numpy as np
import matplotlib.pyplot as plt
import nidaqmx
from nidaqmx.constants import AcquisitionType ,LoggingMode, LoggingOperation, WaitMode
from nidaqmx.stream_readers import AnalogMultiChannelReader
from nidaqmx.stream_writers import AnalogMultiChannelWriter
import threading 
import multiprocessing as mp
from queue import Queue, Empty
import time
from time import perf_counter
import pyvisa
from moku.instruments import Datalogger
from yaml import warnings
import os
import shutil
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(processName)s %(levelname)s: %(message)s"
)

class DAQ():
    def __init__(self,channels = None, devices = None):
        '''
        class constructor

        Parameters
        ----------
        channels : list(string), optional
            DAQ channels from which data is to be collected. The default is None.
        Returns
        -------
        None.

        '''
        self.task = None
        self.channels = channels
        self.devices = devices
        
    def continous_Nread_test(self,stop_event,starttime,q,sample_rate, Nsamples):
        '''
        Function to test DAQ acquisition without hardware

        '''
        # Initalize numpy array
        out = np.ones((len(self.channels), Nsamples))
        # Log starttime
        t0 = perf_counter()
        # Create test data until stop event is set
        while not stop_event.is_set():
            # Create random array
            rn = 0.2*np.random.rand(len(self.channels), Nsamples)

            q.put([perf_counter()-t0,np.multiply(out,rn)])
            # Delay to slow down the code
            time.sleep(1e-3)
        print('Data acquisition stopped')


    def MokuGo_continuous_Nread(self,stop_event,starttime,q,settings):
        '''
        Function to read continuously data from MokuGo with precision mode

        Parameters
        ----------
        stop_event : multiprocessing Event
            event to stop the data aquisition
        q : multiprocessing queue
            queue to send the data onwards
        settings : dict
            Dictionary containing Moku Go settings.

        Returns
        -------
        None.

        '''
        logging.info('Starting Moku Go data acquisition')
        Nsamples = settings['Number of samples']
        # Initialize moku Data Logger with given address
        if settings['Connection type'] == 'IPv4 Address':
            address = settings['IPv4 Address']
        elif settings['Connection type'] == 'IPv6 Address':
            address = settings['IPv6 Address']
        else:
            warnings.warn('Unknown connection type for Moku Go')
        logging.info(f"Connecting to Moku Go at address: {address}")
        # Set the path to mokucli in the environment variable
        path = shutil.which("mokucli")
        os.environ["MOKU_CLI_PATH"] = path
        dl = Datalogger(address, force_connect=True)
        # Change to precision mode
        dl.set_acquisition_mode(mode = settings['Acquisition mode'])
        logging.info('Starting data acquisition from Moku Go')
        # Start streaming samples
        dl.start_streaming(
            duration = settings['Streaming duration [s]'],
            sample_rate = settings['Sample rate [Hz]'],
        )
        # Log in the delay
        dt = perf_counter() - starttime
        # Buffers
        t_buf = np.array([], dtype=float)
        x_buf = np.array([], dtype=float)
        y_buf = np.array([], dtype=float)
        # Keep looping until measurement finishes
        try:
            while not stop_event.is_set():
                # Acquire data
                try:
                    chunk = dl.get_stream_data()
                except Exception as e:
                    print(f"Error while acquiring data from Moku Go: {e}", flush=True)
                    if "No streaming session" in str(e): 
                        break
                    else:
                        continue
                # Append new data
                t_buf = np.concatenate((t_buf, chunk["time"]))
                x_buf = np.concatenate((x_buf, chunk["ch1"]))
                y_buf = np.concatenate((y_buf, chunk["ch2"]))
                
                # Put only full blocks to queue
                while len(x_buf) >= Nsamples:
                    t = t_buf[:Nsamples]
                    ch1 = x_buf[:Nsamples]
                    ch2 = y_buf[:Nsamples]
            
                    out = np.stack([t, ch1, ch2], axis=0)  # shape (3, Nsamples)
                    # Send full block to measurement queue
                    q.put(out)
                    # Keep remainder (carry over)
                    t_buf = t_buf[Nsamples:]
                    x_buf = x_buf[Nsamples:]
                    y_buf = y_buf[Nsamples:]
        
        finally:
            logging.info('Stopping Moku Go data acquisition')
            # End streaming and empty the buffer
            dl.stop_streaming()
            while True:
                try:
                    data = dl.get_stream_data()
                except Exception as e:
                    print(f"Error while emptying buffer: {e}")
                    break

        
        
    def NiDAQmx_continous_Nread(self,stop_event,starttime,q,settings):
        '''
        Function to read continuously data from DAQ card. Data is read every time 
        callback is triggered. Best function for fast data collection as this is
        Event based.

        Parameters
        ----------


        Parameters
        ----------
        q : multiprocessing queue
            queue to send the data onwards
        stop_event : multiprocessing Event
            event to stop the data aquisition
        sample_rate : int
            Data measurement rate
        Nsamples : int
            amount of samples collected before event is active

        Returns
        -------
        Puts data to queue, format is [time, array(shape = Nchannel x Nsamples)]

        '''
        Nsamples = settings['Number of samples']
        channels = settings['Channels']
        sample_rate = settings['Sample rate [Hz]']
        #!!!
        # Initalize numpy array
        out = np.zeros((len(channels), Nsamples))
        # Function that is triggered when desired number of samples is registered
        def every_n_callback(task_handle, every_n_samples_event_type, number_of_samples, callback_data):
            # Create reader
            reader = AnalogMultiChannelReader(self.task.in_stream)
            # Read samples to buffer
            reader.read_many_sample(out, number_of_samples_per_channel=number_of_samples)
            # Put samples to queue
            q.put([perf_counter()-t0,out])
            return 0  # Must return 0 or DAQmx will consider it an error
        # Log starttime
        t0 = perf_counter()
        # Create task
        with nidaqmx.Task() as self.task:
            # Create voltage channels
            for ch in channels:
                self.task.ai_channels.add_ai_voltage_chan(ch,min_val=self.range[0], max_val=self.range[1])
        
            # Setting the rate of the Sample Clock and the number of samples to acquire
            self.task.timing.cfg_samp_clk_timing(rate = sample_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan = Nsamples)
        
            # Register the callback for every N samples acquired
            self.task.register_every_n_samples_acquired_into_buffer_event(Nsamples, every_n_callback)
        
            # Start the task
            self.task.start()
            
            # Stop the data acquisition when stop event is set
            while not stop_event.is_set():
                continue
            self.task.stop()
            print('Data acquisition stopped')
            
if __name__ == "__main__":
    print('DAQ tools.')