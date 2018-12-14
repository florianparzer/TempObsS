#!/usr/bin/python
# -*- coding: utf-8 -*-

# this skript was designed to work with python2
import pymysql
import sys
import subprocess
import datetime
import time
import logging
import logging.handlers
import socket

# set up logging
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/onlinetest/onlinetest.log', maxBytes=1000000,
                                                   backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

logging.info("Deamon started")

gateway_ip = ""
gateway_read = False
connectivity = False

reciever = ""
To = ""
try:
    with open("/etc/smsd/recievers.list", mode='r') as recievers:
        for reciever in recievers:
            logging.info("Adding reciever: " + reciever)
            To = "To: " + reciever + "\n"
except Exception as e:
    logging.error(e)
    sys.exit()

gateway_ip = ""
# gateway ip read in
with open("/etc/network/interfaces", mode="r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("gateway "):
            gateway_ip = line.split(" ")[1]
            logging.info("Gateway is read in as: " + gateway_ip)
            gateway_read = True
            break

if not gateway_read:
    logging.info("There is no gateway given")

counter = 0
# ping the gateway
response_tup = subprocess.Popen(["ping", "-c", "4", gateway_ip], stdout=subprocess.PIPE, universal_newlines=True)
response_tup = response_tup.communicate()

response = list(response_tup)
response = response[0].split("\n")

# test connectivity
for line in response:
    line = str(line)
    line = line.strip()

    if line.startswith("64 bytes from " + gateway_ip) and not line.startswith("PING " + gateway_ip):
        counter += 1

logging.info(counter)
if counter >= 1:
    connectivity = True

logging.info("connectivity: " + str(connectivity))

# ip desjenigen PIs
local = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [
    [(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in
     [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]

while True:
    counter = 0;
    # ping the gateway
    response_tup = subprocess.Popen(["ping", "-c", "4", gateway_ip], stdout=subprocess.PIPE, universal_newlines=True)
    response = list(response_tup.communicate())
    response = response[0].split("\n")
    for line in response:
        line = str(line)
        line = line.strip()
        if line.startswith("64 bytes from " + gateway_ip) and not line.startswith("PING " + gateway_ip):
            counter += 1

    # check the response
    if counter == 0:
        # 2min warten
        time.sleep(120)
        # check again
        response_tup = subprocess.Popen(["ping", "-c", "4", gateway_ip], stdout=subprocess.PIPE,
                                        universal_newlines=True)
        response = list(response_tup.communicate())
        response = response[0].split("\n")
        for line in response:
            line = str(line)
            if line.startswith("64 bytes from " + gateway_ip) and not line.startswith("PING " + gateway_ip):
                counter += 1

        if counter == 0:
            with open("/var/spool/sms/outgoing/offline.txt", mode='w') as f:
                print(To + "\nRaspberry " + local + ": Netzwerkkonnektiviteat verloren!", file=f)
            connectivity = False

    while not connectivity:
        counter = 0;
        # ping the gateway
        response_tup = subprocess.Popen(["ping", "-c", "4", gateway_ip], stdout=subprocess.PIPE,
                                        universal_newlines=True)
        response = list(response_tup.communicate())
        response = response[0].split("\n")
        for line in response:
            line = str(line)
            if line.startswith("64 bytes from " + gateway_ip) and not line.startswith("PING " + gateway_ip):
                counter += 1

        # check the response
        if counter >= 1:
            with open("/var/spool/sms/outgoing/online.txt", mode='w') as f:
                print(To + "Raspberry " + local + ": Netzwerkkonnektivität wieder da!", file=f)
            connectivity = True
            break

        # wait 5min
        time.sleep(300)

    # wait 5min
    time.sleep(300)
