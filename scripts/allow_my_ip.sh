#!/usr/bin/env bash
# Add this laptop's current public IP (SSH only, /32) to the Mezon AWS firewall groups. Boss-approved 21.11.2026.
IP=$(curl -s -m 10 https://checkip.amazonaws.com | tr -d '\r\n')
[ -z "$IP" ] && { echo "no IP"; exit 1; }
echo "IP $IP"
for pair in "us-east-1 sg-0deb8f22322c7965a" "us-east-2 sg-09aa1c276b0e583de"; do
  set -- $pair
  aws ec2 authorize-security-group-ingress --region $1 --group-id $2 --protocol tcp --port 22 --cidr $IP/32 >/dev/null 2>&1 \
    && echo "$1 added" || echo "$1 already allowed (or failed)"
done
