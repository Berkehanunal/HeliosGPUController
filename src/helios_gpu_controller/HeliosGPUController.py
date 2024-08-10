import math
import subprocess
import threading
import time
import datetime as dt
from datetime import datetime
import multiprocessing
import yaml
from .utils import get_electricity_mix, is_location_in_germany, get_pv_kwh, gpu_set_clocks, \
    gpu_reset_clocks, get_default_device, has_admin_privileges


class HeliosGPUController:

    def __init__(self, config_file):
        has_admin_privileges()

        self.config = self.read_config(config_file)

        # Conf parameters
        self.use_helios_on_init: bool = self.config["helios"]["use_helios_on_init"]
        self.devices = self.config["helios"]["devices"]
        self.min_clock_speed_percent: float = self.config["helios"]["min_clock_speed_percent"]
        self.update_rate: int = self.config["helios"]["update_rate"]

        # Conf parameters solar power
        self.using_solar_panels: bool = self.config["solar"]["using_solar_panels"]
        self.avg_power_consumption_per_year: float = self.config["solar"]["avg_power_consumption_per_year"]
        self.max_power_of_home_pc: float = self.config["solar"]["max_power_of_home_pc"]
        self.declination: float = self.config["solar"]["declination"]
        self.azimuth: int = self.config["solar"]["azimuth"]
        self.peak_kw: float = self.config["solar"]["peak_kw"]

        # Other conf parameters
        self.need_user_permission: bool = self.config["other"]["need_user_permission"]

        # Program parameters
        self.use_helios = False  # User permission needed to throttle GPU
        self.min_update_rate = 15  # minimum update rate in minutes
        self.avg_power_consumption_per_quarter_hour: float = self.avg_power_consumption_per_year / 8760 / 4
        self.last_time_updated = None
        self.helios_stopped = multiprocessing.Event()
        self.electricity_mix = None
        self.renewable_energy_percentage = None

        if self.use_helios_on_init:
            # Ask for user permission
            if self.need_user_permission:
                self.get_user_permission()
            else:
                self.use_helios = True

            # Throttle GPU
            if self.use_helios:
                # Get data from API
                self.run_dynamic_gpu_throttle(self.update_rate)

    def __del__(self):
        self.unthrottle_gpu()

    def stop_helios(self):
        """Stop the Helios GPU controller and unthrottle GPU."""
        self.helios_stopped.set()
        self.unthrottle_gpu()

    def run_dynamic_gpu_throttle(self, update_rate=15):
        """Dynamically updates the GPU throttle every {update_rate} minutes. Runs in a different Thread.

        Args:
            update_rate (int) : How often to update the GPU throttle.

        Returns:
            None
        """
        # thread = threading.Thread(target=self.__dynamic_gpu_throttle(update_rate), args=())
        # thread.daemon = True
        # thread.start()

        p = multiprocessing.Process(target=self.dynamic_gpu_throttle, args=(self.helios_stopped, update_rate,))
        p.start()

    def dynamic_gpu_throttle(self, stop_event, update_rate=15):
        """
        Dynamically updates the GPU throttle every {update_rate} minutes. Do not call this function directly! Use run_dynamic_gpu_throttle instead

        Args:
            update_rate (int) : How often to update the GPU throttle.
            stop_event (threading.Event) : Stop HeliosGPUController

        Returns:
            None
        """
        if update_rate < self.min_update_rate:
            update_rate = self.min_update_rate

        while not stop_event.is_set():
            current_time = datetime.now()

            if self.last_time_updated is None or current_time - self.last_time_updated > dt.timedelta(minutes=update_rate):
                print(f"Updating the GPU Throttle")
                self.electricity_mix = get_electricity_mix()
                self.renewable_energy_percentage = self.get_renewable_energy_percentage()
                self.throttle_gpu()
                self.last_time_updated = current_time

            time.sleep(10)  # Sleep for 10s. necessary?

    def throttle_gpu(self):
        """Apply the calculated Throttle to the GPU."""
        physical_device = get_default_device()
        if physical_device:
            gpu_throttle = self.predict_gpu_throttle()
            print(f"predicted GPU throttle: {gpu_throttle}")
            set_clocks = gpu_set_clocks(gpu_throttle)
            print(f"GPU clocks have been set to: {set_clocks}")
            print(f"Doublecheck: {subprocess.check_output(['nvidia-smi', '-q', '-d', 'CLOCK']).decode('utf-8')}")
        else:
            print("No GPUs available to throttle.\n")

    def unthrottle_gpu(self):
        """Unthrottle the GPU."""
        physical_device = get_default_device()
        if physical_device:
            reset_clocks = gpu_reset_clocks()
            print(f"GPU clocks have been reset to: {reset_clocks}")
        else:
            print(f"Cannot reset GPU clocks: GPU not found.\nTry manually resetting GPU clocks with the command 'nvidia-smi -lgc [your_max_gpu_clockspeed]'.")

    def predict_gpu_throttle(self):
        """
        Return the amount of GPU throttle to apply.

        Args:
            None

        Returns:
            gpu_throttle (float): amount of GPU throttle to apply in percent
        """
        max_throttle = 1 - self.min_clock_speed_percent
        linear_throttle = self.renewable_energy_percentage
        print(f"linear throttle: {linear_throttle}")

        # y = 2.7396479125299 * x^2 - 2.1570599800969 * x + 0.4039163800523

        p = -2.1570599800969/2.7396479125299
        q = (0.4039163800523- linear_throttle)/2.7396479125299
        x1 = - (p / 2) - math.sqrt((p / 2) ** 2 - q)
        x2 = - (p / 2) + math.sqrt((p / 2) ** 2 - q)
        if x1 >= x2:
            gpu_throttle = x1
        elif x2 >= x1:
            gpu_throttle = x2
        if gpu_throttle > 1:
            return 1.0
        if gpu_throttle < max_throttle:
            return max_throttle
        return round(gpu_throttle,2)

    def get_renewable_energy_percentage(self) -> float:
        """Calculate the amount of renewable energy in percent, that is available to the GPU.

        Depending on the parameters 'is_location_in_germany' and 'is_using_solar_panels', the amount of renewable energy gets calculated differently.

        Args:
            None

        Returns:
            percentage_renewable_energy (float): amount of renewable energy in percent
        """
        # ToDo: rewrite code, so it calculates the power consumption and not assuming its always max
        print(f"average power usage per quarter hour: {round(self.avg_power_consumption_per_quarter_hour * 1000, 0)} Wh")

        # Mode 1: Nutzer nutzt Solarstrom und befindet sich in DE
        if self.using_solar_panels and is_location_in_germany():
            solar_kwh_produced = get_pv_kwh(self.declination, self.azimuth, self.peak_kw)
            kilo_watt_hours_consumed_by_pc = self.max_power_of_home_pc / (60 / 15) / 1000
            print(f"max KWh consumed by PC per quarter hour: {kilo_watt_hours_consumed_by_pc}")
            percentage_solar_power = solar_kwh_produced / (self.avg_power_consumption_per_quarter_hour + kilo_watt_hours_consumed_by_pc)
            if percentage_solar_power > 1:
                return 1
            else:
                percentage_power_grid = 1 - percentage_solar_power
                return self.electricity_mix * percentage_power_grid + 1 * percentage_solar_power

        # Mode 2: Nutzer nutzt keinen Solarstrom und befindet sich in DE
        elif not self.using_solar_panels and is_location_in_germany():
            return self.electricity_mix

        # Mode 3: Nutzer nutzt Solarstrom und befindet sich nicht in DE
        elif self.using_solar_panels and not is_location_in_germany():
            solar_kwh_produced = get_pv_kwh(self.declination, self.azimuth, self.peak_kw)
            kilo_watt_hours_consumed_by_pc = self.max_power_of_home_pc / (60 / 15) / 1000
            percentage_solar_power = solar_kwh_produced / (self.avg_power_consumption_per_quarter_hour + kilo_watt_hours_consumed_by_pc)
            if percentage_solar_power > 1:
                return 1
            else:
                return percentage_solar_power

        # Mode 4: Nutzer nutzt keinen Solarstrom und befindet sich nicht in DE
        elif not self.using_solar_panels and not is_location_in_germany():
            print("Helios is not available, because there is no publicly available power grid data in your region")
            return 0

    def get_user_permission(self, timeout=15):
        """Get user permission for using Helios

        Args:
            timeout (int, optional): How long to wait until the program breaks automatically. Defaults to 15

        Returns:
            percentage_renewable_energy (float): amount of renewable energy in percent
        """
        start_time = time.time()

        while True:
            user_input = input(
                f"\nYour energy mix consists of {round(self.renewable_energy_percentage * 100, 1)}% renewable sources at the moment.\nYour GPU clock speed will be reduced to ~{round(self.predict_gpu_throttle() * 100, 1)}%? Do you want to use Helios for this task? (yes/no): ")

            if user_input.lower() == "yes":
                # Perform the desired action here
                print("Helios GPU Controller will be used.\n")
                self.use_helios = True
                break

            elif user_input.lower() == "no":
                print("Not Using the Helios GPU Controller...\n")
                self.use_helios = False
                break

            else:
                print("Invalid input. Please enter 'yes' or 'no'.")

            if time.time() - start_time > timeout:
                print("Timeout! No input received in 15 seconds.")
                self.use_helios = False
                break

    @staticmethod
    def read_config(config_file):
        with open(config_file, "r") as yamlfile:
            config = yaml.load(yamlfile, Loader=yaml.FullLoader)
        return config
