#!/usr/bin/python
# -*- coding: utf-8 -*-

#this skript was designed to work with python2
import pymysql
import sys
import subprocess
import datetime
import time
import logging
import logging.handlers
import socket
import os
import datetime
from datetime import timedelta
from datetime import datetime




#set up logging
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/onlinesensors/onlinesensors.log',maxBytes=1000000,backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

logging.info("Deamon started")

To = ""
try:
	with open("/etc/smsd/recievers.list", mode='r') as recievers:
		for reciever in recievers:
			logging.info("Adding reciever: " + reciever)
			To = "To: " + reciever + "\n"
except Exception as e:
	logging.error(e)
	sys.exit()


try:
    connection = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
    cur = connection.cursor()

except Exception as e:
    logging.error(e)


while True:
    sens = []
    cur.execute('select fk_sensorID, max(zeit) from messung group by fk_sensorID;')
    results = cur.fetchall()
    logging.info(results)
    for result in results:
        sensor = result[0]
        sens.append(sensor)
        now = datetime.now()
        logging.info(str(now))
        date = datetime.strptime(str(result[1]),"%Y-%m-%d %H:%M:%S")
        logging.info(date)
        cur.execute('select status from sensor where sensorID = ' + str(sensor))
        status = cur.fetchall()
        status = status[0][0]
        logging.info(status)
        if now - timedelta(minutes=2) > date and status == "online":
            #update db
            logging.info("update offline")
            cur.execute('update sensor set status = \'offline\' where sensorID = ' + str(sensor))

            #sms versenden
            with open("/var/spool/sms/outgoing/sensor_offline.txt", mode='w') as f:
                cur.execute('select sensorPosition from sensor where sensorID = ' + str(sensor))
                sensorPosition = cur.fetchall()
                sensorPosition = sensorPosition[0][0]
                print(To + "\nSensor " + sensorPosition + ": keine Messungen mehr", file=f)

        elif now - timedelta(minutes=1) < date and status == "offline":
            logging.info("update online")
            #update db
            cur.execute('update sensor set status = \'online\' where sensorID = ' + str(sensor))

            #sms versenden
            with open("/var/spool/sms/outgoing/sensor_offline.txt", mode='w') as f:
                cur.execute('select sensorPosition from sensor where sensorID = ' + str(sensor))
                sensorPosition = cur.fetchall()
                sensorPosition = sensorPosition[0][0]
                print(To + "\nSensor " + sensorPosition + ": wieder online", file=f)

    cur.execute('select pk_sensorID, status from sensor;')
    results = cur.fetchall()
    for i in results:
        sensor = i[0]
        if sensor not in sens and result[1] == 'online':
            #update db
            cur.execute('update sensor set status = \'offline\' where sensorID = ' + str(sensor))

            # sms versenden
            with open("/var/spool/sms/outgoing/sensor_offline.txt", mode='w') as f:
                cur.execute('select sensorPosition from sensor where sensorID = ' + str(sensor))
                sensorPosition = cur.fetchall()
                sensorPosition = sensorPosition[0][0]
                print(To + "\nSensor " + sensorPosition + ": keine Messungen mehr", file=f)
    logging.info("fertig")
    time.sleep(10)