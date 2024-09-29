#!usr/bin/python

import os, sys, pty, time, socket, signal
from socketserver import (BaseRequestHandler, ThreadingTCPServer)

WAITTIME    = 0.1                 # secs
MAXBYTES    = int(0.25 * 1024)    # 1 KB
STD_IN      = sys.stdin.fileno()
STD_OUT     = sys.stdout.fileno()
LOCAL_USER  = STD_IN, STD_OUT
BASH        = 'bash'
WELCOME_MSG = """

"""

class BaseIO:
    def __init__(self, In, Out):  self.In, self.Out = In, Out
    def read(self, maxinfo): raise NotImplementedError
    def write(self, info):   raise NotImplementedError
    def block(self):         raise NotImplementedError
    def unblock(self):       raise NotImplementedError
    def close(self):         raise NotImplementedError

# Mixin, it intercepts IO instances init operation
class Single:
    def __init__(self, io): BaseIO.__init__(self, io, io)

class PipeIO(BaseIO):
    def read(self, maxinfo):
        return os.read(self.In, maxinfo)
    def write(self, info):
        return os.write(self.Out, info)
    def block(self):
        return os.set_blocking(self.In,  True)
    def unblock(self):
        return os.set_blocking(self.In,  False)
    def close(self): 
        os.close(self.In)
        os.close(self.Out)  

class NonEchoPipeIO(PipeIO):
	def __init__(self, *pargs, **kwargs):
		PipeIO.__init__(self, *pargs, **kwargs)
		self.reset()
	def reset(self):
		self.echo = 0
	def read(self, maxinfo):
		info      = PipeIO.read(self, maxinfo)
		self.echo = len(info) if not self.echo else self.echo
		self.echo+= 1 # \n => \r\n from CLI
		return info
	def write(self, info):
		info = info[self.echo:]
		echo = PipeIO.write(self, info)
		self.reset()
		return echo  

LOCAL_USER = NonEchoPipeIO(*LOCAL_USER)

class PtyForkIO(Single, PipeIO): pass

class SocketIO(Single, BaseIO):
    def read(self, maxinfo):
        return self.In.recv(maxinfo)
    def write(self, info):
        return self.Out.send(info)
    def block(self):
        return self.In.setblocking(True)
    def unblock(self):
        return self.In.setblocking(False)
    def close(self):
        self.In.close() 
        self.Out.close()

class communicate:
    def __init__(self, talker, listener, *, forever=True,
                       maxinfo=MAXBYTES, waittime=WAITTIME):
        self.talker   = talker
        self.listener = listener
        self.maxinfo  = maxinfo
        self.waittime = waittime
        self.reset()
        # start arguing ...
        while forever: self.argue() 
        else:          self.argue()          
        # who got the last word?
    def reset(self):
        self.listener.block()
        self.talker.unblock()
    def talk(self):
        time.sleep(self.waittime)
        self.info = self.talker.read(self.maxinfo)
    def listen(self):
        self.listener.write(self.info)
    def switch(self):
        self.lastword = self.talker
        self.talker   = self.listener
        self.listener = self.lastword
        self.reset()
    def interrupt(self):
        pass
    def argue(self):
        Silence = BlockingIOError
        try:            self.talk()
        except Silence: self.switch()
        else:           self.listen()
        finally:        self.interrupt()

class startlocalCLI:
    def __init__(self, cmd, user=LOCAL_USER, *pargs, **kwargs):
        ID, IO =   self.spawn()
        if not ID: self.child(cmd)
        else:      self.parent(ID, IO, user, *pargs, **kwargs)
    def spawn(self):
        return pty.fork()
    def exec(self, prog, args, env):
        os.execvpe(prog, args, env)
    def child(self, cmd):
        args =  cmd.strip().split()
        prog =  args[0]
        env  =  os.environ
        self.exec(prog, args, env)
    def parent(self, cliID, cliIO, user, *pargs, **kwargs):
        cli  =  PtyForkIO(cliIO)
        try:    communicate(cli, user, *pargs, **kwargs)
        except: self.on_error(cliID, cli, user, sys.exc_info())
    def on_error(self, cliID, cli, user, exc_info):
        os.kill(cliID, signal.SIGKILL) # preserve system resources

class CLIServerHandler(BaseRequestHandler):
    def shake_hands(self, user):
        user.write(b'cmd: ')
        time.sleep(10 * WAITTIME)
        cmd  = user.read(int(4 * MAXBYTES))
        return cmd
    def handle(self): 
        user = SocketIO(self.request)
        cmd  = self.shake_hands(user)
        startlocalCLI(cmd, user)

# run this on remote server machine
class startCLIserver:
    def __init__(self, IP, port):
        IPaddr  = IP, port
        Handler = CLIServerHandler
        Server  = ThreadingTCPServer
        Server(IPaddr, Handler).serve_forever()

# run this on remote user machine
class startremoteCLI:
    def __init__(self, IP, port, user=LOCAL_USER, *pargs, **kwargs):
        cli  = socket.socket()
        cli.connect((IP, port))
        cli  = SocketIO(cli)
        self.shake_hands(cli, user)
        try:    communicate(cli, user, *pargs, **kwargs)
        except: self.on_error(cli, user, sys.exc_info())
    def shake_hands(self, cli, user):
        hello = cli.read(4 * MAXBYTES)
        user  = PipeIO(user.In, user.Out)
        user.write(hello)
        time.sleep(10 * WAITTIME)
        hello = user.read(int(4 * MAXBYTES))
        cli.write(hello)
    def on_error(self, cli, user, exc_info):
        cli.close()
		
if __name__ == '__main__': startlocalCLI(BASH)
