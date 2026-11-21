#!/usr/bin/env bash
# GPU box: a light XFCE desktop in the browser (TigerVNC + noVNC), bound to localhost only; reach it via an ssh tunnel.
[ "$(uname -s)" = Linux ] || exit 1
set -e
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xfce4 xfce4-terminal tigervnc-standalone-server novnc websockify dbus-x11 >/dev/null
mkdir -p ~/.vnc
printf '#!/bin/sh\nunset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS\nexec startxfce4\n' > ~/.vnc/xstartup; chmod +x ~/.vnc/xstartup
vncserver -kill :1 >/dev/null 2>&1 || true
vncserver :1 -localhost yes -geometry 1600x900 -SecurityTypes None --I-KNOW-THIS-IS-INSECURE
websockify -D --web=/usr/share/novnc/ 127.0.0.1:6080 127.0.0.1:5901
echo DESKTOP_READY
