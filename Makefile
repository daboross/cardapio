PYTHON = `which python`

ifeq ($(PREFIX),)
PREFIX = /usr
endif

ifeq ($(DESTDIR),)
DESTDIR =
endif

all:
	@echo "make install - Install on local system"
	@echo "make uninstall - Remove from local system"
	@echo "make buildsrc - Generate a deb source package"
	@echo "make clean - Get rid of scratch and byte files"

install:
	mkdir -p $(DESTDIR)$(PREFIX)/lib/cardapio/plugins
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	mkdir -p $(DESTDIR)/usr/lib/bonobo/servers
	mkdir -p $(DESTDIR)$(PREFIX)/share/locale
	cp -f cardapio/cardapio $(DESTDIR)$(PREFIX)/lib/cardapio/
	ln -s $(DESTDIR)$(PREFIX)/lib/cardapio/cardapio $(DESTDIR)$(PREFIX)/bin/cardapio
	cp -f cardapio/cardapio.py $(DESTDIR)$(PREFIX)/lib/cardapio/
	cp -f cardapio/cardapio.ui $(DESTDIR)$(PREFIX)/lib/cardapio/
	cp -f cardapio/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/
	cp -f cardapio/plugins/* $(DESTDIR)$(PREFIX)/lib/cardapio/plugins/
	cp -rf locale/* $(DESTDIR)$(PREFIX)/share/locale/

buildsrc:
	debuild -S

clean:
	@echo "$(PREFIX)"
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/cardapio
	rm -rf $(DESTDIR)$(PREFIX)/bin/cardapio
	rm $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	find $(DESTDIR)$(PREFIX)/share/locale -name '*cardapio.mo' -delete

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/

