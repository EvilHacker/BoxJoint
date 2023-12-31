import adsk.core
import adsk.fusion
import contextlib
import itertools

from .fusion_util import *


class FusionCustomFeatureAddIn:
	"""
	Abstract base class for Fusion 360 Custom Feature Add-Ins.

	A subclass should override specific methods as needed.
	"""
	def __init__(self, *,
		baseCommandId: str,
		name: str,
		createTooltip: str,
		editTooltip: str,
		resourceFolder: str,
		toolbarControls,
	):
		self.baseCommandId = baseCommandId
		self._computeDisabled = False
		self._editedCustomFeature: adsk.fusion.CustomFeature = None
		self._savedTimelineObject: adsk.fusion.TimelineObject = None

		# Create all handlers.
		self._createHandler = newEventHandler(self.onCreate, adsk.core.CommandCreatedEventHandler)
		self._editHandler = newEventHandler(self.onEdit, adsk.core.CommandCreatedEventHandler)
		self._computeHandler = newEventHandler(self.onCompute, adsk.fusion.CustomFeatureEventHandler)
		self._activateHandler = newEventHandler(self.onActivate, adsk.core.CommandEventHandler)
		self._preSelectHandler = newEventHandler(self.onPreSelect, adsk.core.SelectionEventHandler)
		self._validateInputsHandler = newEventHandler(self.onValidateInputs, adsk.core.ValidateInputsEventHandler)
		self._previewHandler = newEventHandler(self.onPreview, adsk.core.CommandEventHandler)
		self._executeCreateHandler = newEventHandler(self.onExecuteCreate, adsk.core.CommandEventHandler)
		self._executeEditHandler = newEventHandler(self.onExecuteEdit, adsk.core.CommandEventHandler)

		userInterface = adsk.core.Application.get().userInterface

		# Add the command definition for the "create" command.
		createCommandDef = userInterface.commandDefinitions.addButtonDefinition(
			baseCommandId + 'Create',
			name,
			createTooltip,
			resourceFolder)
		createCommandDef.commandCreated.add(self._createHandler)

		# Create the command definition for the "edit" command.
		editCommandDef = userInterface.commandDefinitions.addButtonDefinition(
			baseCommandId + 'Edit',
			name,
			editTooltip,
			'')
		editCommandDef.commandCreated.add(self._editHandler)

		# Create the custom feature definition.
		self._customFeatureDef = adsk.fusion.CustomFeatureDefinition.create(
			baseCommandId + 'Create',
			name,
			resourceFolder)
		self._customFeatureDef.editCommandId = baseCommandId + 'Edit'
		self._customFeatureDef.customFeatureCompute.add(self._computeHandler)

		# Add "create" control(s) to the toolbar.
		for toolbarControl in toolbarControls:
			control = (userInterface
				.workspaces.itemById(toolbarControl['workspace'])
				.toolbarPanels.itemById(toolbarControl['panel'])
				.controls.addCommand(
					createCommandDef,
					toolbarControl.get('beforeControl') or
						toolbarControl.get('afterControl') or '',  # positionID
					toolbarControl.get('beforeControl') is not None  # isBefore
				)
			)
			control.isPromotedByDefault = toolbarControl.get('promote', False)

	def __del__(self):
		userInterface = adsk.core.Application.get().userInterface

		commandIds = [self.baseCommandId + suffix for suffix in ['Create', 'Edit']]

		# Remove UI elements and commands.
		for collection in itertools.chain(
			(toolbar.controls for toolbar in userInterface.toolbars),
			(toolbar.controls for toolbar in userInterface.allToolbarPanels),
			[userInterface.commandDefinitions]
		) :
			for commandId in commandIds:
				command = collection.itemById(commandId)
				if command:
					command.deleteMe()

	def onCreate(self, eventArgs: adsk.core.CommandCreatedEventArgs):
		self._computeDisabled = False
		self._editedCustomFeature = None
		self._savedTimelineObject = None

		command = eventArgs.command
		self.createInputs(command, self.defaultParams())
		command.preSelect.add(self._preSelectHandler)
		command.validateInputs.add(self._validateInputsHandler)
		command.executePreview.add(self._previewHandler)
		command.execute.add(self._executeCreateHandler)

	def onEdit(self, eventArgs: adsk.core.CommandCreatedEventArgs):
		self._computeDisabled = False
		self._editedCustomFeature = None
		self._savedTimelineObject = None

		userInterface = adsk.core.Application.get().userInterface

		command = eventArgs.command
		customFeature = userInterface.activeSelections[0].entity
		self._editedCustomFeature = customFeature
		params = self.customFeatureToParams(customFeature)

		self.createInputs(command, params)
		command.activate.add(self._activateHandler)
		command.preSelect.add(self._preSelectHandler)
		command.validateInputs.add(self._validateInputsHandler)
		command.executePreview.add(self._previewHandler)
		command.execute.add(self._executeEditHandler)

	def onCompute(self, eventArgs: adsk.fusion.CustomFeatureEventArgs):
		if self._computeDisabled:
			return

		customFeature = eventArgs.customFeature

		# Save the current position of the timeline.
		savedTimelineObject = currentTimelineObject()

		customFeature.timelineObject.rollTo(rollBefore=True)
		params = self.customFeatureToParams(customFeature)
		features = list(customFeature.features)
		customFeature.setStartAndEndFeatures(None, None)
		customFeature.timelineObject.rollTo(rollBefore=False)
		features = self.createOrUpdateChildFeatures(params,
			existingFeatures=features,
			allowFeatureCreationAndDeletion=False)
		customFeature.timelineObject.rollTo(rollBefore=True)
		if features:
			customFeature.setStartAndEndFeatures(features[0], features[-1])
		customFeature.timelineObject.rollTo(rollBefore=False)

		# Roll the timeline to its previous position.
		savedTimelineObject.rollTo(False)

	def onActivate(self, eventArgs: adsk.core.CommandEventArgs):
		command = eventArgs.command
		customFeature = self._editedCustomFeature

		if not customFeature:
			# Not currently editing an existing custom feature.
			return

		self._savedTimelineObject = currentTimelineObject()
		customFeature.timelineObject.rollTo(rollBefore = True)
		command.beginStep()

		params = self.customFeatureToParams(customFeature)
		with self.computeDisabled():
			self.paramsToInputs(params, command.commandInputs)

		command.doExecutePreview()

	def onPreSelect(self, eventArgs: adsk.core.SelectionEventArgs):
		eventArgs.isSelectable = False
		eventArgs.isSelectable = self.canSelect(eventArgs.selection.entity, eventArgs.activeInput)

	def onValidateInputs(self, eventArgs: adsk.core.ValidateInputsEventArgs):
		eventArgs.areInputsValid = False
		eventArgs.areInputsValid = self.areInputsValid(eventArgs.inputs)

	def onPreview(self, eventArgs: adsk.core.CommandEventArgs):
		if self._computeDisabled:
			return

		command = eventArgs.command
		customFeature = self._editedCustomFeature
		params = self.inputsToParams(command.commandInputs)

		with self.computeDisabled():
			if customFeature and customFeature.timelineObject:
				# Previewing changes to an existing feature.
				self._updateCustomFeature(params, customFeature)
			else:
				# Previewing a new feature.
				self._createCustomFeature(params)

		eventArgs.isValidResult = True

	def onExecuteCreate(self, eventArgs: adsk.core.CommandEventArgs):
		params = self.inputsToParams(eventArgs.command.commandInputs)

		with self.computeDisabled():
			self._createCustomFeature(params)

		eventArgs.executeFailed = False

	def onExecuteEdit(self, eventArgs: adsk.core.CommandEventArgs):
		command = eventArgs.command
		customFeature = self._editedCustomFeature
		params = self.inputsToParams(command.commandInputs)

		with self.computeDisabled():
			self._updateCustomFeature(params, customFeature)

		# Roll the timeline to its previous position.
		if self._savedTimelineObject:
			self._savedTimelineObject.rollTo(False)
			self._savedTimelineObject = None

		eventArgs.executeFailed = False

	def _createCustomFeature(self, params):
		design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
		customFeatures = design.activeComponent.features.customFeatures

		customFeatureInput = customFeatures.createInput(self._customFeatureDef)

		# Add all custom feature parameters.
		for name, value in self.getCustomParameters(params).items():
			customFeatureInput.addCustomParameter(
				name, self.getCustomParameterDescription(name),
				value.valueInput, value.units.strip())

		# Add all dependencies.
		for name, entity in self.getDependencies(params).items():
			customFeatureInput.addDependency(name, entity)

		# Create an empty custom feature first.
		customFeature = customFeatures.add(customFeatureInput)

		# Add all custom named values.
		for name, value in self.getCustomNamedValues(params).items():
			customFeature.customNamedValues.addOrSetValue(name, value)

		# Create all child features.
		features = self.createOrUpdateChildFeatures(params,
			existingFeatures=[],
			allowFeatureCreationAndDeletion=True)
		customFeature.timelineObject.rollTo(rollBefore=True)
		if features:
			customFeature.setStartAndEndFeatures(features[0], features[-1])
		customFeature.timelineObject.rollTo(rollBefore=False)

	def _updateCustomFeature(self, params, customFeature: adsk.fusion.CustomFeature):
		customFeature.timelineObject.rollTo(rollBefore=True)

		# Update all custom feature parameters.
		for name, value in self.getCustomParameters(params).items():
			customFeature.parameters.itemById(name).expression = value.expression

		# Update all dependencies.
		customFeature.dependencies.deleteAll()
		for name, entity in self.getDependencies(params).items():
			customFeature.dependencies.add(name, entity)

		# Update all custom named values.
		for name, value in self.getCustomNamedValues(params).items():
			customFeature.customNamedValues.addOrSetValue(name, value)

		# Update child features.
		customFeature.timelineObject.rollTo(rollBefore=True)
		features = list(customFeature.features)
		customFeature.setStartAndEndFeatures(None, None)
		customFeature.timelineObject.rollTo(rollBefore=False)
		features = self.createOrUpdateChildFeatures(params,
			existingFeatures=features,
			allowFeatureCreationAndDeletion=True)
		customFeature.timelineObject.rollTo(rollBefore=True)
		if features:
			customFeature.setStartAndEndFeatures(features[0], features[-1])
		customFeature.timelineObject.rollTo(rollBefore=False)

	def createInputs(self, command: adsk.core.Command, params):
		pass

	def canSelect(self, entity, forInput: adsk.core.SelectionCommandInput) -> bool:
		return True

	def areInputsValid(self, commandInputs: adsk.core.CommandInputs) -> bool:
		return True

	def defaultParams(self):
		return {}

	def paramsToInputs(self, params, commandInputs: adsk.core.CommandInputs):
		pass

	def inputsToParams(self, commandInputs: adsk.core.CommandInputs):
		return self.defaultParams()

	def customFeatureToParams(self, feature: adsk.fusion.CustomFeature):
		return self.defaultParams()

	def getCustomParameters(self, params) -> dict[str, Parameter]:
		return {}

	def getCustomParameterDescriptions(self) -> dict[str, str]:
		return {}

	def getCustomParameterDescription(self, parameterId: str) -> str:
		return self.getCustomParameterDescriptions().get(parameterId, parameterId)

	def getCustomNamedValues(self, params) -> dict[str, str]:
		return {}

	def getDependencies(self, params) -> dict[str, adsk.core.Base]:
		return {}

	def createOrUpdateChildFeatures(self,
		params,
		existingFeatures: list[adsk.fusion.Feature],
		allowFeatureCreationAndDeletion: bool
	) -> list[adsk.fusion.Feature]:
		return existingFeatures

	@contextlib.contextmanager
	def computeDisabled(self):
		computeDisabled = self._computeDisabled
		self._computeDisabled = True
		yield
		self._computeDisabled = computeDisabled
