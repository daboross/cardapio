PYTHON=`which python`
DESTDIR=/

all:
		@echo "make install - Install on local system"
		@echo "make builddeb - Generate a deb source package"
		@echo "make clean - Get rid of scratch and byte files"
		@echo "make cleandeb - Get rid of package files"

install:
		$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

builddeb:
		debuild -S

clean:
		$(PYTHON) setup.py clean
		rm -rf build/ MANIFEST
		$(MAKE) -f $(CURDIR)/debian/rules clean
		find . -name '*.pyc' -delete

