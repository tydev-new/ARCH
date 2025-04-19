#!/bin/sh

cd /home/ec2-user/new-tardis
python3 -m src.container_finalizer

#sudo ctr c checkpoint --rw --task --image tc checkpoint/tc-1
