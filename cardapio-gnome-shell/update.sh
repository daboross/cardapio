#!/bin/bash

OLD=$(echo $1 | sed 's/\./\\\./g')
NEW=$2

if [ $# -eq 0 ]; then
	echo 'Usage: update_version.sh 1.2.2 1.2.3'
	exit
fi

# update version
sed -i "s/$OLD/$NEW/g" latest_changelog
find -name '*.py' -exec sed -i "s/$OLD/$NEW/g" \{\} \;
find -name '*.ui' -exec sed -i "s/$OLD/$NEW/g" \{\} \;

echo 'Waiting 3s...'
sleep 3

# edit changelog
vim latest_changelog

# Lucid stuff
cp latest_changelog      latest_changelog_tmp
cat debian/changelog  >> latest_changelog_tmp
mv debian/changelog      debian/changelog_old
mv latest_changelog_tmp  debian/changelog
sed -i 's/XXXXX/lucid/g' debian/changelog
make buildsrc
dput ppa:cardapio-team/unstable ../cardapio-gnome-shell_$NEW-ubuntu1-lucid1_source.changes

# Maverick stuff
cp latest_changelog      latest_changelog_tmp
cat debian/changelog  >> latest_changelog_tmp
mv debian/changelog      debian/changelog_old
mv latest_changelog_tmp  debian/changelog
sed -i 's/XXXXX/maverick/g' debian/changelog
make buildsrc
dput ppa:cardapio-team/unstable ../cardapio-gnome-shell_$NEW-ubuntu1-maverick1_source.changes

# Natty stuff
cp latest_changelog      latest_changelog_tmp
cat debian/changelog  >> latest_changelog_tmp
mv debian/changelog      debian/changelog_old
mv latest_changelog_tmp  debian/changelog
sed -i 's/XXXXX/natty/g' debian/changelog
make buildsrc
dput ppa:cardapio-team/unstable ../cardapio-gnome-shell_$NEW-ubuntu1-natty1_source.changes
