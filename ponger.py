__author__ = 'ceremcem'

from aktos_dcs import Actor,  ProxyActor, sleep, joinall
from aktos_dcs.Messages import *


class Ponger(Actor):
    def handle_PongMessage(self, msg):
        print "Ponger got pong message:", msg.text, msg.timestamp
        sleep(2)
        self.send(PingMessage(text="Hello pinger, this is ponger 1!"))

if __name__ == "__main__":
    ProxyActor()
    ponger = Ponger()
    ponger.send(PingMessage(text="startup message from ponger..."))
    ponger.join()
