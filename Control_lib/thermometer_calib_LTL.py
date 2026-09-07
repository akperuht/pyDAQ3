from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

def getTemperature(thermometer,resistance):
    '''
    Function to get temperature from resistance using the calibration data of the thermometer
    Parameters
    ----------
    thermometer : str
        Name of the thermometer. Currently only Montana_4K is supported.
    resistance : float
        Resistance in Ohms

    Returns
    -------
    temperature : float
        Temperature in Kelvins

    '''
    if thermometer == 'Montana_4K':
        return Montana_4K_calib(resistance)
    else:
        raise ValueError(f'Thermometer {thermometer} not supported. Please use Montana_4K.')
    


def Montana_4K_calib(R):
    '''
    Method to interpolate thermometer calibration data
    Based on calibration data Montana_4K_241110.txt
    Parameters
    ----------
    R : float
        resistance

    Returns
    -------
    T
        Calculated temperature in Kelvins

    '''
    # Extract calibration file for the thermometer
    current_dir = Path(__file__).resolve().parent
    # Load calibration data
    calibration_file = current_dir / 'LTL_Thermometer_calibration_files' / 'Montana_4K_241110.txt'
    therm_calib_data = pd.read_csv(calibration_file,
                              skiprows = 9, sep = ' ', names = ['Temperature(K)','Resistance(Ohm)'])
    therm_calib = interp1d(therm_calib_data['Temperature(K)'],therm_calib_data['Resistance(Ohm)'],fill_value='extrapolate')
    return therm_calib(R)

if __name__ == '__main__':
    plt.figure()
    r_arr = np.linspace(1.6,30)
    plt.plot(Montana_4K_calib(r_arr),r_arr,'k-')