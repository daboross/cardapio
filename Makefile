PYTHON = `which python`

ifeq ($(DESTDIR),)
DESTDIR = 
endif

ifeq ($(PREFIX),)
PREFIX = $(DESTDIR)/usr
endif

all:
	@echo "make install - Install on local system"
	@echo "make install-alone - Install just Cardapio."
	@echo "make install-panel - Install Gnome Panel applet."
	@echo "make install-docky - Install AWN applet."
	@echo "make install-awn - Install AWN applet."
	@echo "make install-shell - Install Gnome Shell applet."
	@echo "make install-mate - Install Mate Panel applet."
	@echo "make install-cinnamon - Install Cinnamon applet."
	@echo "make uninstall - Remove from local system"
	@echo "make uninstall-* - Remove * from local system"
	@echo "make buildsrc - Generate a deb source package"
	@echo "make clean - Get rid of scratch and byte files"

buildsrc:
	debuild -S

clean:
	find . -name '*.pyc' -delete

install: install-alone install-panel install-docky install-awn install-shell install-mate install-cinnamon

install-alone:
	python -m compileall src/
	python -m compileall src/plugins/

	# remove old files which have been renamed or moved to another package
	rm -f $(PREFIX)/lib/cardapio/cardapio.py
	rm -f $(PREFIX)/lib/cardapio/cardapio.pyc
	rm -f $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.py
	rm -f $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.pyc

	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.pyc $(PREFIX)/lib/cardapio/
	cp -f src/Constants.py $(PREFIX)/lib/cardapio/
	cp -f src/Constants.pyc $(PREFIX)/lib/cardapio/
	cp -f src/DesktopEnvironment.py $(PREFIX)/lib/cardapio/
	cp -f src/DesktopEnvironment.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioSimpleDbusApplet.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioSimpleDbusApplet.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioPluginInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioPluginInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/OptionsWindow.py $(PREFIX)/lib/cardapio/
	cp -f src/OptionsWindow.pyc $(PREFIX)/lib/cardapio/
	cp -f src/misc.py $(PREFIX)/lib/cardapio/
	cp -f src/misc.pyc $(PREFIX)/lib/cardapio/
	cp -f src/MenuHelperInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/MenuHelperInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/GMenuHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/GMenuHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f src/XDGMenuHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/XDGMenuHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f src/IconHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/IconHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f src/SettingsHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/SettingsHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f res/cardapio.desktop $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/ui
	cp -f src/ui/cardapio.ui $(PREFIX)/lib/cardapio/ui/
	cp -f src/ui/options.ui $(PREFIX)/lib/cardapio/ui/

	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f src/plugins/* $(PREFIX)/lib/cardapio/plugins/

	mkdir -p $(PREFIX)/share/locale
	cp -rf locale/* $(PREFIX)/share/locale/

	mkdir -p $(PREFIX)/share/pixmaps
	cp -f res/cardapio*.png $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.svg $(PREFIX)/share/pixmaps/

	mkdir -p $(PREFIX)/bin
	ln -sf ../lib/cardapio/cardapio $(PREFIX)/bin/cardapio

	mkdir -p $(PREFIX)/share/applications
	cp -f res/cardapio.desktop $(PREFIX)/share/applications/

	mkdir -p $(PREFIX)/share/dbus-1/services
	cp -f res/cardapio.service $(PREFIX)/share/dbus-1/services/cardapio.service

install-panel: install-alone
	python -m compileall src/gnomepanel/
	cp -f src/gnomepanel/cardapio-gnome-panel $(PREFIX)/lib/cardapio/
	cp -f src/gnomepanel/cardapio-gnome3-panel $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/gnomepanel
	cp -f src/gnomepanel/CardapioGnomeApplet* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/CardapioGnomeAppletFactory* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/CardapioGnome3Applet* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/__init__* $(PREFIX)/lib/cardapio/gnomepanel/

	mkdir -p $(PREFIX)/bin
	ln -sf ../lib/cardapio/cardapio-gnome-panel $(PREFIX)/bin/cardapio-gnome-panel
	ln -sf ../lib/cardapio/cardapio-gnome3-panel $(PREFIX)/bin/cardapio-gnome3-panel

	mkdir -p $(PREFIX)/lib/gnome-applets
	ln -sf ../cardapio/cardapio-gnome3-panel $(PREFIX)/lib/gnome-applets/cardapio-gnome-panel

	mkdir -p $(PREFIX)/share/dbus-1/services
	cp -f src/gnomepanel/cardapio.service $(PREFIX)/share/dbus-1/services/org.gnome.panel.applet.CardapioGnomeApplet.service

	mkdir -p $(PREFIX)/share/gnome-panel/4.0/applets
	cp -f src/gnomepanel/cardapio.panel-applet $(PREFIX)/share/gnome-panel/4.0/applets/org.gnome.applets.CardapioGnomeApplet.panel-applet

	mkdir -p $(PREFIX)/lib/bonobo/servers
	#cp -f src/gnomepanel/cardapio-gnome-panel.server $(PREFIX)/lib/bonobo/servers/
	for f in locale/*; \
		do test -f $$f/LC_MESSAGES/cardapio.mo && msgunfmt -o $$f.po $$f/LC_MESSAGES/cardapio.mo || true; \
	done
	intltool-merge -b locale src/gnomepanel/cardapio.server $(PREFIX)/lib/bonobo/servers/cardapio.server
	rm locale/*.po

install-mate: install-alone
	python -m compileall src/matepanel/
	cp -f src/matepanel/cardapio-mate-panel-applet $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/matepanel
	cp -f src/matepanel/CardapioMateApplet* $(PREFIX)/lib/cardapio/matepanel/
	cp -f src/matepanel/CardapioMateAppletFactory* $(PREFIX)/lib/cardapio/matepanel/
	cp -f src/matepanel/__init__* $(PREFIX)/lib/cardapio/matepanel/

	mkdir -p $(PREFIX)/bin
	ln -sf ../lib/cardapio/cardapio-mate-panel-applet $(PREFIX)/bin/cardapio-mate-panel-applet

	mkdir -p $(PREFIX)/lib/matecomponent/servers
	#cp -f src/matepanel/cardapio.server $(PREFIX)/lib/matecomponent/servers/
	for f in locale/*; \
		do test -f $$f/LC_MESSAGES/cardapio.mo && msgunfmt -o $$f.po $$f/LC_MESSAGES/cardapio.mo || true; \
	done
	intltool-merge -b locale src/matepanel/cardapio.server $(PREFIX)/lib/matecomponent/servers/cardapio.server
	rm locale/*.po

install-docky: install-alone
	python -m compileall src/docky/
	cp -f res/cardapioDocky.desktop $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/docky
	cp -f src/docky/DockySettingsHelper* $(PREFIX)/lib/cardapio/docky/
	cp -f src/docky/__init__* $(PREFIX)/lib/cardapio/docky/

	mkdir -p $(PREFIX)/share/dockmanager/metadata $(PREFIX)/share/dockmanager/scripts
	cp -f src/docky/cardapio_helper.py.info $(PREFIX)/share/dockmanager/metadata/
	cp -f src/docky/cardapio_helper.py $(PREFIX)/share/dockmanager/scripts/
	chmod +x $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py

install-awn: install-alone
	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/awn/CardapioAwnWrapper.py $(PREFIX)/lib/cardapio/
	cp -f src/awn/CardapioAwnApplet.py $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/share/avant-window-navigator/applets
	cp -f src/awn/cardapio.desktop $(PREFIX)/share/avant-window-navigator/applets

install-shell: install-alone
	mkdir -p $(PREFIX)/share/gnome-shell/extensions
	cp -rf src/gnomeshell/cardapio@varal.org $(PREFIX)/share/gnome-shell/extensions/

install-cinnamon: install-alone
	mkdir -p $(PREFIX)/share/cinnamon/applets
	cp -rf src/cinnamon/cardapio@varal.org $(PREFIX)/share/cinnamon/applets/

uninstall: uninstall-alone uninstall-panel uninstall-docky uninstall-awn uninstall-cinnamon uninstall-mate

uninstall-alone: uninstall-panel uninstall-docky uninstall-awn uninstall-cinnamon
	rm -rf $(PREFIX)/lib/cardapio
	rm -f $(PREFIX)/bin/cardapio
	rm -f $(PREFIX)/share/pixmaps/cardapio*
	rm -f $(PREFIX)/share/applications/cardapio.desktop
	rm -f $(DESTDIR)/usr/share/dbus-1/services/cardapio.service
	find $(PREFIX)/share/locale -name '*cardapio.*' -delete

	# remove old files which have been renamed or moved to another package
	rm -f $(PREFIX)/lib/cardapio/cardapio.py
	rm -f $(PREFIX)/lib/cardapio/cardapio.pyc
	rm -f $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.py
	rm -f $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.pyc

uninstall-panel:
	rm -rf $(PREFIX)/lib/cardapio/gnomepanel
	rm -f $(PREFIX)/lib/cardapio/cardapio-gnome-panel-applet
	rm -f $(PREFIX)/bin/cardapio-gnome-panel-applet
	rm -f $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server

uninstall-applet:
	rm -rf $(PREFIX)/lib/cardapio/gnomeapplet
	rm -f $(PREFIX)/lib/cardapio/cardapio-gnome-applet
	rm -f $(PREFIX)/lib/gnome-applets/cardapio-gnome-applet
	rm -f $(PREFIX)/share/dbus-1/services/org.gnome.panel.applet.cardapio.service
	rm -f $(PREFIX)/share/gnome-panel/4.0/applets/org.gnome.applets.cardapio.panel-applet

uninstall-docky:
	rm -f $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info
	rm -f $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py

uninstall-awn:
	rm -f $(PREFIX)/lib/cardapio/CardapioAwnWrapper.*
	rm -f $(PREFIX)/lib/cardapio/CardapioAwnApplet.*
	rm -f $(PREFIX)/share/avant-window-navigator/applets/cardapio.desktop

uninstall-mate:
	rm -f $(PREFIX)/lib/cardapio/cardapio-mate-panel-applet
	rm -rf $(PREFIX)/bin/cardapio-mate-panel-applet
	rm -f $(DESTDIR)/usr/lib/matecomponent/servers/cardapio.server

uninstall-cinnamon:
	rm -rf $(PREFIX)/share/cinnamon/applets/cardapio@varal.org

# I hear these "old" entries are useful in Gentoo, so I'm leaving them here:

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
