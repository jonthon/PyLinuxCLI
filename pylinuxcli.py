
import os, sys, pty, time, socket
from socketserver import (BaseRequestHandler, ThreadingTCPServer)

WAITTIME = 0.5       # secs
MAXBYTES = 1024 ** 1 # 1 KB

class Done(Exception): pass

def input(handler):
    done = False            # remember state
    def input(terminalIO):
        nonlocal done
        if done: done = False; raise Done
        else:    handler(terminalIO); done = True
    return input

@input
def localinput(terminalIO): 
    data = sys.stdin.readline().encode()
    terminalIO.write(data)

def localoutput(terminalIO):
    data = terminalIO.read()
    data = data.decode()
    sys.stdout.write(data)
    sys.stdout.flush()

def communicate(terminalIO, input, output):
    while True:
        try:
            terminalIO.unblock()            # unblock cli
            while True: output(terminalIO)  # read all output
        except BlockingIOError: 
            terminalIO.block()              # re-block cli
        try:
            while True: input(terminalIO)   # write to cli ...
        except Done: pass                   # till done

# cmd line prog. Could be customized 
# to use diff other than os.execvp
def runprogram(cmd):
    "Program/Command to be run on CLI"
    args = cmd.strip().split()
    name = args[0]
    os.execvp(name, args)

# linux terminal
def startterminal(cmd, input, output):
    progID, progIO = pty.fork()
    if not progID: runprogram(cmd)
    communicate(TerminalIO(progIO), input, output)

# run locally
def startlocalterminal(cmd):
    startterminal(cmd, localinput, localoutput)

class TerminalIO:
    def __init__(self, io, waittime=WAITTIME, maxbytes=MAXBYTES):
        self.io = io
        self.waittime = waittime
        self.maxbytes = maxbytes
    def read(self):
        time.sleep(self.waittime)
        return os.read(self.io, self.maxbytes)
    def write(self, data):
        return os.write(self.io, data)
    def block(self):
        return os.set_blocking(self.io, True)
    def unblock(self):
        return os.set_blocking(self.io, False)
    def close(self): os.close(self.io)

class SocketIO:
    def __init__(self, conn, waittime=WAITTIME, maxbytes=MAXBYTES):
        self.conn = conn
        self.waittime = waittime
        self.maxbytes = maxbytes
    def read(self):
        time.sleep(self.waittime)
        return self.conn.recv(self.maxbytes)
    def write(self, data):
        return self.conn.send(data)
    def block(self):
        return self.conn.setblocking(True)
    def unblock(self):
        return self.conn.setblocking(False)
    def close(self):
        self.conn.close()

class TerminalServerHandler(BaseRequestHandler):
    "Server handler"
    def handle(self):
        user = SocketIO(self.request, 0.0) # no wait on read
        @input
        def socketinput(terminalIO):
            data = user.read()             # 1KB at a time 
            terminalIO.write(data)
        def socketoutput(terminalIO):
            data = terminalIO.read()
            user.write(data)
        cmd = self.request.recv(MAXBYTES)
        startterminal(cmd, socketinput, socketoutput)

# run this on server machine
class StartTerminalServer:
    def __init__(self, name, port):
         IP      = name, port
         Handler = TerminalServerHandler
         Server  = ThreadingTCPServer
         Server(IP, Handler).serve_forever()

# run this on a client device
class StartSocketTerminal:
    def __init__(self, name, port, cmd=None):
        conn = socket.socket()
        cmd  = 'bash' if not cmd else cmd
        cmd  = (cmd + '\n').encode()
        conn.connect((name, port))
        conn.send(cmd)
        terminal = SocketIO(conn, 1)
        communicate(terminal, localinput, localoutput)
        

if __name__ == '__main__':
    startlocalterminal('bash')
