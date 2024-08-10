import ctypes
import os
import platform
import subprocess
import re
import datetime
import requests
import json
import geocoder
import pytz
import numpy as np
import matplotlib.pyplot as plt

from datetime import datetime
from timezonefinder import TimezoneFinder
from suntime import Sun
from geopy.geocoders import Nominatim


last_time_called = datetime.now()
api_cache = {}
debug = True


def is_daytime():
    """Check if the current time is within the daytime period based on the observer's location.

    Args:
        None

    Returns:
        is_daytime (bool): True if the current time is within the daytime
    """
    # Set the latitude and longitude of the observer's location
    latitude, longitude = get_location_lat()

    # Create a Sun object for the observer's location
    sun = Sun(latitude, longitude)

    # Get the sunrise and sunset times
    sunrise = sun.get_local_sunrise_time()
    sunset = sun.get_local_sunset_time()

    print("Sunrise time:", sunrise)
    print("Sunset time:", sunset)

    utc_now = datetime.utcnow()
    local_timezone = pytz.timezone('CET')  # Replace 'Your_Time_Zone' with the actual time zone
    local_now = utc_now.replace(tzinfo=pytz.utc).astimezone(local_timezone)
    return sunrise < local_now < sunset


def plot_electricity_mix(data, filters, x_total, y_total, last_common_index):
    """Retrieve the electricity mix data for renewable energy sources.

    Args:
        data (pd.DataFrame):
        filters (list): List of
        x_total (list):
        y_total (list):
        last_common_index (int):

    Returns:
        None
    """
    plt.figure(figsize=(10, 6))

    # Plot data for each filter except "Generation: Total (Grid Load)"
    for filter_id, filter_label in filters.items():
        x, y = [], []
        for timestamp, value in data[filter_id]["series"]:
            timestamp = datetime.fromtimestamp(int(timestamp) / 1000)
            if value is None:
                break
            x.append(timestamp)
            y.append(value)
        plt.plot_date(x, y, "-", label=filter_label)

    plt.plot_date(x_total[:last_common_index], y_total[:last_common_index], "-", label="All Renewable Sources")

    # Set labels and title
    plt.xlabel("Timestamp")
    plt.ylabel("Generation in MWh / 15min")
    plt.title("Renewable Energy Generation")

    # Add grid
    plt.grid(True)

    # Adjust legend position and prevent overlap
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    # Show the plot
    plt.tight_layout()

    plt.show()


def get_electricity_mix(show_electricity_mix=False) -> float:
    """Retrieve the electricity mix data for renewable energy sources.

    Args:
        show_electricity_mix (bool, optional): Whether to plot the electricity mix or not. Defaults to False

    Returns:
        percentage_renewable (float): The percentage of renewable energy in the power grid.
    """
    # https://github.com/bundesAPI/smard-api
    filter = "410"
    region = get_power_grid_region()
    if region is None:
        region = "DE"
    resolution = "quarterhour"
    percentage_renewable = 0

    # Get the index of available hours
    index_hours_response = requests.get(
        f"https://www.smard.de/app/chart_data/{filter}/{region}/index_{resolution}.json")
    index_hours = json.loads(index_hours_response.text)
    last_element = index_hours['timestamps'][-1]

    # Fetch data for each filter
    filters = {
        "410": "Generation: Total (Grid Load)",
        "1225": "Generation: Wind Offshore",
        "4067": "Generation: Wind Onshore",
        "1226": "Generation: Hydropower",
        "4068": "Generation: Photovoltaic",
        "1228": "Generation: Other Renewables"
    }

    if region == "Amprion" or region == "TransnetBW":
        filters.pop("1225")

    data = {}
    for filter_id, filter_label in filters.items():
        data_response = requests.get(
            f"https://www.smard.de/app/chart_data/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{last_element}.json")
        try:
            data[filter_id] = data_response.json()
        except json.decoder.JSONDecodeError:
            print(f"Error decoding JSON for filter: {filter_label}")

    # Calculate the total renewable energy generation
    x_total, y_total = [], []
    timestamps = data["410"]["series"]
    min_length = min(len(data[filter_id]["series"]) for filter_id in filters.keys() if filter_id != "410")

    for i in range(min_length):
        total_generation = sum(
            data[filter_id]["series"][i][1] if data[filter_id]["series"][i][1] is not None else 0 for filter_id in
            filters.keys() if filter_id != "410")
        timestamp = datetime.fromtimestamp(int(timestamps[i][0]) / 1000)
        x_total.append(timestamp)
        y_total.append(total_generation)

    last_common_index = np.argmin(
        np.array([y_total[i] for i in range(len(y_total)) if y_total[i] is not None and y_total[i] != 0]))

    last_valid_element = get_last_valid_element(data["410"]["series"])
    total_grid_load = last_valid_element[-1]

    total_renewable_generation = y_total[last_common_index - 1]

    print(f"{round(float(total_renewable_generation)/float(total_grid_load)*100,1)} % renewable,total renewable: "
          f"{total_renewable_generation} MWh, total total_grid_load: {total_grid_load} MWh")

    if total_grid_load is not None and total_renewable_generation is not None and total_grid_load != 0:
        percentage_renewable = (total_renewable_generation / total_grid_load)

        if percentage_renewable > 1:
            percentage_renewable = 1
    else:
        print("Unable to calculate the percentage due to missing or zero data.")
        percentage_renewable = .05

    # Plot the electricity mix
    if show_electricity_mix:
        plot_electricity_mix(data, filters, x_total, y_total, last_common_index)
    return round(percentage_renewable, 3)


