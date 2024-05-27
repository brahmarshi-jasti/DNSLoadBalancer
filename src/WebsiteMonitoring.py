import urllib.request
import time
import os


def is_file_modified_recently(file_path, threshold_minutes=1):
    # Get the modification time of the file
    modification_time = os.path.getmtime(file_path)

    current_time = time.time()
    time_difference_seconds = current_time - modification_time

    # Check if the file has been modified within the last threshold_minutes
    return time_difference_seconds < (threshold_minutes * 60)


def check_server_availability(ip_address):
    try:
        response = urllib.request.urlopen(f"http://{ip_address}", timeout=5)
        return response.getcode() == 200
    except urllib.error.URLError:
        return False
    except Exception as e:
        return True


def update_ip_addresses_file(unavailable_servers):
    with open("brahmarshi-arvind.online.txt", "r") as file:
        lines = file.readlines()

    updated_lines = [
        line.strip() for line in lines if line.strip() not in unavailable_servers
    ]

    with open("monitoring.txt", "w") as file:
        file.write("\n".join(updated_lines))


def main_function():
    while True:
        with open("brahmarshi-arvind.online.txt", "r") as file:
            ip_addresses = [line.strip() for line in file.readlines()]

        unavailable_servers = [
            ip for ip in ip_addresses if not check_server_availability(ip)
        ]

        if unavailable_servers:
            print(" script found out unavailable servers")
            print(f"Detected unavailable servers: {unavailable_servers}")
            update_ip_addresses_file(unavailable_servers)

        if is_file_modified_recently("monitoring.txt"):
            print("Yes File Modified recently", 1)
        else:
            print("File Not modified recently")

        time.sleep(600)


if __name__ == "__main__":
    main_function()
