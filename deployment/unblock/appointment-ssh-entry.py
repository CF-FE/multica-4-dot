#!/usr/bin/python3 -I
import os
import re
import subprocess
import sys

COMMAND = "/usr/local/sbin/multica-unblock-appointment-ssh"
REQUEST = r"read-appointment tencent [0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"

def main():
    request = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if sys.argv[1:] != ["-c", COMMAND] or not re.fullmatch(REQUEST, request):
        print("Appointment query refused", file=sys.stderr)
        return 64
    command = ["/usr/bin/sudo", "-n", "--",
               "/usr/bin/python3", "-I", "/opt/multica-backend/read-appointment.py"]
    return subprocess.run(command, input=(request + "\n").encode("ascii"),
                          env={"PATH": "/usr/bin:/bin", "LANG": "C"}, check=False).returncode

if __name__ == "__main__":
    sys.exit(main())
