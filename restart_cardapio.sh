#!/bin/bash

PID=`ps -Af | awk '/cardapio-gnome-panel-applet --oaf-activate-iid/ && !/awk/ {print $2}'`
kill $PID
