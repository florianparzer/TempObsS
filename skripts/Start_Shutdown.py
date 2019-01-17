import logging
import logging.handlers
import os
import socket
import pymysql
import time
from pexpect import pxssh

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


def shutdownVCenter(id, ip, user, passw, ssh):
    try:
        vmSsh = pxssh.pxssh();
        vmSsh.login(ip, user, passw)
        vmSsh.sendline("shutdown now")
        vmSsh.prompt()
        vmSsh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)
    ssh.sendline(f"esxcli vm process kill --type soft --world-id= {id}")
    time.sleep(100)
    ssh.sendline(f"esxcli vm process kill --type hard --world-id= {id}")
    time.sleep(100)
    ssh.sendline(f"esxcli vm process kill --type force --world-id= {id}")
    ssh.prompt()
    time.sleep(100)


def getVMsOfHost(ip):
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = {ip}')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
        logging.info(f"Mit ESXi-Server[{ip}] verbunden")
        ssh.sendline('esxcli network vm list')
        ssh.prompt()
        output = ssh.before.split('\n')
        count = 0
        vmIDs = []

        # Get VMIDs of running VMs
        for line in output:
            if count < 3:
                count += 1
                continue
            vmIDs.append(line.strip().split(" ")[0])

        # Get IPs of running VMs
        for id in vmIDs:
            ssh.sendline(f'esxcli network vm port list -w {id}')
            ssh.prompt()
            output = ssh.before.split('\n')
            for line in output:
                line = line.strip()
                if line.startswith("IP Address"):
                    vmIP = line.split(": ")
                    yield (vmIP[1], id)
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def getAllVMs(ips):
    try:
        vms = []
        for ip in ips:
            vmData = getVMsOfHost(ip)
            for i in vmData:
                vmIP, vmID = i
                vms.append((vmIP, vmID, ip[0]))
        return vms
    except Exception as e:
        logging.error(e)

def shutdownVM_SSH(vmData):
    '''
    Schaltet alle VMs über eine SSH-Verbindung aus
    :param vmData: Eine Liste, welche Tuples speichert in denen die IP Adresse und ID der VM und die IP Adresse des ESXi-Hosts enthalten sind
    :return: die IP Adresse und ID des vCenter Servers und die IP Adresse des ESXi, auf dem der vCenter Server ist
    '''
    for data in vmData:
        vmip, id, hIP = data
        vCenterID = None
        vCenterIP = None
        esxi = None
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort, betriebssystem from VM where IP_Adresse = {vmip}')
        except Exception as e:
            logging.error(e)
            continue
        try:
            for select in cursor.fetchall():
                if select[2] == 'vCenter':
                    vCenterID = id
                    vCenterIP = vmip
                    esxi = hIP
                    continue
                ssh = pxssh.pxssh()
                ssh.login(vmip, select[0], select[1])
                logging.info(f"Mit VM[{vmip}] verbunden")
                if select[2] == 'Windows':
                    ssh.sendline('shutdown -s -t 0')
                    ssh.prompt()
                elif select[2] == 'Linux':
                    ssh.sendline('shutdown now')
                    ssh.prompt()
            ssh.logout()
        except pxssh.ExceptionPxssh as e:
            logging.error(e)
    return (vCenterID, vCenterIP, esxi)

def shutdownVM_Kill(ips, vCenterIP, type):
    '''
    Führt einen Kill Befehl auf den Servern mit den IP-Adressen, die in ips sind, druch
    :param ips: die IP-Adressen der ESXi-Hosts
    :param vCenterIP: die IP-Adresse des vCenter-Servers
    :param type: der Type des Kill-Befehlts (soft, hard, forced)
    :return:
    '''
    try:
        for ip in ips:
            try:
                db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
                cursor = db.cursor()
                logging.info("Connected to database")
                cursor.execute(f'select benutzername, passwort from server where IP_Adresse = {ip}')
                user = cursor.fetchone()[0]
                password = cursor.fetchone()[1]
            except Exception as e:
                logging.error(e)

            ssh = pxssh.pxssh()
            ssh.login(ip, user, password)
            logging.info(f"Mit ESXi[{ip}] verbunden")
            for data in getVMsOfHost(ip):
                vmip, id = data
                if vmip == vCenterIP:
                    continue
                ssh.sendline(f"esxcli vm process kill --type {type} --world-id= {id}")
                ssh.prompt()
            ssh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)


def shutdownvCenter_SSH(ip):
    try:
        db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',
                             db='serverraum_temperaturueberwachung', autocommit=True)
        cursor = db.cursor()
        logging.info("Connected to database")
        cursor.execute(f'select benutzername, passwort from server where IP_Adresse = {ip}')
        user = cursor.fetchone()[0]
        password = cursor.fetchone()[1]
    except Exception as e:
        logging.error(e)
    try:
        ssh = pxssh.pxssh()
        ssh.login(ip, user, password)
        logging.info(f"Mit vCenter Server[{ip}] verbunden")
        ssh.sendline('shutdown -s -t 0')
        ssh.prompt()
        logging.info(f'vCenter Server [{ip}] über ssh heruntergefahren')
        ssh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def shutdownvCenter_Kill(ip, vCenterID, type):
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = {ip}')
            user = cursor.fetchone()[0]
            password = cursor.fetchone()[1]
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, user, password)
        logging.info(f"Mit ESXi[{ip}] verbunden")
        isRunning = False
        for data in getVMsOfHost(ip):
            vmip, id = data
            if id == vCenterID:
                isRunning = True

        if not isRunning:
            return

        ssh.sendline(f"esxcli vm process kill --type {type} --world-id= {vCenterID}")
        ssh.prompt()
        ssh.logout()
        logging.info(f'vCenter Server [{ip}] mit einem {type} Kill heruntergefahren')
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def shutdownServer(ip):
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = {ip}')
            user = cursor.fetchone()[0]
            password = cursor.fetchone()[1]
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, user, password)
        logging.info(f"Mit ESXi[{ip}] verbunden")
        ssh.sendline('poweroff')
        ssh.logout()
        logging.info(f"ESXi[{ip}] heruntergefahren")
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def shutdown_Rack(rack):
    try:
        db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',db='serverraum_temperaturueberwachung', autocommit=True)
        cursor = db.cursor()
        logging.info("Connected to database")
        cursor.execute(f'select IP_Adresse from server where fk_RackNr_int = {rack} and connectivity = TRUE')
        ips = []
        for ip in cursor.fetchall():
            ips.append(ip[0])
    except Exception as e:
        logging.error(e)

    vmData = getAllVMs(ips)
    vCenterID, vCenterIP, esxi = shutdownVM_SSH(vmData)
    vmTimer = 300
    vCenterTimer = 180
    time.sleep(vmTimer)
    shutdownVM_Kill(ips, vCenterIP, 'soft')
    time.sleep(vmTimer)
    shutdownVM_Kill(ips, vCenterIP, 'hard')
    time.sleep(vmTimer)
    shutdownVM_Kill(ips, vCenterIP, 'force')
    time.sleep(vmTimer)
    shutdownvCenter_SSH(vCenterIP)
    time.sleep(vCenterTimer)
    shutdownvCenter_Kill(esxi, vCenterID, 'soft')
    time.sleep(vCenterTimer)
    shutdownvCenter_Kill(esxi, vCenterID, 'hard')
    time.sleep(vCenterTimer)
    shutdownvCenter_Kill(esxi, vCenterID, 'force')
    time.sleep(vCenterTimer)
    for i in ips:
        shutdownServer(i)