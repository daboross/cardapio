PYTHON = `which python`

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
	@echo "make clean - Get rid of scratch and byte files"

install:
	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.ui $(PREFIX)/lib/cardapio/
	cp -f src/plugins/* $(PREFIX)/lib/cardapio/plugins/
	
	mkdir -p $(PREFIX)/share/locale
	cp -rf locale/* $(PREFIX)/share/locale/
	
	mkdir -p $(PREFIX)/bin
	ln -fs $(PREFIX)/lib/cardapio/cardapio $(PREFIX)/bin/cardapio
	
	mkdir -p $(DESTDIR)/usr/lib/bonobo/servers
	cp -f src/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/

buildsrc:
	debuild -S

clean:
	$(MAKE) -f $(CURDIR)/debian/rules clean
	find . -name '*.pyc' -delete

uninstall:
	rm -rf $(PREFIX)/lib/cardapio
	rm -rf $(PREFIX)/bin/cardapio
	rm $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	find $(PREFIX)/share/locale -name '*cardapio.mo' -delete

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/

oldclean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete

