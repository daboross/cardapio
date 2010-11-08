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
	python -m compileall src/
	python -m compileall src/plugins/
	
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.pyc $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.ui $(PREFIX)/lib/cardapio/
	cp -f res/Cardapio.desktop $(PREFIX)/lib/cardapio/
	
	mkdir -p $(PREFIX)/share/pixmaps
	cp -f res/cardapio*.xcf $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.png $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.svg $(PREFIX)/share/pixmaps/
	
	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f src/plugins/* $(PREFIX)/lib/cardapio/plugins/
	
	mkdir -p $(PREFIX)/lib/cardapio/docky
	cp -f src/docky/DockySettingsHelper.py $(PREFIX)/lib/cardapio/docky/
	cp -f src/docky/DockySettingsHelper.pyc $(PREFIX)/lib/cardapio/docky/
	if test -d $(PREFIX)/share/dockmanager; then \
		cp -f src/docky/metadata/cardapio.py.info $(PREFIX)/share/dockmanager/metadata/; \
		cp -f src/docky/scripts/cardapio.py $(PREFIX)/share/dockmanager/scripts/; \
		chmod +x $(PREFIX)/share/dockmanager/scripts/cardapio.py; \
	fi
	
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
	rm -rf $(PREFIX)/share/pixmaps/cardapio*
	rm $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	find $(PREFIX)/share/locale -name '*cardapio.mo' -delete
	if test -d $(PREFIX)/share/dockmanager; then\
		rm $(PREFIX)/share/dockmanager/metadata/cardapio.py.info; \
		rm $(PREFIX)/share/dockmanager/scripts/cardapio.py; \
	fi

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)
	# TODO: add docky stuff here

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/
	if test -d $(PREFIX)/share/dockmanager; then\
		rm $(PREFIX)/share/dockmanager/metadata/cardapio.py.info; \
		rm $(PREFIX)/share/dockmanager/scripts/cardapio.py; \
	fi

oldclean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete

