import traceback
import warnings

from Control_lib.drivers import AVS47, SR830, SR860,AMI340,BlueforsController
# Add other device classes here as needed

# Available devices 
# Requirement for the device: apply_settings function and for DAQ devices continuousRead
DEVICE_CLASSES = {
    "AVS-47": AVS47.AVS47,
    "SR830": SR830.SR830,
    "SR860": SR860.SR860,
    "AMI340": AMI340.AMI340,
    "BF":BlueforsController.BlueFTController
}

def initialize_device(dev_name, address, settings):
    '''
    Function to initialize device
    '''
    # Read device from device dict
    device_class = DEVICE_CLASSES[dev_name]

    # Check that device is supported
    if device_class is None:
        raise ValueError(f"Unknown device: {dev_name}")

    # Initialize device using GPIB or IP address
    device = device_class(address)
    return device


def add_device(devicelist, dev_name, address, settings):
    '''
    Method to add device 
    '''
    try:
        # First initialize device
        device = initialize_device(dev_name, address, settings)
        # Add device to devicelist
        devicelist[address] = {"Device": device,"Name": dev_name,}
        return device

    except Exception:
        traceback.print_exc()
        warnings.warn(f"Not able to connect to {dev_name}")
        return None