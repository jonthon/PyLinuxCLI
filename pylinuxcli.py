
import os, sys, pty, time, socket
from socketserver import (BaseRequestHandler, ThreadingTCPServer)

WAITTIME = 0.2       # secs
MAXBYTES = 1024 ** 1 # 1 KB

# cmd line prog. Could be customized 
# to use diff other than os.execvp
def runprogram(cmd):
    "Program/Command to be run on CLI"
    args = cmd.strip().split()
    name = args[0]
    os.execvp(name, args)  

def read( i, maxbytes): return os.read(i, maxbytes)
def write(o, data):     return os.write(o, data)
def block(io):   return os.set_blocking(io, True)
def unblock(io): return os.set_blocking(io, False)

def communicate(i1, o1, i2, o2, input, output, *, waittime=WAITTIME, 
                                                  maxbytes=MAXBYTES):
    
    class Participant:
        def __init__(self, i, o):
            self.i = i
            self.o = o

    sender   = Participant(i1, o1)  
    receiver = Participant(i2, o2)
    while True:
        try:
            unblock(sender.i)                               # free sender. 
            while True:
                if sender.i == i2: input(sender.o)          # write first   ..
                time.sleep(waittime)                        # wait a little ..
                write(receiver.o, read(sender.i, maxbytes)) # then read.
        except BlockingIOError:
            if receiver.o == o2:                            # read prog out.
                try:
                    unblock(receiver.i)
                    time.sleep(waittime)
                    while True: output(receiver.i)
                except BlockingIOError: pass
                finally: block(receiver.i)         
            temp     = sender
            sender   = receiver                             # switch roles.
            receiver = temp
        finally: block(sender.i)                            # reblock sender. 

def input(handler):
    done = False    # remember state
    def input(fd):
        nonlocal done
        if done: 
            done = False
            raise BlockingIOError
        handler(fd)
        done = True
    return input

@input
def localinput(fd): 
    data = sys.stdin.readline().encode()
    os.write(fd, data)

def localoutput(fd):
    data = os.read(fd, MAXBYTES)
    data = data.decode()
    sys.stdout.write(data)
    sys.stdout.flush()

# linux terminal
def startterminal(cmd, input, output):
    i2, o2 = os.pipe()
    progID, progIO = pty.fork()
    if not progID: runprogram(cmd)
    communicate(progIO, progIO, i2, o2, input, output)

def startlocalterminal(cmd):
    startterminal(cmd, localinput, localoutput)

class SocketTerminalHandler(BaseRequestHandler):
    "Server handler"
    def handle(self):
        @input
        def socketinput(fd):
            data = self.request.recv(MAXBYTES)    # 1KB at a time 
            os.write(fd, data)
        def socketoutput(fd):
            data = os.read(fd, MAXBYTES)
            self.request.send(data)
        startterminal(self.request.recv(MAXBYTES), socketinput, 
                                                   socketoutput)

class StartSocketTerminal:
    "Server interface"
    def __init__(self, name, port):
         ThreadingTCPServer((name, port), 
                            SocketTerminalHandler).serve_forever()

# run this on a client device
class StartUserSocketTerminal:
    "Client interface"
    def __init__(self, name, port):
        conn = socket.socket()
        conn.connect((name, port))
        conn.send(b'bash\n')
        while True:
            odata = conn.recv(1024 ** 2)
            print(odata.decode(), end='')
            idata = sys.stdin.readline()
            conn.send(idata.encode())
            