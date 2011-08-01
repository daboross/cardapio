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
	mkdir -p $(PREFIX)/share/gnome-shell/extensions
	cp -rf src/cardapio@varal.org $(PREFIX)/share/gnome-shell/extensions/

uninstall:
	rm -rf $(PREFIX)/share/gnome-shell/extensions/cardapio@varal.org


