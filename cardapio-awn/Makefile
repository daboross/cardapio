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
	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/cardapio_awn_applet_wrapper.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAwnApplet.py $(PREFIX)/lib/cardapio/
	
	mkdir -p /usr/share/avant-window-navigator/applets
	cp -f src/cardapio.desktop /usr/share/avant-window-navigator/applets

uninstall:
	rm -rf $(PREFIX)/lib/cardapio/cardapio_awn_applet_wrapper.py
	rm -rf $(PREFIX)/lib/cardapio/CardapioAwnApplet.py
	rm -rf /usr/share/avant-window-navigator/applets/cardapio.desktop


