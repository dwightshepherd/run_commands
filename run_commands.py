#!/usr/bin/env python

# https://github.com/ktbyers/netmiko/blob/develop/examples/use_cases/case1_simple_conn/simple_conn.py
# Reference for Netmiko - https://ktbyers.github.io/netmiko/docs/netmiko/index.html

# Take from  netmiko github repository
# NOTE: You must be running python version 3

# Edited: Dwight Shepherd, February 13, 2024
# Version 1.5
# Added COMMAND TIMEOUT feature

# Todo:
# To update the Todo

from netmiko import ConnectHandler
from netmiko import redispatch
from getpass import getpass
from datetime import datetime

import json
import time
import signal
import sys
import os
import ipaddress
import argparse
import re

from netmiko.exceptions import NetMikoTimeoutException
from netmiko.exceptions import NetMikoAuthenticationException

# FYI, turning on logging (this will write a file named test.log in your current directory) for debugging: To see what is happening).
#import logging
#logging.basicConfig(filename='test.log', level=logging.DEBUG)
#logger = logging.getLogger("netmiko")

signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # IOError: Broken Pipe
signal.signal(signal.SIGINT, signal.SIG_DFL)  # KeyboardInterrupt: Ctrl + C

if len(sys.argv) < 3:
    print(f"Usage: {sys.argv[0]} commands.txt devices.json [-t timeout]")
    exit()

parser = argparse.ArgumentParser()
parser.add_argument("commands_file", help="Path to the commands file (commands.txt)")
parser.add_argument("devices_file", help="Path to the devices file (devices.json)")
parser.add_argument("-t", "--timeout", help="Set Timeout value for script", type=int)
args = parser.parse_args()

GLOBAL_TIMEOUT = 0 #Use to set the timeout of the each command

if args.timeout:
    GLOBAL_TIMEOUT = args.timeout
    print(f"\n*** COMMAND TIMEOUT SET: {GLOBAL_TIMEOUT} seconds\n")

nodes_processed = 0
nodes_skipped = 0


def getCredentials():
    """Gets Login creditials from User"""
    password = None
    username = input("Enter username: ")

    while not password:
        password = getpass()

    return username, password


def gethostnameFromPrompt(hostname):
    """ Strip RSP from hostname"""
    if "RSP" in hostname:
        hostname = re.split(r'[#:]', hostname)
        hostname = hostname[-2]
    elif "#" in hostname:
        hostname = hostname.split("#")[0]
    return hostname


def getTNOW_string():
    """Converts Time NOW to formatted string"""
    TNOW = datetime.now().replace(microsecond=0)
    s_TNOW = str(TNOW).replace(' ', '_').replace(':', '-')
    return s_TNOW


def createDirectory(parent_dir, directory):
    """ Creates a output directory """
    path = os.path.join(parent_dir, directory)
    try:
        os.makedirs(path)
        print('Directory "% s" created\n' % path)
    except OSError as error:
        # print(error)
        print('Storing outputs in directory - "% s"\n' % path)

    return path


def generateOutput(parent_dir, cpe, show_run_config):
    """ Generates Output for CPE """
    #TNOW = getTNOW_string()

    CPE_filename = parent_dir + "/" + cpe + ".txt"
    CPE_output_file = open(CPE_filename, 'w')
    CPE_output_file.write(show_run_config)
    CPE_output_file.close()
    output = 'Output complete: "%s"' % CPE_filename
    return output


def getNodesFromFile(nodes_file):
    """ description: Gets the network nodes from nodes file"""
    n_list = []

    if not os.path.exists(nodes_file):
        print(f'\n!!! ERROR: {nodes_file} does not exist\n')
        raise FileNotFoundError

    if nodes_file.endswith(".json"):
        with open(nodes_file) as f:
            n_list = json.load(f)
    else:
        with open(nodes_file) as f:
            n_list = f.read().splitlines()
    return n_list


