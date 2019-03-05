import logging
import logging.handlers
import subprocess
import socket
import sys
import pymysql
import time

local = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [[(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]
logFormatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
rootLogger = logging.getLogger()
fileHandler = logging.handlers.RotatingFileHandler('/var/log/escd/onoffd.log', maxBytes=1000000, backupCount=5)
fileHandler.setFormatter(logFormatter)
console = logging.StreamHandler()
rootLogger.addHandler(fileHandler)
rootLogger.addHandler(console)
rootLogger.setLevel(logging.INFO)

sql = "select name from pk_systemID where ip = '%s';" % (local)
while True:
    try:
        db = pymysql.connect(host='localhost', user='webuser', password='La4R2uyME78hAfn9I1pH',
                             db='serverraum_temperaturueberwachung', autocommit=True)
        cursor = db.cursor()
        logging.info("Connected to database")
        cursor.execute(sql)
        systemID = cursor.fetchone()[0]
        cursor.execute(f"select IP_Adresse from server join rack on fk_RackNr_int = pk_RackNr_int join messsystem on fk_systemID = pk_systemID where pk_systemID = {systemID};")
        ips = cursor.fetchall()
        for ip in ips:
            ip = ip[0]
            response = subprocess.Popen(["ping", "-c", "4", ip], stdout=subprocess.PIPE,
                                        universal_newlines=True).communicate()[0].split['\n']
            isOnline = False
            for line in response:
                if line.startswith("64 bytes from " + ip):
                    isOnline = True
                    break
            cursor.execute(f"UPDATE server SET connectivity = {isOnline} where IP_Adresse = {ip};")
        db.close()
    except Exception as e:
        logging.error(e)
        time.sleep(60)