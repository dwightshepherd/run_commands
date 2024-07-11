import csv
import os
import json
import argparse
from datetime import datetime
from getpass import getpass
from netmiko import ConnectHandler, redispatch
from netmiko.exceptions import NetMikoTimeoutException, NetMikoAuthenticationException
from concurrent.futures import ThreadPoolExecutor
import re

def get_credentials_from_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            creds = json.load(file)
        return creds['username'], creds['password']
    else:
        return None, None

def get_credentials():
    username = os.getenv("DEVICE_USERNAME")
    password = os.getenv("DEVICE_PASSWORD")

    if not username:
        username = input("Enter username: ")
    if not password:
        password = getpass("Enter password: ")

    return username, password

def gethostname_from_prompt(hostname):
    if "RSP" in hostname:
        hostname = re.split(r'[#:]', hostname)
        hostname = hostname[-2]
    elif "#" in hostname:
        hostname = hostname.split("#")[0]
    return hostname

def get_tnow_string():
    tnow = datetime.now().replace(microsecond=0)
    return str(tnow).replace(' ', '_').replace(':', '-')

def create_directory(parent_dir, directory):
    path = os.path.join(parent_dir, directory)
    try:
        os.makedirs(path)
        print(f'Directory "{path}" created')
    except OSError as error:
        print(f'Storing outputs in directory - "{path}"')
    return path

def generate_output(parent_dir, cpe, show_run_config):
    s_tnow = get_tnow_string()
    cpe_filename = f"{parent_dir}/{cpe}_{s_tnow}.txt"
    with open(cpe_filename, 'w') as cpe_output_file:
        cpe_output_file.write(show_run_config)
    return f'Output complete: "{cpe_filename}"'

def write_to_report_file(r_output, r_name):
    with open(r_name, 'a') as r_file:
        r_file.write(r_output)
        r_file.write("\n")

def get_nodes_from_file(nodes_file):
    if not os.path.exists(nodes_file):
        print(f'\n!!! ERROR: {nodes_file} does not exist\n')
        raise FileNotFoundError

    with open(nodes_file) as f:
        return json.load(f) if nodes_file.endswith(".json") else f.read().splitlines()

def get_commands_from_file(commands_file):
    with open(commands_file) as f:
        return f.read().splitlines()

def process_node(node, commands, credentials, output_path, global_timeout, global_configure, global_print_to_screen, log_report):
    output = ""
    try:
        node['username'] = credentials[0]
        node['password'] = credentials[1]

        net_connect = ConnectHandler(**node)
        node_prompt = net_connect.find_prompt()
        node_name = gethostname_from_prompt(node_prompt)
        p_node_prompt = node_name + "#"
        print(f"{p_node_prompt}:[running...]")
        #output = p_node_prompt
        #write_to_report_file(output, log_report)

        timeout = 10 if not global_timeout else global_timeout
        if global_configure:
            config_commands = commands
            output += net_connect.send_config_set(config_commands)
            if node['device_type'] in ('cisco_xe', 'cisco_nxos', 'cisco_ios'):
                net_connect.save_config()
            output += "Configuration changes saved"
        else:
            for command in commands:
                if command and not command.startswith("#"):
                    header = f'{command:-^70}'
                    output += f"\n{header}\n{p_node_prompt}{command}\n"
                    if "location all" in command:
                        timeout = 20 if not global_timeout else global_timeout
                    elif "show logg" in command:
                        timeout = 30 if not global_timeout else global_timeout
                    result = net_connect.send_command(command, read_timeout=timeout)
                    if global_print_to_screen:
                        print(result)
                    output += result

        generate_output(output_path, node_name, output)
        print(f"{node_name}: [Ok]")
        return node['ip'], node_name, "Ok"

    except (NetMikoAuthenticationException) as e:
        print(f"{node['ip']}: fail - Authentication Error")
        return node['ip'], "", "Authentication Error"
    except (NetMikoTimeoutException):
        print(f"{node['ip']}: fail - Connection timed out")
        return node['ip'], "", "Connection timed out"
    except Exception as e:
        print(f"{node['ip']}: fail - {str(e)}")
        return node['ip'], "", str(e)

def generate_nodes_csv(all_nodes, output_path):
    s_tnow = get_tnow_string()
    csv_filename = f"{output_path}/nodes_{s_tnow}.csv"
    with open(csv_filename, 'w', newline='') as csvfile:
        fieldnames = ['ip', 'hostname', 'status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for node in all_nodes:
            writer.writerow({'ip': node[0], 'hostname': node[1], 'status': node[2]})

    print(f"CSV file generated: {csv_filename}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("commands_file", help="Path to the commands file (commands.txt)")
    parser.add_argument("devices_file", help="Path to the devices file (devices.json)")
    parser.add_argument("-c", "--credentials_file", help="Path to the credentials file (credentials.json)")
    parser.add_argument("-t", "--timeout", help="Set Timeout value for script", type=int)
    parser.add_argument('--configure', action='store_true', help='Flag to configure the devices')
    parser.add_argument('-p','--print_to_screen', action='store_true', help='Flag to print output to screen')
    parser.add_argument("-n", "--num_threads", help="Number of threads to use", type=int, default=10)
    args = parser.parse_args()

    global_timeout = args.timeout if args.timeout else 0
    global_configure = args.configure
    global_print_to_screen = args.print_to_screen

    if args.timeout: print(f"! Global Timeout set: {global_timeout}")
    if global_configure: print(f"! Configuration mode set")
    if global_print_to_screen: print(f"! Print to Screen mode set")

    output_path = "./"
    output_dir = "Output"
    output_path = create_directory(output_path, output_dir)

    log_report = f"Log-Report_{get_tnow_string()}.txt"

    nodes = get_nodes_from_file(args.devices_file)
    commands = get_commands_from_file(args.commands_file)

    print(f"\n{len(commands)} commands on {len(nodes)} nodes")

    username, password = get_credentials_from_file(args.credentials_file) if args.credentials_file else (None, None)
    if not username or not password:
        username, password = get_credentials()

    credentials = (username, password)

    with ThreadPoolExecutor(max_workers=args.num_threads) as executor:
        futures = [
            executor.submit(
                process_node, node, commands, credentials, output_path, global_timeout, global_configure, global_print_to_screen, log_report
            )
            for node in nodes if not node['ip'].startswith("#")
        ]

    all_nodes = [future.result() for future in futures]
    print(f"\n{len(all_nodes)} of {len(nodes)} nodes processed")
    generate_nodes_csv(all_nodes, output_path)
   

if __name__ == "__main__":
    main()
