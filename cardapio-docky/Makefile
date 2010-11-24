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
	mkdir -p $(PREFIX)/share/dockmanager/metadata/
	mkdir -p $(PREFIX)/share/dockmanager/scripts/
	cp -f src/cardapio_helper.py.info $(PREFIX)/share/dockmanager/metadata/
	cp -f src/cardapio_helper.py $(PREFIX)/share/dockmanager/scripts/
	chmod +x $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py

uninstall:
	rm -rf $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info
	rm -rf $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py


