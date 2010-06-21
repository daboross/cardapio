PYTHON = `which python`
DESTDIR = /

ifeq ($(PREFIX),)
PREFIX = /usr
endif

all:
	@echo "make install - Install on local system"
	@echo "make uninstall - Remove from local system"
	@echo "make buildsrc - Generate a deb source package"
	@echo "make clean - Get rid of scratch and byte files"

install:
	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f cardapio/cardapio $(PREFIX)/lib/cardapio
	ln -s $(PREFIX)/lib/cardapio/cardapio $(PREFIX)/bin/cardapio
	cp -f cardapio/cardapio.py $(PREFIX)/lib/cardapio
	cp -f cardapio/cardapio.ui $(PREFIX)/lib/cardapio
	cp -f cardapio/cardapio.server /usr/lib/bonobo/servers
	cp -f cardapio/plugins/* $(PREFIX)/lib/cardapio/plugins/
	cp -rf locale/* $(PREFIX)/share/locale

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)

buildsrc:
	debuild -S

clean:
	@echo "$(PREFIX)"
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/

uninstall:
	rm -rf $(PREFIX)/lib/cardapio
	rm -rf $(PREFIX)/bin/cardapio
	rm /usr/lib/bonobo/servers/cardapio.server
	find $(PREFIX)/share/locale -name '*cardapio.mo' -delete

