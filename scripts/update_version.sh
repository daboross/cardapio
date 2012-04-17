#!/bin/bash

OLD=$(echo $1 | sed 's/\./\\\./g')
NEW=$2

if [ $# -eq 0 ]; then
	echo 'Usage: update_version.sh 1.2.2 1.2.3'
	exit
fi

# update version
find -name '*.py' -exec sed -i "s/$OLD/$NEW/g" \{\} \;
find -name '*.ui' -exec sed -i "s/$OLD/$NEW/g" \{\} \;

