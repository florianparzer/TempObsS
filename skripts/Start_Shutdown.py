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

"""
def getIpOfVMsOnHost(ip):
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}"')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
        logging.info(f"Mit ESXi-Server[{ip}] verbunden")
        ssh.sendline('vim-cmd vmsvc/getallvms | grep -v Vmid')
        ssh.prompt()
        output = ssh.before.decode("UTF-8").split('\n')
        count = 0
        vmIDs = []

        # Get VMIDs of running VMs
        for line in output:
            if count < 1:
                count += 1
                continue
            id = line.split(' ')[0]
            if id != '':
                vmIDs.append(id)

        # Get IPs of running VMs
        for id in vmIDs:
            ssh.sendline(f'vim-cmd vmsvc/get.guest {id} | grep -i ipaddress')
            ssh.prompt()
            output = ssh.before.decode("UTF-8").split('\n')
            for line in output:
                line = line.strip()
                if line.startswith("ipAddress"):
                    if '<unset>' in line:
                        break
                    vmIP = line.split('"')[1]
                    yield vmIP
                    break
        ssh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)
"""
def getVMWorldIDs(ip):
    """
    Liefert die WorldIDs der auf einem ESXi Host laufenden VMs
    :param ip: die IP Adresse des ESXi Hosts
    :return: eine Liste mit allen WorldIDs
    """
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
        logging.info(f"Mit ESXi-Server[{ip}] verbunden")
        ssh.sendline('esxcli network vm list')
        ssh.prompt()
        output = ssh.before.decode("UTF-8").split('\n')
        count = 0
        vmIDs = []

        # Get VMIDs of running VMs
        for line in output:
            if count < 3 or line == '':
                count += 1
                continue
            vmIDs.append(line.strip().split(" ")[0])
        ssh.logout()
        return vmIDs
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def getVMsOfHost(ip):
    """
    Liefert von einem ESXi Host die IP Adressen und WorldIDs der VMs
    :param ip: die IP Adresse des ESXi Hosts
    :return: ein Dictionary mit den IP Adressen als Key und den WorldIDs als Value
    """
    vmIDs = getVMWorldIDs(ip)
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        vmData = dict()
        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
        ssh.prompt()
        logging.info(f"Mit ESXi-Server[{ip}] verbunden")
        # Get IPs of running VMs
        for id in vmIDs:
            ssh.sendline(f'esxcli network vm port list -w {id} | grep -i "IP Address"')
            ssh.prompt()
            output = ssh.before.decode("UTF-8").split('\n')
            for line in output:
                line = line.strip()
                if line.startswith("IP Address"):
                    vmData[line.split(':')[1].strip()] = id
                    break
        ssh.logout()
        return vmData
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def getAllVMs(ips):
    """
    Liefert von mehreren ESXi Hosts die IP Adressen und WorldIDs der VMs
    :param ips: eine Liste mit IP Adressen der ESXi Hosts
    :return: ein Dictionary mit den IP Adressen als Key und den WorldIDs als Value
    """
    try:
        vms = dict()
        for ip in ips:
            vmData = getVMsOfHost(ip)
            for i in vmData:
                id = vmData[i]
                vms[i] = (id, ip)
        return vms
    except Exception as e:

        logging.error(e)
def shutdownVM_SSH(vmData):
    '''
    Schaltet alle VMs über eine SSH-Verbindung aus
    :param vmData: Eine Liste, welche Tuples speichert in denen die IP Adresse und ID der VM und die IP Adresse des ESXi-Hosts enthalten sind
    :return: die IP Adresse und ID des vCenter Servers und die IP Adresse des ESXi, auf dem der vCenter Server ist
    '''
    vCenterID = None
    vCenterIP = None
    esxi = None
    for vmip in vmData:
        id, hostIP = vmData[vmip]
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort, betriebssystem from VM where pk_IP_Adresse = "{vmip}";')
            for select in cursor.fetchall():
                try:
                    if select[2] == 'vCenter':
                        vCenterID = id
                        vCenterIP = vmip
                        esxi = hostIP
                        continue
                    ssh = pxssh.pxssh()
                    if select[2] == 'Windows':
                        ssh.PROMPT = r'C:\\Users\\.+>'
                        ssh.login(vmip, select[0], select[1], auto_prompt_reset=False)
                        logging.info(f"Mit VM[{vmip}] verbunden")
                        ssh.prompt()
                        ssh.sendline('shutdown -s -t 0')
                        ssh.prompt()
                    elif select[2] == 'Linux':
                        ssh.PROMPT = r'\[.+\]#'
                        ssh.login(vmip, select[0], select[1], auto_prompt_reset=False, login_timeout=30)
                        logging.info(f"Mit VM[{vmip}] verbunden")
                        ssh.prompt()
                        ssh.sendline('shutdown now')
                    logging.info(f'VM {vmip} is down')
                except pxssh.ExceptionPxssh as e:
                    logging.error(e)
        except Exception as e:
            logging.error(e)
            continue
    return (vCenterID, vCenterIP, esxi)


