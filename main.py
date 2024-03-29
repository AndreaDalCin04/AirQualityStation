# Module Imports



import requests
import ST7735
from bme280 import BME280
from enviroplus import gas
from pms5003 import PMS5003, ReadTimeoutError, ChecksumMismatchError
import mariadb
import mysql.connector
import sys
import datetime
import pytz
import time
import math as m
from Noise import Noise

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

import logging
#format for the message that you see when a detection is made
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# Create I2C canal connection
bus = SMBus(1)

# Create BME280 instance
bme280 = BME280(i2c_dev=bus)

# Create PMS5003 instance
pms5003 = PMS5003()

# Set up sound settings
spl_ref_level = 0.000001 # Sets quiet level reference baseline for dB(A) measurements. alsamixer at 10
spl_thresholds = (70, 90)
log_sound_data = True # Set to True to log sound data for debugging
debug_recording_capture = False # Set to True for plotting each recording stream sample
#Noise object must be instanciated in the loop

#Antoinconstants for Water to calculate vapor pressure or boiling temperature
AntA=18.88579
AntB=-3994.017
AntC=233.874

# Calculate vapor pressure at T of water using Antoine equation
def pvap(T):
    pv=m.exp(AntA-(AntB/(T+AntC)))
    return pv

# Calculate boiling temperature of water using Antoine equation
def tboil(pres):
    tboil=AntB/(m.log(pres)-AntA)-AntC
    return tboil

# Function that read the values from the bme280, the pms5003 and the enviro board
def read_values():
    # Create array for contains values
    values = {}
    noise = Noise(spl_ref_level, log_sound_data, debug_recording_capture)
    # Get cpu temperature and external temperature
    cpu_temp = get_cpu_temperature()
    raw_temp = bme280.get_temperature()
    # Get the correct temperature adjusting raw temperature with the CPU temperature
    comp_temp = raw_temp - ((cpu_temp - raw_temp) /comp_factor)
    raw_humid = bme280.get_humidity()
    dew_point = tboil(raw_humid / 100 * pvap(raw_temp)) # humid is in %, devide by 100 to get factor 
    # Humidity correction 
    humidity = raw_humid * pvap(raw_temp) / pvap(comp_temp)
    # Get the detection and put it insiede the array
    values["temperature"] = int(comp_temp)
    values["air_pressure"] = int(bme280.get_pressure() * 100)
    values["humidity"] = int(humidity)
    values["Reducing"] = gas.read_reducing()
    values["Oxidising"] = gas.read_oxidising()
    values["NH3"] = gas.read_nh3()
    values["dBA"] = int(noise.spl())
    try:
        #valori random per testare quando non è collegato il rilevatore di pm

        # Get supported pollution type values
        #pm_values = pms5003.read()
        #values["PM1"] = int(pm_values.pm_ug_per_m3(1))
        values["PM1"] = 1
        #values["PM25"] = int(pm_values.pm_ug_per_m3(2.5))
        values["PM25"] = 25
        #values["PM10"] = int(pm_values.pm_ug_per_m3(10))
        values["PM10"] = 10
    except(ReadTimeoutError, ChecksumMismatchError):
        values["PM1"] = 1
        values["PM25"] = 25
        values["PM10"] = 10
        #logging.info("Failed to read PMS5003. Reseting and retrying.")
        #pms5003.reset()
        #pm_values = pms5003.read()
        #values["PM1"] = int(pm_values.pm_ug_per_m3(1))
        #values["PM25"] = int(pm_values.pm_ug_per_m3(2.5))
        #values["PM10"] = int(pm_values.pm_ug_per_m3(10))
    return values


# cretae the function to get the temperature of the CPU for compensation
def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp
        
# Compensation factor for temperature
comp_factor = 2.8

# Main loop to read data, display, and send to Database
while True:
    try:
        # Create connection to Database
        mydb = mysql.connector.connect(
            user="MS12486_aqs",
            password="Arianetta!_23",
            host="hostingmysql310.register.it",
            port=3306,
            database="airqualitystation",
            #use_pure=True
        )
        
    except mariadb.Error as e:
        print(f"Error connecting to MariaDB Platform: {e}")
        sys.exit(1)

    # Create a cursor to write on database
    mycursor = mydb.cursor()
    i=0
    # SQL query creation and execution
    try:
        logging.warning(bme280.get_pressure())
        values = read_values()
        # Get the timezone of our area
        now = datetime.datetime.now(pytz.timezone("Europe/Rome"))
        # For hour with *:00:00 delete %M and %S 
        formatted_date = now.strftime('%Y-%m-%d %H:%M:%S')
        logging.info(values)
        # Create the query for the database 
        sql = "INSERT INTO readings (date_time, pm1, pm25, pm10, temperature, humidity, air_pressure, no2, co, nh3, dBA, luogo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        val = (formatted_date, values['PM1'], values['PM25'], values['PM10'], values['temperature'], values['humidity'], values['air_pressure'], values['Oxidising'], values['Reducing'], values['NH3'], values['dBA'], "ITT Città della Vittoria")
        # Execute the SQL query
        mycursor.execute(sql, val)
        #Confirm the changes in the dataabse are made correctly
        mydb.commit()
        print("query fatta")
    except Exception as e:
        logging.warning('Main Loop Exception: {}'.format(e))

    # Close cursor and databese connection for internet saving
    mycursor.close()
    mydb.close()

    # Wait the time for the next detection
    time.sleep(300)
