
#!/usr/bin/python
import serial
import time
import json
import sys
import glob
import mysql.connector
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# VARIABLES TO CALIBRATE-----------------------------------------------------------

# email stuff
sender_email = 'XXXXX@gmail.com'
receiver_email = 'XXXX@gmail.com'
sender_password = 'XXXX-XXXX-XXXX'
email_server = 'smtp.gmail.com'
port = 587

# air temperature range in celcius?
high_air_temp = 9
low_air_temp = 1

# humidity range
high_humid = 9
low_humid = 1

# water temperature range in celcius?
high_wat_temp = 9
low_wat_temp = 1

# electroconductivity range
high_ec = 9
low_ec = 1

# PH range
high_ph = 9
low_ph = 1

# low water reading
# should be set that above this value means there is enough water and below means its time for a refill
water_level = 1

# light threshhold (used to verify if the lights are on or off? if not remove code from light_switch method)
# should be set that above this value means lights are on and below this value means lights are off
light_thresh = 4


# END VARIABLES TO CALIBRATE--------------------------------------------------------

#database login
def db_insert(varAirTemp, varHumidity, varUV, varWaterTemp, varPH, varEC, varWaterLevel):
    #table used is named data
    green_basement = mysql.connector.connect(
        host='localhost',
        user='root',
        password='farmDB',
        database='green_basement'
        )
    db_writer = green_basement.cursor()
        #code to write sensed vals to database
    vTStamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db_writer.execute("""INSERT INTO data (tstamp, air_temp, humidity, uv, water_temp, ph, ec, water_level) VALUES (%s, %s,%s,%s,%s,%s,%s,%s)""", (vTStamp, varAirTemp, varHumidity, varUV, varWaterTemp, varPH, varEC, varWaterLevel))
    green_basement.commit()
    db_writer.close()
    green_basement.close()
    print('Database updated!')

def discover_port():

    print('Discovering ports...')
    
    #port scanner found on stack overflow
    #makes a list of usable port names on the machine, OS agnostic
    if sys.platform.startswith('win'):
        my_ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        my_ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        my_ports = glob.glob('/dev/cu.*')
    else:
        raise EnvironmentError('Unsupported platform')

    ports = []
    for port in my_ports:
        try:
            s = serial.Serial(port)
            s.close()
            ports.append(port)
        except (OSError, serial.SerialException):
            pass
    # end stack overflow port scan section
        
    # my stuff for the port scan
    found = False
    sync_message = 'Old MacDonald'
    ack_message = 'had a farm'
    loop_count = 0
    
    while not found:
        for i in ports:
            loop_count += 1
            if (loop_count > 3):
                send_email('Arduino not found', 'There was an error finding the growth station on any port. No communication was established. Any scheduled scripts were terminated')
                quit()
            else:
                print('\nTesting connection on port ' + i)
                try:
                    ser = serial.Serial(port=i, baudrate='9600', timeout=2, write_timeout=1)
                    # let arduino reboot
                    time.sleep(5)
                    # send our handshake key
                    ser.write(sync_message.encode('utf-8'))
                    time.sleep(1)
                    # get the response from arduino' serial
                    handshake = ser.readline().decode().strip()
                    print(sync_message)
                    print(handshake)
                except:
                    print('- Connection not found on port ' + i)
                    break
                if (handshake == ack_message):
                    # if it matches, break the for loop and exit the while loop
                    print('- Arduino found on port ' + i + '! Initalizing...')
                    found = True
                    break
                else:
                    print('- Connection not found on port ' + i)
    return ser

#used to format messages sent to Arduino across serial
message = {
    'sensor': '',
    'value': ''
}

#request what sensor is read on Arduino
def read_sensor(sensor, ser):
    message['sensor'] = sensor
    to_arduino = json.dumps(message)
    ser.write(to_arduino.encode('utf-8'))
    received = ser.readline().decode().strip()
    result = json.loads(received)
    check_values(result)
    time.sleep(1)
    return float(result['value'])

#turn lights on and off
def light_switch(relay, value, ser):
    message['sensor'] = relay
    message['value'] = value
    to_arduino = json.dumps(message)
    ser.write(to_arduino.encode('utf-8'))
    received = ser.readline().decode().strip()
    time.sleep(1)

    # remove if this isn't what UV is for?-------------------------------------
    lights = read_sensor('lightCheck', ser)
    if ((message['value'] == float(1)) & (lights < float(light_thresh))):
        send_email('LIGHTS DIDN\'T TURN ON', 'Lights were supposed to turn on and didn\'t')
    elif ((message['value'] == float(0)) & (lights > float(light_thresh))):
        send_email('LIGHTS DIDN\'T TURN OFF', 'Lights were supposed to turn off and didn\'t')
    # end stuff to remove------------------------------------------------------
    
    return received

#run water pump for X length
def run_pump(pump_time, ser):
    message['sensor'] = 'pump'
    message['value'] = float(pump_time) * 1000
    to_arduino = json.dumps(message)
    ser.write(to_arduino.encode('utf-8'))
    received = ser.readline().decode().strip()
    result = json.loads(received)
    print('PUMP TIME: ' + str(float(result['value']) / 1000))
    time.sleep(pump_time)
    received = ser.readline().decode().strip()
    return received

#send an email if parameter fails
def send_email(subject, body):
    mail = MIMEMultipart()
    mail['From'] = sender_email
    mail['To'] = receiver_email
    mail['Subject'] = 'Trouble on the farm: ' + subject
    mail.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(email_server, port)
        server.starttls()
        
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, mail.as_string())

        print('Warning email sent: ' + subject)
    except:
        print('Email not sent')
    finally:
        server.quit()

# code to check readings and trigger emails
def check_values(reading):

    if ((reading['sensor'] == 'airTemp') & (float(reading['value']) < low_air_temp)):
        subject = 'TEMP LOW'
        body = f'The air temp is {reading["value"]}, which is below the recommended temp of {low_air_temp}'
        send_email(subject, body)
    elif ((reading['sensor'] == 'airTemp') & (float(reading['value']) > high_air_temp)):
        subject = 'TEMP HIGH'
        body = f'The air temp is {reading["value"]}, which is above the recommended temp of {high_air_temp}'
        send_email(subject, body)
        
    elif ((reading['sensor'] == 'humidity') & (float(reading['value']) < low_humid)):
        subject = 'HUMIDITY LOW'
        body = f'The humidity temp is {reading["value"]}, which is below the recommended humidity of {low_humid}'
        send_email(subject, body)
    elif ((reading['sensor'] == 'humidity') & (float(reading['value']) > high_humid)):
        subject = 'HUMIDITY HIGH'
        body = f'The humidity temp is {reading["value"]}, which is above the recommended humidity of {high_humid}'
        send_email(subject, body)
        
    elif ((reading['sensor'] == 'waterTemp') & (float(reading['value']) < low_wat_temp)):
        subject = 'WATER TEMP LOW'
        body = f'The water temp is {reading["value"]}, which is below the recommended temp of {low_wat_temp}'
        send_email(subject, body)
    elif ((reading['sensor'] == 'waterTemp') & (float(reading['value']) > high_wat_temp)):
        subject = 'WATER TEMP HIGH'
        body = f'The water temp is {reading["value"]}, which is above the recommended temp of {high_wat_temp}'
        send_email(subject, body)
        
    elif ((reading['sensor'] == 'EC') & (float(reading['value']) < low_ec)):
        subject = 'EC LOW'
        body = f'The electroconductivity is {reading["value"]}, which is below the recommended electroconductivity of {low_ec}'
        send_email(subject, body)
    elif ((reading['sensor'] == 'EC') & (float(reading['value']) > high_ec)):
        subject = 'EC HIGH'
        body = f'The electroconductivity is {reading["value"]}, which is above the recommended electroconductivity of {high_ec}'
        send_email(subject, body)

    elif ((reading['sensor'] == 'PH') & (float(reading['value']) < low_ph)):
        subject = 'PH LOW'
        body = f'The PH is {reading["value"]}, which is below the recommended PH of {low_ph}'
        send_email(subject, body)
    elif ((reading['sensor'] == 'PH') & (float(reading['value']) > high_ph)):
        subject = 'PH HIGH'
        body = f'The PH is {reading["value"]}, which is above the recommended PH of {high_ph}'
        send_email(subject, body)
        
    elif ((reading['sensor'] == 'waterLevel') & (float(reading['value']) < water_level)):
        subject = 'WATER LOW'
        body = f'The water level is {reading["value"]}, which is below the recommended water level of {water_level}'
        send_email(subject, body)

def main():

    #loop to find port of arduino
    #creates serial connection to be passed into other methods
    ser = discover_port()
    
    #get readings for each sensor
    varAirTemp = read_sensor('airTemp', ser)
    print(varAirTemp)
    varHumidity = read_sensor('humidity', ser)
    print(varHumidity)
    varUV = read_sensor('lightCheck', ser)
    print(varUV)
    varWaterTemp = read_sensor('waterTemp', ser)
    print(varWaterTemp)
    varPH = read_sensor('PH', ser)
    print(varPH)
    varEC = read_sensor('EC', ser)
    print(varEC)
    varWaterLevel = read_sensor('waterLevel', ser)
    print(varWaterLevel)

    db_insert(varAirTemp, varHumidity, varUV, varWaterTemp, varPH, varEC, varWaterLevel)
    
    #end readings to db code-------------------------------------------------------


    #copy these to seperate files to be run with a scheduler as needed
    
    #turn the lights on
    #args are which light, 1 for on, serial connection
    print(light_switch('light1', 1, ser))
    time.sleep(1)
    
    print(light_switch('light2', 1, ser))
    time.sleep(1)
    
    #turn the lights off
    #args are which light, 0 for on, serial connection
    print(light_switch('light1', 0, ser))
    time.sleep(1)
    print(light_switch('light2', 0, ser))
  
    #run the water pump cycle with feedback
    #argument is length of pump run in seconds
    print(run_pump(2, ser))

if __name__ == "__main__":
    main()
