ifeq ($(DESTDIR),)
DESTDIR = 
endif

ifeq ($(PREFIX),)
PREFIX = $(DESTDIR)/usr
endif

all:
	@echo "make install - Install on local system"
	@echo "make uninstall - Remove from local system"
	@echo "make buildsrc - Generate a deb source package"

buildsrc:
	debuild -S

install: 
	#mkdir -p $(PREFIX)/lib/cardapio
	#cp -f src/cardapio-gnome-panel-applet $(PREFIX)/lib/cardapio/
	#mkdir -p $(PREFIX)/bin
	#ln -fs $(PREFIX)/lib/cardapio/cardapio-gnome-panel-applet $(PREFIX)/bin/cardapio-gnome-panel-applet

uninstall:
	#rm -f $(PREFIX)/lib/cardapio/cardapio-gnome-panel-applet
	#rm -rf $(PREFIX)/bin/cardapio-gnome-panel-applet 

