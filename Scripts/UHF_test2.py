from zhinst.qcodes import UHFLI
from zhinst.qcodes import ZISession
import matplotlib.pyplot as plt
import numpy as np
import time
#from qcodes.instrument_drivers.bluefors.BlueForsBFTC import BlueForsBFTC
# Connect to UHF
#uhfli = UHFLI("dev2288", "localhost", name="lockin", allow_version_mismatch=True)   # py zhinst (26.4) newer than LabOne server (24.10)
session = ZISession('localhost', allow_version_mismatch=True)
device = session.connect_device("dev2288")

SCOPE_CHANNEL = 0
SIGNAL_INPUT = 0
SIGNAL_OUTPUT = 0

#UHFLI: 3, HF2LI: 6, MFLI: 1
OUT_MIXER_CHANNEL = 3
with device.set_transaction():
    device.sigouts[SIGNAL_OUTPUT].on(True)
    device.sigouts[SIGNAL_OUTPUT].range(1.5)
    device.sigouts[SIGNAL_OUTPUT].amplitudes[OUT_MIXER_CHANNEL].value(0.5)
    device.sigouts[SIGNAL_OUTPUT].enables[OUT_MIXER_CHANNEL].value(True)

    device.sigins[SIGNAL_INPUT].imp50(1)
    device.sigins[SIGNAL_INPUT].ac(0)

    OSC_INDEX = 0
    device.oscs[OSC_INDEX].freq(400e3) # UHFLI: 10.0e6
    device.demods[OUT_MIXER_CHANNEL].oscselect(OSC_INDEX)

#  Execute autorange and wait for the correct state chang
if device.sigins[SIGNAL_INPUT].autorange(1, deep=True) != 0:
    # The auto ranging takes some time. We do not want to continue before the
    # best range is found. Therefore, we wait for state to change to 0.
    # These nodes maintain value 1 until autoranging has finished.
    device.sigins[SIGNAL_INPUT].autorange.wait_for_state_change(0, timeout=20)

SCOPE_TIME = 0

# Configure the scope
with device.set_transaction():
    device.scopes[0].length(2 ** 12)
    device.scopes[0].channel(1)
    device.scopes[0].channels[0].bwlimit(1)
    device.scopes[0].channels[0].inputselect(SIGNAL_INPUT)
    device.scopes[0].time(SCOPE_TIME)
    device.scopes[0].single(False)
    device.scopes[0].trigenable(False)
    device.scopes[0].trigholdoff(0.050)
    device.scopes[0].segments.enable(False)

# Initialize scope module
MIN_NUMBER_OF_RECORDS = 20

scope_module = session.modules.scope
scope_module.mode(1)
scope_module.historylength(20)
scope_module.fft.window(0)

# Subscribe to scope node data
wave_node = device.scopes[0].wave
scope_module.subscribe(wave_node)

# Obtain scope records from the device using an instance of the Scope Module.
# Helper functions for getting the scope records.
def check_scope_record_flags(scope_records, num_records):
    """
    Loop over all records and print a warning to the console if an error bit in
    flags has been set.
    """
    num_records = len(scope_records)
    for index, record in enumerate(scope_records):
        record_idx = f"{index}/{num_records}"
        record_flags = record[0]["flags"]
        if record_flags & 1:
            print(f"Warning: Scope record {record_idx} flag indicates dataloss.")
        if record_flags & 2:
            print(f"Warning: Scope record {record_idx} indicates missed trigger.")
        if record_flags & 4:
            print(f"Warning: Scope record {record_idx} indicates transfer failure" \
                "(corrupt data).")

        totalsamples = record[0]["totalsamples"]
        for wave in record[0]["wave"]:
            # Check that the wave in each scope channel contains
            # the expected number of samples.
            assert (
                len(wave) == totalsamples
            ), f"Scope record {index}/{num_records} size does not match totalsamples."


def get_scope_records(scope_module, num_records: int):
    """Obtain scope records from the device using an instance of the Scope Module."""
    scope_module.execute()
    device.scopes[0].enable(True)
    session.sync()

    start = time.time()
    timeout = 30 # [s]
    records = 0
    progress = 0
    # Wait until the Scope Module has received and processed
    # the desired number of records.
    while (records < num_records) or (progress < 1.0):
        time.sleep(0.5)
        records = scope_module.records()
        progress = scope_module.progress()
        print(
            f"Scope module has acquired {records} records (requested {num_records}). "
            f"Progress of current segment {100.0 * progress}%.",
            end="\r",
        )
        if (time.time() - start) > timeout:
            # Break out of the loop if for some reason we're no longer receiving
            # scope data from thedevice
            print(
                f"\nScope Module did not return {num_records} records after {timeout} s - \
                    forcing stop."
            )
            break

    device.scopes[0].enable(False)
    # Read out the scope data from the module.
    data = scope_module.read()[wave_node]
    # Stop the module; to use it again we need to call execute().
    scope_module.finish()
    check_scope_record_flags(data, num_records)
    return data


data_no_trig = get_scope_records(scope_module, MIN_NUMBER_OF_RECORDS)
clockbase = device.clockbase()

def plot_time_domain(axis, scope_records, scope_input_channel):
    colors = plt.cm.rainbow(np.linspace(0, 1, len(scope_records)))

    def to_timestamp(record):
        totalsamples = record[0]["totalsamples"]
        dt = record[0]["dt"]
        timestamp = record[0]["timestamp"]
        triggertimestamp = record[0]["triggertimestamp"]
        t = np.arange(-totalsamples, 0) * dt + (
            timestamp - triggertimestamp
        ) / float(clockbase)
        return 1e6 * t

    for index, record in enumerate(scope_records):
        wave = record[0]["wave"][scope_input_channel, :]
        ts = to_timestamp(record)
        axis.plot(ts, wave, color=colors[index])

    plt.draw()
    axis.grid(True)
    axis.set_ylabel("Amplitude [V]")
    axis.autoscale(enable=True, axis="x", tight=True)

_, (ax1, ax2) = plt.subplots(2)
# Plot the scope data with triggering disabled.
plot_time_domain(ax1, data_no_trig, SCOPE_CHANNEL)
ax1.set_title(f"{len(data_no_trig)} Scope records from {device} (triggering disabled)")

plt.subplots_adjust(hspace = 1)

# Plot the scope data with triggering enabled.
plot_time_domain(ax2, data_no_trig, SCOPE_CHANNEL)
ax2.axvline(0.0, linewidth=2, linestyle="--", color="k", label="Trigger time")
ax2.set_title(f"{len(data_no_trig)} Scope records from {device}")
ax2.set_xlabel("t (relative to trigger) [us]")
plt.show()