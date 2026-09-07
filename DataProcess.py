import numpy as np
import sys
import logging
import Control_lib.thermometer_calib_LTL as tc

logging.basicConfig(level=logging.INFO)

class DataProcess:
    '''Class for processing measurement data'''
    def __init__(self, stop_event, used_queues, q1, q3, qr, processdict):
        # Set up class variables
        self.stop_event = stop_event
        self.used_queues = used_queues
        self.q1 = q1
        self.q3 = q3
        self.qr = qr
        self.processdict = processdict
        # Extract details from the processdict
        if 'multips' in processdict:
            self.multips = processdict['multips']
        if 'therm_calib_name' in processdict:
            self.therm_calib_name = processdict['therm_calib_name']
        if 'rawdataout' in processdict:
            self.rawdataout = processdict['rawdataout']
        if 'thermCh' in processdict:
            self.thermCh = processdict['thermCh']
        if 'chunk_averaging' in processdict:
            self.chunk_averaging = processdict['chunk_averaging']
        if 'DAQsettingDict' in processdict:
            self.DAQsettingDict = processdict['DAQsettingDict']
        if 'paramSweepDict' in processdict:
            self.paramSweepDict = processdict['paramSweepDict']
        if 'N_logging' in processdict:
            self.N_logging = processdict['N_logging']

    def process(self):
        '''
        Process measured data and send it forward

        Returns
        -------
        None.

        '''
        multipsdaq = {}
        # Initialize data arrays
        output = {}
        outputm = {}
        Nsm = {}
        i_ch = 0
        # Set up thermometer calibration function if necessary
        if self.therm_calib_name != 'None':
            self.calibfunc = lambda x:tc.getTemperature(self.therm_calib_name,x)

        # Iterate through DAQ interfaces to get correct size for the data
        Ndaq = 0
        for daqch in self.DAQsettingDict:
            try:
                # Read number of channels from the DAQ settings
                Nch = len(self.DAQsettingDict[daqch]['Settings']['Channels'])
                # Only one channel active
            except:
                Nch = 1
            # Set up data arrays and initialize them with NaN values
            if self.chunk_averaging:
                output[daqch] = np.zeros(shape = (self.N_logging,Nch+1))* np.nan
                outputm[daqch] = np.zeros(shape = (self.N_logging,Nch+1))* np.nan
            else:
                try:
                    Nsmi = int(self.DAQsettingDict[daqch]['Settings']['Number of samples'])
                except:
                    Nsmi = 1
                Nsm[daqch] = Nsmi
                output[daqch] = np.zeros(shape = (self.N_logging*Nsmi,Nch+1))* np.nan
                outputm[daqch] = np.zeros(shape = (self.N_logging*Nsmi,Nch+1))* np.nan
            
            # Construct multipliers and take time into account
            print(f'Channel {daqch} has {Nch} channels, multipliers: {self.multips[i_ch:i_ch + Nch]}')
            multipsdaq[daqch] = [1] + self.multips[i_ch:i_ch + Nch]
            if len(multipsdaq[daqch]) != Nch+1:
                multipsdaq[daqch] = np.ones(Nch+1)
            i_ch += Nch
            Ndaq+=1

        Nps = 0
        # Iterate through Parameter sweeps
        for psi in self.paramSweepDict.keys():
            Nch = 1
            j = Ndaq + psi
            Nsm[j] = 1
            # Set up data arrays and initialize them with NaN values
            output[j] = np.zeros(shape = (self.N_logging,2))* np.nan
            outputm[j] = np.zeros(shape = (self.N_logging,2))* np.nan
            # Construct multipliers and take time into account
            print(f'Channel {f'PS{psi}'} has {Nch} channels, multipliers: {self.multips[i_ch:i_ch + Nch]}')
            multipsdaq[j] = [1] + self.multips[i_ch:i_ch + Nch]
            if len(multipsdaq[j]) != 2:
                multipsdaq[j] = np.ones(2)
            i_ch += Nch
            Nps += 1

        # Start while loop
        while not self.stop_event.is_set():
            # Read channel multipliers and get only the latest one
            while not self.qr.empty() and not self.stop_event.is_set():
                multips = self.qr.get_nowait()
            # Read channel measurement data
            n_out = 0
            data_received = [False for qi in self.used_queues]
            # Take data out of DAQ until desired amount of data is fetched
            while n_out < self.N_logging and not self.stop_event.is_set():
                # Take all the data from queues
                for i,(chi,qi) in enumerate(zip(self.used_queues.keys(),self.used_queues.values())):
                    try:
                        datain = qi.get_nowait()
                        data_received[chi] = True
                    except Exception as e:
                        continue
                    try:
                        # Calculate average for each channel
                        if self.chunk_averaging:
                            # Add one averaged row to output array
                            output[chi][n_out] = np.average(datain, axis=1)
                        else:
                            output[chi][n_out*Nsm[chi]:(n_out+1)*Nsm[chi]] = np.transpose(datain)
                        # Multiply output with channel multipliers
                        outputm[chi] = np.multiply(output[chi],multipsdaq[chi])
                        if self.therm_calib_name != 'None' and chi == self.thermCh[0]:
                            # Apply thermometer function to only one column of the data
                            try:
                                outputm[chi][:,self.thermCh[1]+1] = np.apply_along_axis(self.calibfunc, 0, outputm[self.thermCh[0]][:,self.thermCh[1]+1])
                            except Exception as e:
                                logging.info(f'Error occurred while applying thermometer calibration: {e}')
                    except Exception as e:
                        logging.info(f'Error occurred {e}')
                # Check if there is incoming data in any of the queues
                if not any(data_received) or not all(data_received):
                    # Continue to next iteration if no data or partial data is received
                    continue
                else:
                    # Initialize back to zero
                    data_received = [False for qi in self.used_queues]
                    n_out += 1

            # Send data to datalogging queue with raw data without multiplication
            # TODO MAKE THIS PROPERLY
            #if self.rawdataout:
                # Send data to logging queue
            #    q3.put({'Data':outputm,'rawdata':output})
            #else:
            #    q3.put({'Data':outputm})
                
            # Send multiplied data to plotting queue
            # Flatten the multiplied data
            outputm_flatten = np.hstack([outputm[k] if k == 0 else outputm[k][:, 1:]
                                         for k in sorted(outputm)
            ])
            # Flatten the raw data
            output_flatten = np.hstack([output[k][:, 1:] for k in sorted(output)])
            self.q3.put(np.concatenate([outputm_flatten, output_flatten], axis=1))
            self.q1.put(np.concatenate([outputm_flatten, output_flatten], axis=1))
        print('Data processing stopped')
        sys.exit()
            
if __name__ == "__main__":
    print("DataProcess module")