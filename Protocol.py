# coding: utf-8

import time

if __name__ == "__main__":
  with open("bibi.txt", "w+") as bibi:
    i = 0
    while True:
      try:
        bibi.write(str(i))
        i += 1
        time.sleep(1)
      except KeyboardInterrupt:
        bibi.write('STOP')
        break
