#!/bin/sh

xgettext --language=Python --keyword=_ --keyword=N_ --output=locale/cardapio.pot src/*.py src/plugins/*.py src/docky/*.py src/gnomepanel/*.py
xgettext --language=Glade --keyword=_ --keyword=N_ --output=locale/cardapio.pot --join-existing src/ui/*.ui 
intltool-extract --type="gettext/xml" src/gnomepanel/cardapio.server
xgettext --language=C --keyword=N_ --output=locale/cardapio.pot --join-existing src/gnomepanel/cardapio.server.h
