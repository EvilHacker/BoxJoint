import adsk.core
import adsk.fusion
from dataclasses import dataclass, field
import itertools
import math
import re

from .fusion_brep_util import *
from .fusion_base_combines import BaseCombines
from .fusion_cf_addin import FusionCustomFeatureAddIn
from .fusion_util import *


@dataclass
class BoxJointParameters:
	"""
	All parameter that define a specific box joint.

	Note that assignment of default values is deferred to instance creation time
	(using `default_factory`) rather than using static values because `Parameter` units
	will vary within the context of the current document and user preferences.
	"""
	faces: list[EntityRef] = field(default_factory=list)
	minFingers: Parameter = field(
		default_factory=lambda: Parameter(3))
	maxFingers: Parameter = field(
		default_factory=lambda: Parameter(33))
	minFingerWidth: Parameter = field(
		default_factory=lambda: Parameter.length(centimeters=cmOrIn(2.5, 1)))  # 2.5cm or 1"
	maxFingerWidth: Parameter = field(
		default_factory=lambda: Parameter.length(centimeters=cmOrIn(15, 6)))  # 15cm or 6"
	fingerRatio: Parameter = field(
		default_factory=lambda: Parameter(0.5))
	margin: Parameter = field(
		default_factory=lambda: Parameter.length(centimeters=0))
	bitDiameter: Parameter = field(
		default_factory=lambda: Parameter.length(centimeters=0.635))  # 1/4"


