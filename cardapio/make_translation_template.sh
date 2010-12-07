#!/bin/sh

xgettext --language=Python --keyword=_ --keyword=N_ --output=locale/cardapio.pot src/*.py src/plugins/*.py src/docky/*.py
xgettext --language=Glade --keyword=_ --keyword=N_ --output=locale/cardapio.pot --join-existing src/ui/*.ui 

