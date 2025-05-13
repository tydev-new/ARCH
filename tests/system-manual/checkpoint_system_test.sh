#!/bin/sh

cd /home/ec2-user/ARCH
./arch-cli container finalize
#python3 -m src.arch container finalize

#sudo ctr c checkpoint --rw --task --image tc checkpoint/tc-1
