#!/bin/sh

intltool-extract --type=gettext/glade cardapio.ui
xgettext --language=Python --keyword=_ --keyword=N_ --output=cardapio.pot cardapio.py cardapio.ui.h cardapio.server plugins/*.py
rm cardapio.ui.h
