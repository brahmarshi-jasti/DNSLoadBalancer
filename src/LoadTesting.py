import subprocess
import re


def run_ab(url, num_clients, num_requests_per_client):
    # Build the ab command
    ab_command = f"ab -n {num_requests_per_client} -c {num_clients} {url}"

    # Run the ab command and capture its output
    result = subprocess.run(ab_command, shell=True,
                            capture_output=True, text=True)

    # Extract and print relevant information from the output
    output = result.stdout
    print(output)

    # Extracting the maximum number of requests per second using regex
    match = re.search(r"Requests per second:\s+([0-9.]+)", output)
    if match:
        max_requests_per_second = float(match.group(1))
        print(f"Maximum Requests per second: {max_requests_per_second}")
        return max_requests_per_second
    else:
        print("Unable to determine the maximum Requests per second.")

    return 10


# if __name__ == "__main__":
#     # Replace 'http://example.com/' with the actual URL of your web server
#     server_url = "http:3.3.3.3/"

#     # Set the number of clients and requests per client
#     num_clients = 10
#     num_requests_per_client = 100

#     # Run Apache Benchmark
#     run_ab(server_url, num_clients, num_requests_per_client)
