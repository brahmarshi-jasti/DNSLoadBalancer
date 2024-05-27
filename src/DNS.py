import sys
import time
import datetime
import threading
import traceback
import socketserver
import random
import logging
from logging.handlers import RotatingFileHandler
from ip2geotools.databases.noncommercial import DbIpCity
from dnslib import *
from LoadTesting import run_ab


formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger1 = logging.getLogger('logger1')
logger1.setLevel(logging.INFO)


web_server_ip = []
current_server_index = 0
switch_load_balancing_algo = 1

# for Load based balancing
clients_count = {server: 0 for server in web_server_ip}
max_load = {server: 1 for server in web_server_ip}

# for overall monitoring - performance log
monitor_count = {server: 0 for server in web_server_ip}
total_requests_handled = 0


class DomainName(str):
    def __getattr__(self, item):
        return DomainName(item + "." + self)


D = DomainName("brahmarshi-arvind.online.")
IP = ""
TTL = 5
PORT = 53
global_variable_lock = threading.Lock()


def round_robin_algo():
    global current_server_index
    global_variable_lock.acquire()
    ip = web_server_ip[0]
    current_server_index = current_server_index % len(web_server_ip)
    try:
        ip = web_server_ip[current_server_index]
    except Exception as e:
        print(str(e))
    finally:
        global_variable_lock.release()
    current_server_index = current_server_index + 1
    return ip.strip()


def geo_algo(client_ip_address):
    ip = web_server_ip[0]
    global_variable_lock.acquire()
    try:
        location = DbIpCity.get(client_ip_address, api_key="free")

        # print(f"IP Address: {location.ip_address}")
        # print(f"Location: {location.country}")

        # Mapping region based on the country, and return the corresponding IP address of web server
        if location and location.country in ["US", "CA", "MX"]:
            ip = web_server_ip[0]
        elif location and location.country in ["GB", "FR", "DE", "NL", "BE", "IE", "LU", "CH", "AT"]:
            ip = web_server_ip[1]
        elif location and location.country in ["IN", "LK", "NP", "BT", "MM", "TH", "MY"]:
            ip = web_server_ip[2]
        else:
            random_integer = random.randint(0, 2)
            ip = web_server_ip[random_integer]

    except Exception as e:
        print("")
    finally:
        global_variable_lock.release()
    return ip.strip()


def web_load_based_algo():
    current_server = web_server_ip[0]

    global current_server_index
    current_server_index = current_server_index % len(web_server_ip)
    global_variable_lock.acquire()
    global clients_count
    try:
        current_server = web_server_ip[current_server_index]
        clients_count[current_server] += 1

        if clients_count[current_server] >= max_load[current_server]:
            clients_count[current_server] = 0
            current_server_index = (current_server_index + 1)
    except Exception as e:
        print(str(e))
    finally:
        global_variable_lock.release()

    return current_server.strip()


def dns_response(data, client_ip):

    try:
        request = DNSRecord.parse(data)
        # print(request)
        qname = request.q.qname
        qn = str(qname)

        global switch_load_balancing_algo
        global IP
        global total_requests_handled
        global monitor_count
        qn = qn.lower()
        if qn == D or qn.endswith("." + D):
            if switch_load_balancing_algo == 2:
                IP = geo_algo(client_ip)
            elif switch_load_balancing_algo == 3:
                IP = web_load_based_algo()
            else:
                IP = round_robin_algo()
            logger1.info(
                f"Requested for {qn} from {client_ip},The resolved IP address is {IP}\n")
            # print(
            #     f"Requested for {qn} from {client_ip},The resolved IP address is {IP}\n")
            monitor_count[IP] += 1
            total_requests_handled += 1

        soa_record = SOA(
            mname=D.ns1,  # primary name server
            rname=D.jasti,  # email of the domain administrator
            times=(
                2023112701,  # serial number
                60 * 60 * 1,  # refresh
                60 * 60 * 3,  # retry
                60 * 60 * 24,  # expire
                60 * 60 * 1,  # minimum
            ),
        )
        ns_records = [NS(D.ns1), NS(D.ns2)]
        records = {
            D: [A(IP), AAAA((0,) * 16), MX(D.mail), soa_record] + ns_records,
            D.ns1: [
                A(IP)
            ],  # MX and NS records must never point to a CNAME alias (RFC 2181 section 10.3)
            D.ns2: [A(IP)],
            D.mail: [A(IP)],
            D.andrei: [CNAME(D)],
        }

        reply = DNSRecord(DNSHeader(id=request.header.id,
                                    qr=1, aa=1, ra=1), q=request.q)

        qtype = request.q.qtype
        qt = QTYPE[qtype]

        if qn == D or qn.endswith("." + D):
            for name, rrs in records.items():
                if name == qn:
                    for rdata in rrs:
                        rqt = rdata.__class__.__name__
                        if qt in ["*", rqt]:
                            reply.add_answer(
                                RR(
                                    rname=qname,
                                    rtype=getattr(QTYPE, rqt),
                                    rclass=1,
                                    ttl=TTL,
                                    rdata=rdata,
                                )
                            )

            for rdata in ns_records:
                reply.add_ar(RR(rname=D, rtype=QTYPE.NS,
                                rclass=1, ttl=TTL, rdata=rdata))

            reply.add_auth(
                RR(rname=D, rtype=QTYPE.SOA, rclass=1, ttl=TTL, rdata=soa_record)
            )

        # print("-------Reply:\n", reply)
    except Exception as e:
        logger1.info("dns_response function raised exception")

    return reply.pack()


