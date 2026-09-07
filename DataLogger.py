import sys

def DataLogger(stop_event,q3,fname):
    '''
    Log data to file in own process

    Returns
    -------
    None.

    '''
    while not stop_event.is_set():
        # Iterate data queue until empty
        while not q3.empty():
            # Get data from measurement thread
            data = q3.get_nowait()
            # write data to file
            with open(fname,'a+') as f:
                # Write every row in data
                for di in data:
                    f.write(" ".join(str(item) for item in di))
                    f.write("\n")
    print('Logging stopped')
    sys.exit()