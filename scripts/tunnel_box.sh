#!/usr/bin/env bash
# Laptop as the middle (Boss, 20.11.2026): the box reaches Uzbek-only public sites (public.sud.uz, data.egov.uz,
# regulation.gov.uz if needed) through the laptop's own connection, and everything is saved ON THE BOX, nothing on the
# laptop. OpenSSH reverse dynamic forwarding: on the box, socks5://127.0.0.1:1080 exits through this laptop.
# On the box: MEZON_PROXY=socks5://127.0.0.1:1080 python -m ...   (research/polite_http.py reads MEZON_PROXY)
# Reconnects by itself (box swaps, internet drops). Stop: kill this script.
while true; do
  ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o ConnectTimeout=20 -R 127.0.0.1:1080 box
  echo "$(date '+%F %T') tunnel down, retrying in 30 s" >&2
  sleep 30
done