class BoxJointAddIn(FusionCustomFeatureAddIn):
	"""
	The Box Joint Fusion Add-In.
	"""
	def __init__(self):
		super().__init__(
			baseCommandId='Suska_BoxJoint',
			name='Box Joint',
			createTooltip='Create box/finger joints between two or more bodies.',
			editTooltip='Edit box/finger joints between bodies.',
			resourceFolder='Resources/BoxJoint',
			toolbarControls=[
				{
					'workspace': 'FusionSolidEnvironment',
					'panel': 'SolidScriptsAddinsPanel',
				},
				{
					'workspace': 'FusionSolidEnvironment',
					'panel': 'SolidModifyPanel',
					'afterControl': 'FusionCombineCommand',
					'promote': True
				},
			],
		)

	def createInputs(self, command: adsk.core.Command, params: BoxJointParameters):
		inputs = command.commandInputs

		# Create the selection input to select the planar faces on solid bodies.
		# Note: Selections cannot be pre-populated now.
		facesSelectInput = inputs.addSelectionInput(
			'faces',
			'Faces',
			'Select outside faces of bodies to join.')
		facesSelectInput.addSelectionFilter('SolidFaces')
		facesSelectInput.tooltip = 'Select outside faces of bodies to join.'
		facesSelectInput.setSelectionLimits(2)  # At least two faces needed.

		input = inputs.addFloatSpinnerCommandInput(
			'minFingers', 'Min Fingers',
			unitType=Parameter.UNITLESS, min=3, max=99, spinStep=2,
			initialValue=params.minFingers.value)
		input.expression = params.minFingers.expression

		input = inputs.addFloatSpinnerCommandInput(
			'maxFingers', 'Max Fingers',
			unitType=Parameter.UNITLESS, min=3, max=99, spinStep=2,
			initialValue=params.maxFingers.value)
		input.expression = params.maxFingers.expression

		input = inputs.addValueInput(
			'minFingerWidth', 'Min Finger Width',
			params.minFingerWidth.units, params.minFingerWidth.valueInput)
		input.minimumValue = 0
		input.isMinimumInclusive = False
		input.isMinimumLimited = True

		input = inputs.addValueInput(
			'maxFingerWidth', 'Max Finger Width',
			params.maxFingerWidth.units, params.maxFingerWidth.valueInput)
		input.minimumValue = 0
		input.isMinimumInclusive = False
		input.isMinimumLimited = True

		input = inputs.addFloatSpinnerCommandInput(
			'fingerRatio', 'Finger Ratio',
			unitType=Parameter.UNITLESS, min=0.01, max=0.99, spinStep=0.1,
			initialValue=params.fingerRatio.value)
		input.expression = params.fingerRatio.expression

		input = inputs.addValueInput(
			'margin', 'Margin',
			params.margin.units, params.margin.valueInput)
		input.minimumValue = 0
		input.isMinimumInclusive = True
		input.isMinimumLimited = True

		input = inputs.addValueInput(
			'bitDiameter', 'Tool Diameter',
			params.bitDiameter.units, params.bitDiameter.valueInput)
		input.minimumValue = 0
		input.isMinimumInclusive = True
		input.isMinimumLimited = True

		# For error message output.
		inputs.addTextBoxCommandInput('error', '', '', numRows=1, isReadOnly=True)

	def canSelect(self, entity, input: adsk.core.SelectionCommandInput) -> bool:
		if input.id == 'faces':
			# Must be a planar face on a solid body.
			if entity.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
				return False
			if not entity.body.isSolid:
				return False
		return True

	def areInputsValid(self, commandInputs: adsk.core.CommandInputs) -> bool:
		errorMessage = None
		try:
			for input in commandInputs:
				if hasattr(input, 'isValidExpression') and not input.isValidExpression:
					raise UserInputError(input, 'is invalid')

			for inputId in 'minFingers', 'maxFingers':
				input = commandInputs.itemById(inputId)
				value = input.value
				if math.floor(value) != math.ceil(value):
					raise UserInputError(input, 'must be an integer')
				if int(value) & 1 == 0:
					raise UserInputError(input, 'must be odd')
		except UserInputError as error:
			errorMessage = f'<span style="color:red"><b>{error.input.name}</b> {error.message}.</span>'

		# Set error message only if it has changed.
		errorBox: adsk.core.TextBoxCommandInput = commandInputs.itemById('error')
		if errorMessage:
			if errorBox.text != withoutHtml(errorMessage):
				log(f'User input error: {withoutHtml(errorMessage)}')
				errorBox.formattedText = errorMessage
		elif errorBox.text:
			log(f'User input error cleared')
			errorBox.formattedText = ''

		return errorMessage is None

	def defaultParams(self) -> BoxJointParameters:
		return BoxJointParameters()

	def paramsToInputs(self, params: BoxJointParameters, commandInputs: adsk.core.CommandInputs):
		facesInput: adsk.core.SelectionCommandInput = commandInputs.itemById('faces')
		facesInput.clearSelection()
		for face in params.faces:
			facesInput.addSelection(face.entity)

		commandInputs.itemById('minFingers').expression = params.minFingers.expression
		commandInputs.itemById('maxFingers').expression = params.maxFingers.expression
		commandInputs.itemById('minFingerWidth').expression = params.minFingerWidth.expression
		commandInputs.itemById('maxFingerWidth').expression = params.maxFingerWidth.expression
		commandInputs.itemById('fingerRatio').expression = params.fingerRatio.expression
		commandInputs.itemById('margin').expression = params.margin.expression
		commandInputs.itemById('bitDiameter').expression = params.bitDiameter.expression

	def inputsToParams(self, commandInputs: adsk.core.CommandInputs) -> BoxJointParameters:
		facesInput: adsk.core.SelectionCommandInput = commandInputs.itemById('faces')
		faces = []
		for i in range(0, facesInput.selectionCount):
			faces.append(EntityRef(facesInput.selection(i).entity))

		return BoxJointParameters(
			faces=faces,
			minFingers=Parameter(commandInputs.itemById('minFingers')),
			maxFingers=Parameter(commandInputs.itemById('maxFingers')),
			minFingerWidth=Parameter(commandInputs.itemById('minFingerWidth')),
			maxFingerWidth=Parameter(commandInputs.itemById('maxFingerWidth')),
			fingerRatio=Parameter(commandInputs.itemById('fingerRatio')),
			margin=Parameter(commandInputs.itemById('margin')),
			bitDiameter=Parameter(commandInputs.itemById('bitDiameter')),
		)

	def customFeatureToParams(self, feature: adsk.fusion.CustomFeature) -> BoxJointParameters:
		customNamedValues = feature.customNamedValues
		parameters = feature.parameters

		faces = [EntityRef(token) for token in
			customNamedValues.value('faces').split()]

		return BoxJointParameters(
			faces=faces,
			minFingers=Parameter(parameters.itemById('minFingers')),
			maxFingers=Parameter(parameters.itemById('maxFingers')),
			minFingerWidth=Parameter(parameters.itemById('minFingerWidth')),
			maxFingerWidth=Parameter(parameters.itemById('maxFingerWidth')),
			fingerRatio=Parameter(parameters.itemById('fingerRatio') or 0.5),
			margin=Parameter(parameters.itemById('margin') or 0),
			bitDiameter=Parameter(parameters.itemById('bitDiameter') or 0),
		)

	def getCustomParameters(self, params: BoxJointParameters) -> dict[str, Parameter]:
		return {
			'minFingers': params.minFingers,
			'maxFingers': params.maxFingers,
			'minFingerWidth': params.minFingerWidth,
			'maxFingerWidth': params.maxFingerWidth,
			'fingerRatio': params.fingerRatio,
			'margin': params.margin,
			'bitDiameter': params.bitDiameter,
		}

	def getCustomParameterDescriptions(self) -> dict[str, str]:
		return {
			'minFingers': 'Min Fingers',
			'maxFingers': 'Max Fingers',
			'minFingerWidth': 'Min Finger Width',
			'maxFingerWidth': 'Max Finger Width',
			'fingerRatio': 'Finger Ratio',
			'margin': 'Margin',
			'bitDiameter': 'Tool Diameter',
		}

	def getCustomNamedValues(self, params: BoxJointParameters) -> dict[str, str]:
		return {
			'faces': ' '.join([face.entityToken for face in params.faces]),
		}

	def getDependencies(self, params: BoxJointParameters) -> dict[str, adsk.core.Base]:
		bodies = {}
		for face in params.faces:
			body = face.entity.body
			bodies[body.revisionId] = body
		return {f'body{i}': body for i, body in enumerate(bodies.values())}

	def createOrUpdateChildFeatures(self,
		params: BoxJointParameters,
		existingFeatures: list[adsk.fusion.Feature],
		allowFeatureCreationAndDeletion: bool
	) -> list[adsk.fusion.Feature]:
		baseCombines = computeBoxJoint(params)
		features = baseCombines.createOrUpdate(
			existingFeatures=existingFeatures,
			allowFeatureCreationAndDeletion=allowFeatureCreationAndDeletion)
		return features


