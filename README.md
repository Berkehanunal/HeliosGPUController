# Helios version: 2.0


This is the code for the Helios GPU Controller

Developers:

Lasse Müller, Bao Tran Nguyen, Berkehan Ünal

## Usage
### Requirements
Our solution was developed using Python. To run the software, these are the prerequisites:
* Operating system distribution of Windows or Linux
* Python >=3.8
* Preferably a virtual environment

### Installation of Software and Dependencies
A development copy of the project's repository or software can be created using the following command.
```
$ git clone https://github.com/automl-private/MLProject_Mueller-Nguyen-Uenal_Helios
```

To include the package into a virtual environment directly, consider installing with:
```
$ pip install HeliosGPUController

Include in the code: from helios_gpu_controller.HeliosGPUController import HeliosGPUController
```

## Config File ##
An example config file can be found in src/helios_gpu_controller/conf.yaml
These are the configuration parameters

* use_helios_on_init: If set to false, GPU throttling won't be enabled by instantiating HeliosGPUController, but only with calling throttle_gpu() method
* devices: List of all devices that the HeliosGPUController has access to
* min_clock_speed_percent: minimum GPU clock frequency in percent. Helios recommendation: 0.5. Going higher than 0.5 reduces Helios' effectiveness.
* update_rate: Update Rate in minutes. The update rate determines, how often the GPU clock frequency is updated.
* using_solar_panels: Enable Helios solar
* avg_power_consumption_per_year: Average power consumption of your household. In kWh
* max_power_of_home_pc: Maximum power consumption of your computer. In Watts
* declination: Declination of your solar panels
* azimuth: Azimuth of your solar panels. 0 - south, 90 - west, 180 - north, 270 - east
* peak_kw: Peak Output of your photovoltaic system
* need_user_permission: if set to true, prompt a permission window, before Helios reduces your GPU frequency

## Code Execution ##
Helios GPU controller runs in a subprocess and does not interfere with the main program loop. When use_helios_on_init is set to True, the Controller is executed automatically on init.
To run Helios, use the following code snippets:

When use_helios_on_init is set to True:
```
Execute: gpu_controller = HeliosGPUController("conf.yaml")
After the program finishes: gpu_controller.stop_helios()
```

When use_helios_on_init is set to False:
```
Execute: gpu_controller = HeliosGPUController("conf.yaml")
To throttle GPU manually: gpu_controller.throttle_gpu()
After the program finishes: gpu_controller.stop_helios()
```

## License ##

This project is licensed under the [MIT License](./LICENSE).

```
 _   _         _                       ___    ___    _   _     ___                  _                _    _                
( ) ( )       (_ )  _                 (  _`\ (  _`\ ( ) ( )   (  _`\               ( )_             (_ ) (_ )              
| |_| |   __   | | (_)   _     ___    | ( (_)| |_) )| | | |   | ( (_)   _     ___  | ,_) _ __   _    | |  | |    __   _ __ 
|  _  | /'__`\ | | | | /'_`\ /',__)   | |___ | ,__/'| | | |   | |  _  /'_`\ /' _ `\| |  ( '__)/'_`\  | |  | |  /'__`\( '__)
| | | |(  ___/ | | | |( (_) )\__, \   | (_, )| |    | (_) |   | (_( )( (_) )| ( ) || |_ | |  ( (_) ) | |  | | (  ___/| |   
(_) (_)`\____)(___)(_)`\___/'(____/   (____/'(_)    (_____)   (____/'`\___/'(_) (_)`\__)(_)  `\___/'(___)(___)`\____)(_)                                                                                                                                                                                                                                                
```
