#!/usr/bin/python
# -*- coding: utf-8 -*-

#this skript was designed to work with python2
import pymysql
import sys
import Adafruit_DHT
import datetime
import time
import logging
import logging.handlers
import socket
import os


#destination for the XML File
path = '/var/www/html/xml/feucht.xml'
#set up logging
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/dht/dht.log',maxBytes=1000000,backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

gateway_ip =""
gateway_read=False
connectivity=False

#gateway ip read in
with open("/etc/network/interfaces", mode="r") as f:
    for line in f:
        line.strip()
        if line.startswith("gateway "):
            gateway_ip = line.split(" ")[1]
            logging.info("Gateway is read in as:" + gateway_ip)
            gateway_read=True
            break

if not gateway_read:
    logging.info("There is no gateway given")

counter = 0;
#ping the gateway
response = os.system("ping -c 4" + gateway_ip)

#test connectivity
for line in response:
    if response.startswith("64 bytes from " + gateway_ip) and not response.startswith("PING " + gateway_ip):
        counter+=1

if counter >=1:
    connectivity=True



while True:
    counter = 0;
    #ping the gateway
    response = os.system("ping -c 4" + gateway_ip)
    os.system(response + " > test.txt")
    for line in response:
        if response.startswith("64 bytes from " + gateway_ip) and not response.startswith("PING " + gateway_ip):
            counter+=1

    #check the response
    if counter ==0:
        connectivity=False

    while not connectivity:
        counter = 0;
        # ping the gateway
        response = os.system("ping -c 4" + gateway_ip)
        os.system(response + " > test.txt")
        for line in response:
            if response.startswith("64 bytes from " + gateway_ip) and not response.startswith("PING " + gateway_ip):
                counter += 1

        # check the response
        if counter >= 1:
            connectivity = True
            break
        else:
            connectivity = False

        #wait 5min
        time.sleep(300)

    #wait 5min
    time.sleep(300)






