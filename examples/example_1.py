from time import sleep

from pca9536 import PCA9536


def main():
    with PCA9536(bus=1) as device:  # You may need to change the bus number
        device.mode = "input"  # Set the mode of all pins to input.
        while True:
            inputs = device.read()
            print(f"Pin inputs: {inputs[0]}, {inputs[1]}, {inputs[2]}, {inputs[3]}")
            sleep(1)


if __name__ == "__main__":
    main()
