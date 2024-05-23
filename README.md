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
