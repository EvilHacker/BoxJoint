from .fusion_box_joint import BoxJointAddIn
from .fusion_util import log, handleException


log(f'Loading Fusion Add-In {repr(__file__)} ...')


thisAddIn: BoxJointAddIn = None


def run(context):
	try:
		log(f'Starting Fusion Add-In {repr(__file__)} ...')
		global thisAddIn
		thisAddIn = BoxJointAddIn()
	except:
		handleException()


def stop(context):
	try:
		log(f'Stopping Fusion Add-In {repr(__file__)} ...')
		global thisAddIn
		del thisAddIn
	except:
		handleException()


log(f'Finished loading Fusion Add-In {repr(__file__)}')
