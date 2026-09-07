# -*- coding: utf-8 -*-
"""
Created on Fri Jul  3 10:34:03 2026

@author: ruhtina1
"""

from moku.instruments import Datalogger
import numpy as np
import importlib.metadata
import subprocess
import os
import shutil
import time
print(importlib.metadata.version("moku"))

print(
    subprocess.run(
        ["mokucli", "--version"],
        capture_output=True,
        text=True
    ).stdout
)

path = shutil.which("mokucli")
print(path)

os.environ["MOKU_CLI_PATH"] = path

address = '[fe80::7269:79ff:feb9:7b5e]'
dl = Datalogger(address, force_connect=True)
# Start streaming samples
dl.start_streaming(
    duration = 10,
    sample_rate = 10,
)
print(dl.get_stream_status())
time.sleep(1)
try:
    data = dl.get_stream_data()
    print(data)
except Exception as e:
    import traceback
    traceback.print_exc()
