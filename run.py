#!/usr/bin/python

__author__ = 'scukonick'


import os
import re
import select
import socket
import logging






result = {}

configname = '/etc/pyeximer'
filename = '/var/log/exim4/mainlog'
logfile = '/var/log/pyeximer/pyeximer.log'
pidfile = '/var/run/pyeximer.pid'

interface = '0.0.0.0'
port = 8083

EOL1 = b'\n'


# Configuring logging
log = logging.getLogger()
ch = logging.FileHandler(logfile)

log.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)


pid = str(os.getpid())
if os.path.isfile(pidfile):
    log.error ("%s already exists, exiting" % pidfile)
    exit()
else:
    open(pidfile, 'w').write(pid)
log.info('Configname is: '+configname)
log.info('Exim log filename is: '+filename)



regex = '(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*=>.* T=(?P<transport>\S+)'

transports = []
# Config
try:
    with open(configname) as config:
        for line in config:
            result[line.rstrip('\n')]=0
            transports.append(line.rstrip('\n'))
except Exception:
    log.fatal("Couldn't open config, exiting")
    exit (2)

log.debug('Result at start is: '+str(result))
log.debug('Transports are: '+str(transports))

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serversocket.bind((interface, port))
serversocket.listen(1)
serversocket.setblocking(0)

log.info('Listening on: '+interface + ':' + str(port))

epoll = select.epoll()
epoll.register(serversocket.fileno(), select.EPOLLIN)

connections = {}; requests = {}; responses = {}


def openFile(filename):
    for x in range(0,3): # Let's try to open file 3 times
        try:
            file = open(filename)
            return file
        except Exception:
            log.debug ("Try "+str(x)+": Could not open file: "+filename)
            #sleep(1)
    log.fatal ("Failed opening file")
    exit(1)


file = openFile(filename)
inode = os.stat(filename).st_ino
file.seek(0,2)
i = 0

while True:
    # check if file replaced
    if inode != os.stat(filename).st_ino:
        log.info("File changed, reopening")
        file = openFile(filename)
        inode = os.stat(filename).st_ino
    newline = file.readline()
    # check if we can read new line
    if newline:
        log.debug("Read line")
        match = re.search(regex,newline)
        if match:
            log.debug ("Matched with regexp")
            date = match.group('date')
            transport = match.group('transport')
            log.debug ("Received msg to transport: "+transport)
            if transport in transports:
                result[transport] = result[transport] + 1
                log.debug ('Increased result for transport: '+str(result))
    else:
        log.debug('Sleeping')

    events = epoll.poll(.1)
    for fileno, event in events:
        if fileno == serversocket.fileno():

            connection, address = serversocket.accept()
            connection.setblocking( 0)
            epoll.register(connection.fileno(), select.EPOLLIN)
            connections[connection.fileno()] = connection
            requests[connection.fileno()] = b''
            log.debug("Socket: "+str(connection.fileno())+": Connected somebody")
        elif event & select.EPOLLIN:
            log.debug("Socket: "+str(connection.fileno())+": Got something to read")
            requests[fileno] += connections[fileno].recv(1024)
            log.debug ("Socket: "+str(connection.fileno())+":We read: "+requests[fileno].decode())
            if EOL1 in requests[fileno]:
                log.debug("Socket: "+str(connection.fileno())+": Received EOL")
                epoll.modify(fileno, select.EPOLLOUT)
                log.info ("Received request: "+requests[fileno].decode()[:-2])
                asked_transport = requests[fileno].decode()[:-2]
                try:
                    responses[fileno] = str(result[asked_transport])
                    result[asked_transport] = 0
                    log.info('Answering with: '+responses[fileno])
                except KeyError:
                    log.info('Wrong key')
                    responses[fileno] = b'Wrong key\n'

        elif event & select.EPOLLOUT:
            byteswritten = connections[fileno].send(responses[fileno])
            responses[fileno] = responses[fileno][byteswritten:]
            if len(responses[fileno]) ==  0:
                epoll.modify(fileno,  0)
                log.debug('Sent response')
                connections[fileno].shutdown(socket.SHUT_RDWR)
        elif event & select.EPOLLHUP:
            log.debug('Disconnecting')
            epoll.unregister(fileno)
            connections[fileno].close()
            del connections[fileno]


log.info ("Ok")
os.unlink(pidfile)