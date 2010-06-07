#!/bin/sh

intltool-extract --type=gettext/glade cardapio.ui

xgettext --language=Python --keyword=_ --keyword=N_ --output=cardapio.pot cardapio.py cardapio.ui.h

rm cardapio.ui.h