def computeBoxJoint(params: BoxJointParameters) -> BaseCombines:
	baseCombines = BaseCombines()

	if len(params.faces) < 2:
		return baseCombines

	# Normalize parameter values.
	faces = [face.entity for face in params.faces]
	bitDiameter = max(params.bitDiameter.value, 0)
	bitRadius = bitDiameter / 2
	minFingers = max(int(params.minFingers.value), 3) | 1
	maxFingers = max(int(params.maxFingers.value) - 1, minFingers) | 1
	minFingerWidth = max(params.minFingerWidth.value, bitDiameter, 0.0001)
	maxFingerWidth = max(params.maxFingerWidth.value, minFingerWidth)
	fingerRatio = clamp(params.fingerRatio.value,
		minFingerWidth / (minFingerWidth + maxFingerWidth),
		maxFingerWidth / (minFingerWidth + maxFingerWidth))
	rAB = (1 - fingerRatio) / fingerRatio
	rBA = fingerRatio / (1 - fingerRatio)
	margin = max(params.margin.value, 0)

	# Add all possible target bodies in case there are no operations on some.
	for face in faces:
		baseCombines.addTargetBody(face.body)

	# Compute the box joint between each pair of faces.
	for faceA, faceB, buttingFace in getAllButtingFaces(faces):
		bodyA = faceA.body
		bodyB = faceB.body
		planeA: adsk.core.Plane = faceA.geometry
		planeB: adsk.core.Plane = faceB.geometry
		faceAInwardNormal = planeA.normal.copy()
		faceBInwardNormal = planeB.normal.copy()

		# Normalize the orientation of the joint.
		if not faceA.isParamReversed:
			faceAInwardNormal.scaleBy(-1)
			planeA.normal = faceAInwardNormal
		if not faceB.isParamReversed:
			faceBInwardNormal.scaleBy(-1)
			planeB.normal = faceBInwardNormal

		# Define actual Joint and Nominal coordinate systems.
		outerEdge = planeB.intersectWithPlane(planeA)
		jointOrigin = outerEdge.origin
		jointZAxis = outerEdge.direction
		jointYAxis = faceAInwardNormal
		jointXAxis = faceAInwardNormal.crossProduct(jointZAxis)
		jointToNominal = adsk.core.Matrix3D.create()
		jointToNominal.setToAlignCoordinateSystems(
			fromOrigin=jointOrigin,
			fromXAxis=jointXAxis,
			fromYAxis=jointYAxis,
			fromZAxis=jointZAxis,
			toOrigin=adsk.core.Point3D.create(0, 0, 0),
			toXAxis=adsk.core.Vector3D.create(1, 0, 0),
			toYAxis=adsk.core.Vector3D.create(0, 1, 0),
			toZAxis=adsk.core.Vector3D.create(0, 0, 1))
		nominalToJoint = jointToNominal.copy()
		nominalToJoint.invert()

		# Sweep the butting face to define the overlapping region between
		# body A and body B where the joint will be created.
		sweepLine = adsk.core.InfiniteLine3D.create(
			jointOrigin, faceBInwardNormal.crossProduct(jointZAxis))
		pB: adsk.core.Point3D = buttingFace.geometry.intersectWithLine(sweepLine)
		sweepVector = pB.vectorTo(jointOrigin)
		overlap = createObliquePrism(buttingFace, sweepVector)
		tempBrepMgr.booleanOperation(overlap, bodyA, adsk.fusion.BooleanTypes.IntersectionBooleanType)
		tempBrepMgr.transform(overlap, jointToNominal)
		overlapBox = overlap.boundingBox
		minX, minY, minZ = overlapBox.minPoint.asArray()
		maxX, maxY, maxZ = overlapBox.maxPoint.asArray()

		# Compute the number of fingers and their widths.
		lengthWithMargins = maxZ - minZ
		length = lengthWithMargins - 2 * margin
		if fingerRatio < 0.5:
			fingerAWidth = min(minFingerWidth * rAB, maxFingerWidth)
		else:
			fingerAWidth = minFingerWidth
		fingers = min(
			math.floor(2 * (length / fingerAWidth - 1) / (1 + rBA)) | 1,
			maxFingers)
		if fingers < minFingers:
			# Would have too few fingers.
			continue
		fingerAWidth = length / ((1 + rBA) * math.floor(fingers / 2) + 1)
		if fingerAWidth > maxFingerWidth:
			fingerAWidth = maxFingerWidth
		fingerBWidth = fingerAWidth * rBA
		if fingerBWidth > maxFingerWidth:
			fingerBWidth = maxFingerWidth
			fingerAWidth = maxFingerWidth * rAB
		length = fingerAWidth + math.floor(fingers / 2) * (fingerAWidth + fingerBWidth)
		margin = (lengthWithMargins - length) / 2

		# Create a transformation matrix that will be reused for all upward translations.
		translateUp = adsk.core.Matrix3D.create()
		translateUp.setCell(2, 3, fingerBWidth)

		# Create a template for a single B finger.
		finger = createSimpleBox(
			minX, minY, minZ,
			maxX - minX, maxY - minY, fingerBWidth)
		fingerACutter = fingerBJoiner = finger

		# Define various reference points and vectors on the finger cross-section.
		pO = jointOrigin.copy()
		pO.transformBy(jointToNominal)
		pO.z = minZ
		pB.transformBy(jointToNominal)
		pB.z = minZ
		vOB = pO.vectorTo(pB)
		vOBPerp = adsk.core.Vector3D.create(vOB.y, -vOB.x, 0)

		isAcute = pB.x > pO.x + adsk.core.Application.get().pointTolerance
		isObtuse = pB.x < pO.x - adsk.core.Application.get().pointTolerance

		if isObtuse:
			# Joint angle is > 90°.
			pI = adsk.core.Point3D.create(maxX + vOB.x, maxY, minZ)
			pA = adsk.core.Point3D.create(maxX, minY, minZ)
			pAe = adsk.core.Point3D.create(max(pI.x, pO.x), minY, minZ)
			lOB = adsk.core.InfiniteLine3D.create(pO, vOB)
			lBeI = adsk.core.InfiniteLine3D.create(pI, vOBPerp)
			pBe = lOB.intersectWithCurve(lBeI)[0]
			if pBe.y < minY:
				pBe = pO
			vOBe = pO.vectorTo(pBe)
			pBe = pO.copy()
			pBe.translateBy(vOBe)

			# Slope the finger.
			try:
				slopeCrossSection = createFaceFromCurves([
					adsk.core.Line3D.create(pI, pAe),
					adsk.core.Line3D.create(pAe, pA),
					adsk.core.Line3D.create(pA, pI),
				])
				slope = createPrism(slopeCrossSection, fingerBWidth)
				tempBrepMgr.booleanOperation(finger, slope, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			except RuntimeError as e:
				# Ignore if slope is too tiny.
				if not any('ASM_WIRE_SELF_INTERSECTS' in arg for arg in e.args):
					raise
			try:
				slopeCrossSection = createFaceFromCurves([
					adsk.core.Line3D.create(pI, pB),
					adsk.core.Line3D.create(pB, pBe),
					adsk.core.Line3D.create(pBe, pI),
				])
				slope = createPrism(slopeCrossSection, -(fingerAWidth + margin))
				tempBrepMgr.booleanOperation(finger, slope, adsk.fusion.BooleanTypes.UnionBooleanType)
				slope = createPrism(slopeCrossSection, fingerBWidth + fingerAWidth + margin)
				tempBrepMgr.booleanOperation(finger, slope, adsk.fusion.BooleanTypes.UnionBooleanType)
			except RuntimeError as e:
				# Ignore if slope is too tiny.
				if not any('ASM_WIRE_SELF_INTERSECTS' in arg for arg in e.args):
					raise
		else:
			# Joint angle is <= 90°.
			pI = adsk.core.Point3D.create(maxX, maxY, minZ)
			pA = adsk.core.Point3D.create(maxX - vOB.x, minY, minZ)
			pAe = pA
			vOBe = vOB
			pBe = pB

		if bitRadius > 0:
			vOA = adsk.core.Vector3D.create(pA.x - pO.x, 0, 0)
			vOBc = vOB.copy()
			vOBc.scaleBy(-bitRadius / vOBc.length)
			vOBc.add(vOBe)
			vOAPerp = adsk.core.Vector3D.create(-vOA.y, vOA.x, 0)

			pAc = pAe.copy()
			pAc.x = pAc.x - bitRadius
			pBc = pO.copy()
			pBc.translateBy(vOBc)

			vAeI = pAe.vectorTo(pI)
			vBeI = pBe.vectorTo(pI)
			lAeI = adsk.core.InfiniteLine3D.create(pAe, vAeI)
			lBeI = adsk.core.InfiniteLine3D.create(pBe, vBeI)
			lAcIc = adsk.core.InfiniteLine3D.create(pAc, vAeI)
			lBcIc = adsk.core.InfiniteLine3D.create(pBc, vBeI)
			pIa = pBc.copy()
			pIa.translateBy(vBeI)
			pIb = adsk.core.Point3D.create(pI.x - bitRadius, pI.y, pI.z)
			pIc = lAcIc.intersectWithCurve(lBcIc)[0]
			vAcIc = pAc.vectorTo(pIc)
			vBcIc = pBc.vectorTo(pIc)
			pIae = lAeI.intersectWithCurve(lBcIc)[0]
			pIbe = lBeI.intersectWithCurve(lAcIc)[0]
			vAeIae = pAe.vectorTo(pIae)
			vBeIbe = pBe.vectorTo(pIbe)

			# Reference points up and down by the bit radius.
			zUp = minZ + bitRadius
			zDown = minZ - bitRadius
			pAeUp = pAe.copy()
			pAeUp.z = zUp
			pAeDown = pAe.copy()
			pAeDown.z = zDown
			pBeUp = pBe.copy()
			pBeUp.z = zUp
			pBeDown = pBe.copy()
			pBeDown.z = zDown
			pAcUp = pAc.copy()
			pAcUp.z = zUp
			pAcDown = pAc.copy()
			pAcDown.z = zDown
			pBcUp = pBc.copy()
			pBcUp.z = zUp
			pBcDown = pBc.copy()
			pBcDown.z = zDown
			if isAcute:
				pIcDown = pIc.copy()
				pIcDown.z = zDown
				pIaDown = pIa.copy()
				pIaDown.z = zDown
				pIbDown = pIb.copy()
				pIbDown.z = zDown
				pUaDown = pIcDown.copy()
				pUaDown.translateBy(vOAPerp)
				pUbDown = pIcDown.copy()
				pUbDown.translateBy(vOBPerp)

			fingerACutter = finger
			fingerBJoiner = tempBrepMgr.copy(finger)

			# Add rounded inside corners to the fingers on body B.
			coveCrossSection = createFaceFromCurves([
				adsk.core.Arc3D.createByCenter(
					center=pBcDown,
					normal=vOBPerp,
					referenceVector=vOB,
					radius=bitRadius,
					startAngle=0,
					endAngle=0.5 * math.pi),
				adsk.core.Arc3D.createByCenter(
					center=pBcUp,
					normal=vOBPerp,
					referenceVector=vOB,
					radius=bitRadius,
					startAngle=1.5 * math.pi,
					endAngle=0),
				adsk.core.Line3D.create(pBeUp, pBeDown),
			])
			cove = createObliquePrism(coveCrossSection, vBeIbe)
			tempBrepMgr.booleanOperation(fingerACutter, cove, adsk.fusion.BooleanTypes.UnionBooleanType)
			tempBrepMgr.transform(cove, translateUp)
			tempBrepMgr.booleanOperation(fingerACutter, cove, adsk.fusion.BooleanTypes.UnionBooleanType)
			cove = createObliquePrism(coveCrossSection, vBcIc)
			tempBrepMgr.booleanOperation(fingerBJoiner, cove, adsk.fusion.BooleanTypes.UnionBooleanType)
			tempBrepMgr.transform(cove, translateUp)
			tempBrepMgr.booleanOperation(fingerBJoiner, cove, adsk.fusion.BooleanTypes.UnionBooleanType)

			# Add rounded inside corners to the fingers on body A.
			coveCrossSection = createFaceFromCurves([
				adsk.core.Arc3D.createByCenter(
					center=pAcUp,
					normal=vOAPerp,
					referenceVector=vOA,
					radius=bitRadius,
					startAngle=0,
					endAngle=0.5 * math.pi),
				adsk.core.Arc3D.createByCenter(
					center=pAcDown,
					normal=vOAPerp,
					referenceVector=vOA,
					radius=bitRadius,
					startAngle=1.5 * math.pi,
					endAngle=0),
				adsk.core.Line3D.create(pAeDown, pAeUp),
			])
			cove = createObliquePrism(coveCrossSection, vAcIc)
			tempBrepMgr.booleanOperation(fingerACutter, cove, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			tempBrepMgr.transform(cove, translateUp)
			tempBrepMgr.booleanOperation(fingerACutter, cove, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			cove = createObliquePrism(coveCrossSection, vAeIae)
			tempBrepMgr.booleanOperation(fingerBJoiner, cove, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			tempBrepMgr.transform(cove, translateUp)
			tempBrepMgr.booleanOperation(fingerBJoiner, cove, adsk.fusion.BooleanTypes.DifferenceBooleanType)

			# Add dog bones (T-bones) on the inside face of body A.
			dogBoneCrossSection = createFaceFromCurves([
				adsk.core.Circle3D.createByCenter(
					center=pIc,
					normal=vOAPerp,
					radius=bitRadius),
			])
			dogBone = createObliquePrism(dogBoneCrossSection, vAeI)
			tempBrepMgr.booleanOperation(fingerACutter, dogBone, adsk.fusion.BooleanTypes.UnionBooleanType)
			tempBrepMgr.transform(dogBone, translateUp)
			tempBrepMgr.booleanOperation(fingerACutter, dogBone, adsk.fusion.BooleanTypes.UnionBooleanType)
			if isAcute:
				try:
					dogBone = createObliquePrism(dogBoneCrossSection, vOAPerp)
					tempBrepMgr.booleanOperation(fingerACutter, dogBone, adsk.fusion.BooleanTypes.UnionBooleanType)
					tempBrepMgr.transform(dogBone, translateUp)
					tempBrepMgr.booleanOperation(fingerACutter, dogBone, adsk.fusion.BooleanTypes.UnionBooleanType)
				except RuntimeError as e:
					if not any('ASM_OSCULATING_CURVES' in arg for arg in e.args):
						raise
				try:
					dogBoneWedge = createObliquePrism(
						createFaceFromCurves([
							adsk.core.Line3D.create(pIcDown, pUaDown),
							adsk.core.Line3D.create(pUaDown, pIbDown),
							adsk.core.Line3D.create(pIbDown, pIcDown),
						]),
						adsk.core.Vector3D.create(0, 0, fingerBWidth + bitDiameter))
					tempBrepMgr.booleanOperation(fingerACutter, dogBoneWedge, adsk.fusion.BooleanTypes.UnionBooleanType)
				except RuntimeError as e:
					# Ignore if wedge is too tiny.
					if not any('ASM_WIRE_SELF_INTERSECTS' in arg for arg in e.args):
						raise

			# Add dog bones (T-bones) on the inside face of body B.
			dogBoneCrossSection = createFaceFromCurves([
				adsk.core.Circle3D.createByCenter(
					center=pIc,
					normal=vOBPerp,
					radius=bitRadius),
			])
			dogBone = createObliquePrism(dogBoneCrossSection, vBeI)
			tempBrepMgr.booleanOperation(fingerBJoiner, dogBone, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			tempBrepMgr.transform(dogBone, translateUp)
			tempBrepMgr.booleanOperation(fingerBJoiner, dogBone, adsk.fusion.BooleanTypes.DifferenceBooleanType)
			if isAcute:
				try:
					dogBone = createObliquePrism(dogBoneCrossSection, vOBPerp)
					tempBrepMgr.booleanOperation(fingerBJoiner, dogBone, adsk.fusion.BooleanTypes.DifferenceBooleanType)
					tempBrepMgr.transform(dogBone, translateUp)
					tempBrepMgr.booleanOperation(fingerBJoiner, dogBone, adsk.fusion.BooleanTypes.DifferenceBooleanType)
				except RuntimeError as e:
					if not any('ASM_OSCULATING_CURVES' in arg for arg in e.args):
						raise
				try:
					dogBoneWedge = createObliquePrism(
						createFaceFromCurves([
							adsk.core.Line3D.create(pIcDown, pUbDown),
							adsk.core.Line3D.create(pUbDown, pIaDown),
							adsk.core.Line3D.create(pIaDown, pIcDown),
						]),
						adsk.core.Vector3D.create(0, 0, bitDiameter))
					tempBrepMgr.booleanOperation(fingerBJoiner, dogBoneWedge, adsk.fusion.BooleanTypes.DifferenceBooleanType)
					tempBrepMgr.transform(dogBoneWedge, translateUp)
					tempBrepMgr.booleanOperation(fingerBJoiner, dogBoneWedge, adsk.fusion.BooleanTypes.DifferenceBooleanType)
				except RuntimeError as e:
					# Ignore if wedge is too tiny.
					if not any('ASM_WIRE_SELF_INTERSECTS' in arg for arg in e.args):
						raise

		# Move each finger into its final position and combine with body A and body B.
		for i in range(0, math.floor(fingers / 2)):
			translateUp.setCell(2, 3, margin + fingerAWidth + i * (fingerAWidth + fingerBWidth))

			finger = tempBrepMgr.copy(fingerACutter)
			tempBrepMgr.transform(finger, translateUp)
			tempBrepMgr.booleanOperation(finger, overlap, adsk.fusion.BooleanTypes.IntersectionBooleanType)
			tempBrepMgr.transform(finger, nominalToJoint)
			baseCombines.add(BooleanOperation.difference(
				targetBody=bodyA,
				toolBody=finger))

			finger = tempBrepMgr.copy(fingerBJoiner)
			tempBrepMgr.transform(finger, translateUp)
			tempBrepMgr.booleanOperation(finger, overlap, adsk.fusion.BooleanTypes.IntersectionBooleanType)
			tempBrepMgr.transform(finger, nominalToJoint)
			baseCombines.add(BooleanOperation.union(
				targetBody=bodyB,
				toolBody=finger))

	return baseCombines


def getAllButtingFaces(outsideFaces: list[adsk.fusion.BRepFace]) -> list[tuple[
	adsk.fusion.BRepFace, adsk.fusion.BRepFace, adsk.fusion.BRepFace
]]:
	buttingFaces = []
	for faceA, faceB in itertools.permutations(outsideFaces, 2):
		for buttingFace in getButtingFaces(faceA, faceB):
			buttingFaces.append((faceA, faceB, buttingFace))
	return buttingFaces


def getButtingFaces(faceA: adsk.fusion.BRepFace, faceB: adsk.fusion.BRepFace) -> list[adsk.fusion.BRepFace]:
	buttingFaces = []

	if faceA.body == faceB.body:
		# Both faces on same body.
		return buttingFaces
	if faceA.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
		# Face A is not planar.
		return buttingFaces
	if faceB.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
		# Face B is not planar.
		return buttingFaces

	# Check all planar faces adjacent to face B.
	for edgeOnFaceB in faceB.edges:
		for candidateButtingFace in edgeOnFaceB.faces:
			if candidateButtingFace == faceB:
				# This is face B itself, not an adjacent face.
				continue
			candidateButtingFaceGeometry = candidateButtingFace.geometry
			if candidateButtingFaceGeometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
				# Not a planar face.
				continue
			if not candidateButtingFaceGeometry.isParallelToPlane(faceA.geometry):
				# Not parallel to face A.
				continue
			if candidateButtingFaceGeometry.isCoPlanarTo(faceA.geometry):
				# There is zero distance to face A.
				continue

			# Check that there is an overlapping exterior face on body A.
			for f in faceA.body.shells[0].faces:
				if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
					continue
				if not candidateButtingFaceGeometry.isCoPlanarTo(f.geometry):
					continue
				imprint = tempBrepMgr.imprintOverlapBodies(
					tempBrepMgr.copy(candidateButtingFace),
					tempBrepMgr.copy(f),
					False)
				if imprint[3].size() > 0:
					# This face butts up with a face on body A.
					buttingFaces.append(candidateButtingFace)

	return buttingFaces


def clamp(value, min, max):
	"""
	Clamps the given `value` to be between the given `min` and `max` values.
	"""
	return min if value < min else max if value > max else value


_htmlTagRegex = re.compile('<[^>]*>')
def withoutHtml(string):
	"""
	Removes all HTML tags from the given `string`.
	"""
	return re.sub(_htmlTagRegex, '', string)
