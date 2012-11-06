#!/bin/bash

# Version v1.2

dists="lucid maverick natty oneiric precise quantal"
srcs="$(cd .; pwd)"
noask="no"
repo="ppa:cardapio-team/unstable"

help() {
	cat <<EOB
Usage: ${0} [-y] [-o] [-p <ppa:user/repo>] [-d <dist1 distx>] <debsrc>
	-y : Do not approve each upload in series
	-o : Create source package including .orig tarball
	-f : Force upload even if source package marked as already uploaded
	-d : Specify distribution series, might be multiple in single quotes
	-p : Specify target PPA / repository
Example: ${0} -y -o -p "${repo}" -d "lucid oneiric" .
EOB
	exit 1
}

build_src() {
	for dist in ${dists}; do
		pushd ${1} > /dev/null
		dist_old="$(dpkg-parsechangelog | grep "Distribution:" | awk '{print $2}')"
		src="$(dpkg-parsechangelog | grep "Source:" | awk '{print $2}')"
		echo -n "Will build [${src}]/[${dist_old} => ${dist}] in [$(pwd)] for repository [${repo}]"
		if [ ! "${noask}" == "y" ]; then
			read -p ", [y/n]" input
			if [ ! ${input} == "y" ]; then
				popd > /dev/null
				continue
			fi
		else
			echo "."
		fi

		sed -i "s/${dist_old}/${dist}/g" debian/changelog
		dput${force} ${repo} $(dpkg-buildpackage -S${orig} 2>&1 | grep "dpkg-genchanges -S${orig} >.." | cut -f2 -d'>')
		popd > /dev/null

		unset orig
		unset input
	done
}

#gather options from command line and set flags
[ $# -eq 0 ] && help
while getopts yofp:d: opt; do
	case "$opt" in
		y)	noask="y"	;;
		o)	orig=" -sa"	;;
		f)	force=" -f"	;;
		d)	dists=${OPTARG}	;;
		p)	repo=${OPTARG}	;;
		*)	help		;;
	esac
done

shift `expr $OPTIND - 1`

echo "Will build and upload source packages [${@}] for [${dists}], orig:[${orig}], noask:[${noask}]"

for src in "$@"; do
	echo "Building [${src}]"
	build_src ${src}
done
