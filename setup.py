from os import path
from distutils.core import setup
from distutils.sysconfig import get_python_lib

setup(
		name         = 'Cardapio',
		version      = '0.9.0',
		description  = 'A menu with search capabilities.',
		author       = 'Thiago Teixeira',
		author_email = 'tvst@hotmail.com',
		url          = 'https:// launchpad.net/cardapio',
		packages     = ['cardapio'],
		package_data = {'cardapio': ['cardapio.ui']},
		data_files   = [
				('/usr/local/bin', ['cardapio/cardapio']),
				('/usr/lib/bonobo/servers', ['cardapio/cardapio.server']),
			],
		)

