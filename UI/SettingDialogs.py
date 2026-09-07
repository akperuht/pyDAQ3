from PySide6 import QtWidgets
from PySide6 import QtCore,QtGui
from PySide6.QtCore import Qt,Signal
import pyvisa
import json
import yaml

class DeviceSettingDialog(QtWidgets.QDialog):
    '''
    Class for asking device settings for the experiment
    '''
    # Communicate dialog data via pyqtSignal
    accepted = QtCore.Signal(dict) #!!! Working also here

    def __init__(self,settings,paramsfile,channel,parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device settings")
        
        # Set input dialog stylesheet
        self.setStyleSheet( "background-color:rgb(25, 35, 45);color:white")
        # Set stylesheets
        self.combostyle = """QComboBox { 
            background-color: rgb(43, 61, 79);
            selection-background-color: gray; 
            color : white; 
            border: 1px solid black; 
            padding :4px;
            selection-color:cyan;
            font-family: Arial;
            font-size:15 pt;
            }
            QComboBox::hover {
            background-color: rgb(55, 79, 102);
                }
            QListView{
            background-color: rgb(57, 68, 79);
            border: 1px solid black; 
            }
                """
        
        
        
        self.channel = channel
        self.settings = settings
        
        # Get available visa resources
        resm = pyvisa.ResourceManager()
        self.visa_list = resm.list_resources()
        
        #self.visa_list = ['GPIB0::20::INSTR','GPIB0::10::INSTR']
                
        # Create form
        form = QtWidgets.QFormLayout(self)
        # Open JSON file
        with open(paramsfile) as jf:
            paramsdict = json.load(jf)
        # Add controls corresponding to keys in paramsdict
        self.combo = {}
        self.ps = paramsdict['Settings']
        for key in self.ps:
            # Check if key is meant to be shown in dialog
            if self.ps[key]['toDialog']:
                # Check key type
                if self.ps[key]['type'] == 'QComboBox':
                    # Create combobox
                    combo_i = QtWidgets.QComboBox(self)
                    # Add all available values to combobox, handle GPIB channels differently
                    if key == 'GPIB channel':
                        combo_i.addItems(self.visa_list)
                    else:
                        combo_i.addItems([str(vi) for vi in self.ps[key]['values']])
                    # Set stylesheet
                    combo_i.setStyleSheet(self.combostyle)
                    # Set index to default or already applied value
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    try:
                        if key == 'GPIB channel':
                            combo_i.setCurrentIndex(self.visa_list.index(current_value))
                        else:
                            combo_i.setCurrentIndex(self.ps[key]['values'].index(current_value))
                    except:
                        # Fall back to first index
                        combo_i.setCurrentIndex(0)
                    # Add combobox to list of comboboxes
                    self.combo[key] = combo_i
                    # Add to form
                    form.addRow(key, combo_i)
        self.btn = QtWidgets.QPushButton('OK')
        self.btn.clicked.connect(self.ok_pressed)
        form.addRow(self.btn)

    def ok_pressed(self):
        '''
        Handles event when ok button is pressed in the dialog

        Returns
        -------
        None.

        '''
        # Get settings from dialog
        settings = {}
        multip = 1
        # Iterate over the keys in setting dictionary
        for key in self.ps:
            # Take values only if values can be changed in dialog
            if self.ps[key]['toDialog']:
                # Extract values from comboboxes
                if self.ps[key]['type'] == 'QComboBox':
                    # Get current setting
                    if key == 'GPIB channel':
                        try:
                            ic = self.combo[key].currentIndex()
                        except:
                            ic = 0
                        val = self.visa_list[ic]
                    else:
                        ic = self.combo[key].currentIndex()
                        val = self.ps[key]['values'][ic]
                    settings[key] = val
                    # Get channel multiplier 
                    if 'Multiplier' in self.ps[key]:
                        # Check if value multiplies or divides channel value
                        if self.ps[key]['Multiplier'] == 'Multiply': #!!! Add new if clause if needed
                            multip=multip*val
                        elif self.ps[key]['Multiplier'] == 'Divide':
                            multip=multip/val
                        elif self.ps[key]['Multiplier'] == 'Multiply0.5':
                            multip=multip*val*0.5
            # Take default value
            else:
                settings[key] = self.ps[key]['default']
        values = {'Channel':self.channel,'Multiplier':multip,'Settings': settings}
        self.accepted.emit(values)
        self.accept()


class DAQSettingDialog(QtWidgets.QDialog):
    '''
    Class for asking device settings for the experiment
    '''
    # Communicate dialog data via pyqtSignal
    accepted = QtCore.Signal(dict) #!!! Working also here

    def __init__(self,settings,paramsfile,channel,parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device settings")
        
        # Set input dialog stylesheet
        self.setStyleSheet( "background-color:rgb(25, 35, 45);color:white")
        # Set stylesheets
        self.combostyle = """QComboBox { 
            background-color: rgb(43, 61, 79);
            selection-background-color: gray; 
            color : white; 
            border: 1px solid black; 
            padding :4px;
            selection-color:cyan;
            font-family: Arial;
            font-size:15 pt;
            }
            QComboBox::hover {
            background-color: rgb(55, 79, 102);
                }
            QListView{
            background-color: rgb(57, 68, 79);
            border: 1px solid black; 
            }
                """
        
        
        
        self.channel = channel
        self.settings = settings
        
        # Get available visa resources
        resm = pyvisa.ResourceManager()
        self.visa_list = resm.list_resources()
        
                
        # Create form
        form = QtWidgets.QFormLayout(self)
        # Open JSON file
        with open(paramsfile) as jf:
            paramsdict = json.load(jf)
        # Add controls corresponding to keys in paramsdict
        self.combo = {}
        self.linee = {}
        self.spin = {}
        self.listwgs = {}
        self.ps = paramsdict['Settings']
        for key in self.ps:
            # Check if key is meant to be shown in dialog
            if self.ps[key]['toDialog']:
                # Check key type
                if self.ps[key]['type'] == 'QComboBox':
                    # Create combobox
                    combo_i = QtWidgets.QComboBox(self)
                    # Add all available values to combobox, handle GPIB channels differently
                    if key == 'GPIB channel':
                        combo_i.addItems(self.visa_list)
                    else:
                        combo_i.addItems([str(vi) for vi in self.ps[key]['values']])
                    # Set stylesheet
                    combo_i.setStyleSheet(self.combostyle)
                    # Set index to default or already applied value
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    try:
                        if key == 'GPIB channel':
                            combo_i.setCurrentIndex(self.visa_list.index(current_value))
                        else:
                            combo_i.setCurrentIndex(self.ps[key]['values'].index(current_value))
                    except:
                        # Fall back to first index
                        combo_i.setCurrentIndex(0)
                    # Add combobox to list of comboboxes
                    self.combo[key] = combo_i
                    # Add to form
                    form.addRow(key, combo_i)
                # Create QLineEdit for string values
                elif self.ps[key]['type'] == 'QLineEdit':
                    # Create line edit
                    linee_i = QtWidgets.QLineEdit(self)
                    # Set default value
                    linee_i.setText(self.ps[key]['default'])
                    # Add Line edit to list
                    self.linee[key] = linee_i
                    form.addRow(key, linee_i)         
                # Create QSpinBox for integer values       
                elif self.ps[key]['type'] == 'QSpinBox':
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    spin_i = QtWidgets.QSpinBox(self)
                    # Set range and default value
                    spin_i.setRange(self.ps[key]['minimum'], self.ps[key]['maximum'])
                    spin_i.setValue(current_value)
                    # Add Spin box to list
                    self.spin[key] = spin_i
                    form.addRow(key, spin_i)
                elif self.ps[key]['type'] == 'QDoubleSpinBox':
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    spin_i = QtWidgets.QDoubleSpinBox(self)
                    # Set deicmal precision if available
                    if 'decimals' in self.ps[key]:
                        spin_i.setDecimals(self.ps[key]['decimals'])
                    # Set suffix if available
                    if 'unit' in self.ps[key]:
                        spin_i.setSuffix(' '+self.ps[key]['unit'])
                    # Set range and default value
                    spin_i.setRange(self.ps[key]['minimum'], self.ps[key]['maximum'])
                    spin_i.setValue(current_value)
                    # Add Spin box to list
                    self.spin[key] = spin_i
                    form.addRow(key, spin_i)
                # Create QListWidget for multiple selection
                elif self.ps[key]['type'] == 'QListWidget':
                    listwg = QtWidgets.QListWidget(self)
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    for val in self.ps[key]['values']:
                        item = QtWidgets.QListWidgetItem(val)
                        # Try to remember the state
                        if val in current_value:
                            item.setCheckState(Qt.Checked)
                        else:
                            item.setCheckState(Qt.Unchecked)
                        listwg.addItem(item)
                    self.listwgs[key] = listwg
                    # Restrict height
                    height = (listwg.sizeHintForRow(0) * listwg.count() + 2 * listwg.frameWidth())
                    listwg.setFixedHeight(height)
                    form.addRow(key, listwg)
                else:
                    pass
        self.btn = QtWidgets.QPushButton('OK')
        self.btn.clicked.connect(self.ok_pressed)
        form.addRow(self.btn)

    def ok_pressed(self):
        '''
        Handles event when ok button is pressed in the dialog

        Returns
        -------
        None.

        '''
        # Get settings from dialog
        settings = {}
        multip = 1
        # Iterate over the keys in setting dictionary
        for key in self.ps:
            # Take values only if values can be changed in dialog
            if self.ps[key]['toDialog']:
                # Extract values from comboboxes
                if self.ps[key]['type'] == 'QComboBox':
                    # Get current setting
                    if key == 'GPIB channel':
                        try:
                            ic = self.combo[key].currentIndex()
                        except:
                            ic = 0
                        val = self.visa_list[ic]
                    else:
                        try:
                            ic = self.combo[key].currentIndex()
                            val = self.ps[key]['values'][ic]
                        except:
                            val = None
                    settings[key] = val
                elif self.ps[key]['type'] == 'QLineEdit':
                    val = self.linee[key].text()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QSpinBox':
                    val = self.spin[key].value()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QDoubleSpinBox':
                    val = self.spin[key].value()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QListWidget':
                    checked = []
                    for i in range(self.listwgs[key].count()):
                        item = self.listwgs[key].item(i)
                        if item.checkState() == Qt.Checked:
                            checked.append(item.text())
                    settings[key] = checked
            # Take default value
            else:
                settings[key] = self.ps[key]['default']
        values = {'Channel':self.channel,'Settings': settings}
        self.accepted.emit(values)
        self.accept()

class paramSweepSettingDialog(QtWidgets.QDialog):
    '''
    Class for asking parameter sweep settings for the experiment
    '''
    # Communicate dialog data via pyqtSignal
    accepted = QtCore.Signal(dict) #!!! Working also here

    def __init__(self,settings,paramsfile,channel,parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up parameter sweep")
        
        # Set input dialog stylesheet
        self.setStyleSheet( "background-color:rgb(25, 35, 45);color:white")
        # Set stylesheets
        self.combostyle = """QComboBox { 
            background-color: rgb(43, 61, 79);
            selection-background-color: gray; 
            color : white; 
            border: 1px solid black; 
            padding :4px;
            selection-color:cyan;
            font-family: Arial;
            font-size:15 pt;
            }
            QComboBox::hover {
            background-color: rgb(55, 79, 102);
                }
            QListView{
            background-color: rgb(57, 68, 79);
            border: 1px solid black; 
            }
                """
        
        
        
        self.channel = channel
        self.settings = settings
        
        # Get available visa resources
        resm = pyvisa.ResourceManager()
        self.visa_list = resm.list_resources()
        
        # Create form
        form = QtWidgets.QFormLayout(self)
        # Open JSON file
        with open(paramsfile) as jf:
            paramsdict = json.load(jf)
        # Add controls corresponding to keys in paramsdict
        self.combo = {}
        self.linee = {}
        self.spin = {}
        self.listwgs = {}
        self.check = {}
        self.ps = paramsdict['Settings']
        for key in self.ps:
            # Check if key is meant to be shown in dialog
            if self.ps[key]['toDialog']:
                # Check key type
                if self.ps[key]['type'] == 'QComboBox':
                    # Create combobox
                    combo_i = QtWidgets.QComboBox(self)
                    # Add all available values to combobox, handle GPIB channels differently
                    if key == 'GPIB channel':
                        combo_i.addItems(self.visa_list)
                    else:
                        combo_i.addItems([str(vi) for vi in self.ps[key]['values']])
                    # Set stylesheet
                    combo_i.setStyleSheet(self.combostyle)
                    # Set index to default or already applied value
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    try:
                        if key == 'GPIB channel':
                            combo_i.setCurrentIndex(self.visa_list.index(current_value))
                        else:
                            combo_i.setCurrentIndex(self.ps[key]['values'].index(current_value))
                    except:
                        # Fall back to first index
                        combo_i.setCurrentIndex(0)
                    # Add combobox to list of comboboxes
                    self.combo[key] = combo_i
                    # Add to form
                    form.addRow(key, combo_i)
                # Create QLineEdit for string values
                elif self.ps[key]['type'] == 'QLineEdit':
                    # Create line edit
                    linee_i = QtWidgets.QLineEdit(self)
                    # Set default value
                    linee_i.setText(self.ps[key]['default'])
                    # Add Line edit to list
                    self.linee[key] = linee_i
                    form.addRow(key, linee_i)         
                # Create QSpinBox for integer values       
                elif self.ps[key]['type'] == 'QSpinBox':
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    spin_i = QtWidgets.QSpinBox(self)
                    # Set range and default value
                    spin_i.setRange(self.ps[key]['minimum'], self.ps[key]['maximum'])
                    spin_i.setValue(current_value)
                    # Add Spin box to list
                    self.spin[key] = spin_i
                    form.addRow(key, spin_i)
                elif self.ps[key]['type'] == 'QDoubleSpinBox':
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    spin_i = QtWidgets.QDoubleSpinBox(self)
                    # Set deicmal precision if available
                    if 'decimals' in self.ps[key]:
                        spin_i.setDecimals(self.ps[key]['decimals'])
                    # Set suffix if available
                    if 'unit' in self.ps[key]:
                        spin_i.setSuffix(' '+self.ps[key]['unit'])
                    # Set range and default value
                    spin_i.setRange(self.ps[key]['minimum'], self.ps[key]['maximum'])
                    spin_i.setValue(current_value)
                    # Add Spin box to list
                    self.spin[key] = spin_i
                    form.addRow(key, spin_i)
                elif self.ps[key]['type'] == 'QCheckBox':
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    checki = QtWidgets.QCheckBox(self)
                    # Try to remember the state
                    if current_value:
                        checki.setCheckState(Qt.Checked)
                    else:
                        checki.setCheckState(Qt.Unchecked)
                    # Add Check box to list
                    self.check[key] = checki
                    form.addRow(key, checki)
                # Create QListWidget for multiple selection
                elif self.ps[key]['type'] == 'QListWidget':
                    listwg = QtWidgets.QListWidget(self)
                    try:
                        # Try to get current value
                        current_value = self.settings['Settings'][key]
                    except Exception as e:
                        # Fall back to default if no current value is set
                        current_value = self.ps[key]['default']
                    for val in self.ps[key]['values']:
                        item = QtWidgets.QListWidgetItem(val)
                        # Try to remember the state
                        if val in current_value:
                            item.setCheckState(Qt.Checked)
                        else:
                            item.setCheckState(Qt.Unchecked)
                        listwg.addItem(item)
                    self.listwgs[key] = listwg
                    # Restrict height
                    height = (listwg.sizeHintForRow(0) * listwg.count() + 2 * listwg.frameWidth())
                    listwg.setFixedHeight(height)
                    form.addRow(key, listwg)
                else:
                    pass
        self.btn = QtWidgets.QPushButton('OK')
        self.btn.clicked.connect(self.ok_pressed)
        form.addRow(self.btn)

    def ok_pressed(self):
        '''
        Handles event when ok button is pressed in the dialog

        Returns
        -------
        None.

        '''
        # Get settings from dialog
        settings = {}
        # Iterate over the keys in setting dictionary
        for key in self.ps:
            # Take values only if values can be changed in dialog
            if self.ps[key]['toDialog']:
                # Extract values from comboboxes
                if self.ps[key]['type'] == 'QComboBox':
                    # Get current setting
                    if key == 'GPIB channel':
                        try:
                            ic = self.combo[key].currentIndex()
                        except:
                            ic = 0
                        val = self.visa_list[ic]
                    else:
                        try:
                            ic = self.combo[key].currentIndex()
                            val = self.ps[key]['values'][ic]
                        except:
                            val = None
                    settings[key] = val
                elif self.ps[key]['type'] == 'QLineEdit':
                    val = self.linee[key].text()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QSpinBox':
                    val = self.spin[key].value()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QDoubleSpinBox':
                    val = self.spin[key].value()
                    settings[key] = val
                elif self.ps[key]['type'] == 'QCheckBox':
                    # Check state
                    if self.check[key].checkState() == Qt.Checked:
                        settings[key] = True
                    else:
                        settings[key] = False
                    settings[key] = val
                elif self.ps[key]['type'] == 'QListWidget':
                    checked = []
                    for i in range(self.listwgs[key].count()):
                        item = self.listwgs[key].item(i)
                        if item.checkState() == Qt.Checked:
                            checked.append(item.text())
                    settings[key] = checked
            # Take default value
            else:
                settings[key] = self.ps[key]['default']
        values = {'Channel':self.channel,'Settings': settings}
        self.accepted.emit(values)
        self.accept()


class MetadataDialog(QtWidgets.QDialog):
    '''
    Class for asking users metadata for the experiment
    '''
    accepted = QtCore.Signal(dict)

    def __init__(self, measChannels,settingDict,daqsettingdict, available_devices, parent=None):
        super().__init__(parent)
        # Set up controls
        self.setWindowTitle("Measurement metadata")
        self.date = QtWidgets.QDateEdit()
        self.date.setDisplayFormat('MMM d, yyyy')
        self.date.setDate(QtCore.QDate.currentDate())
        self.sample = QtWidgets.QLineEdit()
        self.author_name = QtWidgets.QLineEdit()
        self.author_name.textEdited[str].connect(self.unlock)
        self.channelNameLabel = QtWidgets.QLabel()
        self.channelNameLabel.setText('Description')
        
        # Add controls to form
        form = QtWidgets.QFormLayout(self)
        form.addRow('Date', self.date)
        form.addRow('Sample', self.sample)
        form.addRow('Measured by', self.author_name)
        form.addRow('Channel',self.channelNameLabel)
        self.chs = {}
        for i,chi in enumerate(measChannels):
            lei = QtWidgets.QLineEdit()
            self.chs[chi] = lei
            form.addRow(chi, lei)
            # Set guess for channel description
            #devicename = settingDict[chi]
            #print(devicename)
            #paramsfile = available_devices[devicename]
            
        self.meas_desc = QtWidgets.QTextEdit()
        form.addRow('Measurement description', self.meas_desc)

        # Set up OK and SKIP buttons        
        self.btn = QtWidgets.QPushButton('OK')
        self.btn.setDisabled(True)
        self.btn.clicked.connect(self.ok_pressed)
        
        self.skip_btn = QtWidgets.QPushButton('SKIP')
        self.skip_btn.setEnabled(True)
        self.skip_btn.clicked.connect(self.skip)
        

        
        # Put buttons in a horizontal layout
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn)
        btn_layout.addWidget(self.skip_btn)
        
        form.addRow(btn_layout)

    def skip(self):
        '''
        Skip formation of metadata

        Returns
        -------
        None.

        '''
        self.reject()

    def unlock(self, text):
        if text:
            self.btn.setEnabled(True)
        else:
            self.btn.setDisabled(True)

    def ok_pressed(self):
        '''
        Handles event when ok button is pressed in dialog

        Returns
        -------
        None.

        '''
        chdict = {}
        chnames = []
        # Get channel names from dialog
        for chi in self.chs.keys():
            chdict[chi] = self.chs[chi].text()
            chnames.append(self.chs[chi].text())
        values = {'Date': self.date.date(),
                  'Author': self.author_name.text(),
                  'Sample': self.sample.text(),
                  'Description': self.meas_desc.toPlainText(),
                  'Channel names':chdict,
                  'Channel labels':chnames
                  }
        self.accepted.emit(values)
        self.accept()

if __name__=='__main__':
    print('Classes for dialogs')
