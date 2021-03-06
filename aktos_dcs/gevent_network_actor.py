# coding: utf-8
__author__ = 'ceremcem'

import gevent
from cca_messages import *
from gevent_actor import Actor
import zmq.green as zmq


if zmq.zmq_version_info()[0] < 4:
    raise Exception("libzmq version should be >= 4.x")

class ProxyActor(Actor):

    def __init__(self, broker_host="localhost", rx_port=5013, tx_port=5012):
        #super(ProxyActor, self).__init__()
        Actor.__init__(self)

        self.broker_host = broker_host
        self.rx_port = rx_port
        self.tx_port = tx_port

        self.context = zmq.Context()
        self.subscriber = self.context.socket(zmq.SUB)
        self.publisher = self.context.socket(zmq.PUB)

        self.broker_sub = self.context.socket(zmq.SUB)
        self.broker_pub = self.context.socket(zmq.PUB)

        self.broker_client_sub = self.context.socket(zmq.SUB)
        self.broker_client_pub = self.context.socket(zmq.PUB)

        self.proxy_client_sub = self.context.socket(zmq.SUB)
        self.proxy_client_pub = self.context.socket(zmq.PUB)

        __subscribers__ = [self.subscriber,
                           self.broker_sub,
                           self.broker_client_sub,
                           self.proxy_client_sub]

        __publishers__ = [self.publisher,
                          self.broker_pub,
                          self.broker_client_pub,
                          self.proxy_client_pub]


        for s in __subscribers__:
            s.setsockopt(zmq.SUBSCRIBE, '')

        for p in __publishers__:
            p.setsockopt(zmq.LINGER, 0)
            p.setsockopt(zmq.SNDHWM, 2)
            p.setsockopt(zmq.SNDTIMEO, 0)


        gevent.spawn(self.broker_client_receiver)
        gevent.spawn(self.__receiver__)
        gevent.spawn(self.broker_receiver)
        gevent.spawn(self.proxy_client_receiver)


        # new actor will bind to a random port
        self.port = self.publisher.bind_to_random_port(addr="tcp://*")
        print "this actor's own publish port is: ", self.port

        # peers known so far
        self.known_publishers = ["tcp://%s:%d" % ("localhost", self.port)]
        if self.broker_host != "localhost":
            self.known_publishers.append("tcp://%s:%d" % (self.broker_host, self.tx_port))


        self.introduction = "NOK"  # not okay, introduce itself
        # is this address broker's server node in localhost?
        self.is_ab_server_node = False

        try:
            self.create_broker(watch=False)
        except:
            gevent.spawn(self.create_broker, watch=True)

        print "connecting to the local address broker"
        self.broker_client_pub.connect("tcp://%s:%d" % ("localhost", self.rx_port))
        self.broker_client_sub.connect("tcp://%s:%d" % ("localhost", self.tx_port))

        if self.broker_host != "localhost":
            print "connecting to the broker host"
            self.proxy_client_pub.connect("tcp://%s:%d" % (self.broker_host, self.rx_port))
            self.proxy_client_sub.connect("tcp://%s:%d" % (self.broker_host, self.tx_port))

        self.refresh_known_publishers()
        

    def refresh_known_publishers(self):
        print "sharing known publishers"
        for i in range(10):
            print "trial ", i, "..."
            self.broker_client_pub.send(pack(NetworkActorMessage(peers=self.known_publishers)))
            if self.introduction == "OK":
                break
            gevent.sleep(0.01)




    def create_broker(self, watch=False):
        while True:
            try:
                rx_addr = "tcp://%s:%d" % ("*", self.rx_port)
                tx_addr = "tcp://%s:%d" % ("*", self.tx_port)

                self.broker_sub.bind(rx_addr)
                self.broker_pub.bind(tx_addr)

                self.is_ab_server_node = True
                self.refresh_known_publishers()
                print "this actor created a broker"
                break  # quit trying to create a broker
            except Exception as e:
                print e.message
                if not watch:
                    raise
                gevent.sleep(10)  # TODO: decrease this time

            gevent.sleep()

    def receive(self, msg):
        try:
            m = pack(msg)
        except:
            pass

        # actors -> local
        self.network_send(m)

        try:
            # actors -> proxy
            if self.broker_host != "localhost":
                #print "forwarding via proxy_client: ", m
                self.proxy_client_pub.send(m)
            else:
                #print "forwarding via broker_pub: ", m
                self.broker_pub.send(m)
                
        except Exception as e:
            print "actors -> proxy error: ", e.message


    def broker_receiver(self):
        print "broker receiver started!"
        while True:
            message = self.broker_sub.recv()
            #print "broker got message", message
            try:
                m = unpack(message)
                self.network_send(m)
                self.send(m)
                self.call_the_handler(message)
            except Exception as e:
                print "exception in broker_receiver: ", e.message


    def broker_client_receiver(self):
        print "broker client receiver started!"
        while True:
            message = self.broker_client_sub.recv()
            #print "broker_client_sub got message: ", message
            try:
                m = unpack(message)
                if type(m) == type(NetworkActorMessage()):
                    if m.sender != self.actor_id:
                        self.handle_NetworkActorMessage(m)
            except Exception as e:
                #print "exception in broker_client_receiver: ", e.message
                print "ERR: in broker_client_receiver: ", message
                import pdb
                pdb.set_trace()


    def proxy_client_receiver(self):
        while True:
            message = self.proxy_client_sub.recv()
            #print "proxy client got message: ", message
            try:
                m = unpack(message)
                self.send(m)
                if self.is_ab_server_node:
                    self.network_send(m)
            except Exception as e:
                print "exception in proxy_client_receiver: ", e.message

    def handle_NetworkActorMessage(self, msg):

        print "debug: NetworkActorMessage received:", msg.peers

        for addr in msg.peers:
            if str(self.port) in addr:
                self.introduction = "OK"

            if addr not in self.known_publishers:
                print "discovered another actor binded to addr: %s" % addr
                self.subscriber.connect(addr)
                self.known_publishers.append(addr)
                print "subscriber is connected to the new actor"

                print "msg.peers: ", msg.peers

        if set(msg.peers) != set(self.known_publishers):
            print "informing others about known peers so far"
            self.broker_pub.send(pack(NetworkActorMessage(peers=self.known_publishers)))

    def network_receive(self, msg):
        self.send(msg)
        self.broker_pub.send(pack(msg))

    def __receiver__(self):
        try:
            #print "started to receive"
            while True:
                message = self.subscriber.recv()
                ###print "got message:", message
                self.call_the_handler(message)
                gevent.sleep(0)
        finally:
            self.subscriber.close()

    def network_send(self, msg):
        try:
            msg.sender = self.actor_id
            msg = pack(msg)
        except:
            pass
        self.publisher.send(msg)


    def call_the_handler(self, message):
        try:
            m = unpack(message)
        except Exception as e:
            #print "exception in call_the_handler:", e.message
            m = message

        if type(m) != type(NetworkActorMessage()):
            #self.receive(message)
            self.network_receive(message)

        try:
            if isinstance(m, Message):
                handler_func = "handle_" + m.__class__.__name__
                getattr(self, handler_func)(m)
        except AttributeError:
            pass

    def __exit__(self, type, value, traceback):
        print "cleanup..."
        self.subscriber.close()
        self.publisher.close()

        self.broker_sub.close()
        self.broker_pub.close()

        self.broker_client_sub.close()
        self.broker_client_pub.close()

        self.proxy_client_sub.close()
        self.proxy_client_pub.close()
        self.context.term()
        

"""
class ProxyActor(NetworkActor):
    def network_receive(self, msg):
        #print "proxy received network message: ", msg
        self.send(msg)

    def receive(self, msg):
        #print "proxy (id: %d) received msg: id: %d" % (id(self), msg.sender )
        self.network_send(msg)

"""

if __name__ == "__main__":
    ProxyActor().join()
