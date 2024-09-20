import adsk.core
import adsk.fusion
from functools import wraps
import io
import inspect
import traceback
from typing import Union


def with_logging(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		log(f'Enter {f.__name__}')
		result = f(*args, **kwargs)
		log(f'Exit {f.__name__} -> {result}')
		return result
	return wrapper


def log(message):
	userInterface = adsk.core.Application.get().userInterface
	userInterface.palettes.itemById('TextCommands').writeText(message)


def messageBox(message):
	adsk.core.Application.get().userInterface.messageBox(message)


def handleException():
	frameInfo = inspect.stack()[1]
	prefix = ''
	if 'self' in frameInfo.frame.f_locals:
		prefix = frameInfo.frame.f_locals['self'].__class__.__name__ + '.'
	log(f'{prefix}{frameInfo.function}: {traceback.format_exc()}\n')


def newObjectCollection(objects) -> adsk.core.ObjectCollection:
	collection = adsk.core.ObjectCollection.create()
	for object in objects:
		collection.add(object)
	return collection


def newEventHandler(handler, superclass):
	class EventHandler(superclass):
		def notify(self, eventArgs):
			try:
				handler(eventArgs)
			except:
				handleException()
	return EventHandler()


def currentTimelineObject() -> adsk.fusion.TimelineObject:
	design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
	timeline = design.timeline
	return timeline[timeline.markerPosition - 1]


def newValueInput(value) -> adsk.core.ValueInput:
	if isinstance(value, str):
		return adsk.core.ValueInput.createByString(value)
	if isinstance(value, (float, int)):
		return adsk.core.ValueInput.createByReal(value)
	if isinstance(value, bool):
		return adsk.core.ValueInput.createByBoolean(value)
	if isinstance(value, adsk.core.Base):
		return adsk.core.ValueInput.createByObject(value)
	return None


def cmOrIn(centimeters: float, inches: float) -> float:
	# Choose a length in centimeters or inches based on user preferences.
	design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
	if design and design.unitsManager.defaultLengthUnits in ('in', 'ft'):
		return inches * 2.54
	else:
		return centimeters


class UserInputError(ValueError):
	def __init__(self, input, message):
		super().__init__(f'{input.name} {message}')
		self.input = input
		self.message = message


class Parameter:
	# Indicates that all units are forbidden within an expression.
	# Note that this is different than allowing ANY units.
	UNITLESS = ''

	def __init__(self,
		value: Union[
			str,
			'Parameter',
			adsk.fusion.Parameter,
			adsk.core.ValueCommandInput,
			adsk.core.FloatSpinnerCommandInput,
			adsk.core.IntegerSpinnerCommandInput,
			adsk.core.DistanceValueCommandInput,
			adsk.core.AngleValueCommandInput,
			adsk.core.SliderCommandInput],
		units: str = UNITLESS
	):
		if isinstance(value, adsk.core.Base):
			if isinstance(value, (adsk.core.ValueCommandInput, adsk.core.FloatSpinnerCommandInput)):
				self._expression = value.expression
				self._units = value.unitType or self.UNITLESS
				return
			if isinstance(value, adsk.core.IntegerSpinnerCommandInput):
				self._expression = str(value.value)
				self._units = self.UNITLESS
				return
			if isinstance(value, adsk.core.DistanceValueCommandInput):
				unitsManager = adsk.core.Application.get().activeProduct.unitsManager
				self._expression = value.expression
				self._units = unitsManager.defaultLengthUnits
				return
			if isinstance(value, adsk.core.AngleValueCommandInput):
				self._expression = value.expression
				self._units = 'deg'
				return
			if isinstance(value, adsk.core.SliderCommandInput):
				self._expression = value.expressionOne
				self._units = value.unitType or self.UNITLESS
				return
		if isinstance(value, (adsk.fusion.Parameter, Parameter)):
			self._expression = value.expression
			self._units = value.unit or self.UNITLESS
			return
		self._expression = str(value)
		self._units = units

	@classmethod
	def length(cls, centimeters: float) -> 'Parameter':
		"""
		Create a length specified in Fusion's internal units (centimeters), and converts
		it to the default length units as per user preferences (usually mm, cm, m, in, ft).
		"""
		unitsManager = adsk.core.Application.get().activeProduct.unitsManager
		lengthUnits = unitsManager.defaultLengthUnits
		return cls(
			unitsManager.formatInternalValue(centimeters, lengthUnits, True),
			lengthUnits)

	@property
	def value(self) -> float:
		unitsManager = adsk.core.Application.get().activeProduct.unitsManager
		return unitsManager.evaluateExpression(self._expression, self._units)

	@property
	def expression(self) -> str:
		return self._expression

	@property
	def unit(self) -> str:
		return self._units

	@property
	def units(self) -> str:
		return self._units

	@property
	def valueInput(self) -> adsk.core.ValueInput:
		return adsk.core.ValueInput.createByString(self._expression)

	def __repr__(self) -> str:
		return f'Parameter({repr(self.expression)}, {repr(self.units)})'


class EntityRef:
	def __init__(self, entityOrToken):
		if not isinstance(entityOrToken, str):
			entityOrToken = entityOrToken.entityToken
		self._token = entityOrToken

	@property
	def entity(self):
		design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
		entities = design.findEntityByToken(self._token)
		if len(entities):
			return entities[0]
		return None

	@property
	def entityToken(self):
		return self._token

	def __repr__(self) -> str:
		entity = self.entity
		return f'EntityRef({entity and f"<{entity.__class__.__name__}>"})'


def dumpMenus() -> str:
	out = io.StringIO()
	userInterface = adsk.core.Application.get().userInterface
	for toolbar in userInterface.toolbars:
		try:
			for control in toolbar.controls:
				out.write(f'Toolbar: {toolbar.id}/{control.id}\n')
		except:
			pass
	for workspace in userInterface.workspaces:
		try:
			for toolbar in workspace.toolbarPanels:
				for control in toolbar.controls:
					out.write(f'Workspace Panel: {workspace.id}/{toolbar.id}/{control.id}\n')
		except:
			pass
	return out.getvalue()
