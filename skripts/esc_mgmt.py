import logging
import logging.handlers
import os
import socket
import pymysql
import sys
import time
import datetime
from pexpect import pxssh
import subprocess
from smsd import save_to_messages_db
from Start_Shutdown import shutdown_Rack

# set up logging
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/escd/escd.log', maxBytes=1000000, backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

max_temp_sms = 35.0
max_temp_shutdown = 45.0
max_temp_emergency = 50.0
max_hum = 70.0
interval = 30
max_rauch = 10

#Get Receiver
To = ""
rec = []
try:
    with open("/etc/smsd/recievers.list", mode='r') as recievers:
        for reciever in recievers:
            logging.info("Adding reciever: " + reciever)
            rec.append(reciever)
except Exception as tel:
    logging.error(tel)
    sys.exit()

# general path
path = "/var/spool/sms"
# find out local ip address (we want to tell the recievers the name of the system)
local = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [
    [(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in
     [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]
# header - figure out system name
sql = "select name from messsystem where ip = '%s';" % (local)
try:
    db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',
                         db='serverraum_temperaturueberwachung', autocommit=True)
    cursor = db.cursor()
    logging.info("Connected to database")
    logging.debug(sql)
    cursor.execute(sql)
    systemname = cursor.fetchone()[0]
    logging.info("SystemName is: " + systemname)
    db.close()
except Exception as e:
    logging.error(e)
    sys.exit()

isEmergency = False
isShutdownPhase = False

tempSens = []
smokeSens = []
waterSens = []
humSens = []

while True:
    silenced = []
    To = ""
    with open("/etc/smsd/sms.conf") as f:
        logging.info("Loaded configuration:")
        for line in f:
            key = line.split(':')[0]
            value = line.split(':')[1].strip()
            if key == "interval":
                interval = int(value)
                logging.info("interval: " + str(interval))
            if key == "silent":
                if value.split(" ")[0] == "True":
                    num = value.split(" ")[1].strip();
                    silenced.append(num)
                    logging.info("muted: " + num)
            if key == "max_temp_sms":
                max_temp_sms = float(value)
                logging.info("max_temp_sms: " + str(max_temp_sms))
            if key == "max_temp_shutdown":
                max_temp_shutdown = float(value)
                logging.info("max_temp_shutdown: " + str(max_temp_shutdown))
            if key == "max_temp_emergency":
                max_temp_emergency = float(value)
                logging.info("max_temp_emergency: " + str(max_temp_emergency))
            if key == "max_hum":
                max_hum = float(value)
                logging.info("max_hum: " + str(max_hum))
            if key == "max_smoke":
                max_rauch = value
                logging.info("max_smoke: " + str(max_rauch))

    for i in rec:
        if i not in silenced:
            To = To + f"To: {i}\n"

    up = To + "\nTemperaturüberwachung " + systemname + " Notfallsms:\n "

    try:
        now = datetime.datetime.now()
        nowf = now.strftime("%Y-%m-%d %H:%M:%S")
        past = (now - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        pastIntervall = now - datetime.timedelta(minutes=interval)
        past18 = now - datetime.timedelta(hours=18)
        tm = now + datetime.timedelta(days=1)
        yes = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        if To == "" and not datetime.datetime.fromtimestamp(os.stat("/home/pi/alive.txt").st_mtime) < past18:
            time.sleep(10)
            logging.info("muted")
            continue
        sms = up
        title = ""
        logging.info("try connecting to db")
        try:
            connection = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',
                                         db='serverraum_temperaturueberwachung', autocommit=True)
            cur = connection.cursor()
        except Exception as e:
            logging.error(e)
            continue

        if not len(os.listdir(path + '/checked/')) == 0:
            continue
        #cur.execute(
         #   "select avg(temp) as temp , avg(feucht) as feucht,  avg(wasser) as wasser , avg(rauch) as rauch, sensorName from web where zeit > '" + past + "' group by sensorName;")
        cur.execute("select sensorName from sensor;")
        results = cur.fetchall()
        temp = dict()
        hum = dict()
        smoke = dict()
        water = dict()
        normSmoke = ""
        normHum = ""
        normTemp = ""
        isTempEmergency = True
        isSmokeEmergency = True
        isWaterEmergency = True
        isHumEmergency = True
        isNewEmergency = False
        message = up

        #Daten der letzen 5 Min auslesen und nach Kategorie gruppieren
        for result in results:
            try:
                sens = result[0]
                cur.execute(
                    f"select temp , feucht,  wasser , rauch from web where zeit > '{past}' and sensorName = {sens};")
                valueResults = cur.fetchall()
                isTemp = False
                isHum = False
                isSmoke = False
                isWater = False
                data = []
                dataHum = []
                for vResult in valueResults:
                    if vResult[0] == None and vResult[1] == None and vResult[2] == None:
                        data.append(vResult[3])
                        isSmoke = True
                    elif vResult[0] == None and vResult[1] == None:
                        data.append(vResult[2])
                        isWater = True
                    elif vResult[1] == None:
                        data.append(vResult[0])
                        isTemp = True
                    else:
                        data.append(vResult[0])
                        dataHum.append([vResult[1]])
                        isTemp = True
                        isHum = True
                if isSmoke:
                    smoke[sens] = data
                elif isWater:
                    water[sens] = data
                elif isTemp and not isHum:
                    temp[sens] = data
                else:
                    temp[sens] = data
                    hum[sens] = dataHum
            except Exception as e:
                logging.error(e)
                continue

        #Überprüfen ob es einen Emergency gibt
        for sens in temp:
            values = temp[sens]
            for value in values:
                if value < max_temp_sms:
                    isTempEmergency = False
                    break
            if isTempEmergency:
                if len(tempSens) == 0:
                    isNewEmergency = True
                tempSens.append(sens)
                isEmergency = True
            isTempEmergency = True
        for sens in smoke:
            values = smoke[sens]
            for value in values:
                if value < max_rauch:
                    isSmokeEmergency= False
                    break
            if isSmokeEmergency:
                if len(smokeSens) == 0:
                    isNewEmergency = True
                smokeSens.append(sens)
                isEmergency = True
            isSmokeEmergency = True
        for sens in water:
            values = water[sens]
            for value in values:
                if value < 1:
                    isWaterEmergency = False
                    break
            if isWaterEmergency:
                if len(waterSens) == 0:
                    isNewEmergency = True
                waterSens.append(sens)
                isEmergency = True
            isWaterEmergency = True
        for sens in hum:
            values = hum[sens]
            for value in values:
                if value < max_hum:
                    isHumEmergency = False
                    break
            if isHumEmergency:
                if len(humSens) == 0:
                    isNewEmergency = True
                humSens.append(sens)
                isEmergency = True
            isHumEmergency = True

        #Emergencies in Message schreiben
        if len(tempSens) > 0:
            message += "Temperatur Emergencies:\n"
            for sens in temp:
                val = temp[sens][-1]
                if sens in tempSens:
                    message += f"Die Temperatur-Werte an Sensor {sens} sind außerhalb des Normalbereichs: {val}\n"
                else:
                    normTemp += f"Die aktuelle Temperatur am Sensor {sens} ist: {val}\n"
        if normTemp != "":
            normTemp = f"Aktuelle Temperaturwerte:\n{normTemp}\n"
        message += "\n"

        if len(smokeSens) > 0:
            message += "Rauch Emergencies:\n"
            for sens in smoke:
                val = smoke[sens][-1]
                if sens in smokeSens:
                    message += f"Die Rauch-Werte an Sensor {sens} sind außerhalb des Normalbereichs: {val}\n"
                else:
                    normSmoke += f"Der aktuelle Rauch-Wert am Sensor {sens} ist: {val}\n"
            if normSmoke!="":
                normSmoke= f"Aktuelle Rauchwerte:\n{normSmoke}\n"
            message += "\n"

        if len(waterSens) > 0:
            message += "Wasser Emergencies:\n"
            for sens in waterSens:
                val = water[sens][-1]
                message += f"Die Wasser-Werte an Sensor {sens} sind außerhalb des Normalbereichs: {val}\n"
            message += "\n"

        if len(humSens) > 0:
            message += "Luftfeuchtigkeit Emergencies:\n"
            for sens in hum:
                val = hum[sens][-1]
                if sens in humSens:
                    message += f"Die Luftfeuchtigkeits-Werte an Sensor {sens} sind außerhalb des Normalbereichs: {val}\n"
                else:
                    normHum+=f"Der aktuelle Luftfeuchtigkeits-Werte an Sensor {sens} ist: {val}\n"
            if normHum != "":
                normHum = f"Aktuelle Luftfeuchtigkeitswerte:\n{normHum}\n"
            message += "\n"

        message+=normTemp+normSmoke+normHum

        files = os.listdir(path + "/sent/")
        for file in files:
            if str(file) == 'emergency-sms.txt' and (
                    datetime.datetime.fromtimestamp(os.stat(path + "/sent/" + str(file)).st_mtime) > pastIntervall) and not isNewEmergency:
                logging.info("Notfallsms vor weniger als 30 Min gesendet")
                message = ''
        if message != '':
            save_to_messages_db(cur, nowf, 1, 'Notfallsms', message)
            with open("/var/spool/sms/outgoing/emergency-sms.txt", mode='w') as f:
                print(message, file=f)
            logging.info("Notfallsms versendet")

        cur.execute("select sensorName from sensor;")
        results = cur.fetchall()
        for result in results:
            cur.execute(
                   f"select temp from web where zeit > '{past}' and sensorName = {result[0]};")
            temperatures = cur.fetchall()
            isShutdownPhase = True
            for temperature in temperatures:
                if temperature[0] < max_temp_shutdown:
                    isShutdownPhase = False
                    break
            if isShutdownPhase:
                break

        if isShutdownPhase:
            cur.execute(f'select rackNr_int from rack where priority = (select min(priority) from rack);')
            racks = cur.fetchall()
            for rack in racks:
                shutdown_Rack(rack[0])
        time.sleep(30)
    except Exception as outer:
        logging.error(outer)
    connection.close()
#Notfall antwort mit Datenbank