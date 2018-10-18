"""
    4CN Parzer Florian
"""
import logging
import logging.handlers
import os
import socket
import time
import subprocess

#find out local ip address (we don't want to forward failed sms packets to our own system)
local = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [[(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]
#set up logging
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/smsd/failover.log',maxBytes=1000000,backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

def startServer(ip, user, password):
    """
    Starts a server by using ipmitool
    :param ip: the ipmi-ipaddress of the server
    :param user: the ipmi-user
    :param password: the ipmi-userpassword
    """
    try:
        os.system("ipmitool -I lanplus -H " + ip + " -U " + user + " -P " + password + " chassis power on")
    except Exception as e:
        logging.error(e)


def shutdownServer(ip, user, password):
    try:
        os.system("ssh " + user + "@" + ip)
        os.system(password)
        count = 0
        vmIDs = []
        process = subprocess.Popen(["esxcli network vm list"], stdout=subprocess.PIPE, universal_newlines=True)
        output = list(process.communicate())
        for line in output:
            if count <= 1:
                continue
            count += 1
            line = str(line).strip().split(" ")[0]
            vmIDs.append(line)
        for id in vmIDs:
            process = subprocess.Popen(["esxcli network vm port list", "-w", id], stdout=subprocess.PIPE, universal_newlines=True)
            output = list(process.communicate())
            for line in output:
                os.system("stop-computer")
    except Exception as e:
        logging.error(e)