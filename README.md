# PyDAQ
## PyDAQmeas
PyDAQ is python data acquisition and hardware control framework developed mainly for the cryogenic measurements performed in Nanoscience Center, University of Jyväskylä. 
PyDAQ contains hardware control libraries for several devices, and measurement can be run using scripts or included GUI. Plotting relies on fast pyqtgraph library.

PyDAQmeas_X_X.py is a GUI for DAQ and hardware control. Data acquisition is designed to be as fast as possible, reaching hardware limits if used properly. This relies heavily on multiprocessing, 
so that all operations run smoothly. However, this may consume all CPU cores in older PC:s. 

It is possible to change settings of the devices as well as generate measurement metadata using GUI.
Code takes into account all the settings in real time, thus measurement output can be in real units. Also it is possible to apply thermometer calibration function for currently to one channel.

Device control is realized with JSON files, in order to add new device you only need to construct new JSON file and add it to available devices.

Note:
Version 2.2 is currently latest stable release tested to work in measurement PC:s. Version 2.2 is using PyQt5 library, and no new features will be added to this version (except for possible bugfixes if I have time).
Version 2.3 is a development version using PySide6 (Qt6).

<p align="center">
  <img src="https://github.com/akperuht/PyDAQ/blob/main/doc/main_UI.png" alt="Main UI" width="1000">
</p>

<p align="center">
  <img src="https://github.com/akperuht/PyDAQ/blob/main/doc/metadata_dialog.png" alt="Metadata dialog" width="300">

## Other codes
PyDAQmeas_1_2.py is legacy code for slow DAQ, without metadata generation and with limited hardware control.

LockinRMeas_v4.py is automatized GUI code for measuring resistance as a function of temperature using SR830 lock in amplifiers with Ithaco preamplifiers. 
Code is specific to the setup, and thus should be modified if used in different setups.