def get_last_valid_element(data):
    """Get the last valid element in a dataset."""
    for item in reversed(data):
        if item[1] is not None:
            return item


def get_location_lat():
    """Get the current latitude and longitude based on the IP address.

    Args:
        None

    Returns:
        Latitude (float): The current latitude
        Longitude (float): The current longitude
    """
    location = geocoder.ip('me')
    if location is not None:
        latitude, longitude = location.latlng
        return latitude, longitude
    else:
        print("Unable to retrieve the location.")
        return 50, 2


def is_location_in_germany():
    geolocator = Nominatim(user_agent="HeliosGPUController")
    latitude, longitude = get_location_lat()
    location = geolocator.reverse(f"{latitude}, {longitude}")
    country = location.raw['address'].get('country', '')
    if country == "Deutschland":
        return True
    return False


def get_power_grid_region():
    """Germany is divided into four power grid regions: TenneT, Amprion, 50Hertz, TransnetBW. Returns the users power grid region
    Args:
        None

    Returns:
        power_grid_region (string): The power grid region of the user.
        """
    def find_element_in_lists(element, lists):
        for list_name, lst in lists.items():
            if element in lst:
                return list_name
        return None

    tennet = ["Niedersachsen", "Bremen", "Hessen", "Bayern"]
    amprion = ["Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland"]
    fuenfzig_hertz = ["Hamburg", "Mecklenburg-Vorpommern", "Sachsen-Anhalt", "Thüringen", "Brandenburg", "Sachsen",
                      "Berlin"]
    transnet_bw = ["Baden-Württemberg"]
    power_grid_regions = {'TenneT': tennet, 'Amprion': amprion, '50Hertz': fuenfzig_hertz, 'TransnetBW': transnet_bw}

    geolocator = Nominatim(user_agent="HeliosGPUController")
    latitude, longitude = get_location_lat()
    location = geolocator.reverse(f"{latitude}, {longitude}")
    state = location.raw['address'].get('state', '')
    power_grid_region = find_element_in_lists(state, power_grid_regions)

    print(f"state: {state}, power grid region: {power_grid_region}")

    return power_grid_region


def get_timezone_from_coords(latitude, longitude):
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=latitude, lng=longitude)

    # Convert to "etc" format
    if timezone_str:
        timezone = pytz.timezone(timezone_str)
        etc_format = timezone.zone
        return etc_format
    else:
        return None


def get_pv_kwh(declination, azimuth, peak_kw):
    """
    Returns the PV generated Kilowatt-hours from the last hour

    Args:
        declination (float): Declination in degrees
        azimuth (float): Azimuth in degrees
        peak_kw (float): Peak power in kW

    Returns:
        pv_kwh (float): PV generated Kilowatt-hours in the last quarter hour
    """
    latitude, longitude = get_location_lat()
    url = f"https://api.forecast.solar/estimate/watthours/period/{latitude}/{longitude}/{declination}/{azimuth}/{peak_kw}"
    current_time = datetime.now()

    make_api_call(url, "get")
    solar_data = api_cache[url]

    # solar_data = response.json()
    # solar_data = example_json

    datetime_objects_dict = solar_data["result"]

    datetime_objects = [(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))
                        for dt in datetime_objects_dict.keys()]

    last_dt_obj = datetime.now()
    for dt in datetime_objects:
        if dt > current_time:
            watthours = solar_data["result"][dt.strftime('%Y-%m-%d %H:%M:%S')]
            print(f"An average of {watthours} Wh solar power was produced between {last_dt_obj} - {dt}")
            timeframe = (dt - last_dt_obj).total_seconds() / 60.0
            if timeframe > 15:
                return (watthours/(timeframe/15)) / 1000
            return watthours / 1000
        last_dt_obj = dt

    return 0


