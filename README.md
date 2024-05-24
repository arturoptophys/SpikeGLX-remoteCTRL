# SpikeGLX-remoteCTRL
SpikeGLX python remote controller

Python based-remote control for SpikeGLX recording software. Needs to run on a Windows computer, on same computer or 
network as SpikeGLX. Enables receiving and sending commands from other python processes over socket network to control
SpikeGLX acquisition.

SglxApi is provided by Bill Karsh <https://github.com/billkarsh/SpikeGLX-CPP-SDK> and is included in this repository.


## Installation guide
(Optional) Create and activate a conda environment

    conda env create -n spike_glx_remote python=3.11
    conda activate spike_glx_remote

Install the following python packages (preferably in a virtual environment):

    git clone https://github.com/arturoptophys/SpikeGLX-remoteCTRL
    cd spikeGLX-remoteCTRL
    pip install -e .[GUI] # for GUI support
    #or
    pip install -e . # for CLI only

## Usage
There are 2 main ways to use this package: GUI and CLI. GUI may be more user-friendly, but requires PyQT6 dependencies.

### GUI
To start the GUI, run:
```bash
python -m spikeGLX_remote.spikeGLXremote_GUI
```
### CLI
To start the CLI, run:
```bash
python -m spikeGLX_remote.spikeGLXremote_ctrl
```
in this mode you can remotely connect to the server via sockets and transmit commands to SpikeGLX. For remote control,
see [here](#remote-control-via-sockets).

The CLI can also be used as a python module, for example:
```python
from spikeGLX_remote.spikeGLXremote_ctrl import SpikeGLX_Controller
ctrl = SpikeGLX_Controller()
ctrl.save_path = 'C:\\path\\to\\save\\data' # set path 2 where SpikeGLX will save the data (should be a path on 
# SpikeGLX computer)
ctrl.connect_spikeglx()
if ctrl.ask_is_initialized():
    ctrl.session_id = 'TestRecording' # set session name
    ctrl.start_run()
    ctrl.start_recording()

ctrl.stop_recording()    # stop recording
ctrl.disconnect_spikeglx() # disconnect from SpikeGLX
```


## Remote control via sockets