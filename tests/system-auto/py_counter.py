#!/usr/bin/env python3

import time
import datetime

def main():
    count = 0
    file_path = "py_counter_output.txt"
    try:
        while count < 6000:
            count += 1
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Write the counter and timestamp to the file in append mode
            with open(file_path, "a") as f:
                f.write(f"{timestamp}: Count = {count}\n")
            # print(f"{timestamp}: Count = {count}")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nCounter stopped.")

if __name__ == "__main__":
    main()