def shutdownVM_Kill(ips, vCenterIP, type):
    '''
    Führt einen Kill Befehl auf den Servern mit den IP-Adressen, die in ips sind, druch
    :param ips: die IP-Adressen der ESXi-Hosts
    :param vCenterIP: die IP-Adresse des vCenter-Servers
    :param type: der Type des Kill-Befehlts (soft, hard, force)
    '''
    try:
        for ip in ips:
            try:
                db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
                cursor = db.cursor()
                logging.info("Connected to database")
                cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
                credentials = cursor.fetchone()
            except Exception as e:
                logging.error(e)
                continue

            ssh = pxssh.pxssh()
            ssh.login(ip, credentials[0], credentials[1])
            logging.info(f"Mit ESXi[{ip}] verbunden")
            vmData = getVMsOfHost(ip)
            for vmip in vmData:
                id = vmData[vmip]
                if vmip == vCenterIP:
                    continue
                ssh.sendline(f"esxcli vm process kill --type {type} --world-id= {id}")
                ssh.prompt()
            ssh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)


def shutdownvCenter_SSH(ip):
    """
    Fährt den vCenter Server über eine SSH-Verbindung herunter
    :param ip: die IP Adresse des vCenter Servers
    """
    try:
        db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',
                             db='serverraum_temperaturueberwachung', autocommit=True)
        cursor = db.cursor()
        logging.info("Connected to database")
        cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
        credentials = cursor.fetchone()
    except Exception as e:
        logging.error(e)
    try:
        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
        logging.info(f"Mit vCenter Server[{ip}] verbunden")
        ssh.sendline('shutdown -s -t 0')
        ssh.prompt()
        logging.info(f'vCenter Server [{ip}] über ssh heruntergefahren')
        ssh.logout()
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def shutdownvCenter_Kill(ip, vCenterID, type):
    """
    Führt einen Kill Befehl druch, um den vCenter Server herunterzufahren
    :param ip: die IP Adresse des ESXi Hosts, auf dem der vCenter Server läuft
    :param vCenterID: die WorldID des vCenter Servers
    :param type: der Type des Kill-Befehlts (soft, hard, force)
    """
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])
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
    """
    Fährt einen ESXi Host herunter
    :param ip: die IP Adresse des ESXi Hosts
    """
    try:
        try:
            db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH', db='serverraum_temperaturueberwachung', autocommit=True)
            cursor = db.cursor()
            logging.info("Connected to database")
            cursor.execute(f'select benutzername, passwort from server where IP_Adresse = "{ip}";')
            credentials = cursor.fetchone()
            db.close()
        except Exception as e:
            logging.error(e)

        ssh = pxssh.pxssh()
        ssh.login(ip, credentials[0], credentials[1])#Passwort nicht definiert ?!
        logging.info(f"Mit ESXi[{ip}] verbunden")
        ssh.sendline('poweroff')
        ssh.logout()
        logging.info(f"ESXi[{ip}] heruntergefahren")
    except pxssh.ExceptionPxssh as e:
        logging.error(e)

def shutdown_Rack(rack):
    """
    Fährt alle Geräte des Serverracks inklusive der VMs sicher herunter
    :param rack: die Rack ID des Serverracks
    """
    try:
        db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',db='serverraum_temperaturueberwachung', autocommit=True)
        cursor = db.cursor()
        logging.info("Connected to database")
        cursor.execute(f'select IP_Adresse from server where fk_RackNr_int = {rack} and connectivity = TRUE;')
        ips = []
        for ip in cursor.fetchall():
            ips.append(ip[0])
        db.close()
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
    if vCenterIP != None:
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