def getCommandsFromFile(commands_file):
    """ description: Gets the commands from commands file"""
    n_list = []
    with open(commands_file) as f:
        n_list = f.read().splitlines()
    return n_list


def writeToReportFile(r_output, r_name):
    """ description: writes output to file """
    r_file = open(r_name, 'a')
    r_file.write(r_output)
    r_file.write("\n")
    r_file.close()


START_TIME = datetime.now().replace(microsecond=0)

s_TNOW = getTNOW_string()
log_Report = "Log-Report" + s_TNOW + ".txt"  # Log file

nodes = getNodesFromFile(args.devices_file)
commands = getCommandsFromFile(args.commands_file)

print(f"Commands: {commands} on nodes in {commands}")

output_PATH = "./"
#root_dir = "Output"
# market_dir = sys.argv[2].split("/")[-1].split(".")[0] #Ugly code... or maybe a bit Nerdy
#output_dir = root_dir + "/"+ market_dir
output_dir = "Output"
output_PATH = createDirectory(output_PATH, output_dir)

username, password = getCredentials()


for node in nodes:
    # if the node ip is NOT commented out with #
    if not node['ip'].startswith("#"):

        node['username'] = username
        node['password'] = password

        print(f"\nConnecting to node {node['ip']} ...")

        try:
            net_connect = ConnectHandler(**node)

            node_prompt = net_connect.find_prompt()
            node_name = gethostnameFromPrompt(node_prompt)
            
            p_node_prompt = node_name + "#"  # pretty prompt
            output = p_node_prompt
            print(output)
            writeToReportFile(output, log_Report)

            output = ""
            timeout = 10; 

            if GLOBAL_TIMEOUT:
                timeout = GLOBAL_TIMEOUT

            command_timeout_list = list() 
            command_timeout_list.append("location all")
            command_timeout_list.append("show logg")

            for command in commands:
                command = command.strip()  # remove any leading or trailing spaces
                if command and not command.startswith("#") :
                    header = f'{command:-^70}'
                    output = output + "\n" + header + "\n"
                    print(p_node_prompt + command)
                    output += p_node_prompt + command + "\n"

                    #Set a longer time if the commands are known to take too long               
                    if   ("location all" in command):
                        if GLOBAL_TIMEOUT:
                            timeout = GLOBAL_TIMEOUT
                        else:
                            timeout = 20
                    elif ("show logg" in command):
                        if GLOBAL_TIMEOUT:
                            timeout = GLOBAL_TIMEOUT
                        else:
                            timeout = 30 
                                            
                    output += net_connect.send_command(command, read_timeout=timeout)

            print("Saving output ... ")
            output = generateOutput(output_PATH, node_name, output)
            nodes_processed = nodes_processed + 1
            print(output)
            writeToReportFile(output, log_Report)
            output = str("-" * 50)
            print(output)
            writeToReportFile(output, log_Report)
            net_connect.disconnect()

        except (NetMikoAuthenticationException) as e:
            print()
            print("\nERROR: Authentication Error")
            print(e)
            break
        except (NetMikoTimeoutException):
            output = node['ip'] + ": ERROR: Connection timed out"
            print(output)
            output = output + "\n" + str("-" * 46)  # draws a line ------
            writeToReportFile("\n" + output + "\n", log_Report)
            nodes_skipped = nodes_skipped + 1
            continue
        except Exception as e:  # Comment out this exception block when debugging and testing
            print("ERROR: Unexpected Error")
            print(sys.exc_info()[0])
            print(e)            
            break


END_TIME = datetime.now().replace(microsecond=0)
total_time = END_TIME - START_TIME

print("\nSCRIPT SUMMARY")
print("Nodes Processed: " + str(nodes_processed))
print("Nodes Skipped: " + str(nodes_skipped))
print("Script executed in " + str(total_time))
print("Report file: %s" % log_Report)