def make_api_call(url, method):
    if debug:
        api_cache[url] = example_json
        return None

    current_time = datetime.now()
    if current_time - last_time_called > datetime.timedelta(minutes=15) or not api_cache:
        print(f"making api call for {url}")
        if method == "get":
            response = requests.get(url)
            api_cache[url] = response.json()
        elif method == "post":
            response = requests.post(url)
            api_cache[url] = response.json()

def gpu_get_power():
    command= "nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits"
    result= subprocess.run(command,capture_output=True, text=True, shell=True)
    power_output=result.stdout.strip()
    power_watts=float(power_output)
    return power_watts

def gpu_get_max_clocks():
    output = subprocess.check_output(['nvidia-smi', '-q', '-d', 'CLOCK']).decode('utf-8')
    max_output = output[840:1070]
    pattern = r'(?P<name>\w+)\s+:\s+(?P<value>\d+)\sMHz'
    max_clocks = {match.group('name'): int(match.group('value')) for match in re.finditer(pattern, max_output)}
    return max_clocks

def gpu_set_clocks(throttle):
    output = subprocess.check_output(['nvidia-smi', '-q', '-d', 'CLOCK']).decode('utf-8')
    max_output = output[840:1070]
    pattern = r'(?P<name>\w+)\s+:\s+(?P<value>\d+)\sMHz'
    clock_speeds = {match.group('name'): int(match.group('value')) for match in re.finditer(pattern, max_output)}

    newggraphics_clocks = int(clock_speeds['Graphics'] * throttle)
    setcommand = "nvidia-smi -lgc " + str(newggraphics_clocks)
    set_clocks = subprocess.run(setcommand, capture_output=True, text=True, shell=True)
    return set_clocks

def gpu_reset_clocks():
    reset_clocks = gpu_set_clocks(1)
    return reset_clocks

def get_default_device():
    """Pick GPU if available, else CPU"""
    try:
        subprocess.check_output('nvidia-smi')
        return 1
    except Exception:  # this command not being found can raise quite a few different errors depending on the configuration
        print("No GPU available. Make sure you have a GPU and appropriate drivers installed.")
        return None

def has_admin_privileges():
    system = platform.system()
    if system == "Windows":
        if not ctypes.windll.shell32.IsUserAnAdmin():
            exit("You need to have Administrator status to run Helios.\nPlease try again, this time launching the process as Administrator. Exiting.")
    elif system == "Linux":
        if os.geteuid() != 0:
            exit("You need to have root privileges to run Helios.\nPlease try again, this time using 'sudo'. Exiting.")
    else:
        exit("Your OS is not supported by Helios.")
    print(f"Success!")

example_json = {
    "result": {
        "2024-01-29 07:29:00": 0,
        "2024-01-29 08:00:00": 406,
        "2024-01-29 18:00:00": 993,
        "2024-01-29 18:27:00": 117,
        "2024-01-30 07:31:00": 0,
        "2024-01-30 08:00:00": 216,
        "2024-01-30 14:00:00": 315,
        "2024-01-30 15:00:00": 447,
        "2024-01-30 18:00:00": 173,
        "2024-01-30 18:24:00": 27

    },
    "message": {
        "code": 0,
        "type": "success",
        "text": "",
        "info": {
            "latitude": 52,
            "longitude": 12,
            "distance": 0,
            "place": "L 51, Schora, Moritz, Zerbst/Anhalt, Anhalt-Bitterfeld, Sachsen-Anhalt, 39264, Deutschland",
            "timezone": "Europe/Berlin",
            "time": "2022-10-12T14:25:10+02:00",
            "time_utc": "2022-10-12T12:25:10+00:00"
        },
        "ratelimit": {
            "period": 3600,
            "limit": 12,
            "remaining": 10
        }
    }
}

