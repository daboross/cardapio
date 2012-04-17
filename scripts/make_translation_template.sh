#!/bin/bash

pushd .
cd ..

xgettext --language=Python --keyword=_ --keyword=N_ --output=locale/cardapio.pot src/*.py src/plugins/*.py src/docky/*.py src/gnomepanel/*.py src/matepanel/*.py
xgettext --language=Glade --keyword=_ --keyword=N_ --output=locale/cardapio.pot --join-existing src/ui/*.ui 
intltool-extract --type="gettext/xml" src/gnomepanel/cardapio.server
intltool-extract --type="gettext/xml" src/matepanel/cardapio.server
xgettext --language=C --keyword=N_ --output=locale/cardapio.pot --join-existing src/gnomepanel/cardapio.server.h
xgettext --language=C --keyword=N_ --output=locale/cardapio.pot --join-existing src/matepanel/cardapio.server.h

popd
