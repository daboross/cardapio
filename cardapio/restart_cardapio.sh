#!/bin/bash

PID=`ps -Af | awk '/cardapio --oaf-activate-iid/ && !/awk/ {print $2}'`
kill $PID
