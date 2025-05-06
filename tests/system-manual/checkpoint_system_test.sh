#!/bin/sh

cd /home/ec2-user/ARCH
python3 -m src.arch container finalize

#sudo ctr c checkpoint --rw --task --image tc checkpoint/tc-1