class BaseRequestHandler(socketserver.BaseRequestHandler):
    def get_data(self):
        raise NotImplementedError

    def send_data(self, data):
        raise NotImplementedError

    def handle(self):
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        print(
            "\n\n%s request %s (%s %s):"
            % (
                self.__class__.__name__[:3],
                now,
                self.client_address[0],
                self.client_address[1],
            )
        )
        client_ip = self.client_address[0]
        try:
            data = self.get_data()
            self.send_data(dns_response(data, client_ip))
        except Exception:
            traceback.print_exc(file=sys.stderr)


class UDPRequestHandler(BaseRequestHandler):
    def get_data(self):
        return self.request[0]

    def send_data(self, data):
        return self.request[1].sendto(data, self.client_address)


def main():

    global web_server_ip
    global clients_count
    global max_load
    global switch_load_balancing_algo
    global monitor_count
    global logger1
    global total_requests_handled

    try:
        with open('brahmarshi-arvind.online.txt', 'r') as file:
            web_server_ip = [str(line.strip())for line in file.readlines()]

    except Exception as e:
        print("Error while reading hosts file")
    # print(web_server_ip)
    clients_count = {server: 0 for server in web_server_ip}
    max_load = {server: 1 for server in web_server_ip}
    monitor_count = {server: 0 for server in web_server_ip}

    try:

        file_handler1 = logging.FileHandler(
            '../logs/all_resolved_dns_queries.txt', mode="w")
        file_handler1.setLevel(logging.INFO)
        file_handler1.setFormatter(formatter)
        logger1.addHandler(file_handler1)

        logger2 = logging.getLogger('logger2')
        logger2.setLevel(logging.INFO)

        # file_handler2 = logging.FileHandler( 'performance_monitoring_log.txt', mode='w')
        file_handler2 = RotatingFileHandler(
            '../logs/performance_monitoring_log.txt',  mode='w', maxBytes=1e6, backupCount=3)
        file_handler2.setLevel(logging.INFO)
        file_handler2.setFormatter(formatter)
        logger2.addHandler(file_handler2)
    except Exception as e:
        print("Error with creation of a file")

    if len(sys.argv) > 1:
        switch_load_balancing_algo = int(sys.argv[1])

    if (switch_load_balancing_algo == 3):
        for i in range(len(web_server_ip)):
            max_load[web_server_ip[i]] = int(
                run_ab(f"http://{web_server_ip[i]}/", 10, 100)
            )
            # print(max_load[web_server_ip[i]])

    servers = []
    servers.append(socketserver.ThreadingUDPServer(
        ("", 53), UDPRequestHandler))

    for s in servers:
        thread = threading.Thread(
            target=s.serve_forever
        )
        thread.daemon = True
        thread.start()
        print(
            "%s server loop running in thread: %s"
            % (s.RequestHandlerClass.__name__[:3], thread.name)
        )

    try:
        while 1:
            time.sleep(1)

            if total_requests_handled >= 100:
                inf = ""
                for key, value in monitor_count.items():
                    inf += f"For web server {key}, the number of requests allocated by DNS is {value}\n"
                logger2.info(
                    f"For the last {total_requests_handled} requests resolved, \n,{inf}")
                monitor_count = {server: 0 for server in web_server_ip}
                total_requests_handled = 0

            sys.stderr.flush()
            sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()


if __name__ == "__main__":
    main()
