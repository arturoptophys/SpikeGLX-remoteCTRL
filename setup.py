from setuptools import setup, find_packages


setup(
    name="spikeglx_remote",
    version='0.3.0',
    description=f'Python based-remote control for SpikeGLX recording software. '
                f'Needs to run on a Windows computer, on same computer or network as SpikeGLX.'
                f'Enables receiving and sending commands from other python processes over socket network to control '
                f'SpikeGLX acquisition.',
    url=f"https://github.com/Optophys-Lab/SpikeGLX-remoteCTRL",
    author='Artur Schneider',
    python_requires=">=3.9",
    packages=find_packages(include=["spikeGLX_remote"], exclude=["docs" ".github"]),
    install_requires=[],
    extras_require={"GUI": [
        "pyqt6 == 6.4.2"
    ]},
)